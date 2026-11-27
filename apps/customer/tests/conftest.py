"""Fixtures of the customer tests: contexts per role and scope, users with a role on a host, a raw DSN, a card and the
moment the reads' facts happen at, what the tests of the writes share (the outbox, a refusal as seen, a race of two
transactions…), and what other apps' tests ask of the Hub admin's «Delete» of a card landing in the middle of their
writes.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it; a test
of B asks for ``hub_b`` and enters it."""

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from django.utils import translation
from live.assistant import tool_name
from live.context import OperationContext, Scope, system_context
from live.models import OutboxEvent
from live.operations import atomic, get

from apps.customer.models import Customer, CustomFieldValue
from apps.customer.schemas.health import HealthGrantIn
from apps.invoice.tests.conftest import catalog_of, in_hubs
from apps.sale.tests.conftest import db_dsn, make_user, night_elsewhere
from base.permissions import permissions_of_role
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, in_a_thread, plan_with_room

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


def told_in_a_turn(operation: str, arguments: dict, *, ask: str, role: str = "hub_owner", yes: bool = False) -> dict:
    """What the model reads of the tool ``operation`` run with ``arguments`` in a turn of ``role`` in Spanish who asked
    ``ask``, as the chat runs it; a write, once the person says yes to its card (``yes``)."""
    call = {"call_id": "c1", "name": tool_name(operation), "arguments": json.dumps(arguments)}
    asked = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}],
    }
    messages = [{"role": "user", "content": ask}, asked]
    turn = get("base.assistant.turn")

    def answer(pending: list, decision: dict | None) -> dict:
        data = turn.input.model_validate({"messages": messages, "pending": pending, "decision": decision})
        return turn(ctx_for(role, language="es"), data).model_dump(mode="json")

    plan = answer([call], None)
    if yes:
        plan = answer(plan["pending"], {"call_id": "c1", "accepted": True})
    [result] = plan["append"]
    return json.loads(result["content"])


#: The moment the facts of the read tests happen at.
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def card(name="Ana García", **fields):
    return Customer.objects.create(name=name, **fields)


# What the tests of the writes share.


def outbox():
    return list(OutboxEvent.objects.values_list("name", "payload"))


def clear_outbox():
    OutboxEvent.objects.all().delete()


def system(name, data):
    return get(name)(system_context(A), data)


def invalid(error):
    return (
        error.status,
        error.code,
        {field: str(message) for field, message in (error.fields or {}).items()},
    )


def values(customer):
    return dict(
        CustomFieldValue.objects.filter(customer=customer).values_list(
            "field__name", "value"
        )
    )


HEALTH_WORDS = "I let this business keep my allergies and my sensitivity tests."


def grant_health(customer, actor="clara"):
    return run(
        "customer.health.grant",
        HealthGrantIn(
            customer_id=customer.id, notice_text=HEALTH_WORDS, notice_version="v1"
        ),
        "hub_employee",
        actor=actor,
    )


# Writes lock their card: two transactions at once, in two threads

#: How long the other transaction keeps its locks: long enough for this one to reach them.
HOLD = 0.5


def race(hold, attempt, then=None):
    """Runs ``attempt`` here while another thread, in a transaction, holds what ``hold`` locked.

    The other thread runs ``hold``, lets ``attempt`` start, waits ``HOLD`` seconds, runs ``then``
    (if any) and commits. ``attempt``'s result (or its exception) is this function's; the other thread's error, a
    deadlock included, fails the test.
    """
    locked = threading.Event()
    problems = [None]

    def holder():
        try:
            with atomic():
                hold()
                locked.set()
                time.sleep(HOLD)
                if then is not None:
                    then()
        finally:
            locked.set()

    thread = in_a_thread(holder, problems)
    thread.start()
    try:
        assert locked.wait(5)
        return attempt()
    finally:
        thread.join(10)
        assert problems == [None]


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
