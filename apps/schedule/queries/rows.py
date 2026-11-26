"""What the reads load: the saved settings, the week, the special days and the temporary changes with their
intervals in opening order, and the calendar of a range of days the engine decides with."""

import datetime as dt
from typing import Any

from django.db.models import Prefetch, Q, QuerySet

from apps.schedule import engine
from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)


def settings_row() -> ScheduleSettings:
    """The saved settings, or the defaults while nobody saved them."""
    return ScheduleSettings.objects.first() or ScheduleSettings()


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
