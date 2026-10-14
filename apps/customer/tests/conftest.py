"""Fixtures of the customer tests: contexts per role and scope, users with a role on a host, a raw DSN."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership
from base.permissions import FULL_ACCESS_ROLES

A = Scope("host", "a")
B = Scope("host", "b")


@pytest.fixture(autouse=True)
def english():
    """These tests read the app's messages in English, the source language.

    A request of another suite with ``Accept-Language: es`` leaves Spanish active in the thread
    (LocaleMiddleware activates it and nothing deactivates it), so each test starts in English.
    """
    with translation.override("en"):
        yield


def ctx_for(
    role: str = "hub_admin", scope: Scope = A, actor: str = "tester"
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets, as ``base.permissions`` computes it.

    Owner and admin get every permission every app declares; the other roles, what each app's
    ``role_permissions`` gives them.
    """
    configs = all_live_app_configs()
    if role in FULL_ACCESS_ROLES:
        permissions = frozenset(
            permission for config in configs for permission in config.permissions
        )
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


def run(
    name: str, data, role: str = "hub_admin", scope: Scope = A, actor: str = "tester"
):
    """Run the operation ``name`` as ``role`` on ``scope``."""
    return get(name)(ctx_for(role, scope, actor), data)


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
    """DSN of the test database, for raw psycopg sessions (LISTEN, or reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
