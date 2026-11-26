"""Fixtures of the pricing tests: contexts per role and scope, users with a role on a host, a raw DSN,
and builders of the data a test starts from (straight to the models: the operations are under test).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist. Products, categories and customer groups are Inventory's and Customers' own rows (the
apps Pricing requires); a service is Services' row, read by its operations.
"""

import datetime as dt
from decimal import Decimal

import psycopg
import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.outbox import channel_for

from apps.flow.tests.test_relay import worker_loop
from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import db_dsn, make_user, night_elsewhere
from apps.sale.tests.test_business_currency import platform
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, users with a role on a host, the raw DSN of
#: control's database, business A at night in another zone and ERPlora's own hub (business B's) as Sales makes them,
#: the assistant's catalogue of a person of business A, and one tick of the worker's real loop over every business as
#: Automations runs it, that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "hub_staff", "in_business_a", "make_user",
    "night_elsewhere", "plan_with_room", "platform", "worker_loop",
]

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
    """The business's today is ``TODAY`` (``queries.resolution.business_today``), whatever the real date."""
    try:
        import apps.pricing.queries.resolution as resolution
    except ModuleNotFoundError:  # the tests of models.py and apps.py run before the queries package exists
        return TODAY
    monkeypatch.setattr(resolution, "business_today", lambda: TODAY)
    return TODAY


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
    from apps.service.models.catalog import Service

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
