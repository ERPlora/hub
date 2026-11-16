"""What a write of the verifactu app tells the live streams, after the COMMIT and only on its own hub's channel
(the guardrail «writing in hub B does not notify A»): sealing and sending in B, inside B's own database, notify B's
channel with VeriFactu's events, never A's; a refused write notifies nobody. The notices are heard as a live stream
hears them: ``LISTEN`` on the scope's channel, in control."""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.outbox import channel_for

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import HUB_DB_COMMITTED, A, B, answering, ctx_for, run

pytestmark = HUB_DB_COMMITTED

WAIT = 1.0
QUIET = 0.3
CUT = [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]


@pytest.fixture(autouse=True)
def _committed(committed_factory_data, committed_factory_data_b):
    """Committed factory data and the issuer of both businesses (``conftest``)."""


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


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


def events_of(notes) -> set[str]:
    return {event for _, payload in notes for event in payload["events"]}


def received_until(session, expected: set[str], timeout=WAIT):
    """The notifications up to the one that completes ``expected``. A nested command (sealing inside
    ``invoice.invoice.create``, sending inside ``verifactu.contingency.process``) notifies on its own
    after the same COMMIT, and the two notifications may arrive in separate packets: stopping after
    the first one only sees both when they happen to share a packet."""
    notes = []
    for note in session.notifies(timeout=timeout):
        notes.append((note.channel, json.loads(note.payload)))
        if expected <= events_of(notes):
            break
    return notes


def test_sealing_in_hub_b_notifies_the_channel_of_b_only(listen, in_business_b):
    on_a, on_b = listen(A), listen(B)
    with in_business_b():
        invoice = run("invoice.invoice.create", {"series_code": "TICKET", "lines": CUT}, ctx_for(scope=B))
    assert invoice.verifactu_status == "sealed"
    notes = received_until(on_b, {"invoice.invoice.issued", "verifactu.record.created"})
    assert {channel for channel, _ in notes} == {channel_for(B)}
    assert {"invoice.invoice.issued", "verifactu.record.created"} <= events_of(notes)
    assert received(on_a, timeout=QUIET) == []


def test_sending_in_hub_b_notifies_the_channel_of_b_only(listen, gateway_answers, in_business_b):
    with in_business_b():
        run("invoice.invoice.create", {"series_code": "TICKET", "lines": CUT}, ctx_for(scope=B))
    gateway_answers.set(answering())
    on_a, on_b = listen(A), listen(B)
    with in_business_b():
        result = run("verifactu.contingency.process", {}, ctx_for(scope=B))
    assert (result.sent, result.accepted) == (1, 1)
    notes = received_until(on_b, {"verifactu.record.transmitted", "verifactu.contingency.processed"})
    assert {channel for channel, _ in notes} == {channel_for(B)}
    assert {"verifactu.record.transmitted", "verifactu.contingency.processed"} <= events_of(notes)
    assert received(on_a, timeout=QUIET) == []


def test_a_refused_write_notifies_nobody(listen):
    run("invoice.invoice.create", {"series_code": "TICKET", "lines": CUT})
    record = Record.objects.get()
    on_a = listen(A)
    with pytest.raises(Conflict):
        run("verifactu.record.correct", {"record_id": str(record.id)})
    assert received(on_a, timeout=QUIET) == []
