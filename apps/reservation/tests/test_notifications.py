"""What a write of the reservation app tells the live streams, after the COMMIT and only on its own hub's
channel (the guardrail «writing in hub B does not notify A», CLAUDE.md): booking in B notifies B's channel
with the reservation's events, never A's; a refused booking notifies nobody."""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.outbox import channel_for

from .conftest import A, B, book, ctx_for, make_slot, open_week

WAIT = 1.0
QUIET = 0.3


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


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


def events_of(notes) -> set[str]:
    return {event for _, payload in notes for event in payload["events"]}


def received_until(session, expected: set[str], timeout=WAIT):
    """The notifications up to the one that completes ``expected``. Booking creates the guest's card
    first (``customer.customer.create`` nested in ``reservation.reservation.create``), which notifies on
    its own after the same COMMIT, and the two notifications may arrive in separate packets: stopping
    after the first one only sees the reservation's when they happen to share a packet."""
    notes = []
    for note in session.notifies(timeout=timeout):
        notes.append((note.channel, json.loads(note.payload)))
        if expected <= events_of(notes):
            break
    return notes


@pytest.mark.django_db(transaction=True)
def test_booking_in_hub_b_notifies_the_channel_of_b_only(listen):
    open_week()
    on_a, on_b = listen(A), listen(B)
    book(ctx=ctx_for(scope=B))
    notes = received_until(on_b, {"customer.customer.created", "reservation.reservation.created"})
    assert {channel for channel, _ in notes} == {channel_for(B)}
    assert {"customer.customer.created", "reservation.reservation.created"} <= events_of(notes)
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_booking_notifies_nobody(listen):
    from .conftest import THURSDAY

    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    book()
    on_a = listen(A)
    with pytest.raises(Conflict):
        book(guest_name="Luis", guest_phone="600333444")
    assert received(on_a, timeout=QUIET) == []
