"""Write operations of the schedule app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). The rules of the
intervals are ``schemas.check_intervals`` (engine.py underneath), applied again here to what a
correction leaves. Writes on the temporary changes lock the settings row first, so two that would
cover the same day never slip past each other's check; a special day's date is unique in the database.
"""

from collections.abc import Iterable
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import formats
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.schedule import events
from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)
from apps.schedule.queries import (
    override_out,
    resolve_override,
    resolve_special_day,
    settings_out,
    special_day_out,
    week_out,
)
from apps.schedule.schemas import (
    RANGE_BACKWARDS,
    BulkCreatedOut,
    BulkSpecialDayIn,
    DeletedOut,
    IntervalIn,
    NoParamsIn,
    OverrideIn,
    OverrideOut,
    OverridePatchIn,
    OverrideRefIn,
    SetDayIn,
    SettingsIn,
    SettingsOut,
    SpecialDayIn,
    SpecialDayOut,
    SpecialDayPatchIn,
    SpecialDayRefIn,
    WeekOut,
    check_intervals,
)

SPECIAL_DAY_EXISTS = _("There is already a special day on that date.")
OVERRIDE_OVERLAPS = _(
    "Those dates overlap the temporary change “%(reason)s” (%(start)s – %(end)s)."
)
NO_WEEK = _("There are no weekly opening hours to confirm.")
SPECIAL_DAY_DATE_UNIQUE = "schedule_special_day_date_unique"


# ── Helpers ────────────────────────────────────────────────────────────────────────────────────


def _locked_settings() -> ScheduleSettings:
    """The settings row, created by the first write, locked until the end of the command."""
    row = ScheduleSettings.objects.select_for_update().first()
    if row is None:
        ScheduleSettings.objects.get_or_create(slot=1)
        row = ScheduleSettings.objects.select_for_update().get(slot=1)
    return row


def _write_intervals(
    model: type, owner: dict[str, Any], intervals: Iterable[IntervalIn]
) -> None:
    """Replaces the intervals of their owner (``{"day": day}``…) with ``intervals``, in order."""
    model.objects.filter(**owner).delete()
    model.objects.bulk_create(
        model(
            **owner, position=position, open_time=i.open_time, close_time=i.close_time
        )
        for position, i in enumerate(intervals)
    )


def _checked(is_closed: bool, intervals: list[IntervalIn]) -> list[IntervalIn]:
    """``check_intervals`` with its refusal under ``intervals`` (a correction's merged values)."""
    try:
        return check_intervals(is_closed, intervals)
    except ValueError as refused:
        raise InvalidPayload(str(refused), fields={"intervals": str(refused)}) from None


def _stored(row: SpecialDay | Override) -> list[IntervalIn]:
    return [
        IntervalIn(open_time=i.open_time, close_time=i.close_time)
        for i in row.intervals.order_by("position")
    ]


def _same(left: list[IntervalIn], right: list[IntervalIn]) -> bool:
    return [(i.open_time, i.close_time) for i in left] == [
        (i.open_time, i.close_time) for i in right
    ]


def _date_taken() -> Conflict:
    return Conflict(
        str(SPECIAL_DAY_EXISTS),
        code="schedule.special_day_exists",
        fields={"date": str(SPECIAL_DAY_EXISTS)},
    )


def _save_special_day(row: SpecialDay) -> None:
    """Saves ``row``; another special day on its date (also one saved at the same time) is the 409."""
    if SpecialDay.objects.filter(date=row.date).exclude(pk=row.pk).exists():
        raise _date_taken()
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == SPECIAL_DAY_DATE_UNIQUE:
            raise _date_taken() from None
        raise


def _refuse_overlap(start, end, exclude=None) -> None:
    """409 ``schedule.override_overlaps`` when a temporary change already covers a day of the range."""
    clash = (
        Override.objects.filter(start_date__lte=end, end_date__gte=start)
        .exclude(pk=exclude)
        .order_by("start_date")
        .first()
    )
    if clash is None:
        return
    message = str(OVERRIDE_OVERLAPS) % {
        "reason": clash.reason,
        "start": formats.date_format(clash.start_date, "SHORT_DATE_FORMAT"),
        "end": formats.date_format(clash.end_date, "SHORT_DATE_FORMAT"),
    }
    raise Conflict(
        message, code="schedule.override_overlaps", fields={"start_date": message}
    )


def _special_day_event(ctx: OperationContext, name: str, row: SpecialDay) -> None:
    record_event(ctx, name, {"id": str(row.id), "date": row.date.isoformat()})


def _override_event(ctx: OperationContext, name: str, row: Override) -> None:
    record_event(
        ctx,
        name,
        {
            "id": str(row.id),
            "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(),
        },
    )


# ── The week ───────────────────────────────────────────────────────────────────────────────────


