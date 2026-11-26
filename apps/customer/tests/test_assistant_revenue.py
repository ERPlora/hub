"""What the assistant's model reads of the customers' money: in the business's currency, as the screen shows it.

Clientes keeps an amount in cents (``total_revenue`` 360 is 3.60 €) and the model, which never sees a result's schema,
repeated the figure as it read it: «¿cuánto nos han dejado entre todos?» got «360,00 EUR» for the 3.60 € on the screen.
"""

import pytest

from apps.customer.models import Customer
from apps.customer.tests.conftest import HUB_DB, in_business_a, told_in_a_turn
from base.models import Hub
from base.tenancy.tests.business import A

__all__ = ["in_business_a"]
pytestmark = HUB_DB

ASK = "¿Cuántos clientes tengo ya apuntados, cuántos son VIP y cuánto nos han dejado entre todos?"


def told(name: str, *, yes: bool = False, **arguments) -> dict:
    """What the model reads of the tool ``name`` run in a turn of the owner, as the chat runs it; a write, once the
    owner says yes to its card (``yes``)."""
    return told_in_a_turn(name, arguments, ask=ASK, yes=yes)


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


def test_a_change_the_owner_said_yes_to_tells_the_model_its_amounts_as_the_screen_shows_them(lucia):
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "country": "ES"})
    card = Customer.objects.get(name="Lucía QA")
    assert told("customer.customer.update", yes=True, id=str(card.id), company_name="QA")["total_spent"] == "3.60 EUR"
