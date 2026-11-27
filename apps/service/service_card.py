"""The assistant's card for a new service (``service.service.create``): its name, its price and how long it lasts, first,
as a card's line shows only three data. A duration the person does not say is the settings' one the service takes."""

from django.utils import translation
from live import assistant as shared
from live.context import OperationContext
from live.operations import get

from base.assistant import card_order

FIRST = ("name", "price", "duration_minutes")
SETTINGS = "service.settings.get"


def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The settings' duration is shown as if said; when they cannot be read, the card says no duration at all."""
    if arguments.get("duration_minutes") is not None:
        return card_order.put_first(fields, FIRST)
    failure, settings = shared.run(ctx, get(SETTINGS), {})
    if failure is not None:
        return card_order.put_first(fields, FIRST)
    said = shared.card(get("service.service.create"), {"duration_minutes": settings.default_duration}, translation.get_language() or "en")
    return card_order.put_first(fields, FIRST[:2], *said["fields"])
