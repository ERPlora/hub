"""The hours a working day of a schedule does not say are the business's default working day (Staff › Settings), as the
schedule's window proposes a new week: its start, its end and, for a day that says none of its hours, its break in the
middle of the day, the break's start rounded down to the quarter hour (``proposedBreak`` of ``scheduleForm.ts``)."""

import datetime as dt
from typing import NamedTuple

from live.errors import InvalidPayload
from live.ninja import field_message
from pydantic import ValidationError

from apps.staff.schemas.schedules import DayIn

HOURS = ("start_time", "end_time", "break_start", "break_end")


class Workday(NamedTuple):
    start: dt.time
    end: dt.time
    break_minutes: int


def workday_of(settings: object) -> Workday:
    """The working day of the staff settings: their row, or their read, with its hours as HH:MM."""
    start, end = (dt.time.fromisoformat(str(getattr(settings, name))) for name in ("default_work_start", "default_work_end"))
    return Workday(start, end, settings.default_break_duration)


def proposed_break(workday: Workday) -> tuple[dt.time | None, dt.time | None]:
    """None for 0 minutes or in a day that cannot hold it."""
    start = _minutes(workday.start)
    length = _minutes(workday.end) - start
    if workday.break_minutes <= 0 or workday.break_minutes >= length:
        return None, None
    begins = start + (length - workday.break_minutes) // 30 * 15
    return _time(begins), _time(begins + workday.break_minutes)


def with_working_day(day: DayIn, workday: Workday) -> DayIn:
    """``day`` with the hours it does not say taken from ``workday``, checked as a day sent with them; a day off as it
    came, its hours ignored."""
    said = {name: value for name, value in day.model_dump().items() if value is not None}
    if not day.is_working or {"start_time", "end_time"} <= said.keys():
        return day
    if not said.keys() & set(HOURS):
        said["break_start"], said["break_end"] = proposed_break(workday)
    return DayIn.model_validate({"start_time": workday.start, "end_time": workday.end, **said})


def with_working_days(days: list[DayIn], workday: Workday) -> list[DayIn]:
    """Each day ``with_working_day``; the first one the working day makes wrong is refused under its field."""
    week = []
    for at, day in enumerate(days):
        try:
            week.append(with_working_day(day, workday))
        except ValidationError as refused:
            error = refused.errors()[0]
            reason = field_message(error)
            raise InvalidPayload(reason, fields={f"days.{at}.{error['loc'][0]}": reason}) from None
    return week


def _minutes(moment: dt.time) -> int:
    return moment.hour * 60 + moment.minute


def _time(minutes: int) -> dt.time:
    return dt.time(minutes // 60, minutes % 60)
