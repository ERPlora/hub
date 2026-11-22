"""Fixtures of the customer tests: contexts per role and scope, users with a role on a host, a raw DSN, and what
other apps' tests ask of the Hub admin's «Delete» of a card landing in the middle of their writes.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it; a test
of B asks for ``hub_b`` and enters it."""

from collections.abc import Callable

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.operations import get

from apps.invoice.tests.conftest import catalog_of, in_hubs
from apps.sale.tests.conftest import db_dsn, make_user, night_elsewhere
from base.permissions import permissions_of_role
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, the assistant's catalogue of a person of business A,
#: and what Sales' tests already make of it (its users with a role, the raw DSN of control, a night in another zone),
#: that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "hub_staff", "in_business_a", "in_hubs",
    "make_user", "night_elsewhere", "plan_with_room",
]


@pytest.fixture(autouse=True)
def english():
    """These tests read the app's messages in English, the source language.

    A request of another suite with ``Accept-Language: es`` leaves Spanish active in the thread
    (LocaleMiddleware activates it and nothing deactivates it), so each test starts in English.
    """
    with translation.override("en"):
        yield


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    permissions: set[str] | frozenset[str] | None = None,
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets, as ``base.permissions`` computes it.

    ``permissions`` replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_of_role(role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language=language)


def run(
    name: str, data, role: str = "hub_admin", scope: Scope = A, actor: str = "tester"
):
    """Run the operation ``name`` as ``role`` on ``scope``."""
    return get(name)(ctx_for(role, scope, actor), data)


# ── The Hub admin's «Delete» of a card in the middle of a write that links it ──────────────────────
#
# Another app's write finds a card and then writes the row that points at it (an appointment, a sale, a
# reservation, a conversation…). Its tests run the platform staff's «Delete» of that card right before one of these
# statements with ``meanwhile`` and ``admin_delete`` of ``base/tenancy/tests/concurrency.py``.


def reads(table: str) -> Callable[[str], bool]:
    """Whether a statement reads rows of ``table``."""
    return lambda sql: sql.lstrip().startswith("SELECT") and f'FROM "{table}"' in sql


def writes(table: str) -> Callable[[str], bool]:
    """Whether a statement inserts or updates rows of ``table``."""
    return lambda sql: sql.lstrip().startswith((f'INSERT INTO "{table}"', f'UPDATE "{table}"'))


def card_protected(answer) -> bool:
    """Whether the Hub admin answered «Cannot delete customer»: something protects the card."""
    assert not isinstance(answer, Exception), answer
    return answer.status_code == 200 and str(answer.context["title"]) == "Cannot delete customer"
