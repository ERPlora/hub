"""Fixtures of the combo tests: contexts per role and scope, users with a role on a host, a raw DSN, and
builders of the data a test starts from (straight to the models: the operations are under test).

The components of a menu are real products of the Inventory app and its tax category a real category
of the Taxes app (the two ``requires``): no doubles. The builders import the models lazily, so that
the tests of apps.py still collect while models.py does not exist.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")

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
