"""Erasing a customer's personal data (CUSTOMER-F16) reaches the automations (hub#1225): a run that could still go on
with what it read of her card — waiting (FLOW-F23), asking someone, or stopped by an error and resumable (FLOW-F24) —
is cancelled, saying why, and forgets what its steps read; nothing is sent to her and nothing of hers stays. The other
customers' runs go on, an automation that starts on the erasure still starts (FLOW-F21), a repeated delivery changes
nothing and an erasure in another business leaves this one's runs alone.

Through the real apps and the worker's real outbox relay (``worker``): Customers' own operation erases the card and
writes its notice; one tick hands it to flow.
"""

import datetime as dt
import json

import pytest
from django.utils import timezone
from live.context import Scope, system_context
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get

from apps.customer.models import Customer
from apps.flow import events
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.schemas import RunRefIn
from apps.task.models import Task
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

from .conftest import A, ctx_for, make_run, run

EVA = {"name": "Eva Ruiz", "phone": "+34600111222", "email": "eva@example.com"}
READ_HER_CARD = {"id": "s1", "kind": "query", "operation": "customer.customer.detail", "params": {"id": "input.id"}}
A_DAY = {"id": "s2", "kind": "delay", "seconds": 86400}
WELCOME_TASK = {
    "id": "s3",
    "kind": "command",
    "operation": "task.task.create",
    "params": {"title": "Welcome {{steps.s1.name}}"},
}
ON_A_NEW_CUSTOMER = {"kind": "event", "event": "customer.customer.created"}


def automation(steps: list[dict], operations: list[str], trigger: dict = ON_A_NEW_CUSTOMER, ctx=None) -> str:
    """An automation as the owner makes it: created, granted and turned on through its operations."""
    created = run("flow.flow.create", {"name": "Welcome", "trigger": trigger, "steps": steps}, ctx)
    run("flow.flow.grant", {"id": str(created.id), "operations": operations}, ctx)
    run("flow.flow.set_enabled", {"id": str(created.id), "enabled": True}, ctx)
    return str(created.id)


def welcome_a_day_later() -> str:
    """«When a customer is created → read her card → wait a day → create the task "Welcome {name}"» (the issue's)."""
    return automation([READ_HER_CARD, A_DAY, WELCOME_TASK], ["customer.customer.detail", "task.task.create"])


def stored(row: FlowRun) -> str:
    """Everything a run keeps that could hold a person's data, as one text."""
    return json.dumps([row.input, row.outputs, row.error_message], default=str, ensure_ascii=False)


def erase(worker, customer_id) -> None:
    worker.request("customer.customer.erase", {"id": str(customer_id), "reason": "She asked (RGPD)"})


@pytest.mark.django_db
def test_a_waiting_run_that_read_her_card_is_cancelled_and_never_sends_her_anything(worker, clock):
    welcome_a_day_later()
    eva = worker.request("customer.customer.create", EVA)
    worker()
    waiting = FlowRun.objects.get()
    assert waiting.status == FlowRun.Status.WAITING
    assert "Eva Ruiz" in stored(waiting) and "+34600111222" in stored(waiting)  # positive control: it read her card

    erase(worker, eva.id)
    worker()

    waiting.refresh_from_db()
    assert (waiting.status, waiting.error_code) == (FlowRun.Status.CANCELLED, "flow.customer_erased")
    assert waiting.error_reason == {"key": "flow.customer_erased", "values": {}}
    assert waiting.outputs == {}
    assert waiting.finished_at is not None and waiting.resume_at is None
    assert "Eva Ruiz" not in stored(waiting) and "+34600111222" not in stored(waiting)
    finished = OutboxEvent.objects.filter(name=events.RUN_FINISHED, payload__id=str(waiting.id)).get()
    assert finished.payload["status"] == "cancelled"

    clock(timezone.now() + dt.timedelta(days=2))
    assert run("flow.run.resume_due", {}, system_context(A)).count == 0
    assert not Task.objects.exists()


@pytest.mark.django_db
def test_the_history_says_why_in_the_readers_language(worker):
    welcome_a_day_later()
    eva = worker.request("customer.customer.create", EVA)
    worker()
    erase(worker, eva.id)
    worker()
    waiting = FlowRun.objects.get()
    row = run("flow.run.get", {"id": str(waiting.id)}, ctx_for(language="es"))
    assert row.error_code == "flow.customer_erased"
    assert row.error_message == "Cancelada: se borraron los datos personales del cliente."


@pytest.mark.django_db
def test_the_runs_of_other_customers_go_on(worker, clock):
    welcome_a_day_later()
    eva = worker.request("customer.customer.create", EVA)
    worker.request("customer.customer.create", {"name": "Ana López"})
    worker()
    assert FlowRun.objects.filter(status=FlowRun.Status.WAITING).count() == 2

    erase(worker, eva.id)
    worker()

    left = FlowRun.objects.get(status=FlowRun.Status.WAITING)
    assert "Ana López" in stored(left)
    clock(timezone.now() + dt.timedelta(days=2))
    assert run("flow.run.resume_due", {}, system_context(A)).count == 1
    assert list(Task.objects.values_list("title", flat=True)) == ["Welcome Ana López"]


