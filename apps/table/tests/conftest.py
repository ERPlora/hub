"""Fixtures of the table tests: contexts per role and scope, users with a role on a host, a raw DSN, and
builders of the data a test starts from.

The room (zones, tables, holds) is built straight on the models: the operations are under test. The
checks of Sales and the cards of Customers are made by their own apps' operations, never by hand: the
integration with ``sale`` and ``customer`` is tested as it runs (no mocks). The builders import the
models lazily, so the tests of apps.py still collect while models.py does not exist.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    language: str = "en",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (owner and admin: every declared permission,
    as base.permissions; the others what each app's ``role_permissions`` gives them)."""
    configs = all_live_app_configs()
    if permissions is None:
        if role in ("hub_owner", "hub_admin"):
            permissions = {p for config in configs for p in config.permissions}
        else:
            permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


#: A fixed instant for the tests that read the business's «today»: noon in Madrid (10:00 UTC, summer time).
NOON = dt.datetime(2026, 10, 14, 10, 0, tzinfo=dt.UTC)


def pin_clock(monkeypatch, instant: dt.datetime) -> None:
    """Pins Django's clock (``django.utils.timezone.now``, what the app calls «now») to ``instant``."""
    monkeypatch.setattr("django.utils.timezone.now", lambda: instant)


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


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


# ── Builders of the room ─────────────────────────────────────────────────────────────────────────


def make_zone(name: str = "Dining room", **fields):
    from apps.table.models import Zone

    return Zone.objects.create(name=name, **fields)


def make_table(number: str = "1", zone=None, **fields):
    from apps.table.models import Table

    return Table.objects.create(number=number, zone=zone, **fields)


def make_session(
    table, *, order_id=None, guests_count: int = 2, minutes_ago: int = 0, **fields
):
    """An open check seated at ``table`` ``minutes_ago`` minutes ago, with its first history segment."""
    from apps.table.models import SessionMove, TableSession

    opened = timezone.now() - dt.timedelta(minutes=minutes_ago)
    session = TableSession.objects.create(
        table=table,
        order_id=order_id,
        guests_count=guests_count,
        opened_at=opened,
        **fields,
    )
    if session.table_id and session.status == TableSession.Status.OPEN:
        SessionMove.objects.create(
            session=session, table=table, assigned_at=opened, assignment_reason="opened"
        )
    return session


def make_hold(
    table, *, starts_in: int = 30, lasts: int = 120, ref: str = "r-1", **fields
):
    """A hold on ``table`` starting ``starts_in`` minutes from now and lasting ``lasts`` minutes."""
    from apps.table.models import Hold

    start = timezone.now() + dt.timedelta(minutes=starts_in)
    fields.setdefault("source", "manual")
    return Hold.objects.create(
        table=table,
        source_ref=ref,
        held_from=start,
        held_until=start + dt.timedelta(minutes=lasts),
        **fields,
    )


# ── Sales and Customers, by their own operations ─────────────────────────────────────────────────


def open_check(label: str = "", ctx=None, **more):
    """An open check of Sales, opened by Sales."""
    return run("sale.order.open", {"label": label, **more}, ctx or system_context(A))


def make_customer(name: str = "Ana García", **more):
    """A customer card, made by Customers."""
    return run("customer.customer.create", {"name": name, **more}, system_context(A))


@pytest.fixture
def product(db):
    """``product(name, sku, price, tax_category_key)``: a product of Inventory, to put lines on a check."""

    def make(
        name: str = "Coffee",
        sku: str = "COF",
        price: int = 150,
        tax_category_key: str = "restaurant.drink",
    ):
        data = {
            "name": name,
            "sku": sku,
            "price": price,
            "tax_category_key": tax_category_key,
        }
        return run("inventory.product.create", data, system_context(A))

    return make


def add_line(order_id, product, quantity: str = "1", ctx=None):
    """A line of ``product`` on the open check ``order_id``, added by Sales."""
    data = {
        "order_id": str(order_id),
        "product_id": str(product.id),
        "quantity": quantity,
    }
    return run("sale.order.add_line", data, ctx or system_context(A))


def charge(order_id, *, key: str, line_ids=(), ctx=None):
    """Charges the check (or some of its lines) by card, through Sales."""
    data = {
        "idempotency_key": f"table-test-{key}",
        "order_id": str(order_id),
        "line_ids": [str(line) for line in line_ids],
        "payments": [{"method": "card"}],
    }
    return run("sale.sale.complete", data, ctx or ctx_for())
