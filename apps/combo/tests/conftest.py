"""Fixtures of the combo tests: contexts per role and scope, and builders of the data a test starts from (straight to
the models: the operations are under test).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

The components of a menu are real products of the Inventory app and its tax category a real category
of the Taxes app (the two ``requires``): no doubles. The builders import the models lazily, so that
the tests of apps.py still collect while models.py does not exist.
"""

import psycopg
import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from live.outbox import channel_for

from apps.flow.tests.test_relay import worker_loop
from apps.invoice.tests.conftest import catalog_of
from apps.inventory.tests.test_relay import tick
from apps.sale.tests.conftest import db_dsn, make_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, factory_data, factory_data_b, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host and the raw DSN of
#: control's database as Sales makes them, the assistant's catalogue of a person of business A, and one tick of the
#: worker's real loop over every business with the factory data planted again (Inventory's, on Automations' loop), that
#: these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "factory_data", "factory_data_b", "hub_staff",
    "in_business_a", "make_user", "plan_with_room", "tick", "worker_loop",
]

#: Factory categories of the Taxes app (its migration 0002): 10 % on the premises, 21 % to take away.
FOOD = "restaurant.food"
DRINK = "restaurant.drink"
ALCOHOL_TO_GO = "retail.alcohol"
#: A restaurant's beer or wine: 10 % served on the premises, retail.alcohol (21 %) to take away.
ALCOHOL = "restaurant.alcohol"
GENERIC = "product.generic"


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(
        scope=scope, actor=actor, permissions=frozenset(permissions)
    )


def run(name: str, data: dict, ctx: OperationContext | None = None):
    """Runs the operation ``name`` as its route does: the input validated, then the operation."""
    op = get(name)
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate(data))


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def listen(db_dsn):
    """``listen(scope)``: a raw session LISTENing on the channel of ``scope``; it hears only what is committed."""
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


# Builders


def tax_category(key: str = FOOD):
    """A category of the Taxes app (the factory one when it exists)."""
    from apps.tax.models import TaxCategory

    return TaxCategory.objects.get_or_create(key=key, defaults={"name": key})[0]


_skus = iter(range(1, 1_000_000))


def make_product(
    name: str = "Lentils", *, price: int = 500, tax: str | None = FOOD, **fields
):
    """A product of the Inventory app, active and sold by units unless told otherwise."""
    from apps.inventory.models import Product

    fields.setdefault("sku", f"P{next(_skus):05d}")
    return Product.objects.create(
        name=name,
        price=price,
        tax_category=tax_category(tax) if tax else None,
        **fields,
    )


def make_combo(name: str = "Menu of the day", *, price: int = 1350, **fields):
    """A menu eaten in at the food category unless told otherwise."""
    from apps.combo.models import Combo

    fields.setdefault("supply_kind", "service")
    if fields["supply_kind"] == "service":
        fields.setdefault("tax_category", tax_category(FOOD))
    return Combo.objects.create(name=name, price=price, **fields)


def make_group(combo, name: str = "Starters", **fields):
    from apps.combo.models import ChoiceGroup

    fields.setdefault("sort_order", combo.groups.count())
    return ChoiceGroup.objects.create(combo=combo, name=name, **fields)


def make_option(group, product, **fields):
    from apps.combo.models import ChoiceOption

    fields.setdefault("sort_order", group.options.count())
    return ChoiceOption.objects.create(group=group, product=product, **fields)
