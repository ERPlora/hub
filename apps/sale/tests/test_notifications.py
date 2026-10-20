"""What a write of the sale app tells the live streams, after the COMMIT and only on its own hub's channel (the
guardrail «writing in hub B does not notify A», CLAUDE.md): opening a check and charging it in B notify B's
channel with Sales' events, never A's; a refused write notifies nobody."""

import json

import psycopg
import pytest
from live.errors import Conflict
from live.outbox import channel_for

from apps.sale.tests.conftest import A, B, ctx_for, run

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


def open_price(ctx):
    return run(
        "sale.order.open",
        {"label": "Table 4", "open_lines": [{"unit_price": 250, "tax_category_key": "product.generic"}]},
        ctx,
    )


# Transactional: the notice leaves after a real COMMIT. `serialized_rollback` keeps Taxes' factory catalogue,
# seeded by its migrations, which a flush between transactional tests would empty.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_check_opened_and_charged_in_hub_b_notifies_the_channel_of_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    order = open_price(ctx_for(scope=B))
    run(
        "sale.sale.complete",
        {"idempotency_key": "notify-b-0001", "order_id": str(order.id), "payments": [{"method": "cash"}]},
        ctx_for(scope=B),
    )
    notes = received(on_b, stop_after=2)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert {"sale.order.opened", "sale.sale.completed"} <= events
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_refused_write_notifies_nobody(listen):
    order = open_price(ctx_for())
    on_a = listen(A)
    run("sale.order.fire", {"order_id": str(order.id)})
    # The listener hears its own hub: the silence below is a refusal's, not a deaf channel's.
    assert [channel for channel, _ in received(on_a, stop_after=1)] == [channel_for(A)]
    with pytest.raises(Conflict) as refused:
        run("sale.order.fire", {"order_id": str(order.id)})
    assert refused.value.code == "sale.nothing_to_fire"
    assert received(on_a, timeout=QUIET) == []
