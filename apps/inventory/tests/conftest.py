"""Fixtures of the inventory tests: contexts per role and scope, users with a role on a host, a raw DSN, and what the
tests of the reads share (running a read, a product, a movement, reading an export).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.
"""

import csv
import io

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from apps.flow.tests.test_relay import worker_loop
from apps.inventory.models import Product, ProductCategory, StockMovement
from apps.invoice.tests.conftest import catalog_of
from apps.tax.models import TaxCategory
from base.models import Membership
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, factory_data, factory_data_b, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, the assistant's catalogue of a person of business
#: A and the worker's real pass over every business, that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "factory_data", "factory_data_b", "hub_staff",
    "in_business_a", "plan_with_room", "worker_loop",
]


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English, the source language: a request in Spanish activates it and
    Django's LocaleMiddleware leaves it active in the thread for the tests that follow."""
    with translation.override("en"):
        yield


def ctx_for(role: str = "hub_admin", scope: Scope = A, actor: str = "tester") -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    return OperationContext(scope=scope, actor=actor, permissions=permissions_for_role(all_live_app_configs(), role))


def ctx_with(*permissions: str, scope: Scope = A, actor: str = "tester") -> OperationContext:
    """A context holding exactly ``permissions`` (a custom role or an API key with a chosen scope)."""
    return OperationContext(scope=scope, actor=actor, permissions=frozenset(permissions))


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = A.key, role: str = Membership.Role.ADMIN):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (LISTEN, or reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


def run(name, data, role="hub_admin"):
    return get(name)(ctx_for(role), data)


@pytest.fixture
def general(db):
    return TaxCategory.objects.create(key="product.general", name="Product — general")


def product(name, sku=None, *, tax=None, **fields):
    return Product.objects.create(
        name=name, sku=sku or name.upper(), tax_category=tax, **{"price": 100, **fields}
    )


def link(product, category):
    ProductCategory.objects.create(product=product, category=category)


def names(page):
    return [row.name for row in page.rows]


def movement(prod, movement_type, qty, stock_after, **fields):
    return StockMovement.objects.create(
        product=prod,
        movement_type=movement_type,
        qty=qty,
        stock_after=stock_after,
        **fields,
    )


def read_csv(export, delimiter):
    assert export.content.startswith("\ufeff")  # Excel reads it as UTF-8
    return list(csv.reader(io.StringIO(export.content[1:]), delimiter=delimiter))
