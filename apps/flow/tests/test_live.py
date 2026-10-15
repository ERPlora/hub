"""Live queries of the flow app: which events re-run which query (WORKBOOK «Servicios»)."""

import json
import uuid

import psycopg
import pytest
from live.context import system_context
from live.live_registry import live_registry
from live.outbox import channel_for

from apps.flow import events

from .conftest import A, B, ctx_for, make_flow, run


def flow_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("flow.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_lists_and_the_detail_can_be_followed_live():
    assert set(flow_queries()) == {"flow.flow.list", "flow.flow.detail", "flow.run.list", "flow.draft.list"}


def test_each_query_and_its_events():
    queries = flow_queries()
    # A row of the list says how its last run ended: a run that starts or ends changes it.
    for name in ("flow.flow.list", "flow.flow.detail"):
        assert queries[name] == [*events.FLOW_EVENTS, *events.RUN_EVENTS], name
    assert queries["flow.run.list"] == events.RUN_EVENTS
    # A draft leaves the tray when it is used or dismissed.
    assert queries["flow.draft.list"] == events.DRAFT_EVENTS


# What a run does in a business is heard by that business only (review 2026-10-15, item 7)



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


def heard(session, timeout=1.0, stop_after=None) -> list[str]:
    return sorted(
        name
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
        for name in json.loads(note.payload)["events"]
    )


@pytest.mark.django_db(transaction=True)
def test_a_run_started_by_an_event_in_b_is_heard_in_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    make_flow()
    events.react(B, "customer.customer.created", {"id": "c"}, event_id=uuid.uuid7())
    assert heard(on_b, stop_after=1) == ["flow.run.finished", "flow.run.started", "task.task.created"]
    assert heard(on_a, timeout=0.3) == []


@pytest.mark.django_db(transaction=True)
def test_a_run_by_hand_in_b_is_heard_in_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    flow = make_flow(trigger_kind="manual")
    run("flow.flow.run", {"id": str(flow.id)}, ctx_for(scope=B))
    assert heard(on_b, stop_after=1) == ["flow.run.finished", "flow.run.started", "task.task.created"]
    assert heard(on_a, timeout=0.3) == []
    # Positive control: the same listener of A hears a run in A.
    run("flow.flow.run", {"id": str(flow.id)}, system_context(A))
    assert "flow.run.finished" in heard(on_a, stop_after=1)
