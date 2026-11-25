"""Fixtures of the task tests: contexts per role and scope, users with a role on a host (and a staff
record of their own), a raw DSN, and builders of the data a test starts from (straight to the models:
the operations are under test).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it.

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from apps.flow.tests.test_relay import worker_loop
from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import db_dsn
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases (the platform staff with business A chosen in the Hub
#: admin, business A on a plan with room for several sessions, the worker's real loop over them, the raw DSN of control
#: where the live notices go, the assistant's catalogue of a person of business A) that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "hub_staff", "in_business_a", "plan_with_room",
    "worker_loop",
]


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
        host: str | None = A.key,
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
def team(make_user):
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    worker = make_user("bea", role="hub_employee", first_name="Bea", last_name="Ruiz")
    return {
        "boss": boss,
        "worker": worker,
        "boss_member": make_member("Marta", "Jefa", user=boss.person),
        "worker_member": make_member("Bea", "Ruiz", user=worker.person),
        "ana": make_member("Ana", "López"),
    }


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
