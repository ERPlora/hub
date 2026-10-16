"""Fixtures of the attendance tests: contexts per role and scope, users with a role on a host, staff
members linked to them (the real staff app, never a double), a frozen clock and a raw DSN."""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from apps.staff.models import Member
from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``actor`` is the user who clocks; ``permissions`` replaces the role's for a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


def run(name: str, data, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` (a dict or its input schema) as ``ctx`` (an admin by default)."""
    op = get(name)
    payload = (
        data if isinstance(data, op.input) else op.input.model_validate(data or {})
    )
    return op(ctx or ctx_for(), payload)


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
        role: str = Membership.Role.EMPLOYEE,
        first_name: str = "",
        last_name: str = "",
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", first_name=first_name, last_name=last_name
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


def make_member(first_name: str = "Ana", last_name: str = "López", **fields) -> Member:
    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


@pytest.fixture
def person(make_user):
    """A user with a staff record linked to it, and that user's context: who clocks in the tests."""

    def make(
        first_name: str = "Ana",
        last_name: str = "López",
        *,
        role: str = Membership.Role.EMPLOYEE,
        scope: Scope = A,
        **member_fields,
    ):
        user = make_user(
            f"{first_name.lower()}.{last_name.lower()}",
            host=scope.key,
            role=role,
            first_name=first_name,
            last_name=last_name,
        )
        member = make_member(first_name, last_name, user=user, **member_fields)
        return member, ctx_for(role, scope=scope, actor=user)

    return make


@pytest.fixture
def clock(monkeypatch):
    """Freezes ``timezone.now()`` at an instant (an aware datetime or ``"YYYY-MM-DDTHH:MM"`` in UTC)."""

    def freeze(instant):
        if isinstance(instant, str):
            instant = dt.datetime.fromisoformat(instant).replace(tzinfo=dt.UTC)
        monkeypatch.setattr(timezone, "now", lambda: instant)
        return instant

    return freeze


def utc(text: str) -> dt.datetime:
    """``"2026-10-06T08:00"`` → that instant in UTC."""
    return dt.datetime.fromisoformat(text).replace(tzinfo=dt.UTC)


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (LISTEN)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
