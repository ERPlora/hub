"""Fixtures of the pricing tests: contexts per role and scope, users with a role on a host, a raw DSN,
and builders of the data a test starts from (straight to the models: the operations are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist. Products, categories and customer groups are Inventory's and Customers' own rows (the
apps Pricing requires); a service is Services' row, read by its operations.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")

#: A fixed business day: the tests never read the real clock.
TODAY = dt.date(2026, 7, 15)


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
    language: str = "en",
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language=language)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """The business's today is ``TODAY`` (``queries.business_today``), whatever the real date."""
    try:
        import apps.pricing.queries as queries
    except ModuleNotFoundError:  # the tests of models.py and apps.py run before queries.py exists
        return TODAY
    monkeypatch.setattr(queries, "business_today", lambda: TODAY)
    return TODAY


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.ADMIN):
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


@pytest.fixture
def no_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database (the tests
    with the hubs ``hub_a`` and ``hub_b`` of the root conftest, each with its own database)."""
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


# Builders: other apps' rows


def make_product(name: str = "Shampoo", sku: str | None = None, price: int = 1200, **fields):
    from apps.inventory.models import Product

    return Product.objects.create(name=name, sku=sku or name.upper()[:12], price=price, **fields)


def make_category(name: str = "Hair care", **fields):
    from apps.inventory.models import Category

    return Category.objects.create(name=name, **fields)


def categorize(product, category):
    from apps.inventory.models import ProductCategory

    return ProductCategory.objects.create(product=product, category=category)


def make_group(name: str = "VIP", **fields):
    from apps.customer.models import CustomerGroup

    return CustomerGroup.objects.create(name=name, **fields)


def make_customer(name: str = "Lucía Pérez", groups=(), **fields):
    from apps.customer.models import Customer

    customer = Customer.objects.create(name=name, **fields)
    customer.groups.set(groups)
    return customer


def make_service(name: str = "Haircut", price: int = 1800, **fields):
    from apps.service.models import Service

    fields.setdefault("pricing_type", "fixed")
    return Service.objects.create(name=name, price=price, **fields)


# Builders: this app's rows


def make_list(code: str = "VIP", name: str | None = None, **fields):
    from apps.pricing.models import PriceList

    return PriceList.objects.create(code=code, name=name or f"{code} prices", **fields)


def make_item(price_list, product=None, price: int = 1000, min_quantity: str = "1", **fields):
    from apps.pricing.models import PriceItem

    return PriceItem.objects.create(
        price_list=price_list, product=product, price=price, min_quantity=Decimal(min_quantity), **fields
    )


def make_rule(code: str = "TEN", rule_type: str = "percent", **fields):
    from apps.pricing.models import DiscountRule

    fields.setdefault("name", f"Rule {code}")
    if rule_type == "percent":
        fields.setdefault("percent", Decimal("10"))
    return DiscountRule.objects.create(code=code, rule_type=rule_type, **fields)
