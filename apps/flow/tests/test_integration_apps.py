"""Automations and the real apps together, no mocks (WORKBOOK FLOW-F21 to F23): a real event of Sales,
Customers or Tasks, as their real operation records it in the outbox, is handed to flow as the relay will
(``events.deliver``), and the automation runs the real operation of another app, whose result is in its
table.

- «Create a flow that creates a task when a sale over 100 € is completed», and the gallery's «note the
  big sales on the card»: Sales → Tasks and Customers.
- «Welcome a new customer»: Customers → a day's wait → Tasks.
- A chain: Customers → Tasks → an automation on new tasks, which is stopped when its own task would
  start it again.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from live.context import system_context
from live.models import OutboxEvent

from apps.customer.models import Activity
from apps.flow import events
from apps.flow.models import FlowRun
from apps.task.models import Task

from .conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)


@pytest.fixture(autouse=True)
def without_cash_register(monkeypatch):
    """Sell as a business without Cash register, as Sales' own tests do (its till asks an operation
    nobody declares)."""
    monkeypatch.setattr(
        "apps.sale.services.DRAWER_CHECK", "cash_register.session.not_installed"
    )


def newest(name: str) -> OutboxEvent:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()


def create_automation(document: dict, operations: list[str]) -> str:
    """An automation as the owner makes it: created, granted and turned on through its operations."""
    created = run("flow.flow.create", document)
    run("flow.flow.grant", {"id": str(created.id), "operations": operations})
    run("flow.flow.set_enabled", {"id": str(created.id), "enabled": True})
    return str(created.id)


def sell(*, customer: str | None = None, key: str):
    """A real sale of one coffee (121,00 €), charged by Sales."""
    data = {"idempotency_key": key, "lines": [{"product": "COF", "quantity": "1"}]}
    if customer:
        data["customer"] = customer
    return run("sale.sale.complete", data, system_context(A))


@pytest.fixture
def coffee():
    return run(
        "inventory.product.create",
        {
            "name": "Coffee",
            "sku": "COF",
            "price": 12100,
            "tax_category_key": "product.generic",
        },
        system_context(A),
    )


def test_a_sale_over_100_euros_leaves_a_task_and_a_note_on_its_customer(coffee):
    task_flow = create_automation(
        {
            "name": "Big sale",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"input.total": {"gt": 10000}},
            },
            "steps": [
                {
                    "id": "s1",
                    "kind": "command",
                    "operation": "task.task.create",
                    "params": {
                        "title": "Thank the big sale {{input.sale_number}}",
                        "priority": "high",
                    },
                }
            ],
        },
        ["task.task.create"],
    )
    note_flow = create_automation(
        {
            "name": "Note the big sales on the card",
            "trigger": {"kind": "event", "event": "sale.sale.completed"},
            "steps": [
                {
                    "id": "s1",
                    "kind": "condition",
                    "when": {
                        "input.customer_id": {"exists": True},
                        "input.total": {"gte": 10000},
                    },
                },
                {
                    "id": "s2",
                    "kind": "command",
                    "operation": "customer.note.add",
                    "params": {
                        "customer_id": "input.customer_id",
                        "content": "Big sale: {{input.total}} cents",
                        "author_name": "Automations",
                    },
                },
            ],
        },
        ["customer.note.add"],
    )
    ana = run(
        "customer.customer.create",
        {"name": "Ana López", "phone": "600111222"},
        system_context(A),
    )
    sale = sell(customer="600 111 222", key="flow-sale-1")
    assert sale.total >= 12100
    result = events.deliver(newest("sale.sale.completed"))
    assert result.started == 2
    task = Task.objects.get()
    assert (task.title, task.priority) == (f"Thank the big sale {sale.number}", "high")
    note = Activity.objects.get(customer_id=ana.id, kind=Activity.Kind.NOTE_ADDED)
    assert note.text == f"Big sale: {sale.total} cents"
    assert note.actor.startswith("flow_run:")
    for flow_id in (task_flow, note_flow):
        assert FlowRun.objects.get(flow_id=flow_id).status == FlowRun.Status.SUCCEEDED
    # The same sale delivered again starts nothing more.
    assert events.deliver(newest("sale.sale.completed")).started == 0
    assert Task.objects.count() == 1


def test_a_small_sale_starts_nothing_and_a_sale_without_customer_stops_at_its_condition(
    coffee,
):
    create_automation(
        {
            "name": "Big sale",
            "trigger": {
                "kind": "event",
                "event": "sale.sale.completed",
                "filter": {"input.total": {"gt": 100000}},
            },
            "steps": [
                {
                    "id": "s1",
                    "kind": "command",
                    "operation": "task.task.create",
                    "params": {"title": "x"},
                }
            ],
        },
        ["task.task.create"],
    )
    note_flow = create_automation(
        {
            "name": "Note",
            "trigger": {"kind": "event", "event": "sale.sale.completed"},
            "steps": [
                {
                    "id": "s1",
                    "kind": "condition",
                    "when": {"input.customer_id": {"exists": True}},
                },
                {
                    "id": "s2",
                    "kind": "command",
                    "operation": "customer.note.add",
                    "params": {"customer_id": "input.customer_id", "content": "x"},
                },
            ],
        },
        ["customer.note.add"],
    )
    sell(key="flow-sale-2")
    result = events.deliver(newest("sale.sale.completed"))
    assert (result.started, result.skipped) == (1, 1)
    assert FlowRun.objects.get(flow_id=note_flow).status == FlowRun.Status.STOPPED
    assert (
        Task.objects.count(),
        Activity.objects.filter(kind=Activity.Kind.NOTE_ADDED).count(),
    ) == (0, 0)


def test_welcome_a_new_customer_a_day_later(clock):
    clock(NOON)
    create_automation(
        {
            "name": "Welcome",
            "trigger": {"kind": "event", "event": "customer.customer.created"},
            "steps": [
                {"id": "s1", "kind": "delay", "seconds": 86400},
                {
                    "id": "s2",
                    "kind": "query",
                    "operation": "customer.customer.detail",
                    "params": {"id": "input.id"},
                },
                {
                    "id": "s3",
                    "kind": "command",
                    "operation": "task.task.create",
                    "params": {"title": "Welcome {{steps.s2.name}}"},
                },
            ],
        },
        ["customer.customer.detail", "task.task.create"],
    )
    run("customer.customer.create", {"name": "Eva Ruiz"}, ctx_for(actor="luis"))
    events.deliver(newest("customer.customer.created"))
    assert Task.objects.count() == 0
    clock(NOON + dt.timedelta(days=1))
    assert run("flow.run.resume_due", {}, system_context(A)).count == 1
    assert Task.objects.get().title == "Welcome Eva Ruiz"


def test_a_chain_of_real_events_is_stopped_when_it_would_start_itself_again():
    create_automation(
        {
            "name": "Welcome task",
            "trigger": {"kind": "event", "event": "customer.customer.created"},
            "steps": [
                {
                    "id": "s1",
                    "kind": "command",
                    "operation": "task.task.create",
                    "params": {"title": "Welcome"},
                }
            ],
        },
        ["task.task.create"],
    )
    follow_up = create_automation(
        {
            "name": "Every new task gets a follow-up",
            "trigger": {"kind": "event", "event": "task.task.created"},
            "steps": [
                {
                    "id": "s1",
                    "kind": "command",
                    "operation": "task.task.create",
                    "params": {"title": "Follow up"},
                }
            ],
        },
        ["task.task.create"],
    )
    run("customer.customer.create", {"name": "Eva"}, system_context(A))
    events.deliver(newest("customer.customer.created"))
    # The welcome task's event starts the follow-up, which creates its own task…
    events.deliver(newest("task.task.created"))
    assert sorted(Task.objects.values_list("title", flat=True)) == [
        "Follow up",
        "Welcome",
    ]
    # …whose event would start the follow-up again: it is stopped, visible, before doing anything.
    events.deliver(newest("task.task.created"))
    stopped = FlowRun.objects.filter(
        flow_id=follow_up, status=FlowRun.Status.FAILED
    ).get()
    assert stopped.error_code == "flow.loop_stopped"
    assert Task.objects.count() == 2