@pytest.mark.django_db
def test_a_run_stopped_by_an_error_that_could_be_resumed_is_cancelled_and_cannot_be_resumed(worker):
    # The task is not granted: the run reads her card and stops at the task, resumable for 7 days (FLOW-F24).
    automation([READ_HER_CARD, WELCOME_TASK | {"id": "s2"}], ["customer.customer.detail"])
    eva = worker.request("customer.customer.create", EVA)
    worker()
    failed = FlowRun.objects.get()
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.not_allowed")
    assert run("flow.run.get", {"id": str(failed.id)}).resumable is True  # positive control
    assert "Eva Ruiz" in stored(failed)

    erase(worker, eva.id)
    worker()

    failed.refresh_from_db()
    assert (failed.status, failed.error_code) == (FlowRun.Status.CANCELLED, "flow.customer_erased")
    assert failed.outputs == {}
    assert "Eva Ruiz" not in stored(failed)
    # The step that had failed is still told in its steps: the history keeps what happened.
    assert failed.log[-1]["outcome"] == "failed" and failed.log[-1]["error"]["code"] == "flow.not_allowed"
    run("flow.flow.grant", {"id": str(failed.flow_id), "operations": ["customer.customer.detail", "task.task.create"]})
    with pytest.raises(Conflict) as refused:
        get("flow.run.retry")(ctx_for(), RunRefIn(id=failed.id))
    assert refused.value.code == "flow.run_not_resumable"
    assert not Task.objects.exists()


@pytest.mark.django_db
def test_a_run_stopped_at_its_first_step_about_her_is_cancelled_too(worker):
    # Nothing read yet, but resumable: resumed, it would go on about her.
    automation([WELCOME_TASK | {"id": "s1", "params": {"title": "Follow up"}}], [],
               trigger={"kind": "event", "event": "customer.customer.updated"})
    eva = worker.request("customer.customer.create", EVA)
    worker.request("customer.customer.update", {"id": str(eva.id), "city": "Sevilla"})
    worker()
    failed = FlowRun.objects.get()
    assert (failed.status, failed.outputs) == (FlowRun.Status.FAILED, {})
    assert run("flow.run.get", {"id": str(failed.id)}).resumable is True  # positive control

    erase(worker, eva.id)
    worker()

    assert FlowRun.objects.get().status == FlowRun.Status.CANCELLED


@pytest.mark.django_db
def test_a_run_stopped_by_an_error_too_long_ago_only_forgets_what_it_read(worker):
    automation([READ_HER_CARD, WELCOME_TASK | {"id": "s2"}], ["customer.customer.detail"])
    eva = worker.request("customer.customer.create", EVA)
    worker()
    old = FlowRun.objects.get()
    eight_days_ago = timezone.now() - dt.timedelta(days=8)
    FlowRun.objects.filter(pk=old.pk).update(finished_at=eight_days_ago)  # not pruned yet: the hourly pass is due
    assert "Eva Ruiz" in stored(FlowRun.objects.get(pk=old.pk))  # positive control

    erase(worker, eva.id)
    worker()

    old.refresh_from_db()
    assert (old.status, old.error_code, old.finished_at) == (FlowRun.Status.FAILED, "flow.not_allowed", eight_days_ago)
    assert old.outputs == {}


@pytest.mark.django_db
def test_a_run_asking_about_her_closes_its_question_and_forgets_its_texts(worker):
    ask = {
        "id": "s2",
        "kind": "ask",
        "title": "Call {{steps.s1.name}} to welcome her?",
        "details": "Her phone: {{steps.s1.phone}}",
    }
    automation([READ_HER_CARD, ask, WELCOME_TASK], ["customer.customer.detail", "task.task.create"])
    eva = worker.request("customer.customer.create", EVA)
    worker()
    question = Question.objects.get()
    assert (question.title, question.details) == ("Call Eva Ruiz to welcome her?", "Her phone: +34600111222")
    assert FlowRun.objects.get().status == FlowRun.Status.ASKING
    assert len(run("flow.question.list", {}).rows) == 1  # positive control: waiting for an answer

    erase(worker, eva.id)
    worker()

    question.refresh_from_db()
    assert (question.status, question.title, question.details) == (Question.Status.CANCELLED, "", "")
    asking = FlowRun.objects.get()
    assert (asking.status, asking.error_code) == (FlowRun.Status.CANCELLED, "flow.customer_erased")
    assert run("flow.question.list", {}).rows == []
    assert not Task.objects.exists()


