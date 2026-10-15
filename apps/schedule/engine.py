"""The rules of the business's hours, without a database: queries.py and services.py feed them.

- An **interval** is ``open_time``–``close_time`` on the business's wall clock; closing at or before it
  opens crosses midnight (22:00–02:00) and 00:00–00:00 is open 24 hours (Google Business Profile).
- A **set of intervals** (one day, one special day, one temporary change) is sorted by opening, never
  overlaps (through midnight too) and holds at most twelve.
- **Which rule governs a day**: the special day of that exact date, else a yearly special day of the
  same day and month (the newest date first), else the temporary change covering it, else the weekly
  day, else none (``no_hours``: the business is not declared open).
- **An interval belongs to the day it opens**, whatever its rule: the small hours of an overnight
  interval are open the next day even when that day is closed.

Hours are wall-clock: a change of time (DST) moves nothing; only an instant asked about is converted
to the business's zone (``parse_when``).
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

Source = Literal["special_day", "override", "weekly", "none"]

MAX_INTERVALS = 12
_DAY = 24 * 60
_MIDNIGHT = dt.time(0, 0)


class IntervalError(ValueError):
    """A set of intervals that breaks a rule: ``empty``, ``overlapping`` or ``too_many``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Interval:
    open_time: dt.time
    close_time: dt.time

    @property
    def all_day(self) -> bool:
        return self.open_time == _MIDNIGHT and self.close_time == _MIDNIGHT

    @property
    def overnight(self) -> bool:
        return not self.all_day and self.close_time <= self.open_time

    @property
    def minutes(self) -> tuple[int, int]:
        """``[start, end)`` in minutes since the midnight of its own day; past 1440 runs into the next."""
        start = self.open_time.hour * 60 + self.open_time.minute
        if self.all_day:
            return 0, _DAY
        end = self.close_time.hour * 60 + self.close_time.minute
        return start, end + _DAY if end <= start else end


def span_text(interval: Interval) -> str:
    """«09:00–14:00»: the stable way a verdict names an interval (the caller phrases it)."""
    return f"{interval.open_time:%H:%M}–{interval.close_time:%H:%M}"


def _minute(value: dt.time) -> dt.time:
    return value.replace(second=0, microsecond=0)


def normalize(intervals: Iterable[Interval]) -> list[Interval]:
    """The intervals without seconds and sorted by opening, or ``IntervalError``.

    An interval opening and closing at the same minute is empty (``empty``), unless it is 00:00–00:00;
    two intervals may not share a minute (``overlapping``), an overnight tail included; twelve at most
    (``too_many``).
    """
    items = [Interval(_minute(i.open_time), _minute(i.close_time)) for i in intervals]
    if len(items) > MAX_INTERVALS:
        raise IntervalError("too_many")
    for item in items:
        if item.open_time == item.close_time and not item.all_day:
            raise IntervalError("empty")
    items.sort(key=lambda item: item.minutes)
    for before, after in zip(items, items[1:]):
        if after.minutes[0] < before.minutes[1]:
            raise IntervalError("overlapping")
    if len(items) > 1 and items[-1].minutes[1] - _DAY > items[0].minutes[0]:
        raise IntervalError("overlapping")
    return items


@dataclass(frozen=True)
class WeeklyDay:
    """A day of the usual week: closed, or its intervals."""

    id: UUID
    is_closed: bool
    intervals: tuple[Interval, ...] = ()


@dataclass(frozen=True)
class ExceptionRule:
    """A special day (``start == end``, maybe yearly) or a temporary change (``start``–``end``)."""

    id: UUID
    start: dt.date
    end: dt.date
    name: str
    is_closed: bool
    intervals: tuple[Interval, ...] = ()
    recurring_yearly: bool = False


@dataclass(frozen=True)
class Calendar:
    """Every rule of a business: ``weekly`` by weekday (Monday = 0)."""

    weekly: dict[int, WeeklyDay] = field(default_factory=dict)
    special_days: list[ExceptionRule] = field(default_factory=list)
    overrides: list[ExceptionRule] = field(default_factory=list)


@dataclass(frozen=True)
class Rule:
    """What governs a day: its source, the row that decided, its name (or reason) and its hours."""

    source: Source
    rule_id: UUID | None = None
    name: str = ""
    is_closed: bool = False
    intervals: tuple[Interval, ...] = ()

    @property
    def is_exception(self) -> bool:
        return self.source in ("special_day", "override")


