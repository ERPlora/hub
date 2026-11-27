"""What the assistant's model reads of the customers' money: in the business's currency, as the screen shows it.

Clientes keeps an amount in cents (``total_revenue`` 360 is 3.60 €) and the model, which never sees a result's schema,
repeated the figure as it read it: «¿cuánto nos han dejado entre todos?» got «360,00 EUR» for the 3.60 € on the screen.
"""

import json

import pytest
from live import assistant as shared
from live.operations import get

from apps.customer.models import Customer
from apps.customer.tests.conftest import HUB_DB, ctx_for, in_business_a
from base.models import Hub
from base.tenancy.tests.business import A

__all__ = ["in_business_a"]
pytestmark = HUB_DB

ASK = "¿Cuántos clientes tengo ya apuntados, cuántos son VIP y cuánto nos han dejado entre todos?"


def turn(messages: list, pending: list, decision: dict | None = None) -> dict:
    operation = get("base.assistant.turn")
    data = {"messages": messages, "pending": pending, "decision": decision}
    return operation(ctx_for("hub_owner", language="es"), operation.input.model_validate(data)).model_dump(mode="json")


def told(name: str, *, yes: bool = False, **arguments) -> dict:
    """What the model reads of the tool ``name`` run in a turn of the owner, as the chat runs it; a write, once the
    owner says yes to its card (``yes``)."""
    call = {"call_id": "c1", "name": shared.tool_name(name), "arguments": json.dumps(arguments)}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}],
    }
    messages = [{"role": "user", "content": ASK}, asked]
    plan = turn(messages, [call])
    if yes:
        plan = turn(messages, plan["pending"], {"call_id": "c1", "accepted": True})
    [result] = plan["append"]
    return json.loads(result["content"])


@pytest.fixture
def lucia():
    """Four customers, one of whom spent 3.60 € in one purchase."""
    Customer.objects.create(name="Lucía QA", total_purchases=1, total_spent=360)
    for name in ("Ana", "Bea", "Carla"):
        Customer.objects.create(name=name)


@pytest.mark.parametrize(("country", "said"), [("ES", "3,60\xa0€"), ("JP", "360\xa0JPY")])
def test_the_customers_revenue_reaches_the_model_as_the_screen_shows_it(lucia, country, said):
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": country})
    assert told("customer.customer.stats") == {"total": 4, "active": 4, "vip": 0, "total_revenue": said}
    [card] = [row for row in told("customer.customer.list")["rows"] if row["name"] == "Lucía QA"]
    assert (card["total_purchases"], card["total_spent"]) == (1, said)


def test_a_change_the_owner_said_yes_to_tells_the_model_its_amounts_as_the_screen_shows_them(lucia):
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": "ES"})
    card = Customer.objects.get(name="Lucía QA")
    assert told("customer.customer.update", yes=True, id=str(card.id), company_name="QA")["total_spent"] == "3,60\xa0€"
