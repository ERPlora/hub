"""The diary's rules without a database: queries.py and services.py feed them what they read.

- **Can this time be booked?** (``verdict``) The first reason that refuses wins, in this order:
  ``invalid_start`` (it does not end after it starts), ``in_past`` and ``too_soon`` (only for the
  customer and the series: the front desk books for right now and in the past), ``too_far`` (beyond the
  maximum advance, in business days; 0 lifts it), ``outside_schedule`` (the business's hours),
  ``outside_staff_hours`` (the professional's shift and time off), ``blocked`` and ``overlap``.
- **The business's hours** come from Schedules per day, as wall-clock spans: a booking fits when it
  lies inside one span of its day or of the eve (past midnight), and it may end at closing. A day no
  rule reaches (``restricted`` false) refuses nothing, as the current product did.
- **The professional's hours** come from Staff per day: with a schedule, the booking fits inside what
  is left of a shift; without one, only an approved absence refuses.
- **Free times** (``slots``) step through the calendar window by the slot interval and keep the
  starts that pass ``verdict`` whole. The front desk never sees the past but does see the times inside
  the notice (marked); with overlaps allowed it also sees a taken time. The customer sees neither.
- **The clock** is the business's: an instant is shown on it (``wall``) and a wall time read on it
  (``aware``); a wall time the change of time skips does not exist, a repeated one is its first time.
- **Series** repeat by RFC 5545 rules through ``dateutil.rrule``: every day, every week or two on a
  weekday (the first one from the start date), or every month on the start date's day (the last day of
  a shorter month); they end on a date (included) or after a number of dates counted from the start.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, rrule

#: The reasons a time cannot be booked, in the order they are judged.
CODES = (
    "invalid_start",
    "in_past",
    "too_soon",
    "too_far",
    "outside_schedule",
    "outside_staff_hours",
    "blocked",
    "overlap",
)
#: How many dates a series enumerates at most (a daily series of 27 years).
MAX_DATES = 10_000

Span = tuple[dt.datetime, dt.datetime]
Hours = tuple[dt.time, dt.time]


class NonexistentTime(ValueError):
    """A wall-clock time the change of time skips (02:30 on the last Sunday of March in Madrid)."""


@dataclass(frozen=True)
class Rules:
    """The business's booking rules (the app's settings)."""

    min_notice: int = 60
    max_advance_days: int = 90
    allow_overlap: bool = True
    calendar_start_hour: int = 8
    calendar_end_hour: int = 20
    slot_interval: int = 15


@dataclass(frozen=True)
class BusinessDay:
    """A day of Schedules: ``restricted`` when a rule governs it; its opening spans, naive wall-clock."""

    date: dt.date
    restricted: bool
    spans: tuple[Span, ...] = ()


@dataclass(frozen=True)
class StaffDay:
    """A day of Staff: whether a schedule governs it, what is left of its shifts, and its absences.

    An absence is ``(start, end)``; ``(None, None)`` is the whole day.
    """

    date: dt.date
    has_schedule: bool
    available: tuple[Hours, ...] = ()
    absences: tuple[tuple[dt.time | None, dt.time | None], ...] = ()


@dataclass(frozen=True)
class Period:
    """A blocked period or another appointment: aware instants, and what names it."""

    start: dt.datetime
    end: dt.datetime
    id: Any = None
    label: str = ""


@dataclass(frozen=True)
class Agenda:
    """Everything a verdict needs about one professional (or nobody) over some days."""

    zone: ZoneInfo
    rules: Rules
    business: Mapping[dt.date, BusinessDay] = field(default_factory=dict)
    #: ``None``: no professional to judge (the business's agenda alone).
    staff: Mapping[dt.date, StaffDay] | None = None
    blocks: Sequence[Period] = ()
    busy: Sequence[Period] = ()


@dataclass(frozen=True)
class Slot:
    start: dt.datetime
    end: dt.datetime
    #: Inside the minimum notice: only the front desk is offered it.
    within_notice: bool = False


# ── The clock ──────────────────────────────────────────────────────────────────────────────────


def wall(moment: dt.datetime, zone: ZoneInfo) -> dt.datetime:
    """``moment`` as the business's naive wall-clock date and time."""
    return moment.astimezone(zone).replace(tzinfo=None)


def aware(moment: dt.datetime, zone: ZoneInfo) -> dt.datetime:
    """A naive wall time read on the business's clock (an aware one only converted to it)."""
    if moment.tzinfo is not None:
        return moment.astimezone(zone)
    instant = moment.replace(tzinfo=zone, fold=0)
    if wall(instant.astimezone(dt.UTC), zone) != moment:
        raise NonexistentTime(moment.isoformat())
    return instant


def midnight(day: dt.date, zone: ZoneInfo) -> dt.datetime:
    """The instant the business's ``day`` starts."""
    return aware(dt.datetime.combine(day, dt.time()), zone)


# ── Can this time be booked? ───────────────────────────────────────────────────────────────────


def _touches(start: dt.datetime, end: dt.datetime, period: Period) -> bool:
    return period.start < end and start < period.end


def overlapping(agenda: Agenda, start: dt.datetime, end: dt.datetime) -> list[Period]:
    """The other appointments of the professional that ``[start, end)`` touches."""
    return [period for period in agenda.busy if _touches(start, end, period)]


def _fits_business(agenda: Agenda, begin: dt.datetime, finish: dt.datetime) -> bool:
    day = agenda.business.get(begin.date())
    if day is None or not day.restricted:
        return True
    eve = agenda.business.get(begin.date() - dt.timedelta(days=1))
    spans = list(day.spans) + list(eve.spans if eve else ())
    return any(opens <= begin and finish <= closes for opens, closes in spans)


