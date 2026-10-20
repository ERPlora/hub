"""Fixtures of the customer tests: contexts per role and scope, users with a role on a host, a raw DSN, and the
Hub admin's «Delete» of a card landing in the middle of another app's write."""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client
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


# ── The Hub admin's «Delete» of a card in the middle of a write that links it ──────────────────────
#
# Another app's write finds a card and then writes the row that points at it (an appointment, a sale, a
# reservation, a conversation…). These run the platform staff's «Delete» of that card right before a given
# statement of the write, in another session, as staff/tests/conftest.py does for a professional.

#: How long a write lets the deletion run until it waits for what the write holds (or ends).
DELETION_WAIT = 10


def _waited_for() -> bool:
    """Whether another session waits for a lock this one holds."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pg_backend_pid() = ANY (pg_blocking_pids(pid)))"
        )
        return cursor.fetchone()[0]


def reads(table: str) -> Callable[[str], bool]:
    """Whether a statement reads rows of ``table``."""
    return lambda sql: sql.lstrip().startswith("SELECT") and f'FROM "{table}"' in sql


def writes(table: str) -> Callable[[str], bool]:
    """Whether a statement inserts or updates rows of ``table``."""
    return lambda sql: sql.lstrip().startswith((f'INSERT INTO "{table}"', f'UPDATE "{table}"'))


@contextmanager
def card_deleted_on_screen(card, how: str, before: Callable[[str], bool]):
    """The platform staff delete the customer ``card`` in the Hub admin, from its delete page (``page``) or
    with the list's «Delete selected» (``list``), in another session started right before the first statement
    of this one for which ``before`` holds; this one goes on once the deletion waits for what it holds (or
    has ended). Yields the answers they got (a 500 is the error raised)."""
    staff = get_user_model().objects.create_superuser(
        username="card-deleter", password="pw", email="card-deleter@example.com"
    )
    client = Client()
    client.force_login(staff)
    if how == "page":
        url, data = f"/admin/customer/customer/{card.pk}/delete/", {"post": "yes"}
    else:
        url, data = "/admin/customer/customer/", {
            "action": "delete_selected",
            "_selected_action": [str(card.pk)],
            "post": "yes",
        }
    answers: list = []

    def deletion():
        try:
            answers.append(
                client.post(url, data, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en")
            )
        except Exception as error:  # a 500, reported to the test
            answers.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and before(sql):
            thread.start()
            deadline = time.monotonic() + DELETION_WAIT
            while thread.is_alive() and not _waited_for() and time.monotonic() < deadline:
                time.sleep(0.02)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield answers
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "the deletion never started"


def cannot_delete(answer) -> bool:
    """Whether the Hub admin answered «Cannot delete customer»: something protects the card."""
    assert not isinstance(answer, Exception), answer
    return answer.status_code == 200 and str(answer.context["title"]) == "Cannot delete customer"
