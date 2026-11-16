"""What a write of the table app tells the live streams, after the COMMIT and only on its own hub's
channel (the guardrail «writing in hub B does not notify A», CLAUDE.md): seating in B notifies B's channel
with the table's and Sales' events, never A's; a refused write notifies nobody."""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.outbox import channel_for

from base.tenancy.context import use_hub

from .conftest import HUB_DB_COMMITTED, A, B, ctx_for, make_session, make_table, make_zone, run

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


def received(session, timeout=WAIT, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@HUB_DB_COMMITTED
def test_seating_in_hub_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        table = make_table("4", zone=make_zone())
        run("table.session.open", {"table_id": str(table.id)}, ctx_for(scope=B))
    notes = received(on_b, stop_after=2)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    assert {event for _, payload in notes for event in payload["events"]} == {"sale.order.opened", "table.session.opened"}
    assert received(on_a, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_refused_write_notifies_nobody(listen):
    table = make_table("4", zone=make_zone())
    make_session(table)
    on_a = listen(A)
    with pytest.raises(Conflict):
        run("table.session.open", {"table_id": str(table.id)})
    assert received(on_a, timeout=QUIET) == []