@pytest.mark.django_db
def test_a_run_started_by_another_apps_notice_about_her_is_cancelled_too(worker):
    # What the run keeps names her card only by its id in the notice that started it (no card read).
    automation([A_DAY, WELCOME_TASK | {"params": {"title": "Follow up"}}], ["task.task.create"],
               trigger={"kind": "event", "event": "customer.customer.updated"})
    eva = worker.request("customer.customer.create", EVA)
    worker.request("customer.customer.update", {"id": str(eva.id), "city": "Sevilla"})
    worker()
    waiting = FlowRun.objects.get()
    assert waiting.input == {"id": str(eva.id)}

    erase(worker, eva.id)
    worker()

    assert FlowRun.objects.get().status == FlowRun.Status.CANCELLED


@pytest.mark.django_db
def test_a_run_that_only_read_her_card_is_cancelled_too():
    # Started by something else (by hand, a schedule): only what its steps read names her.
    flow = Flow.objects.create(name="Morning list", trigger_kind=Flow.Trigger.MANUAL, steps=[A_DAY], enabled=True)
    customer = Customer.objects.create(name="Eva Ruiz")
    waiting = make_run(
        flow,
        status=FlowRun.Status.WAITING,
        resume_at=timezone.now() + dt.timedelta(days=1),
        input={},
        outputs={"s1": {"rows": [{"id": str(customer.id), "name": "Eva Ruiz"}]}},
    )

    assert run("flow.customer.erase", {"id": str(customer.id)}, system_context(A)).changed == 1

    waiting.refresh_from_db()
    assert (waiting.status, waiting.outputs) == (FlowRun.Status.CANCELLED, {})


@pytest.mark.django_db
def test_an_automation_that_starts_on_the_erasure_still_starts(worker):
    automation(
        [{"id": "s1", "kind": "command", "operation": "task.task.create", "params": {"title": "Erased {{input.id}}"}}],
        ["task.task.create"],
        trigger={"kind": "event", "event": "customer.customer.erased"},
    )
    eva = worker.request("customer.customer.create", EVA)
    worker()
    erase(worker, eva.id)
    worker()
    started = FlowRun.objects.get(event_name="customer.customer.erased")
    assert started.status == FlowRun.Status.SUCCEEDED
    assert list(Task.objects.values_list("title", flat=True)) == [f"Erased {eva.id}"]


@pytest.mark.django_db
def test_a_repeated_delivery_changes_nothing(worker):
    welcome_a_day_later()
    eva = worker.request("customer.customer.create", EVA)
    worker()
    erase(worker, eva.id)
    worker()
    erased = OutboxEvent.objects.get(name="customer.customer.erased")
    finished = OutboxEvent.objects.filter(name=events.RUN_FINISHED).count()

    again = get("flow.customer.erase")(system_context(A), get("flow.customer.erase").input.model_validate(erased.payload))

    assert again.changed == 0
    assert OutboxEvent.objects.filter(name=events.RUN_FINISHED).count() == finished


@pytest.mark.django_db
def test_only_the_platform_runs_it():
    from live.errors import PermissionDenied

    with pytest.raises(PermissionDenied):
        run("flow.customer.erase", {"id": "0199f6a0-6b1f-7c3e-9a51-3f1b2c4d5e6f"}, ctx_for("hub_owner"))


@pytest.mark.django_db
def test_a_run_of_a_card_of_the_same_id_in_the_history_finished_well_is_left_as_it_was():
    # A finished run keeps no card (FLOW-F16 shows it): nothing to cancel nor to forget.
    flow = Flow.objects.create(name="Done", trigger_kind=Flow.Trigger.MANUAL, steps=[], enabled=True)
    customer = Customer.objects.create(name="Eva Ruiz")
    done = make_run(flow, input={"id": str(customer.id)}, finished_at=timezone.now())
    assert run("flow.customer.erase", {"id": str(customer.id)}, system_context(A)).changed == 0
    done.refresh_from_db()
    assert (done.status, done.input) == (FlowRun.Status.SUCCEEDED, {"id": str(customer.id)})


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_an_erasure_in_another_business_leaves_this_ones_runs_alone(hub_a, hub_b):
    """Each business in its own database, as production: the same id erased in B cancels nothing in A."""
    in_a, in_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)
    with use_hub(hub_a):
        automation([READ_HER_CARD, A_DAY, WELCOME_TASK], ["customer.customer.detail", "task.task.create"],
                   ctx=ctx_for(scope=in_a))
        eva = run("customer.customer.create", EVA, ctx_for(scope=in_a))
        events.deliver(OutboxEvent.objects.get(name="customer.customer.created"))
        assert FlowRun.objects.get().status == FlowRun.Status.WAITING
    with use_hub(hub_b):
        assert run("flow.customer.erase", {"id": str(eva.id)}, system_context(in_b)).changed == 0
    with use_hub(hub_a):
        assert FlowRun.objects.get().status == FlowRun.Status.WAITING
        assert run("flow.customer.erase", {"id": str(eva.id)}, system_context(in_a)).changed == 1  # positive control
        assert FlowRun.objects.get().status == FlowRun.Status.CANCELLED
