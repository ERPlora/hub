"""The assistant's card of an invoice made by hand (``ai={"summary": assistant_cards.lines}``): each line's typed rate as
the invoice prints it, a percentage («10 %»), never a bare figure beside its quantity and its price."""

from django.utils import translation
from live.assistant import NAMED
from live.context import OperationContext

from apps.invoice.queries.documents import percent


def lines(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card's ``lines``, each with its rate as a percentage, when the card says them one by one (``NAMED``: then
    every rate is a figure)."""
    return [
        {**field, "value": [_line(line) for line in field["value"]]} if field["name"] == "lines" and field.get(NAMED) else field
        for field in fields
    ]


def _line(line: dict) -> dict:
    rate = line.get("tax_rate")
    return line if rate in (None, "") else {**line, "tax_rate": percent(rate, translation.get_language() or "en")}
