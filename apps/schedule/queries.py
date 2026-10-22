"""Read operations of the schedule app (``READ ONLY``): the week, the special days, the temporary changes,
the settings, «is it open?» and the hours of a range of days.

The rules are engine.py's: these operations only load the business's rows (``load_calendar``) and hand
them over, so «is it open?» and the appointment book's hours can never disagree. The business's zone is
the Hub's; in phase 1, ``settings.TIME_ZONE`` (Europe/Madrid).
"""

import datetime as dt
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import F, Prefetch, Q, QuerySet
from django.utils import formats, timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.schedule import engine
from apps.schedule.models import (
    WEEKDAY_NAMES,
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)
from apps.schedule.schemas import (
    HoursRangeIn,
    HoursRangeOut,
    IsOpenIn,
    IsOpenOut,
    NoParamsIn,
    OverrideListIn,
    OverridePage,
    PageIn,
    SettingsOut,
    SpecialDayListIn,
    SpecialDayPage,
    WeekOut,
)

SPECIAL_DAY_NOT_FOUND = _("That special day does not exist in this business.")
OVERRIDE_NOT_FOUND = _("That temporary change does not exist in this business.")
AMBIGUOUS = _("There are several with “%(name)s”: %(matches)s. Say which one.")
MAX_CANDIDATES = 5

SPECIAL_DAY_SORTS = {
    "date": ("date",),
    "name": ("name",),
    "is_closed": ("is_closed", "date"),
    "recurring_yearly": ("recurring_yearly", "date"),
    "id": (),
}
OVERRIDE_SORTS = {
    "start_date": ("start_date",),
    "end_date": ("end_date",),
    "reason": ("reason",),
    "is_closed": ("is_closed", "start_date"),
    "id": (),
}


# ── The business's clock ───────────────────────────────────────────────────────────────────────


def business_zone() -> ZoneInfo:
    """The business's time zone (phase 1: ``settings.TIME_ZONE``, the Hub keeps no zone yet)."""
    return timezone.get_current_timezone()


def zone_name() -> str:
    zone = business_zone()
    return getattr(zone, "key", str(zone))


def day_label(day: dt.date, language: str) -> str:
    """``day`` ready to say in ``language``, its weekday first («martes, 5 de marzo de 2030»): what a flow's
    template prints as it comes, with no formatter (appointments#151). Appointments and Reservations, which
    both require this app, say their days with it."""
    with translation.override(language):
        return f"{formats.date_format(day, 'l')}, {formats.date_format(day, 'DATE_FORMAT')}"


def settings_row() -> ScheduleSettings:
    """The saved settings, or the defaults while nobody saved them."""
    return ScheduleSettings.objects.first() or ScheduleSettings()


# ── Loading rows ───────────────────────────────────────────────────────────────────────────────


def _ordered(intervals: type) -> Prefetch:
    return Prefetch(
        "intervals", queryset=intervals.objects.order_by("open_time", "position", "id")
    )


def week_days() -> QuerySet[WeekDay]:
    return WeekDay.objects.prefetch_related(_ordered(WeekDayInterval))


def special_days() -> QuerySet[SpecialDay]:
    return SpecialDay.objects.prefetch_related(_ordered(SpecialDayInterval))


def overrides() -> QuerySet[Override]:
    return Override.objects.prefetch_related(_ordered(OverrideInterval))


def _intervals(row: Any) -> tuple[engine.Interval, ...]:
    """The stored intervals of a row in opening order (an overnight one goes by its opening)."""
    items = [engine.Interval(i.open_time, i.close_time) for i in row.intervals.all()]
    return tuple(sorted(items, key=lambda item: item.minutes))


def load_calendar(date_from: dt.date, date_to: dt.date) -> engine.Calendar:
    """The rules that can govern ``date_from - 1`` … ``date_to`` (the eve too: its overnight tail)."""
    eve = date_from - dt.timedelta(days=1)
    weekly = {
        day.weekday: engine.WeeklyDay(day.id, day.is_closed, _intervals(day))
        for day in week_days()
    }
    specials = [
        engine.ExceptionRule(
            sd.id,
            sd.date,
            sd.date,
            sd.name,
            sd.is_closed,
            _intervals(sd),
            sd.recurring_yearly,
        )
        for sd in special_days().filter(
            Q(date__range=(eve, date_to)) | Q(recurring_yearly=True)
        )
    ]
    changes = [
        engine.ExceptionRule(
            ov.id, ov.start_date, ov.end_date, ov.reason, ov.is_closed, _intervals(ov)
        )
        for ov in overrides().filter(start_date__lte=date_to, end_date__gte=eve)
    ]
    return engine.Calendar(weekly=weekly, special_days=specials, overrides=changes)


# ── Outputs ────────────────────────────────────────────────────────────────────────────────────


def intervals_out(
    intervals: tuple[engine.Interval, ...] | list[engine.Interval],
) -> list[dict]:
    return [{"open_time": i.open_time, "close_time": i.close_time} for i in intervals]


