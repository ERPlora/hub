"""«A payment completed» starts the business's automations through the worker's outbox relay (PAYMENT-F07).

End to end, with the real pieces (``base/tests/test_relay.py`` and ``apps/flow/tests/test_relay.py`` are the
pattern): Payments' real operations take a payment up its ladder and record ``payment.payment.completed`` in the
outbox, in the step's transaction; one tick of the worker's real loop (``base.worker.run`` → ``base.relay``)
hands it to Automations (``apps.flow``), and the automation that waits for it runs once — a second tick, or the
same notice handed over again, changes nothing. A refused completion records nothing, so it starts nothing. A
payment completed in hub B starts its run in B, and its notices are heard in B only.

The worker's real loop serves each business in its own database and releases its connections once it has served it:
what these tests write is committed.
"""

import pytest
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get

from apps.flow.models import FlowRun
from apps.flow.tests.test_relay import heard
from apps.task.models import Task
from base.models.relay import EventDelivery
from base.tenancy.context import use_hub

from .conftest import HUB_DB_COMMITTED, A, B

RECEIPT = {
    "name": "File the receipt",
    "trigger": {"kind": "event", "event": "payment.payment.completed"},
    "steps": [
        {
            "id": "s1",
            "kind": "command",
            "operation": "task.task.create",
            "params": {"title": "File the receipt of {{input.reference}}"},
        }
    ],
}


def owner(scope: Scope = A) -> OperationContext:
    """The owner of ``scope``: every permission of every app (Payments', Automations' and Tasks')."""
    permissions = {p for config in all_live_app_configs() for p in config.permissions}
    return OperationContext(scope=scope, actor="tester", permissions=permissions)


def run(name: str, data: dict, scope: Scope = A):
    """Run the operation ``name`` as the owner of ``scope``: each app's own, with its permissions."""
    op = get(name)
    return op(owner(scope), op.input.model_validate(data))


def automation(scope: Scope = A) -> str:
    """«When a payment is completed, file its receipt», as the owner makes it: created, granted and on."""
    created = run("flow.flow.create", RECEIPT, scope)
    run("flow.flow.grant", {"id": str(created.id), "operations": ["task.task.create"]}, scope)
    run("flow.flow.set_enabled", {"id": str(created.id), "enabled": True}, scope)
    return str(created.id)


def sent_payment(scope: Scope = A, method: str = "BBVA account"):
    """A payment recorded, approved and marked as sent, by the app's own operations."""
    run("payment.method.create", {"name": method}, scope)
    payment = run(
        "payment.payment.create",
        {
            "method": method,
            "payment_date": "2026-10-14",
            "amount": 12_50,
            "beneficiary_name": "Proveedor Norte SL",
        },
        scope,
    )
    run("payment.payment.approve", {"id": str(payment.id)}, scope)
    run("payment.payment.mark_sent", {"id": str(payment.id)}, scope)
    return payment


def receipts() -> list[str]:
    return sorted(Task.objects.values_list("title", flat=True))


@HUB_DB_COMMITTED
def test_a_completed_payment_starts_the_automation_through_the_workers_relay_once(worker_loop):
    flow_id = automation()
    payment = sent_payment()
    worker_loop()  # created, approved and sent reach Automations too: none of them is this trigger
    assert not FlowRun.objects.exists()

    run("payment.payment.mark_completed", {"id": str(payment.id)})
    event = OutboxEvent.objects.get(name="payment.payment.completed")
    assert event.payload == {
        "id": str(payment.id),
        "reference": payment.reference,
        "status": "completed",
        "amount": 12_50,
        "currency": "EUR",
    }
    assert not FlowRun.objects.exists()  # nothing runs inside the request that completed it

    worker_loop()

    assert EventDelivery.objects.get(event_id=event.id, app_label="flow").status == "delivered"
    started = FlowRun.objects.get(flow_id=flow_id)
    assert (started.trigger_kind, started.trigger_key, started.event_name, started.status) == (
        "event",
        str(event.id),
        "payment.payment.completed",
        "succeeded",
    )
    assert receipts() == [f"File the receipt of {payment.reference}"]

    worker_loop()
    assert (FlowRun.objects.count(), receipts()) == (1, [f"File the receipt of {payment.reference}"])


@HUB_DB_COMMITTED
def test_the_same_notice_handed_over_again_starts_no_second_run(worker_loop):
    automation()
    payment = sent_payment()
    run("payment.payment.mark_completed", {"id": str(payment.id)})
    worker_loop()

    # The notice handed to Automations again, as if its delivery had been lost: the relay runs it once more.
    event = OutboxEvent.objects.get(name="payment.payment.completed")
    EventDelivery.objects.filter(event_id=event.id, app_label="flow").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )
    worker_loop()

    assert EventDelivery.objects.get(event_id=event.id, app_label="flow").attempts == 2
    assert (FlowRun.objects.count(), Task.objects.count()) == (1, 1)


@HUB_DB_COMMITTED
def test_a_refused_completion_records_no_notice_and_starts_nothing(worker_loop):
    automation()
    run("payment.method.create", {"name": "BBVA account"})
    draft = run(
        "payment.payment.create",
        {"method": "BBVA account", "payment_date": "2026-10-14", "amount": 500, "beneficiary_name": "Luz SA"},
    )

    with pytest.raises(Conflict):
        run("payment.payment.mark_completed", {"id": str(draft.id)})
    worker_loop()

    assert not OutboxEvent.objects.filter(name="payment.payment.completed").exists()
    assert (FlowRun.objects.count(), Task.objects.count()) == (0, 0)


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_a_payment_completed_in_hub_b_starts_its_run_in_b_and_is_heard_in_b_only(listen, worker_loop, hub_b):
    automation()
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        automation(B)
        payment = sent_payment(B, method="Caja B")
    worker_loop()
    heard(on_a), heard(on_b)  # the ladder's own notices

    with use_hub(hub_b):
        run("payment.payment.mark_completed", {"id": str(payment.id)}, B)
    assert heard(on_b) == {"payment.payment.completed"}
    worker_loop()

    assert {"flow.run.started", "flow.run.finished", "task.task.created"} <= heard(on_b)
    assert heard(on_a, timeout=0.3) == set()
    with use_hub(hub_b):
        started = OutboxEvent.objects.get(name="flow.run.started")
    assert (started.scope_kind, started.scope_key) == (B.kind, B.key)
    assert not FlowRun.objects.exists()
    # The positive control: a payment completed in A is heard in A and starts its run there.
    in_a = sent_payment(A, method="Caja A")
    worker_loop()
    heard(on_a)
    run("payment.payment.mark_completed", {"id": str(in_a.id)}, A)
    worker_loop()
    assert "flow.run.started" in heard(on_a)
