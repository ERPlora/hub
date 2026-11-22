"""Who opens a cart, fills it and turns it into an order never shows a colleague's email (BASE-F119).

Carts and their orders keep who did each thing by the name a colleague reads: the account's name, else what goes
before the «@» of its email, never the address. An employee sees no colleague's contact details; the manager reads the
same name. The carts and orders saved with an address before are cleaned once by the app's migration
(``test_migrations``).
"""

import pytest

from apps.cart_checkout.models import Cart, CartItem, Order
from apps.flow.tests.test_api import get, post
from base.tests.team_contact import NAMELESS, NAMELESS_IDS, SHOWN, signed_in

from .conftest import HUB_DB

pytestmark = HUB_DB


@pytest.fixture(params=NAMELESS, ids=NAMELESS_IDS)
def zoe(request):
    """Zoe, a manager whose account has no name of its own: her device."""
    return signed_in("zoe", "hub_manager", **request.param)[1]


def ordered(client) -> dict:
    """A cart of ``client`` with a line, turned into an order: the order."""
    for path, data in (
        ("/cart_checkout/carts", {"session_token": "sess_zoe", "customer_email": "carmen@example.com"}),
        ("/cart_checkout/items", {"session_token": "sess_zoe", "product_ref": "p-1", "product_name": "Champú", "quantity": "1", "unit_price": 1200}),
        ("/cart_checkout/checkout/initiate", {"customer": "carmen@example.com"}),
    ):
        response = post(client, path, data)
        assert response.status_code == 201, (path, response.content)
    return response.json()


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_who_opens_a_cart_and_orders_it_is_named_without_their_address(zoe, role):
    ordered(zoe)
    _, reader = signed_in("reader", role)
    carts = [(row["created_by"], row["updated_by"]) for row in get(reader, "/cart_checkout/carts").json()["rows"]]
    orders = [(row["created_by"], row["updated_by"]) for row in get(reader, "/cart_checkout/orders").json()["rows"]]
    assert (carts, orders) == ([(SHOWN, SHOWN)], [(SHOWN, SHOWN)])
    saved = {
        value
        for model in (Cart, CartItem, Order)
        for row in model.objects.values("created_by", "updated_by")
        for value in row.values()
    }
    assert saved == {SHOWN}


def test_a_named_colleague_keeps_their_name(db):
    _, luis = signed_in("luis", "hub_manager", first_name="Luis", last_name="García", email="luis@example.com")
    assert ordered(luis)["created_by"] == "Luis García"
