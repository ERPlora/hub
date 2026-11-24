"""The assistant's card for time off (``staff.time_off.create``): whose it is, what kind and its days as one period
(with its hours, for a part of each day), first: a normal card's line shows only its first three data."""

from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from live.context import OperationContext
from pydantic import ValidationError

from apps.staff.schemas.time_off import TimeOffIn
from base.assistant import card_order
from base.assistant.card_period import each_day, period

DATES = gettext_noop("Dates")
#: What the period says, out of the card.
SAID_IN_THE_PERIOD = ("start_date", "end_date", "is_full_day", "start_time", "end_time")


def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Data the write refuses keep the card as they came."""
    try:
        data = TimeOffIn.model_validate(arguments)
    except ValidationError:
        return fields
    language = translation.get_language() or "en"
    days = period(data.start_date, data.end_date, language)
    if not data.is_full_day:
        days = each_day(days, period(data.start_time, data.end_time, language), language)
    when = {"name": "period", "label": gettext(DATES), "kind": "text", "value": days}
    return card_order.put_first(fields, ("member_id", "member", "leave_type"), when, dropped=SAID_IN_THE_PERIOD)
