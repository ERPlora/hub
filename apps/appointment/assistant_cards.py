"""The assistant's cards of Appointments: whom, when — a start and its end as one period — and with what, first, and
what a change changes by its name. A normal card's line shows only its first three data, in the form's order."""

from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from live.context import OperationContext
from pydantic import ValidationError

from apps.appointment.schemas.blocked_times import BlockedTimeCreateIn
from base.assistant import card_order
from base.assistant.card_period import period

WHEN = gettext_noop("When")
#: The service and who does it, after whom and when.
WITH_WHOM = ("services", "staff_id", "staff")
CUSTOMER = ("customer_id", "customer")
#: When a series repeats, said together: one datum of the line.
REPEATS = ("start_date", "time", "frequency", "day_of_week")
#: What a change of a series changes of when it repeats, from the day it is changed, said together.
REPEATS_FROM = ("from_date", "frequency", "day_of_week", "time", "duration_minutes", "end_date", "max_occurrences")


def booking(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Whom, when it starts, and the service (then who does it)."""
    return card_order.put_first(fields, (*CUSTOMER, "start", *WITH_WHOM))


def blocked_time(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Whose time it blocks (nobody named: the whole business's), its start and its end, and what it is. Data the
    write refuses keep the card as they came."""
    try:
        data = BlockedTimeCreateIn.model_validate(arguments)
    except ValidationError:
        return fields
    start, end = (data.start.date(), data.end.date()) if data.all_day else (data.start, data.end)
    when = {"name": "period", "label": gettext(WHEN), "kind": "text", "value": period(start, end, translation.get_language() or "en")}
    return card_order.put_first(fields, ("staff_id", "staff"), when, dropped=("start", "end", "all_day"))


def series(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Whom, when it repeats (its first day, its time and how often, as one datum), and the service."""
    when = card_order.together(fields, "when", REPEATS)
    return card_order.put_first(fields, CUSTOMER, *_some(when), *_said(fields, WITH_WHOM), dropped=REPEATS)


def series_change(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Which series, from when and what changes of when it repeats (as one datum), and then, as the form asks them,
    who does it and the services: «desde febrero, a las 11:00 y con Carlos»."""
    when = card_order.together(fields, "when", REPEATS_FROM)
    return card_order.put_first(fields, ("id",), *_some(when), dropped=REPEATS_FROM)


def _some(*data: dict | None) -> list[dict]:
    return [datum for datum in data if datum is not None]


def _said(fields: list[dict], names: tuple[str, ...]) -> list[dict]:
    """The data of ``fields`` named in ``names``, in that order, as they are."""
    return sorted((field for field in fields if field["name"] in names), key=lambda field: names.index(field["name"]))
