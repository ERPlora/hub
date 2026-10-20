"""What a write of the service app tells the live streams, after the COMMIT and only on its own hub's channel
(the guardrail «writing in hub B does not notify A», CLAUDE.md): a category created and a voucher's session
spent in B notify B's channel with Services' events, never A's; a refused write notifies nobody."""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.operations import get
from live.outbox import channel_for

from .conftest import (
    A,
    B,
    ctx_for,
    make_customer,
    make_grant,
    make_package,
    make_service,
    make_tax,
)

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
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


def run(name, data, scope=A):
    op = get(name)
    return op(ctx_for(scope=scope), op.input.model_validate(data))


# Transactional: the notice leaves after a real COMMIT, so the rows a test starts from are committed too.
@pytest.mark.django_db(transaction=True)
def test_a_category_and_a_session_spent_in_hub_b_notify_the_channel_of_b_only(listen):
    cut = make_service("Cut", tax=make_tax())
    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    on_a, on_b = listen(A), listen(B)
    run("service.category.create", {"name": "Hair"}, scope=B)
    run("service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)}, scope=B)
    # Everything B's channel heard in the window, not the first two notices: under load a write may come split.
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert {"service.category.created", "service.grant.redeemed"} <= events
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_write_notifies_nobody(listen):
    run("service.category.create", {"name": "Hair"})
    on_a = listen(A)
    run("service.category.create", {"name": "Nails"})
    # The listener hears its own hub: the silence below is a refusal's, not a deaf channel's.
    assert [channel for channel, _ in received(on_a, stop_after=1)] == [channel_for(A)]
    with pytest.raises(Conflict) as refused:
        run("service.category.create", {"name": " hair "})
    assert refused.value.code == "service.category_name_taken"
    assert received(on_a, timeout=QUIET) == []
