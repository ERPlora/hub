"""Fixtures of the kitchen tests: contexts per role, a pinned clock, and builders of the data a test
starts from.

Stations and routes are built straight on the models (the operations are under test). The checks of
Sales, their lines and their rounds, and the products and categories of Inventory, are made by their
own apps' operations, never by hand: the integration with ``sale`` and ``inventory`` is tested as it
runs (no mocks). The builders import the models lazily, so the tests of apps.py still collect while
models.py does not exist.
"""

import datetime as dt

import pytest
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

A = Scope("host", "a")
B = Scope("host", "b")

#: A fixed instant: 13:00 in Madrid (11:00 UTC, summer time) on 2026-10-14.
NOON = dt.datetime(2026, 10, 14, 11, 0, tzinfo=dt.UTC)


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    language: str = "en",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (owner and admin: every declared permission;
    the others what each app's ``role_permissions`` gives them)."""
    configs = all_live_app_configs()
    if permissions is None:
        if role in ("hub_owner", "hub_admin"):
            permissions = {p for config in configs for p in config.permissions}
        else:
            permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


class Clock:
    """Django's clock (``timezone.now``) pinned to an instant that a test moves forward by hand."""

    def __init__(self, monkeypatch, instant: dt.datetime):
        self.now = instant
        monkeypatch.setattr("django.utils.timezone.now", lambda: self.now)

    def advance(self, **delta) -> dt.datetime:
        self.now = self.now + dt.timedelta(**delta)
        return self.now


@pytest.fixture
def clock(monkeypatch):
    """The clock pinned at ``NOON``; ``clock.advance(minutes=5)`` moves it."""
    return Clock(monkeypatch, NOON)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def receives_everything(request):
    """The kitchen receives what was fired since its tables exist (``receiving_since``, set by its
    migration at the real time): a test with a pinned clock moves that moment back so its rounds count."""
    marker = request.node.get_closest_marker("django_db")
    transactional = "transactional_db" in request.fixturenames or bool(
        marker and marker.kwargs.get("transaction")
    )
    if transactional:
        request.getfixturevalue("transactional_db")
    elif marker or "db" in request.fixturenames:
        request.getfixturevalue("db")
    else:
        yield
        return
    from apps.kitchen.models import KitchenSettings

    KitchenSettings.objects.update(
        receiving_since=dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    )
    yield


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = "hub_admin"):
        from django.contrib.auth import get_user_model

        from base.models import Membership

        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (a real LISTEN sees only what is committed)."""
    from django.db import connections
    from psycopg.conninfo import make_conninfo

    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


# ── Builders of the kitchen ──────────────────────────────────────────────────────────────────────


def make_station(name: str = "Grill", **fields):
    from apps.kitchen.models import Station

    return Station.objects.create(name=name, **fields)


def route_product(product_id, station):
    from apps.kitchen.models import ProductRoute

    return ProductRoute.objects.create(product_id=product_id, station=station)


def route_category(category_id, station):
    from apps.kitchen.models import CategoryRoute

    return CategoryRoute.objects.create(category_id=category_id, station=station)


# ── Sales and Inventory, by their own operations ─────────────────────────────────────────────────


@pytest.fixture
def product(db):
    """``product(name, sku, price, category_ids=…)``: a product of Inventory, to put lines on a check."""

    def make(
        name: str = "Burger",
        sku: str | None = None,
        price: int = 1200,
        tax_category_key: str = "restaurant.food",
        **more,
    ):
        data = {
            "name": name,
            "sku": sku or name.upper().replace(" ", "-")[:20],
            "price": price,
            "tax_category_key": tax_category_key,
            **more,
        }
        return run("inventory.product.create", data, system_context(A))

    return make


@pytest.fixture
def category(db):
    """``category(name)``: a category of Inventory."""

    def make(name: str = "Mains"):
        return run("inventory.category.create", {"name": name}, system_context(A))

    return make


def open_check(label: str = "", ctx=None, **more):
    """An open check of Sales, opened by Sales."""
    return run("sale.order.open", {"label": label, **more}, ctx or system_context(A))


def add_line(order_id, product, quantity: str = "1", ctx=None, **more):
    """A line of ``product`` on the open check ``order_id``, added by Sales (by the waiter who sends it)."""
    data = {
        "order_id": str(order_id),
        "product_id": str(product.id),
        "quantity": quantity,
        **more,
    }
    return run("sale.order.add_line", data, ctx or ctx_for(actor="waiter"))


def fire(order_id, ctx=None, **more):
    """Sends the check's pending lines to the kitchen, by Sales."""
    return run(
        "sale.order.fire",
        {"order_id": str(order_id), **more},
        ctx or ctx_for(actor="waiter"),
    )


def charge(order_id, *, key: str, line_ids=(), ctx=None):
    """Charges the check (or some of its lines) by card, through Sales."""
    data = {
        "idempotency_key": f"kitchen-test-{key}",
        "order_id": str(order_id),
        "line_ids": [str(line) for line in line_ids],
        "payments": [{"method": "card"}],
    }
    return run("sale.sale.complete", data, ctx or ctx_for())


def fired_round(
    product, *names, label: str = "Table 4", quantity: str = "1", **fire_more
):
    """A check titled ``label`` with one line per product name (made by ``product``), fired once.
    Returns ``(order, lines)``: the check after firing and its lines in order."""
    order = open_check(label)
    for name in names or ("Burger",):
        add_line(order.id, product(name), quantity)
    fired = fire(order.id, **fire_more)
    return fired.order, list(fired.order.lines)


def now() -> dt.datetime:
    return timezone.now()
