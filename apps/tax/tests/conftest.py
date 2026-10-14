"""Fixtures of the tax tests: contexts per role and scope, users with a role on a host, a raw DSN."""

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
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def no_seed(db):
    """Start from empty tax tables: the factory catalogue (migration 0002) is removed for this test.

    Imported lazily so that the tests of apps.py still collect while models.py does not exist.
    """
    from apps.tax.models import TaxAlias, TaxCategory, TaxRule

    TaxAlias.objects.all().delete()
    TaxRule.objects.filter(parent__isnull=False).delete()
    TaxRule.objects.all().delete()
    TaxCategory.objects.all().delete()


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
