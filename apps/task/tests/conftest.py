"""Fixtures of the task tests: contexts per role and scope, users with a role on a host (and a staff
record of their own), a raw DSN, and builders of the data a test starts from (straight to the models:
the operations are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership
from base.services import ensure_hub_user

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``actor`` is a user for the operations that look at the caller's own tasks; ``permissions``
    replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def today():
    """The business day the test runs on, taken when it runs as the operations take it: a date taken at import
    is the day of the collection, and a run that crosses midnight would compare it with the next one
    (``tests/test_guardrails.py``, ``clock_at_import``)."""
    return timezone.localdate()


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
        first_name: str = "",
        last_name: str = "",
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", first_name=first_name, last_name=last_name
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        # Who they are in the business's database, as their entry makes it: what a task names.
        user.person = ensure_hub_user(user)
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


def make_member(first_name: str = "Ana", last_name: str = "López", **fields):
    from apps.staff.models import Member

    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def make_project(code: str = "opening", name: str = "Opening", **fields):
    from apps.task.models import Project

    return Project.objects.create(code=code, name=name, **fields)


_numbers = iter(range(1, 1_000_000))


def make_task(title: str = "Clean the store room", **fields):
    """A task straight in the table, with a made-up number unless given."""
    from apps.task.models import Task

    fields.setdefault("number", f"TSK-20260101-{next(_numbers):04d}")
    return Task.objects.create(title=title, **fields)


def make_comment(task, text: str = "On it", **fields):
    from apps.task.models import Comment

    return Comment.objects.create(task=task, text=text, **fields)