def special_day_out(row: SpecialDay) -> dict:
    return {
        "id": row.id,
        "date": row.date,
        "name": row.name,
        "is_closed": row.is_closed,
        "recurring_yearly": row.recurring_yearly,
        "notes": row.notes,
        "intervals": intervals_out(_intervals(row)),
    }


def override_out(row: Override) -> dict:
    return {
        "id": row.id,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "reason": row.reason,
        "is_closed": row.is_closed,
        "intervals": intervals_out(_intervals(row)),
    }


def week_out() -> dict:
    """The seven days from the one the week starts on; a day without row is «not set»."""
    row = settings_row()
    stored = {day.weekday: day for day in week_days()}
    first = row.week_starts_on - 1
    days = []
    for offset in range(7):
        weekday = (first + offset) % 7
        day = stored.get(weekday)
        days.append(
            {
                "weekday": weekday,
                "name": str(WEEKDAY_NAMES[weekday]),
                "id": day.id if day else None,
                "is_set": day is not None,
                "is_closed": bool(day and day.is_closed),
                "intervals": intervals_out(_intervals(day)) if day else [],
            }
        )
    return {
        "week_starts_on": row.week_starts_on,
        "confirmed": row.hours_confirmed,
        "timezone": zone_name(),
        "days": days,
    }


def settings_out(row: ScheduleSettings) -> dict:
    return {
        "week_starts_on": row.week_starts_on,
        "hours_confirmed": row.hours_confirmed,
        "timezone": zone_name(),
    }


# ── References by id, name or date (the assistant speaks) ──────────────────────────────────────


