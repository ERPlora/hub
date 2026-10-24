"""WHATSAPP_INBOX-F09 on the Home's bell and on the device (PLAN-HUB rounds 2026-10-21 and 2026-10-23): base's
``base.bell.counters`` shows «WhatsApp customers waiting for an answer» while an open conversation's last message is
the customer's, and leads to the inbox; at zero it is not shown. ``base.notice.list`` tells the device of each
customer left waiting (hub#2303), and whoever reads the inbox hears it, so the installed app asks to notify for a
business that only uses WhatsApp (hub#2306). Every change of the number records an event the counter is refreshed on,
and a message in hub B re-runs the bell on B's channel only.

base, Customers and the inbox run for real: the counter and the notice come from WhatsappInboxConfig through base's
own queries, never a stand-in module.
"""

import json

import psycopg
import pytest
from django.apps import apps
from live.context import OperationContext
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.tests.conftest import A, B, NOW, card, connect, ctx_for, receive, run
from base.permissions import VIEW_HOME
from base.schemas import BellCountersIn, NoticeListIn

COUNTER = {
    "key": "whatsapp_inbox.awaiting_reply",
    "app": "whatsapp_inbox",
    "route": "/whatsapp_inbox/inbox",
    "label": "WhatsApp customers waiting for an answer",
    "icon": "ion:chatbubbles-outline",
}


def bell(ctx) -> dict | None:
    """The inbox's row of the bell for the person of ``ctx``, as the SPA receives it (``None``: not shown)."""
    counters = get("base.bell.counters")(ctx, BellCountersIn()).model_dump(mode="json")["counters"]
    rows = [row for row in counters if row["app"] == "whatsapp_inbox"]
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def counted(ctx=None) -> int:
    row = bell(ctx or ctx_for("hub_employee"))
    return row["count"] if row else 0


def only(*permissions: str) -> OperationContext:
    return OperationContext(scope=A, actor="tester", permissions=frozenset({VIEW_HOME, *permissions}), language="en")


@pytest.mark.django_db
def test_a_customer_waiting_is_counted_and_leads_to_the_inbox():
    receive("wamid.1")
    assert bell(ctx_for("hub_employee")) == {**COUNTER, "count": 1}


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words():
    receive("wamid.1")
    assert bell(ctx_for("hub_admin", language="es"))["label"] == "Clientes de WhatsApp esperando respuesta"


@pytest.mark.django_db
def test_at_zero_nothing_shows_and_without_the_inbox_there_is_no_counter():
    admin = ctx_for("hub_admin")
    assert bell(admin) is None
    receive("wamid.1")
    assert bell(only()) is None
    assert bell(only("whatsapp_inbox.view")) == {**COUNTER, "count": 1}


# ── What refreshes it: every change of the number records one of its events ──────────────────────────────────────


def conversation() -> Conversation:
    return Conversation.objects.get()


def answer_from_the_hub():
    connect()
    run(
        "whatsapp_inbox.message.send",
        {"id": str(conversation().id), "text": "¡Hola!", "client_message_id": "0199e000-0000-7000-8000-0000000000f2"},
    )


def answer_from_the_phone():
    receive("wamid.echo", direction="outbound", text="Te llamo", contact_name="")


def close():
    run("whatsapp_inbox.conversation.set_status", {"id": str(conversation().id), "status": "closed"})


def erase():
    run("whatsapp_inbox.conversation.erase", {"id": str(conversation().id)})


def another_customer_writes():
    receive("wamid.2", "34600999999", contact_name="Bea")


#: Each event of the counter's ``refresh_on`` → a change of the number that records it, seen by an employee.
CHANGES = {
    "whatsapp_inbox.message.received": another_customer_writes,
    "whatsapp_inbox.message.sent": answer_from_the_hub,
    "whatsapp_inbox.conversation.status_changed": close,
    "whatsapp_inbox.conversation.erased": erase,
}


def awaiting_reply():
    return apps.get_app_config("whatsapp_inbox").bell[0]


@pytest.mark.django_db
@pytest.mark.parametrize("event", list(CHANGES))
def test_each_change_of_the_number_records_an_event_that_refreshes_the_bell(event):
    receive("wamid.1")
    before = counted()
    seen = set(OutboxEvent.objects.values_list("id", flat=True))

    CHANGES[event]()

    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert counted() != before
    assert recorded & set(awaiting_reply().refresh_on) == {event}


@pytest.mark.django_db
def test_an_answer_from_the_phone_takes_it_away_too():
    receive("wamid.1")
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    answer_from_the_phone()
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert counted() == 0
    assert recorded & set(awaiting_reply().refresh_on) == {"whatsapp_inbox.message.received"}


def test_every_event_it_is_refreshed_on_changes_the_number():
    """Not one more: the counter is re-run on what changes it, and nothing else."""
    assert set(awaiting_reply().refresh_on) == set(CHANGES)


# ── The device's notices (hub#2303, hub#2306) ────────────────────────────────────────────────────────────────────


def notices(ctx=None) -> list[dict]:
    op = get("base.notice.list")
    return op(ctx or ctx_for("hub_employee"), NoticeListIn()).model_dump(mode="json")["notices"]


def sources(ctx) -> list[str]:
    op = get("base.notice.list")
    return op(ctx, NoticeListIn()).model_dump(mode="json")["sources"]


@pytest.mark.django_db
def test_the_device_is_told_of_each_customer_left_waiting_with_what_she_wrote():
    receive("wamid.1", contact_name="Ana")
    lopez = card("Bea López", "600222222")
    receive("wamid.2", "34600222222", contact_name="Bea", text="¿Abrís el sábado?", sent_at=NOW.isoformat())
    bea = Conversation.objects.get(phone="+34600222222")
    assert bea.customer_id == lopez.id

    told = [n for n in notices() if n["app"] == "whatsapp_inbox"]

    assert {(n["key"], n["title"], n["body"]) for n in told} == {
        ("whatsapp_inbox.awaiting_reply", "WhatsApp · Ana", "Hola, ¿tenéis hora mañana?"),
        ("whatsapp_inbox.awaiting_reply", "WhatsApp · Bea López", "¿Abrís el sábado?"),
    }
    assert {n["route"] for n in told} == {
        f"/whatsapp_inbox/inbox?conversation={row.id}" for row in Conversation.objects.all()
    }
    assert all(n["at"] for n in told)


@pytest.mark.django_db
def test_once_answered_it_is_no_longer_told():
    receive("wamid.1")
    answer_from_the_hub()
    assert [n for n in notices() if n["app"] == "whatsapp_inbox"] == []


@pytest.mark.django_db
def test_whoever_reads_the_inbox_hears_it_so_the_app_asks_to_notify():
    """hub#2306: a business that only uses WhatsApp is asked to let the app notify (base asks where ``sources`` names
    some notice); whoever cannot read the inbox neither hears it nor is asked for it."""
    assert "whatsapp_inbox.awaiting_reply" in sources(ctx_for("hub_employee"))
    assert sources(only("whatsapp_inbox.view")) == ["whatsapp_inbox.awaiting_reply"]
    assert sources(only()) == []


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout=5.0, stop_after=None):
    return [(n.channel, json.loads(n.payload)) for n in session.notifies(timeout=timeout, stop_after=stop_after)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_customer_writing_to_hub_b_re_runs_the_bell_and_the_notices_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    receive("wamid.1", scope=B)
    notes = heard(on_b, stop_after=1)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    affected = live_registry.affected({event for _, payload in notes for event in payload["events"]})
    assert {"base.bell.counters", "base.notice.list"} <= affected
    assert heard(on_a, timeout=0.5) == []
