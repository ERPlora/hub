"""Fixtures of the cart_checkout tests: contexts per role and scope, a fixed clock, builders of the data a test
starts from (straight to the models: the operations are under test), and the helpers that run an operation and read
the events it left, which the tests of every module of services/ share.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get

from apps.cart_checkout.models import Cart
from apps.cash_register.tests.conftest import across_a_change_of_zone
from apps.flow.tests.test_relay import listen
from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import db_dsn, make_user, night_elsewhere
from apps.sale.tests.test_business_currency import platform
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host, the raw DSN of
#: control's database and business A at night in another zone as Sales makes them, ERPlora's own hub as business B
#: (Sales'), business A across a change of zone (Cash register's), the assistant's catalogue of a person of business A
#: (Invoicing's) and a raw session listening on a business's channel (Automations'), that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "across_a_change_of_zone", "catalog_of", "db_dsn", "hub_staff",
    "in_business_a", "listen", "make_user", "night_elsewhere", "plan_with_room", "platform",
]

#: The moment every test lives in (no real clock): 14 October 2026, 10:00 in Madrid.
NOW = dt.datetime(2026, 10, 14, 8, 0, tzinfo=dt.UTC)
LATER = NOW + dt.timedelta(hours=1)
EARLIER = NOW - dt.timedelta(hours=1)


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``permissions`` replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def clock(monkeypatch):
    """Freezes ``timezone.now`` at ``NOW``; ``clock.at(moment)`` moves it."""

    class Clock:
        now = NOW

        def at(self, moment: dt.datetime) -> None:
            self.now = moment

    frozen = Clock()
    monkeypatch.setattr(timezone, "now", lambda: frozen.now)
    return frozen


# Builders


def make_cart(session_token: str = "sess_a1b2c3", **fields):
    """A cart in euros unless the test says another currency (the model has no default: the operation gives a
    new cart the business's)."""
    from apps.cart_checkout.models import Cart

    fields.setdefault("currency", "EUR")
    return Cart.objects.create(session_token=session_token, **fields)


def make_item(
    cart,
    *,
    product_ref: str = "p-1",
    product_name: str = "Champú",
    quantity: Decimal = Decimal("1"),
    unit_price: int = 1250,
    **fields,
):
    """A line with its total already computed (as the operations leave it); the cart's totals are the
    caller's."""
    from apps.cart_checkout.models import CartItem

    fields.setdefault("line_total", int(quantity * unit_price))
    return CartItem.objects.create(
        cart=cart,
        product_ref=product_ref,
        product_name=product_name,
        quantity=quantity,
        unit_price=unit_price,
        **fields,
    )


def make_order(
    cart=None,
    *,
    order_number: str = "OS-20261014-0001",
    customer_email: str = "ana@example.com",
    total_amount: int = 2500,
    **fields,
):
    from apps.cart_checkout.models import Order

    cart = cart or make_cart()
    fields.setdefault("currency", cart.currency)
    return Order.objects.create(
        cart=cart,
        order_number=order_number,
        customer_email=customer_email,
        total_amount=total_amount,
        **fields,
    )


# Running the operations


def run(name, data: dict, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


def refused(error, code: str):
    """Asserts the operation was refused with ``code`` and left no event."""
    assert error.value.code == code
    assert events() == []


def stored(cart) -> Cart:
    return Cart.objects.get(pk=cart.pk)


def add(cart_or_token, quantity="1", unit_price=1250, **fields):
    token = cart_or_token if isinstance(cart_or_token, str) else cart_or_token.session_token
    data = {
        "session_token": token,
        "product_ref": "p-1",
        "product_name": "Champú",
        "quantity": quantity,
        "unit_price": unit_price,
    } | fields
    return run("cart_checkout.item.add", data)
