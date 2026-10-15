"""Fixtures of the invoice tests: contexts per role and scope, users with a role on a host, and the real
apps invoice works with (tax's factory catalogue, inventory's products, customer's cards, sale's charges,
refunds and voids) — made through their own operations, never by hand: no mocks.

``deliver(name)`` hands the newest ``name`` event of the outbox to Invoicing's real reaction
(``apps.invoice.events.react``), as the outbox relay will in phase 2.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")
ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (owner and admin: every declared permission)."""
    configs = all_live_app_configs()
    if role in ("hub_owner", "hub_admin"):
        permissions = frozenset(p for config in configs for p in config.permissions)
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def deliver(name: str, scope: Scope = A):
    """Hands the newest ``name`` event of the outbox to Invoicing, as the relay will."""
    from live.models import OutboxEvent

    from apps.invoice import events

    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    assert event is not None, f"no {name} in the outbox"
    return events.react(scope, event.name, event.payload)


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
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
def issuer(db):
    """The business's tax identity, set up as the owner would (Invoicing → Issuer)."""
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def product(db):
    """``product(name, sku, price, tax_category_key, **more)``: an inventory product, made by inventory."""

    def make(
        name="Shampoo",
        sku="SHA",
        price=1210,
        tax_category_key="product.generic",
        **more,
    ):
        data = {
            "name": name,
            "sku": sku,
            "price": price,
            "tax_category_key": tax_category_key,
            **more,
        }
        return run("inventory.product.create", data, system_context(A))

    return make


@pytest.fixture
def customer(db):
    """``customer(name, **more)``: a customer card, made by customer."""

    def make(name="Ana López", **more):
        return run(
            "customer.customer.create", {"name": name, **more}, system_context(A)
        )

    return make


@pytest.fixture
def charge(db):
    """``charge(key, lines, **more)``: a sale charged by card through the till's own operation."""

    def make(key="inv-sale-0001", lines=None, **more):
        data = {
            "idempotency_key": key,
            "lines": lines if lines is not None else [{"product": "SHA"}],
            "payments": [{"method": "card"}],
            **more,
        }
        return run("sale.sale.complete", data)

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
