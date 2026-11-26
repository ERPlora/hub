"""What the reads hand over: a day ready to say, and the week, the special days, the temporary changes and the
settings as their operations return them (the writes return them too)."""

import datetime as dt

from django.utils import formats, translation

from apps.schedule import engine
from apps.schedule.models import Override, ScheduleSettings, SpecialDay
from base.business import zone_name
from base.weekdays import weekday_name

from .rows import _intervals, settings_row, week_days


def day_label(day: dt.date, language: str) -> str:
    """``day`` ready to say in ``language``, its weekday first («martes, 5 de marzo de 2030»): what a flow's
    template prints as it comes, with no formatter. Appointments and Reservations, which
    both require this app, say their days with it."""
    with translation.override(language):
        return f"{formats.date_format(day, 'l')}, {formats.date_format(day, 'DATE_FORMAT')}"


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
                "name": weekday_name(weekday),
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
