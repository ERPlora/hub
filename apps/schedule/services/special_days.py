"""Special days (SCHEDULE-F04, F06, F07, F13): a date closed or with other hours, one per date, added one by one or
in bulk, corrected and deleted."""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.schedule import assistant_cards, events
from apps.schedule.models import SpecialDay, SpecialDayInterval
from apps.schedule.queries import resolve_special_day, special_day_out
from apps.schedule.schemas.fields import DeletedOut
from apps.schedule.schemas.intervals import check_intervals
from apps.schedule.schemas.special_days import (
    BulkCreatedOut,
    BulkSpecialDayIn,
    SpecialDayIn,
    SpecialDayOut,
    SpecialDayPatchIn,
    SpecialDayRefIn,
)

from .writes import _checked, _same, _stored, _write_intervals

SPECIAL_DAY_EXISTS = _("There is already a special day on that date.")
SPECIAL_DAY_DATE_UNIQUE = "schedule_special_day_date_unique"


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
        with atomic():
            row.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == SPECIAL_DAY_DATE_UNIQUE:
            raise _date_taken() from None
        raise


def _special_day_event(ctx: OperationContext, name: str, row: SpecialDay) -> None:
    record_event(ctx, name, {"id": str(row.id), "date": row.date.isoformat()})


@operation(
    "schedule.special_day.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.add",
    input=SpecialDayIn,
    output=SpecialDayOut,
    ai={
        "description": "Adds a special day: a date closed (a holiday) or with other opening hours, once or every year.",
        "risk": "normal", "summary": assistant_cards.special_day,
        "asks": {
            "en": (
                "the 15th of August is a local holiday, we stay closed",
                "add New Year's Eve as a special date open until 18:00",
            ),
            "es": (
                "el 15 de agosto es fiesta local y no abrimos",
                "en Nochevieja abrimos solo hasta las 18:00, apúntalo como fecha especial",
                "apunta la fiesta del patrón como festivo todos los años",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.add",
    input=BulkSpecialDayIn,
    output=BulkCreatedOut,
    ai={
        "description": "Adds several special days at once (up to 366, such as the year's holidays); a day whose date "
        "is taken or whose hours are not valid is skipped with its reason and the rest go in.",
        "risk": "normal", "summary": assistant_cards.special_days,
        "asks": {
            "en": (
                "load all the national holidays of next year at once",
                "add these three holidays together: 1 May, 15 August and 12 October",
            ),
            "es": (
                "carga de golpe todos los festivos nacionales del año que viene",
                "apunta de una vez Año Nuevo y Reyes, el 1 y el 6 de enero, los dos cerrados",
                "mete juntos estos tres festivos: 1 de mayo, 15 de agosto y 12 de octubre",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.change",
    input=SpecialDayPatchIn,
    output=SpecialDayOut,
    ai={
        "description": "Corrects a special day (by id, name or date): its date, name, closed or hours, yearly or "
        "notes; only what is sent changes, and sent intervals replace them all.",
        "risk": "normal",
        "asks": {
            "en": (
                "on the Epiphany holiday we will open in the morning after all",
                "move the Christmas special date to the 26th",
            ),
            "es": (
                "el festivo de Reyes al final abrimos de 10 a 14",
                "corrige la fecha especial de Navidad: es el 26, no el 25",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.delete",
    input=SpecialDayRefIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a special day (by id, name or date) and its hours; its date is free again. Cannot be "
        "undone.",
        "risk": "high",
        "asks": {
            "en": (
                "remove the local holiday, we open as usual after all",
                "delete the Christmas Eve special date",
            ),
            "es": (
                "borra el festivo del pueblo, al final abrimos como siempre",
                "quita la fecha especial de Nochebuena",
            ),
        },
    },
)
def delete_special_day(ctx: OperationContext, data: SpecialDayRefIn) -> dict:
    """SCHEDULE-F06."""
    row = resolve_special_day(data.id, data.special_day, lock=True)
    deleted = row.id
    row.delete()
    record_event(ctx, events.SPECIAL_DAY_DELETED, {"id": str(deleted)})
    return {"id": deleted}
