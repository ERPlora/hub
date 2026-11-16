"""Fixtures of the modifier tests: contexts per role and scope, and the real Inventory and Taxes rows a group is linked
to (no doubles).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

The models are imported lazily, so that the tests of apps.py still collect while models.py does not exist.
"""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.flow.tests.test_relay import heard, listen, worker_loop
from apps.inventory.tests.test_relay import tick
from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import db_dsn, make_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, factory_data, factory_data_b, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host and the raw DSN of
#: control's database as Sales makes them, the assistant's catalogue of a person of business A, a session that hears the
#: notices of a scope, and one tick of the worker's real loop over every business with the factory data planted again
#: (Inventory's, on Automations' loop), that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "factory_data", "factory_data_b", "heard",
    "hub_staff", "in_business_a", "listen", "make_user", "plan_with_room", "tick", "worker_loop",
]

#: A tax category of Taxes' Spanish factory catalogue (migration tax.0002): restaurant food, 10 %.
FOOD = "restaurant.food"
#: The general one (21 %): what a bottled soft drink pays.
GENERIC = "product.generic"


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, the source language: a request in Spanish activates it and
    Django's LocaleMiddleware leaves it active in the thread for the tests that follow."""
    with translation.override("en"):
        yield


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    return OperationContext(
        scope=scope,
        actor=actor,
        permissions=permissions_for_role(all_live_app_configs(), role),
        language=language,
    )


def ctx_with(
    *permissions: str, scope: Scope = A, actor: str = "tester"
) -> OperationContext:
    """A context holding exactly ``permissions`` (a custom role or an API key with a chosen scope)."""
    return OperationContext(
        scope=scope, actor=actor, permissions=frozenset(permissions)
    )


def run(
    name: str,
    data: dict | None = None,
    role: str = "hub_admin",
    ctx: OperationContext | None = None,
):
    """Runs the operation ``name`` with ``data`` validated by its own input, as a route would."""
    op = get(name)
    return op(ctx or ctx_for(role), op.input.model_validate(data or {}))


def make_product(
    name: str = "Burger",
    sku: str = "BUR",
    price: int = 800,
    tax: str | None = FOOD,
    **fields,
):
    """A product of the real Inventory app, made through its own operation."""
    data = {"name": name, "sku": sku, "price": price, **fields}
    if tax:
        data["tax_category_key"] = tax
    return run("inventory.product.create", data)


def make_category(name: str = "Mains"):
    """A category of the real Inventory app, made through its own operation."""
    return run("inventory.category.create", {"name": name})
