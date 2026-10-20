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
    assert set(flow_queries()) == {
        "flow.flow.list",
        "flow.flow.detail",
        "flow.run.list",
        "flow.draft.list",
        "flow.secret.list",
        "flow.question.list",
    }


def test_each_query_and_its_events():
    queries = flow_queries()
    # A row of the list says how its last run ended: a run that starts or ends changes it.
    for name in ("flow.flow.list", "flow.flow.detail"):
        assert queries[name] == [*events.FLOW_EVENTS, *events.RUN_EVENTS], name
    assert queries["flow.run.list"] == events.RUN_EVENTS
    # A draft leaves the tray when it is used or dismissed.
    assert queries["flow.draft.list"] == events.DRAFT_EVENTS
    # A secret's name comes and goes; never its value (FLOW-F26).
    assert queries["flow.secret.list"] == events.SECRET_EVENTS
    # A question comes, is answered or expires; one whose run is cancelled leaves too (FLOW-F29).
    assert queries["flow.question.list"] == [*events.QUESTION_EVENTS, *events.RUN_EVENTS]


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


def heard(session, timeout=1.0) -> list[str]:
    return sorted(
        name
        for note in session.notifies(timeout=timeout)
        for name in json.loads(note.payload)["events"]
    )


def heard_until(session, expected: list[str], timeout=1.0) -> list[str]:
    """The events heard up to the notification that completes ``expected``, sorted. A run and the task its
    action creates by name (``call_app``) notify on their own after the same COMMIT, and the two
    notifications may arrive in separate packets: stopping after the first one only sees both when they
    happen to share a packet (pattern of ``apps/verifactu/tests/test_notifications.py``)."""
    names: list[str] = []
    for note in session.notifies(timeout=timeout):
        names.extend(json.loads(note.payload)["events"])
        if set(expected) <= set(names):
            break
    return sorted(names)


@pytest.mark.django_db(transaction=True)
def test_a_run_started_by_an_event_in_b_is_heard_in_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    make_flow()
    events.react(B, "customer.customer.created", {"id": "c"}, event_id=uuid.uuid7())
    expected = ["flow.run.finished", "flow.run.started", "task.task.created"]
    assert heard_until(on_b, expected) == expected
    assert heard(on_a, timeout=0.3) == []


@pytest.mark.django_db(transaction=True)
def test_a_run_by_hand_in_b_is_heard_in_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    flow = make_flow(trigger_kind="manual")
    run("flow.flow.run", {"id": str(flow.id)}, ctx_for(scope=B))
    expected = ["flow.run.finished", "flow.run.started", "task.task.created"]
    assert heard_until(on_b, expected) == expected
    assert heard(on_a, timeout=0.3) == []
    # Positive control: the same listener of A hears a run in A.
    run("flow.flow.run", {"id": str(flow.id)}, system_context(A))
    assert "flow.run.finished" in heard_until(on_a, ["flow.run.finished"])


@pytest.mark.django_db(transaction=True)
def test_a_question_asked_and_answered_in_b_is_heard_in_b_only(listen):
    # FLOW-F28/F29: «Waiting for your answer» of A never hears what an automation asked in B.
    from apps.flow.models import Question

    on_a, on_b = listen(A), listen(B)
    flow = make_flow(trigger_kind="manual", steps=[{"id": "s1", "kind": "ask", "title": "Go?"}])
    ran = run("flow.flow.run", {"id": str(flow.id)}, ctx_for(scope=B))
    asked = ["flow.question.asked", "flow.run.parked", "flow.run.started"]
    assert heard_until(on_b, asked) == asked
    question = Question.objects.get(run_id=ran.id)
    run("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(scope=B))
    answered = ["flow.question.answered", "flow.run.finished", "flow.run.resumed"]
    assert heard_until(on_b, answered) == answered
    assert heard(on_a, timeout=0.3) == []

