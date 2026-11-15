"""The loop guard follows a chain of automations through what another app does with a run's work (FLOW-F21).

An automation makes a card; the WhatsApp inbox, on its own, links the conversation of her number to it; an automation
of «a conversation is linked» leaves a task, and the task would make the card again. The inbox's event carries the
mark of the run that made the card (the relay passes it on, ``base.relay.carried``), so the automation that starts
from it knows where it comes from, and the one that would start itself again through the inbox is stopped before
doing anything, as it is in a direct chain.

The real apps and the worker's relay (``base.relay.run``), which hands every event over as it does every tick.
"""

import pytest
from live.context import system_context
from live.models import OutboxEvent

from apps.customer.models import Customer
from apps.flow.models import FlowRun
from apps.flow.services import RUN_ACTOR
from apps.task.models import Task
from apps.whatsapp_inbox.tests.conftest import receive

from .conftest import A, run
from .test_integration_apps import create_automation

pytestmark = pytest.mark.django_db

#: Her number, as WhatsApp gives it and as the business writes it on her card.
WHATSAPP_NUMBER, PHONE = "34600111222", "600111222"


def relayed(worker) -> None:
    """The worker's relay, tick after tick, until it has nothing left to hand over."""
    for _ in range(10):
        done = worker()
        if not (done.taken or done.delivered or done.failed):
            return
    raise AssertionError("The relay still had events to hand over after 10 ticks.")


def card_maker() -> str:
    """«A card for every new task»: what starts the chain."""
    return create_automation(
        {
            "name": "A card for every new task",
            "trigger": {"kind": "event", "event": "task.task.created"},
            "steps": [
                {
                    "id": "s1",
                    "kind": "command",
                    "operation": "customer.customer.create",
                    "params": {"name": "Ana López", "phone": PHONE},
                }
            ],
        },
        ["customer.customer.create"],
    )


def task_maker(name: str, event: str) -> str:
    """An automation that leaves a task when ``event`` happens."""
    return create_automation(
        {
            "name": name,
            "trigger": {"kind": "event", "event": event},
            "steps": [{"id": "s1", "kind": "command", "operation": "task.task.create", "params": {"title": name}}],
        },
        ["task.task.create"],
    )


def runs_of(flow_id: str) -> list[FlowRun]:
    return list(FlowRun.objects.filter(flow_id=flow_id).order_by("started_at", "id"))


def test_a_run_started_by_what_another_app_did_with_a_run_s_work_knows_where_it_comes_from(worker):
    receive("wamid.1", WHATSAPP_NUMBER, A)
    maker = card_maker()
    linked = task_maker("Linked", "whatsapp_inbox.conversation.customer_linked")

    run("task.task.create", {"title": "Start"}, system_context(A))
    relayed(worker)

    first = runs_of(maker)[0]
    linking = OutboxEvent.objects.get(name="whatsapp_inbox.conversation.customer_linked")
    assert linking.actor == f"{RUN_ACTOR}{first.id}"
    assert runs_of(linked)[0].chain == [maker]


def test_an_automation_that_would_start_itself_again_through_another_app_is_stopped_before_doing_anything(worker):
    receive("wamid.1", WHATSAPP_NUMBER, A)
    maker = card_maker()
    task_maker("Linked", "whatsapp_inbox.conversation.customer_linked")

    run("task.task.create", {"title": "Start"}, system_context(A))
    relayed(worker)

    first, again = runs_of(maker)
    assert first.status == FlowRun.Status.SUCCEEDED
    assert (again.status, again.error_code) == (FlowRun.Status.FAILED, "flow.loop_stopped")
    # One card, the first run's: the second never made another.
    assert Customer.objects.live().count() == 1
    assert sorted(Task.objects.values_list("title", flat=True)) == ["Linked", "Start"]


def test_a_chain_of_automations_keeps_each_run_s_own_mark_through_the_relay(worker):
    """A direct chain, maker → card → maker: what the second run's step records is its own, never the first run's, so
    the chain grows by one automation at each run."""
    maker = card_maker()
    card = task_maker("Call the new customer", "customer.customer.created")

    run("task.task.create", {"title": "Start"}, system_context(A))
    relayed(worker)

    (calling,) = runs_of(card)
    first, again = runs_of(maker)
    call = Task.objects.get(title="Call the new customer")
    by_the_call = OutboxEvent.objects.get(name="task.task.created", payload__id=str(call.pk))
    assert by_the_call.actor == f"{RUN_ACTOR}{calling.id}"
    assert (calling.chain, again.chain) == ([maker], [maker, card])
    assert (again.status, again.error_code) == (FlowRun.Status.FAILED, "flow.loop_stopped")
    assert first.status == FlowRun.Status.SUCCEEDED
