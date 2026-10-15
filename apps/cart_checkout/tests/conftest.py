"""Fixtures of the cart_checkout tests: contexts per role and scope, users with a role on a host, a raw
DSN, a fixed clock, and builders of the data a test starts from (straight to the models: the operations
are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py does
not exist.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")

#: The moment every test lives in (no real clock): 14 October 2026, 10:00 in Madrid.
NOW = dt.datetime(2026, 10, 14, 8, 0, tzinfo=dt.UTC)


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


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


# Builders


def make_cart(session_token: str = "sess_a1b2c3", **fields):
    from apps.cart_checkout.models import Cart

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

    return Order.objects.create(
        cart=cart or make_cart(),
        order_number=order_number,
        customer_email=customer_email,
        total_amount=total_amount,
        **fields,
    )
