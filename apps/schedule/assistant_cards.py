"""The assistant's cards of Schedules: what a special day or a temporary change is, when, and the hours it keeps — its
opening intervals, or that it is closed —, first, because a normal card's line shows only its first three data; the
special days loaded at once, each by its day and its name, and its hours when it is open, as their list says them. The
hours are those the write keeps: intervals sent with a day left closed are ignored. Data the write refuses keep the
card as they came."""

from django.utils import translation
from django.utils.translation import pgettext
from live.assistant import NAMED, label
from live.context import OperationContext
from live.operations import get
from pydantic import BaseModel, ValidationError

from apps.schedule.schemas import BulkSpecialDayIn, IntervalIn, OverrideIn, SpecialDayIn
from base.assistant import card_order
from base.assistant.card_period import period

#: What a special day or a temporary change keeps of its hours, said by one datum of the card.
HOURS = ("is_closed", "intervals")


def _language() -> str:
    return translation.get_language() or "en"


def _hours(op: str, data: BaseModel, fields: list[dict]) -> dict | None:
    """The datum that says the hours ``data`` keeps: its intervals as the card says them when open, else «Closed»."""
    if not data.is_closed:
        return next((field for field in fields if field["name"] == "intervals"), None)
    return {"name": "is_closed", "label": str(label(get(op), "is_closed", None)), "kind": "bool", "value": True}


def special_day(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Its name, its day and its hours."""
    try:
        data = SpecialDayIn.model_validate(arguments)
    except ValidationError:
        return fields
    hours = _hours("schedule.special_day.create", data, fields)
    return card_order.put_first(fields, ("name", "date"), *([hours] if hours else []), dropped=HOURS)


def override(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Its reason, its dates as one period and its hours."""
    try:
        data = OverrideIn.model_validate(arguments)
    except ValidationError:
        return fields
    when = {
        "name": "period",
        "label": pgettext("schedule card", "When"),
        "kind": "text",
        "value": period(data.start_date, data.end_date, _language()),
    }
    hours = _hours("schedule.override.create", data, fields)
    return card_order.put_first(
        fields, ("reason",), when, *([hours] if hours else []), dropped=("start_date", "end_date", *HOURS)
    )


def _opening(intervals: list[IntervalIn]) -> str:
    return ", ".join(period(interval.open_time, interval.close_time, _language()) for interval in intervals)


def special_days(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Each day by its day and its name, and its hours when it is open."""
    try:
        data = BulkSpecialDayIn.model_validate(arguments)
    except ValidationError:
        return fields
    lines = [
        {"date": said["date"], "name": day.name, **({} if day.is_closed else {"hours": _opening(day.intervals)})}
        for day, said in zip(data.special_days, _said(fields), strict=True)
    ]
    return [{**field, "value": lines, NAMED: True} if field["name"] == "special_days" else field for field in fields]


def _said(fields: list[dict]) -> list[dict]:
    return next(field["value"] for field in fields if field["name"] == "special_days")
