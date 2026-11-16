"""Fixtures of the tax tests: contexts per role and scope, users with a role on a host, a raw DSN.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it, with its
own factory catalogue; a test of B asks for ``hub_b`` and enters it.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from apps.invoice.tests.conftest import catalog_of, in_hubs
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
    """The factory catalogue (migrations 0002 and 0005) removed from the business at work.

    Imported lazily so that the tests of apps.py still collect while models.py does not exist.
    """
    from apps.tax.models import TaxAlias, TaxCategory, TaxRule

    TaxAlias.objects.all().delete()
    TaxRule.objects.filter(parent__isnull=False).delete()
    TaxRule.objects.all().delete()
    TaxCategory.objects.all().delete()


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
