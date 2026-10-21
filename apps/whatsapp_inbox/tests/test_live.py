"""Live queries of the WhatsApp inbox: which events re-run which screen (the inbox is live, F03)."""

import json
from pathlib import Path

import psycopg
import pytest
from live.errors import InvalidPayload
from live.outbox import channel_for

from live.live_registry import live_registry

from apps.whatsapp_inbox import events as E
from apps.whatsapp_inbox.tests.conftest import A, B, receive

EVENTS_SOURCE = Path(E.__file__).read_text()
CARD = [
    "customer.customer.updated",
    "customer.customer.merged",
    "customer.customer.deleted",
    "customer.customer.erased",
]
INBOX = [
    E.MESSAGE_RECEIVED,
    E.MESSAGE_SENT,
    E.CONVERSATION_READ,
    E.ASSIGNED,
    E.STATUS_CHANGED,
    E.CUSTOMER_LINKED,
    E.ERASED,
]


#: The number's state: erplora.com's photo, and its answer when the business connects or disconnects it here.
CHANNEL = [E.CHANNEL_SYNCED, E.CHANNEL_CONNECTED, E.CHANNEL_DISCONNECTED]


def inbox_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("whatsapp_inbox.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_screen_and_its_events():
    assert inbox_queries() == {
        "whatsapp_inbox.conversation.list": [*INBOX, *CARD],
        "whatsapp_inbox.conversation.detail": [*INBOX, *CARD, *CHANNEL],
        "whatsapp_inbox.conversation.summary": [
            E.MESSAGE_RECEIVED,
            E.MESSAGE_SENT,
            E.CONVERSATION_READ,
            E.STATUS_CHANGED,
            E.ERASED,
            *CHANNEL,
        ],
        "whatsapp_inbox.message.list": [
            E.MESSAGE_RECEIVED,
            E.MESSAGE_SENT,
            E.MESSAGE_STATUS_CHANGED,
            E.ERASED,
        ],
        "whatsapp_inbox.note.list": [E.NOTE_ADDED, E.NOTE_DELETED, E.ERASED],
        "whatsapp_inbox.template.list": [E.CHANNEL_SYNCED, E.TEMPLATE_CREATED, E.TEMPLATE_UPDATED, E.TEMPLATE_DELETED],
        "whatsapp_inbox.channel.get": CHANNEL,
    }


def test_every_own_event_is_a_literal_of_events_py():
    for on in inbox_queries().values():
        for event in on:
            if event.startswith("whatsapp_inbox."):
                assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_message_arriving_re_runs_the_inbox_the_thread_and_the_summary():
    assert {
        n
        for n in live_registry.affected([E.MESSAGE_RECEIVED])
        if n.startswith("whatsapp_inbox.")
    } == {
        "whatsapp_inbox.conversation.list",
        "whatsapp_inbox.conversation.detail",
        "whatsapp_inbox.conversation.summary",
        "whatsapp_inbox.message.list",
    }


def test_a_delivery_status_re_runs_only_the_thread():
    assert {
        n
        for n in live_registry.affected([E.MESSAGE_STATUS_CHANGED])
        if n.startswith("whatsapp_inbox.")
    } == {"whatsapp_inbox.message.list"}


def test_the_exact_number_lookup_and_the_team_are_not_live():
    assert "whatsapp_inbox.conversation.by_phone" not in live_registry.subscribable
    assert "whatsapp_inbox.agent.list" not in live_registry.subscribable


# Notifications: after the COMMIT, on the channel of the receiving hub only


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
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_message_received_by_hub_b_notifies_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    receive("wamid.1", scope=B)
    assert heard(on_b, stop_after=1) == [(channel_for(B), {"events": [E.MESSAGE_RECEIVED]})]
    assert heard(on_a, timeout=0.5) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_message_notifies_nobody(listen):
    on_a = listen(A)
    with pytest.raises(InvalidPayload):
        receive("wamid.1", "999123456789")
    assert heard(on_a, timeout=0.5) == []