def _fits_staff(agenda: Agenda, begin: dt.datetime, finish: dt.datetime) -> bool:
    if agenda.staff is None:
        return True
    day = agenda.staff.get(begin.date())
    if day is None:
        return True
    same_day = finish.date() == begin.date()
    if day.has_schedule:
        return same_day and any(
            start <= begin.time() and finish.time() <= end
            for start, end in day.available
        )
    for start, end in day.absences:
        if start is None or end is None:
            return False
        # Without a schedule a booking may cross midnight: compare it with the absence's own day.
        absence_start = dt.datetime.combine(day.date, start)
        absence_end = dt.datetime.combine(day.date, end)
        if absence_start < finish and begin < absence_end:
            return False
    return True


def verdict(
    agenda: Agenda,
    start: dt.datetime,
    end: dt.datetime,
    *,
    now: dt.datetime,
    customer: bool,
) -> str | None:
    """The first reason ``[start, end)`` cannot be booked (``CODES``), or ``None`` when it can.

    ``customer``: the customer books (or a series), so the past and the notice count and overlapping
    is never allowed.
    """
    rules = agenda.rules
    if end <= start:
        return "invalid_start"
    if customer and start < now:
        return "in_past"
    if customer and start < now + dt.timedelta(minutes=rules.min_notice):
        return "too_soon"
    begin, finish = wall(start, agenda.zone), wall(end, agenda.zone)
    if rules.max_advance_days > 0:
        last = wall(now, agenda.zone).date() + dt.timedelta(days=rules.max_advance_days)
        if begin.date() > last:
            return "too_far"
    if not _fits_business(agenda, begin, finish):
        return "outside_schedule"
    if not _fits_staff(agenda, begin, finish):
        return "outside_staff_hours"
    if any(_touches(start, end, block) for block in agenda.blocks):
        return "blocked"
    if overlapping(agenda, start, end) and (customer or not rules.allow_overlap):
        return "overlap"
    return None


# ── Free times ─────────────────────────────────────────────────────────────────────────────────


def slots(
    agenda: Agenda,
    day: dt.date,
    minutes: int,
    *,
    now: dt.datetime,
    customer: bool,
) -> list[Slot]:
    """The starts of ``day`` where ``minutes`` fit whole (see the module's docstring)."""
    rules = agenda.rules
    first = rules.calendar_start_hour * 60
    last = rules.calendar_end_hour * 60
    step = max(1, rules.slot_interval)
    notice = now + dt.timedelta(minutes=rules.min_notice)
    out: list[Slot] = []
    for minute in range(first, last - minutes + 1, step):
        moment = dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=minute)
        try:
            start = aware(moment, agenda.zone)
        except NonexistentTime:
            continue
        end = start + dt.timedelta(minutes=minutes)
        if start < now:
            continue
        if verdict(agenda, start, end, now=now, customer=customer) is None:
            out.append(Slot(start, end, within_notice=start < notice))
    return out


# ── Series ─────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pattern:
    """A series' rule: how often, on which weekday, from when, until when or how many times."""

    frequency: str
    day_of_week: int | None
    start_date: dt.date
    end_date: dt.date | None = None
    max_occurrences: int | None = None


def first_date(pattern: Pattern) -> dt.date:
    """The series' first date: its start date, or the first of its weekday from it."""
    if pattern.frequency in ("weekly", "biweekly") and pattern.day_of_week is not None:
        ahead = (pattern.day_of_week - pattern.start_date.weekday()) % 7
        return pattern.start_date + dt.timedelta(days=ahead)
    return pattern.start_date


def _rule(pattern: Pattern) -> rrule:
    start = first_date(pattern)
    begin = dt.datetime.combine(start, dt.time())
    count = pattern.max_occurrences
    if pattern.frequency == "daily":
        return rrule(DAILY, dtstart=begin, count=count)
    if pattern.frequency in ("weekly", "biweekly"):
        interval = 1 if pattern.frequency == "weekly" else 2
        return rrule(WEEKLY, interval=interval, dtstart=begin, count=count)
    if start.day <= 28:
        return rrule(MONTHLY, bymonthday=start.day, dtstart=begin, count=count)
    # The 29th to the 31st: the last of 28…day the month has (the last day of a shorter month).
    return rrule(
        MONTHLY,
        bymonthday=tuple(range(28, start.day + 1)),
        bysetpos=-1,
        dtstart=begin,
        count=count,
    )


def _walk(pattern: Pattern):
    """The series' dates in order, up to its end date (included)."""
    for index, moment in enumerate(_rule(pattern)):
        day = moment.date()
        if index >= MAX_DATES or (
            pattern.end_date is not None and day > pattern.end_date
        ):
            return
        yield day


def dates(pattern: Pattern, until: dt.date) -> tuple[list[dt.date], dt.date | None]:
    """The series' dates up to ``until`` (included), and its next date after it (``None``: no more)."""
    out: list[dt.date] = []
    for day in _walk(pattern):
        if day > until:
            return out, day
        out.append(day)
    return out, None


def contains(pattern: Pattern, day: dt.date) -> bool:
    """``day`` is one of the series' dates."""
    for candidate in _walk(pattern):
        if candidate >= day:
            return candidate == day
    return False


def count_before(pattern: Pattern, cut: dt.date) -> int:
    """How many of the series' dates fall before ``cut``."""
    count = 0
    for day in _walk(pattern):
        if day >= cut:
            break
        count += 1
    return count
