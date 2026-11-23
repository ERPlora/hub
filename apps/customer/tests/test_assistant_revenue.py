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


def told(name: str, **arguments) -> dict:
    """What the model reads of the tool ``name`` run in a turn of the owner, as the chat runs it."""
    call = {"call_id": "c1", "name": shared.tool_name(name), "arguments": json.dumps(arguments)}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}],
    }
    turn = get("base.assistant.turn")
    data = {"messages": [{"role": "user", "content": ASK}, asked], "pending": [call]}
    plan = turn(ctx_for("hub_owner", language="es"), turn.input.model_validate(data)).model_dump(mode="json")
    [result] = plan["append"]
    return json.loads(result["content"])


@pytest.fixture
def lucia():
    """Four customers, one of whom spent 3.60 € in one purchase."""
    Customer.objects.create(name="Lucía QA", total_purchases=1, total_spent=360)
    for name in ("Ana", "Bea", "Carla"):
        Customer.objects.create(name=name)


@pytest.mark.parametrize(("country", "said"), [("ES", "3.60 EUR"), ("JP", "360 JPY")])
def test_the_customers_revenue_reaches_the_model_as_the_screen_shows_it(lucia, country, said):
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": country})
    assert told("customer.customer.stats") == {"total": 4, "active": 4, "vip": 0, "total_revenue": said}
    [card] = [row for row in told("customer.customer.list")["rows"] if row["name"] == "Lucía QA"]
    assert (card["total_purchases"], card["total_spent"]) == (1, said)
