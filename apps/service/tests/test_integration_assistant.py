"""Services with the platform's assistant (flow service-business-currency): every amount a write of Services takes
is money for the assistant — the card the person confirms paints it in the business's currency (``kind == "money"``)
and the assistant's instructions tell the AI to send it in the minor unit of that currency (17 € → 1700, ¥17 → 17).
An amount is a ``Cents`` field of the schemas (bounded by ``MAX_CENTS``); a write that is a tool of the assistant with
such a field must hand it to the card as money, or the AI could send 65 for «65 €»."""

import pytest
from live.operations import get, registry

from apps.service.schemas import MAX_CENTS
from base import assistant

#: The writes of Services the assistant calls, by name.
TOOLS = sorted(name for name, op in registry.items() if op.app_label == "service" and op.kind == "command" and assistant.is_tool(op))


def money_fields(name: str) -> list[str]:
    """The fields of the input of ``name`` that are an amount (``Cents``: at most ``MAX_CENTS``)."""
    schema = assistant._schema(get(name))
    defs = schema.get("$defs", {})
    return [field for field, prop in schema.get("properties", {}).items() if assistant._resolved(prop, defs).get("maximum") == MAX_CENTS]


def test_the_writes_with_an_amount_are_found():
    """The detector is not empty: a service's price and a voucher's closed price are among them."""
    found = {(name, field) for name in TOOLS for field in money_fields(name)}
    assert {("service.service.create", "price"), ("service.package.create", "fixed_price")} <= found


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("name", TOOLS)
def test_every_amount_of_a_write_reaches_the_card_as_money(name, language):
    fields = money_fields(name)
    card = assistant.card(get(name), {field: 1500 for field in fields}, language)
    assert {field["name"]: field["kind"] for field in card["fields"]} == dict.fromkeys(fields, "money")