@operation(
    "schedule.week.set_day",
    kind="command",
    permission="schedule.change",
    input=SetDayIn,
    output=WeekOut,
    ai={
        "description": "Sets the opening hours of one day of the usual week (by number, 0 = Monday, or by name): "
        "closed, or its intervals (split shifts, past midnight, 00:00–00:00 for 24 hours). Replaces what the day had.",
        "risk": "normal",
    },
)
def set_day(ctx: OperationContext, data: SetDayIn) -> dict:
    """SCHEDULE-F02: the day's intervals are replaced, and whoever saves a day has seen the week."""
    settings = _locked_settings()
    day, _created = WeekDay.objects.select_for_update().get_or_create(
        weekday=data.weekday
    )
    day.is_closed = data.is_closed
    day.save()
    _write_intervals(WeekDayInterval, {"day": day}, data.intervals)
    if not settings.hours_confirmed:
        settings.hours_confirmed = True
        settings.save(update_fields=["hours_confirmed", "updated_at"])
    record_event(ctx, events.WEEK_UPDATED, {"weekday": data.weekday})
    return week_out()


@operation(
    "schedule.week.confirm",
    kind="command",
    permission="schedule.change",
    input=NoParamsIn,
    output=WeekOut,
    ai={
        "description": "Confirms the usual week as it is saved (the default one set up for the business) without "
        "changing any hour.",
        "risk": "normal",
    },
)
def confirm_week(ctx: OperationContext, data: NoParamsIn) -> dict:
    """SCHEDULE-F03: no hour travels; confirming twice says nothing."""
    settings = _locked_settings()
    if not WeekDay.objects.exists():
        raise Conflict(str(NO_WEEK), code="schedule.no_week")
    if not settings.hours_confirmed:
        settings.hours_confirmed = True
        settings.save(update_fields=["hours_confirmed", "updated_at"])
        record_event(ctx, events.WEEK_UPDATED, {})
    return week_out()


# ── Special days ───────────────────────────────────────────────────────────────────────────────


@operation(
    "schedule.special_day.create",
    kind="command",
    permission="schedule.add",
    input=SpecialDayIn,
    output=SpecialDayOut,
    ai={
        "description": "Adds a special day: a date closed (a holiday) or with other opening hours, once or every year.",
        "risk": "normal",
    },
)
def create_special_day(ctx: OperationContext, data: SpecialDayIn) -> dict:
    """SCHEDULE-F04: one special day per date."""
    row = SpecialDay(
        date=data.date,
        name=data.name,
        is_closed=data.is_closed,
        recurring_yearly=data.recurring_yearly,
        notes=data.notes,
    )
    _save_special_day(row)
    _write_intervals(SpecialDayInterval, {"special_day": row}, data.intervals)
    _special_day_event(ctx, events.SPECIAL_DAY_CREATED, row)
    return special_day_out(row)


@operation(
    "schedule.special_day.bulk_create",
    kind="command",
    permission="schedule.add",
    input=BulkSpecialDayIn,
    output=BulkCreatedOut,
    ai={
        "description": "Adds several special days at once (up to 366, such as the year's holidays); a day whose date "
        "is taken or whose hours are not valid is skipped with its reason and the rest go in.",
        "risk": "normal",
    },
)
def bulk_create_special_days(ctx: OperationContext, data: BulkSpecialDayIn) -> dict:
    """SCHEDULE-F07: tolerant per day, never silent; one «created» per day that went in."""
    taken = set(
        SpecialDay.objects.filter(
            date__in=[day.date for day in data.special_days]
        ).values_list("date", flat=True)
    )
    created, skipped = [], []
    for index, day in enumerate(data.special_days):
        if day.date in taken:
            skipped.append(
                {
                    "index": index,
                    "date": day.date,
                    "code": "already_exists",
                    "message": str(SPECIAL_DAY_EXISTS),
                }
            )
            continue
        try:
            intervals = check_intervals(day.is_closed, day.intervals)
        except ValueError as refused:
            skipped.append(
                {
                    "index": index,
                    "date": day.date,
                    "code": "invalid_hours",
                    "message": str(refused),
                }
            )
            continue
        row = SpecialDay(
            date=day.date,
            name=day.name,
            is_closed=day.is_closed,
            recurring_yearly=day.recurring_yearly,
            notes=day.notes,
        )
        try:
            _save_special_day(row)
        except Conflict as refused:
            # Taken by someone else meanwhile: that day is skipped (its insert ran in a savepoint).
            skipped.append({"index": index, "date": day.date, "code": "already_exists", "message": refused.message})
            taken.add(day.date)
            continue
        _write_intervals(SpecialDayInterval, {"special_day": row}, intervals)
        _special_day_event(ctx, events.SPECIAL_DAY_CREATED, row)
        taken.add(day.date)
        created.append(row.id)
    return {"created": created, "skipped": skipped}


