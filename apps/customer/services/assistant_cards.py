"""The assistant's card of a change to a customer's card (``ai={"summary": assistant_cards.field_values}``): each custom
field it sets by its name and its value as that field's card shows it — a yes or no in the person's language, a day as
the card writes one, a field left empty by a dash —, never the code the write takes («true», «2027-01-02»)."""

from django.utils import translation
from django.utils.translation import pgettext
from live import assistant as shared
from live.assistant import NAMED
from live.context import OperationContext
from live.operations import get

from apps.customer.services.field_values import BOOLEANS
from base.assistant.cards import moment

#: The read that names a custom field on the card (``A_FIELD``), which also says its type.
FIELD = "customer.field.detail"
#: How the card says a datum left empty (@erplora/ui ``fieldText``).
EMPTY = "—"


def _value(ctx: OperationContext, field_id: str, value: str) -> str:
    """``value`` as the card of the field ``field_id`` shows it; as written when the write refuses it or keeps it as
    text, or when the field cannot be read."""
    if value == "":
        return EMPTY
    failure, field = shared.run(ctx, get(FIELD), {"id": field_id})
    if failure is not None:
        return value
    if field.field_type == "boolean" and value.lower() in BOOLEANS:
        yes = BOOLEANS[value.lower()] == "true"
        return pgettext("custom field value", "Yes") if yes else pgettext("custom field value", "No")
    if field.field_type == "date":
        return moment(value, "date", translation.get_language() or "en") or value
    return value


def field_values(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card's ``field_values`` with each value in words, when the card says them one by one (``NAMED``: each field
    by its name); counted, as they came."""
    return [
        {**field, "value": [_line(ctx, sent, said) for sent, said in zip(arguments["field_values"], field["value"], strict=True)]}
        if field["name"] == "field_values" and field.get(NAMED)
        else field
        for field in fields
    ]


def _line(ctx: OperationContext, sent: dict, said: dict) -> dict:
    return {**said, "value": _value(ctx, sent["field_id"], sent.get("value", ""))}