def _as_date(text: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _by_text(rows: QuerySet[Any], field: str, text: str, label: Any) -> Any:
    """The row whose ``field`` is ``text`` (any case), else the one that contains it; 409 if several."""
    matches = list(
        rows.filter(**{f"{field}__iexact": text})[: MAX_CANDIDATES + 1]
    ) or list(rows.filter(**{f"{field}__icontains": text})[: MAX_CANDIDATES + 1])
    if len(matches) > 1:
        names = ", ".join(str(match) for match in matches[:MAX_CANDIDATES])
        raise Conflict(
            str(AMBIGUOUS) % {"name": text, "matches": names},
            code="schedule.ambiguous_reference",
        )
    if not matches:
        raise NotFound(str(label))
    return matches[0]


def resolve_special_day(
    special_day_id: UUID | None, text: str | None, *, lock: bool = False
) -> SpecialDay:
    """The special day by id; or by date (a yearly one answers for its day and month of any year); or
    by name. ``lock`` takes its row until the end of the command."""
    rows = SpecialDay.objects.select_for_update() if lock else SpecialDay.objects.all()
    if special_day_id is not None:
        found = rows.filter(pk=special_day_id).first()
        if found is None:
            raise NotFound(str(SPECIAL_DAY_NOT_FOUND))
        return found
    on = _as_date(text or "")
    if on is None:
        return _by_text(
            rows.order_by("date", "id"), "name", text or "", SPECIAL_DAY_NOT_FOUND
        )
    found = rows.filter(date=on).first() or (
        rows.filter(recurring_yearly=True, date__month=on.month, date__day=on.day)
        .order_by("-date", "-id")
        .first()
    )
    if found is None:
        raise NotFound(str(SPECIAL_DAY_NOT_FOUND))
    return found


def resolve_override(
    override_id: UUID | None, text: str | None, *, lock: bool = False
) -> Override:
    """The temporary change by id; or the one covering a date; or by reason."""
    rows = Override.objects.select_for_update() if lock else Override.objects.all()
    if override_id is not None:
        found = rows.filter(pk=override_id).first()
        if found is None:
            raise NotFound(str(OVERRIDE_NOT_FOUND))
        return found
    on = _as_date(text or "")
    if on is None:
        return _by_text(
            rows.order_by("start_date", "id"), "reason", text or "", OVERRIDE_NOT_FOUND
        )
    found = (
        rows.filter(start_date__lte=on, end_date__gte=on)
        .order_by("-start_date", "-id")
        .first()
    )
    if found is None:
        raise NotFound(str(OVERRIDE_NOT_FOUND))
    return found


# ── Pages ──────────────────────────────────────────────────────────────────────────────────────


def _sorted(
    rows: QuerySet[Any], sort: str, direction: str, columns: dict[str, tuple[str, ...]]
) -> QuerySet[Any]:
    """``rows`` by the columns of ``sort`` in ``direction``, then by id (the stable tie-break)."""
    descending = direction == "desc"
    order = [
        F(column).desc() if descending else F(column).asc() for column in columns[sort]
    ]
    return rows.order_by(*order, "-id" if descending else "id")


def _page(rows: QuerySet[Any], params: PageIn, out: Any) -> dict:
    return {
        "rows": [
            out(row) for row in rows[params.offset : params.offset + params.limit]
        ],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


# ── Operations ─────────────────────────────────────────────────────────────────────────────────


@operation(
    "schedule.week.get",
    kind="query",
    permission="schedule.view",
    input=NoParamsIn,
    output=WeekOut,
    expose_api=True,
    ai={
        "description": "Returns the business's usual opening week: each day closed, not set or with its opening "
        "intervals (several = split shift; closing before opening = past midnight; 00:00–00:00 = 24 hours), and "
        "whether the week is still the default one nobody confirmed."
    },
)
def get_week(ctx: OperationContext, data: NoParamsIn) -> dict:
    """SCHEDULE-F01: the seven days, from the one the settings say."""
    return week_out()


@operation(
    "schedule.special_day.list",
    kind="query",
    permission="schedule.view",
    input=SpecialDayListIn,
    output=SpecialDayPage,
    expose_api=True,
    ai={
        "description": "Lists the special days (holidays, closures, days with other hours) with their intervals."
    },
)
def list_special_days(ctx: OperationContext, params: SpecialDayListIn) -> dict:
    rows = special_days()
    if params.search:
        rows = rows.filter(
            Q(name__icontains=params.search) | Q(notes__icontains=params.search)
        )
    if params.name:
        rows = rows.filter(name__icontains=params.name)
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_closed is not None:
        rows = rows.filter(is_closed=params.is_closed)
    if params.recurring_yearly is not None:
        rows = rows.filter(recurring_yearly=params.recurring_yearly)
    return _page(
        _sorted(rows, params.sort, params.dir, SPECIAL_DAY_SORTS),
        params,
        special_day_out,
    )


@operation(
    "schedule.override.list",
    kind="query",
    permission="schedule.view",
    input=OverrideListIn,
    output=OverridePage,
    expose_api=True,
    ai={
        "description": "Lists the temporary changes of the opening hours (a range of dates closed or with other hours)."
    },
)
def list_overrides(ctx: OperationContext, params: OverrideListIn) -> dict:
    rows = overrides()
    if params.search:
        rows = rows.filter(reason__icontains=params.search)
    if params.reason:
        rows = rows.filter(reason__icontains=params.reason)
    for field, lookup in (
        ("start_from", "start_date__gte"),
        ("start_to", "start_date__lte"),
        ("end_from", "end_date__gte"),
        ("end_to", "end_date__lte"),
    ):
        if getattr(params, field):
            rows = rows.filter(**{lookup: getattr(params, field)})
    if params.is_closed is not None:
        rows = rows.filter(is_closed=params.is_closed)
    return _page(
        _sorted(rows, params.sort, params.dir, OVERRIDE_SORTS), params, override_out
    )


@operation(
    "schedule.settings.get",
    kind="query",
    permission="schedule.view",
    input=NoParamsIn,
    output=SettingsOut,
    ai={
        "description": "Returns the settings of the opening hours (the day the week starts on) and the business's time zone."
    },
)
def get_settings(ctx: OperationContext, data: NoParamsIn) -> dict:
    return settings_out(settings_row())


@operation(
    "schedule.business.is_open",
    kind="query",
    permission="schedule.view",
    input=IsOpenIn,
    output=IsOpenOut,
    expose_api=True,
    ai={
        "description": "Says whether the business is open at a moment (now if none) on its own clock, which rule "
        "decided (special day > yearly special day > temporary change > usual week > nothing) and why, as a stable "
        "code: exception_closed, exception_hours, open_interval, closed_today, overnight_open, outside_hours or "
        "no_hours (nothing configured: not open)."
    },
)
def business_is_open(ctx: OperationContext, data: IsOpenIn) -> dict:
    """SCHEDULE-F10; the rules are the server's own, the caller only says when."""
    moment = engine.parse_when(data.when, business_zone(), timezone.now())
    verdict = engine.is_open(load_calendar(moment.date(), moment.date()), moment)
    return {
        "is_open": verdict.is_open,
        "code": verdict.code,
        "source": verdict.source,
        "rule_id": verdict.rule_id,
        "intervals": verdict.intervals,
        "timezone": zone_name(),
        "today": moment.date(),
        "current_time": f"{moment:%H:%M}",
        "reason": verdict.reason or None,
    }


@operation(
    "schedule.hours.for_range",
    kind="query",
    permission="schedule.view",
    input=HoursRangeIn,
    output=HoursRangeOut,
    expose_api=True,
    ai={
        "description": "Returns the business's opening hours of each day of a range (up to 366 days): the rule that "
        "governs the day and its opening spans as wall-clock date and time. A booking fits when it lies inside one "
        "span of its day or of the eve (past midnight). The authoritative answer to when the business is open."
    },
)
def hours_for_range(ctx: OperationContext, data: HoursRangeIn) -> dict:
    """SCHEDULE-F11: what the appointment book crosses with each professional's availability (staff)."""
    date_to = data.date_to or data.date_from
    calendar = load_calendar(data.date_from, date_to)
    days = []
    for offset in range((date_to - data.date_from).days + 1):
        day = data.date_from + dt.timedelta(days=offset)
        rule = engine.rule_for(calendar, day)
        days.append(
            {
                "date": day,
                "source": rule.source,
                "rule_id": rule.rule_id,
                "name": rule.name,
                "is_closed": rule.is_closed,
                "intervals": intervals_out(rule.intervals),
                "spans": [
                    {"start": start, "end": end}
                    for start, end in engine.spans_of(rule, day)
                ],
            }
        )
    return {"timezone": zone_name(), "days": days}
