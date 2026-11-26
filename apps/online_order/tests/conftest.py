"""Fixtures of the online order tests: contexts per role and scope, and the room they start from.

The tables are made straight on Tables' models (``make_zone``, ``make_table``), as Tables' own tests make them: what is
under test is this app's operations, which read the tables through Tables' operations.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

import pytest
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.combo.tests.conftest import make_product
from apps.flow.tests.test_relay import listen
from apps.sale.tests.conftest import db_dsn, make_user
from apps.table.tests.conftest import make_table, make_zone
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a

PUBLIC = "online_order.public"

__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "db_dsn", "in_business_a", "listen", "make_table", "make_user",
    "make_zone",
]


def ctx_for(
    role: str | None = "hub_admin",
    scope: Scope = A,
    *,
    permissions: set[str] | None = None,
    request=None,
) -> OperationContext:
    """The context a person with ``role`` on ``scope`` gets (owner and admin: every declared permission, as
    base.permissions; the others what each app's ``role_permissions`` gives them), or exactly ``permissions``."""
    configs = all_live_app_configs()
    if permissions is None:
        if role in ("hub_owner", "hub_admin"):
            permissions = {permission for config in configs for permission in config.permissions}
        else:
            permissions = permissions_for_role(configs, role) if role else set()
    return OperationContext(scope=scope, actor="tester", permissions=frozenset(permissions), request=request)


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input, validated as a route would."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def visitor():
    """Nobody signed in, holding the page's permission and nothing more, as the door runs it."""
    return ctx_for(None, permissions={PUBLIC})


def regenerate(table, scope=A) -> str:
    return run("online_order.qr_code.regenerate", {"id": str(table.id)}, ctx_for(scope=scope)).code


@pytest.fixture
def table_code() -> str:
    return regenerate(make_table("4", make_zone("Terrace")))


@pytest.fixture
def dishes():
    from apps.inventory.models import Category, ProductCategory

    starters = Category.objects.create(name="Starters", slug="starters", order=0)
    drinks = Category.objects.create(name="Drinks", slug="drinks", order=1)
    croquettes = make_product(
        "Croquettes", price=750, sku="CRO", cost=200, description="Six, of ham", allergens=["gluten", "milk"]
    )
    cola = make_product("Cola", price=250, sku="COLA", cost=90)
    staff_meal = make_product("Staff meal", price=500, sku="STAFF", show_on_website=False)
    gone = make_product("Gone", price=100, sku="GONE", is_sold_out=True)
    ProductCategory.objects.create(product=croquettes, category=starters)
    ProductCategory.objects.create(product=cola, category=drinks)
    ProductCategory.objects.create(product=staff_meal, category=starters)
    ProductCategory.objects.create(product=gone, category=starters)
    return {"croquettes": croquettes, "cola": cola, "staff_meal": staff_meal, "gone": gone}
