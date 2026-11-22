"""Fixtures of the tax tests: contexts per role and scope, users with a role on a host, a raw DSN, and the helpers
the tests of the tax reads share.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it, with its
own factory catalogue; a test of B asks for ``hub_b`` and enters it.
"""

import datetime as dt
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from apps.invoice.tests.conftest import catalog_of, in_hubs
from apps.tax import queries
from apps.tax.models import TaxAlias, TaxCategory, TaxRule
from apps.tax.schemas import AliasListIn, AliasResolveIn, CalculateIn, CategoryListIn, RuleListIn
from base.models import Membership
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, factory_data, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases (the platform staff with business A chosen in the Hub
#: admin, business A on a plan with room for several sessions, its factory catalogue planted again in a committed test,
#: the assistant's catalogue of a person of A) that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "factory_data", "hub_staff", "in_business_a", "in_hubs",
    "plan_with_room",
]


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


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test (LocaleMiddleware) may have left
    another language active in this thread, and the messages are read in the active language."""
    with translation.override("en"):
        yield


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = A.key,
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


def empty_tax_tables():
    """The factory catalogue (migrations 0002 and 0005) removed from the business at work."""
    TaxAlias.objects.all().delete()
    TaxRule.objects.filter(parent__isnull=False).delete()
    TaxRule.objects.all().delete()
    TaxCategory.objects.all().delete()


def turn_the_rate_at_midnight(category) -> None:
    """``category``'s rate in Spain changes at the turn of the night: 10 % until 2 November 2026, 21 % from the 3rd."""
    TaxRule.objects.filter(category=category).delete()
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="10", valid_to=dt.date(2026, 11, 2))
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="21", valid_from=dt.date(2026, 11, 3))


@pytest.fixture
def no_seed(db):
    """Start from empty tax tables in business A."""
    empty_tax_tables()


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of control's test database, where the live notices go after the COMMIT, for raw psycopg sessions."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


TODAY = date(2026, 6, 27)


def run(name, data, role="hub_admin", language="en"):
    return get(name)(ctx_for(role, language=language), data)


def category(key="product.generic", name=None, system=False, description=""):
    return TaxCategory.objects.create(
        key=key, name=name or key, is_system=system, description=description
    )


def rule(cat, rate="21", country="ES", region="", **fields):
    return TaxRule.objects.create(
        category=cat,
        country_code=country,
        region_code=region,
        rate_pct=Decimal(rate),
        **fields,
    )


def resolve(key="product.generic", country="ES", region=None, on=TODAY):
    return queries.resolve_tax(
        category_key=key, country_code=country, region_code=region, on=on
    )


def calculate(role="hub_admin", **params):
    return run("tax.rate.calculate", CalculateIn(**params), role=role)


def categories(language="en", **params):
    return run("tax.category.list", CategoryListIn(**params), language=language)


def rules(language="en", **params):
    return run("tax.rule.list", RuleListIn(**params), language=language)


def aliases(**params):
    return run("tax.alias.list", AliasListIn(**params))


def resolved(text, language="en"):
    out = run("tax.alias.resolve", AliasResolveIn(text=text), language=language)
    return (out.text, out.tax_category_key, out.matched_by)


def food_and_book_aliases():
    """A shipped and a learned alias of restaurant.food and a learned one of product.books.

    Returns the books category, for a test that adds one more alias of its own.
    """
    food, books = category("restaurant.food"), category("product.books")
    TaxAlias.objects.create(alias="meal", category=food, source="shipped")
    TaxAlias.objects.create(alias="comida casera", category=food)
    TaxAlias.objects.create(alias="libros", category=books)
    return books