NO_RULE = Rule("none")


def rule_for(calendar: Calendar, day: dt.date) -> Rule:
    """The rule that governs ``day`` (precedence in the module's docstring)."""
    exact = [sd for sd in calendar.special_days if sd.start == day]
    yearly = [
        sd
        for sd in calendar.special_days
        if sd.recurring_yearly
        and (sd.start.month, sd.start.day) == (day.month, day.day)
    ]
    winner = max(exact or yearly, key=lambda sd: (sd.start, sd.id), default=None)
    if winner is not None:
        return Rule(
            "special_day", winner.id, winner.name, winner.is_closed, winner.intervals
        )
    covering = [ov for ov in calendar.overrides if ov.start <= day <= ov.end]
    winner = max(covering, key=lambda ov: (ov.start, ov.id), default=None)
    if winner is not None:
        return Rule(
            "override", winner.id, winner.name, winner.is_closed, winner.intervals
        )
    weekly = calendar.weekly.get(day.weekday())
    if weekly is not None:
        return Rule("weekly", weekly.id, "", weekly.is_closed, weekly.intervals)
    return NO_RULE


def spans_of(rule: Rule, day: dt.date) -> list[tuple[dt.datetime, dt.datetime]]:
    """The opening spans of ``day`` under ``rule``, wall-clock ``[start, end)``; ``end`` may be the next day."""
    if rule.is_closed:
        return []
    midnight = dt.datetime.combine(day, _MIDNIGHT)
    return [
        (midnight + dt.timedelta(minutes=start), midnight + dt.timedelta(minutes=end))
        for start, end in (interval.minutes for interval in rule.intervals)
    ]


@dataclass(frozen=True)
class Verdict:
    """The answer to «is it open?»: a stable ``code`` the caller phrases in its own language."""

    is_open: bool
    code: str
    source: Source
    rule_id: UUID | None
    intervals: list[str]
    reason: str = ""


def is_open(calendar: Calendar, moment: dt.datetime) -> Verdict:
    """Open from an opening to the minute before its closing; yesterday's overnight tail counts."""
    day = moment.date()
    rule = rule_for(calendar, day)
    for interval, (start, end) in zip(rule.intervals, spans_of(rule, day)):
        if start <= moment < end:
            code = "exception_hours" if rule.is_exception else "open_interval"
            spans = (
                [span_text(i) for i in rule.intervals]
                if rule.is_exception
                else [span_text(interval)]
            )
            return Verdict(True, code, rule.source, rule.rule_id, spans, rule.name)
    eve = rule_for(calendar, day - dt.timedelta(days=1))
    for interval, (start, end) in zip(
        eve.intervals, spans_of(eve, day - dt.timedelta(days=1))
    ):
        if start <= moment < end:
            return Verdict(
                True,
                "overnight_open",
                eve.source,
                eve.rule_id,
                [span_text(interval)],
                eve.name,
            )
    spans = [span_text(i) for i in rule.intervals]
    if rule.source == "none":
        return Verdict(False, "no_hours", "none", None, [])
    if rule.is_exception:
        code = "exception_closed" if rule.is_closed else "exception_hours"
        return Verdict(
            False,
            code,
            rule.source,
            rule.rule_id,
            [] if rule.is_closed else spans,
            rule.name,
        )
    if rule.is_closed:
        return Verdict(False, "closed_today", "weekly", rule.rule_id, [])
    return Verdict(False, "outside_hours", "weekly", rule.rule_id, spans)


def parse_when(text: str | None, zone: ZoneInfo, now: dt.datetime) -> dt.datetime:
    """The moment asked about, as a wall-clock datetime of the business (to the minute).

    With an offset (``…Z``, ``…+02:00``) it is an instant, converted to ``zone``; without one it already
    is the shop's own wall clock and is read as written; empty is ``now``. ``ValueError`` for anything
    that is not a real date with a time.
    """
    if not text or not text.strip():
        moment = now.astimezone(zone)
    else:
        text = text.strip()
        if len(text) < 16 or text[10] not in "Tt ":
            raise ValueError(text)
        moment = dt.datetime.fromisoformat(text)
        if moment.tzinfo is not None:
            try:
                moment = moment.astimezone(zone)
            except OverflowError:
                # An instant at an end of the calendar (year 1 or 9999) has no wall clock here.
                raise ValueError(text) from None
    return moment.replace(second=0, microsecond=0, tzinfo=None)