@operation(
    "schedule.special_day.update",
    kind="command",
    permission="schedule.change",
    input=SpecialDayPatchIn,
    output=SpecialDayOut,
    ai={
        "description": "Corrects a special day (by id, name or date): its date, name, closed or hours, yearly or "
        "notes; only what is sent changes, and sent intervals replace them all.",
        "risk": "normal",
    },
)
def update_special_day(ctx: OperationContext, data: SpecialDayPatchIn) -> dict:
    """SCHEDULE-F13; no change, no event."""
    row = resolve_special_day(data.id, data.special_day, lock=True)
    sent = data.model_dump(
        exclude_unset=True, exclude={"id", "special_day", "intervals"}
    )
    before = _stored(row)
    fields_changed = False
    for field, value in sent.items():
        if value is not None and getattr(row, field) != value:
            setattr(row, field, value)
            fields_changed = True
    intervals = data.intervals if data.intervals is not None else before
    if data.intervals is not None and row.is_closed and "is_closed" not in sent:
        # Hours sent for a closed day open it.
        row.is_closed = False
        fields_changed = True
    after = _checked(row.is_closed, intervals)
    if fields_changed:
        _save_special_day(row)
    if not _same(before, after):
        _write_intervals(SpecialDayInterval, {"special_day": row}, after)
    if fields_changed or not _same(before, after):
        _special_day_event(ctx, events.SPECIAL_DAY_UPDATED, row)
    return special_day_out(row)


@operation(
    "schedule.special_day.delete",
    kind="command",
    permission="schedule.delete",
    input=SpecialDayRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a special day (by id, name or date) and its hours; its date is free again. Cannot be "
        "undone.",
        "risk": "high",
    },
)
def delete_special_day(ctx: OperationContext, data: SpecialDayRefIn) -> dict:
    """SCHEDULE-F06."""
    row = resolve_special_day(data.id, data.special_day, lock=True)
    deleted = row.id
    row.delete()
    record_event(ctx, events.SPECIAL_DAY_DELETED, {"id": str(deleted)})
    return {"id": deleted}


# ── Temporary changes ──────────────────────────────────────────────────────────────────────────


@operation(
    "schedule.override.create",
    kind="command",
    permission="schedule.add",
    input=OverrideIn,
    output=OverrideOut,
    ai={
        "description": "Adds a temporary change of the opening hours for a range of dates (holidays, summer hours, "
        "works): closed, or the same intervals every day of the range.",
        "risk": "normal",
    },
)
def create_override(ctx: OperationContext, data: OverrideIn) -> dict:
    """SCHEDULE-F05: two temporary changes never cover the same day."""
    _locked_settings()
    _refuse_overlap(data.start_date, data.end_date)
    row = Override.objects.create(
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        is_closed=data.is_closed,
    )
    _write_intervals(OverrideInterval, {"override": row}, data.intervals)
    _override_event(ctx, events.OVERRIDE_CREATED, row)
    return override_out(row)


@operation(
    "schedule.override.update",
    kind="command",
    permission="schedule.change",
    input=OverridePatchIn,
    output=OverrideOut,
    ai={
        "description": "Corrects a temporary change (by id, reason or a date it covers): its dates, reason, closed or "
        "hours; only what is sent changes, and sent intervals replace them all.",
        "risk": "normal",
    },
)
def update_override(ctx: OperationContext, data: OverridePatchIn) -> dict:
    """SCHEDULE-F13; no change, no event."""
    _locked_settings()
    row = resolve_override(data.id, data.override, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude={"id", "override", "intervals"})
    before = _stored(row)
    fields_changed = False
    for field, value in sent.items():
        if value is not None and getattr(row, field) != value:
            setattr(row, field, value)
            fields_changed = True
    if row.end_date < row.start_date:
        raise InvalidPayload(
            str(RANGE_BACKWARDS), fields={"end_date": str(RANGE_BACKWARDS)}
        )
    intervals = data.intervals if data.intervals is not None else before
    if data.intervals is not None and row.is_closed and "is_closed" not in sent:
        row.is_closed = False
        fields_changed = True
    after = _checked(row.is_closed, intervals)
    if fields_changed:
        _refuse_overlap(row.start_date, row.end_date, exclude=row.pk)
        row.save()
    if not _same(before, after):
        _write_intervals(OverrideInterval, {"override": row}, after)
    if fields_changed or not _same(before, after):
        _override_event(ctx, events.OVERRIDE_UPDATED, row)
    return override_out(row)


@operation(
    "schedule.override.delete",
    kind="command",
    permission="schedule.delete",
    input=OverrideRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a temporary change (by id, reason or a date it covers) and its hours; the usual week "
        "rules those dates again. Cannot be undone.",
        "risk": "high",
    },
)
def delete_override(ctx: OperationContext, data: OverrideRefIn) -> dict:
    """SCHEDULE-F06."""
    row = resolve_override(data.id, data.override, lock=True)
    deleted = row.id
    row.delete()
    record_event(ctx, events.OVERRIDE_DELETED, {"id": str(deleted)})
    return {"id": deleted}


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


@operation(
    "schedule.settings.update",
    kind="command",
    permission="schedule.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    ai={
        "description": "Changes the day the opening week starts on (1 = Monday … 7 = Sunday): only the order of the "
        "week's table, never an hour.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    """SCHEDULE-F08: the first save creates the row; only a change says so."""
    row = _locked_settings()
    if data.week_starts_on is not None and data.week_starts_on != row.week_starts_on:
        row.week_starts_on = data.week_starts_on
        row.save(update_fields=["week_starts_on", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(row)
