"""The assistant's card for a person's weekly schedule (``staff.schedule.create`` and ``staff.schedule.update``): whose it
is and its week first, each run of days in a row with the same hours on one line with those hours, as the write keeps
them: a day without its hours, with the business's default working day (``apps.staff.workday``). A normal card's line
shows only its first three data, and a week said as a list of days showed only how many it had."""

from django.utils import translation
from live import assistant as shared
from live.assistant import NAMED
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import get
from pydantic import BaseModel, ValidationError

from apps.staff.schemas.schedules import DayIn, ScheduleIn, ScheduleUpdateIn
from apps.staff.workday import with_working_days, workday_of
from base.assistant import card_order
from base.assistant.card_period import period
from base.business import babel_locale
from base.weekdays import weekday_name

SETTINGS = "staff.settings.get"


def created(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    return _with_week(ctx, ScheduleIn, arguments, fields, ("member_id", "member"))


def updated(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    return _with_week(ctx, ScheduleUpdateIn, arguments, fields, ("id",))


def _with_week(
    ctx: OperationContext, schema: type[BaseModel], arguments: dict, fields: list[dict], whose: tuple[str, ...]
) -> list[dict]:
    """Data the write refuses keep the card as they came."""
    try:
        data = schema.model_validate(arguments)
    except ValidationError:
        return fields
    said = next(field for field in fields if field["name"] == "days")
    week = {**said, "value": _lines(_kept(ctx, data.days), translation.get_language() or "en"), NAMED: True}
    return card_order.put_first(fields, whose, week)


def _kept(ctx: OperationContext, days: list[DayIn]) -> list[DayIn]:
    """The days with the hours the write gives them; as said when this person cannot read the working day, or when it
    makes a day wrong (the write refuses it): never hours made up."""
    if all(day.start_time is not None and day.end_time is not None for day in days if day.is_working):
        return days
    failure, settings = shared.run(ctx, get(SETTINGS), {})
    if failure is not None:
        return days
    try:
        return with_working_days(days, workday_of(settings))
    except InvalidPayload:
        return days


def _lines(days: list[DayIn], language: str) -> list[dict]:
    runs: list[list] = []
    for day in sorted((day for day in days if day.is_working), key=lambda day: day.weekday):
        hours = _hours(day, language)
        if runs and runs[-1][1] == day.weekday - 1 and runs[-1][2] == hours:
            runs[-1][1] = day.weekday
        else:
            runs.append([day.weekday, day.weekday, hours])
    return [{"days": _days(first, last, language), **({"hours": hours} if hours else {})} for first, last, hours in runs]


def _hours(day: DayIn, language: str) -> str:
    """Its stretches, as the card says a period: two around its break («10:00–14:00, 15:00–19:00»)."""
    if day.start_time is None or day.end_time is None:
        return ""
    if day.break_start is None or day.break_end is None:
        return period(day.start_time, day.end_time, language)
    return f"{period(day.start_time, day.break_start, language)}, {period(day.break_end, day.end_time, language)}"


def _days(first: int, last: int, language: str) -> str:
    """One day by its name, or the first and the last as the language writes an interval (CLDR)."""
    if first == last:
        return weekday_name(first, language)
    pattern = babel_locale(language).interval_formats[None]
    return pattern.replace("{0}", weekday_name(first, language)).replace("{1}", weekday_name(last, language))
