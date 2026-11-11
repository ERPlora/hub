"""Erasing a customer's personal data (CUSTOMER-F16) reaches the automations (hub#1225): a run that could still go on
with what it read of her card — waiting (FLOW-F23), asking someone, or stopped by an error and resumable (FLOW-F24) —
is cancelled, saying why, and forgets what its steps read; nothing is sent to her and nothing of hers stays. The other
customers' runs go on, an automation that starts on the erasure still starts (FLOW-F21), a repeated delivery changes
nothing and an erasure in another business leaves this one's runs alone. In the same pass, every run that names her card
by its id, also one that has already ended, forgets the free texts its History keeps (hub#1227, FLOW-F16): an answer's
note, what the assistant or another app answered, the title of a question in a «no»; what happened stays.

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
    """Everything a run keeps that could hold a person's data, as one text: what started it, what its steps read, its
    History (its steps and why it ended) and the texts of its questions."""
    row.refresh_from_db()
    texts = list(Question.objects.filter(run=row).values_list("title", "details", "note"))
    kept = [row.input, row.outputs, row.error_message, row.error_reason, row.log, texts]
    return json.dumps(kept, default=str, ensure_ascii=False)


def run_that_read_her_card(status: str, steps: list[dict], **fields) -> tuple[FlowRun, Customer]:
    """A run of an automation started by hand, parked as ``status``, whose first step left her card."""
    flow = Flow.objects.create(name="By hand", trigger_kind=Flow.Trigger.MANUAL, steps=steps, enabled=True)
    customer = Customer.objects.create(name="Eva Ruiz")
    fields.setdefault("resume_at", timezone.now() + dt.timedelta(days=1))
    parked = make_run(flow, status=status, input={}, outputs={"s1": {"id": str(customer.id), "name": "Eva Ruiz"}}, **fields)
    return parked, customer


def erase(worker, customer_id) -> None:
    worker.request("customer.customer.erase", {"id": str(customer_id), "reason": "She asked (RGPD)"})


ERASED_TASK = {"id": "s9", "kind": "command", "operation": "task.task.create", "params": {"title": "Erased {{input.id}}"}}


def started_by_her_erasure(worker, steps: list[dict]) -> tuple[FlowRun, str]:
    """The run that an automation waiting for the erasure starts when her card is erased, and the card's id."""
    automation(steps, ["task.task.create"], trigger={"kind": "event", "event": "customer.customer.erased"})
    eva = worker.request("customer.customer.create", EVA)
    worker()
    erase(worker, eva.id)
    worker()
    return FlowRun.objects.get(event_name="customer.customer.erased"), str(eva.id)


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
def test_a_run_calling_another_system_with_her_card_is_cancelled_and_a_late_answer_changes_nothing():
    # The call left with no lock held (FLOW-F27): its answer comes back after the erasure and finds the run closed.
    call = {"id": "s2", "kind": "http", "method": "POST", "url": "https://example.com/orders", "timeout": 5}
    calling, customer = run_that_read_her_card(FlowRun.Status.CALLING, [A_DAY, call], step_index=1)

    assert run("flow.customer.erase", {"id": str(customer.id)}, system_context(A)).changed == 1

    late = run("flow.run.record_call", {"id": str(calling.id), "kind": "ok", "status": 200, "body": {"name": "Eva Ruiz"}},
               system_context(A))
    assert late.count == 0
    calling.refresh_from_db()
    assert (calling.status, calling.error_code, calling.outputs) == (FlowRun.Status.CANCELLED, "flow.customer_erased", {})


@pytest.mark.django_db
def test_a_question_of_the_run_answered_before_forgets_its_note_and_keeps_its_answer():
    # Two «Ask someone first» steps: the first was answered yes with a note about her, the second still waits.
    note = {"step": "s2", "kind": "ask", "outcome": "answered", "approved": True, "by": "tester",
            "note": "Eva Ruiz prefers the morning", "at": timezone.now().isoformat()}
    asking, customer = run_that_read_her_card(FlowRun.Status.ASKING, [A_DAY], log=[note])
    flow = asking.flow
    soon = timezone.now() + dt.timedelta(days=1)
    answered = Question.objects.create(
        run=asking, flow=flow, step_id="s2", title="Call Eva Ruiz?", details="Her phone: +34600111222",
        expires_at=soon, status=Question.Status.APPROVED, decided_by="tester", note="Eva Ruiz prefers the morning",
    )
    pending = Question.objects.create(run=asking, flow=flow, step_id="s3", title="Send Eva Ruiz a gift?", expires_at=soon)

    assert run("flow.customer.erase", {"id": str(customer.id)}, system_context(A)).changed == 1

    answered.refresh_from_db()
    pending.refresh_from_db()
    assert (answered.status, answered.title, answered.details, answered.note) == (Question.Status.APPROVED, "", "", "")
    assert (pending.status, pending.title) == (Question.Status.CANCELLED, "")
    # The step that told the answer still says who answered and what, without the note.
    assert "Eva Ruiz" not in stored(asking)
    assert [(e["outcome"], e["approved"], e["by"]) for e in asking.log] == [("answered", True, "tester")]


@pytest.mark.django_db
def test_a_run_that_ended_on_a_no_about_her_forgets_her_name_and_keeps_who_said_no(worker):
    # The issue's: «When a customer is created → read her card → ask "Call {name}?"», answered no with a note.
    ask = {"id": "s2", "kind": "ask", "title": "Call {{steps.s1.name}}?", "details": "Her phone: {{steps.s1.phone}}"}
    automation([READ_HER_CARD, ask, WELCOME_TASK], ["customer.customer.detail", "task.task.create"])
    eva = worker.request("customer.customer.create", EVA)
    worker()
    question = Question.objects.get()
    run("flow.question.answer", {"id": str(question.id), "approve": False, "note": "Eva Ruiz moved away"})
    ended = FlowRun.objects.get()
    assert (ended.status, ended.error_code, ended.outputs) == (FlowRun.Status.CANCELLED, "flow.question_rejected", {})
    assert "Eva Ruiz" in stored(ended) and "+34600111222" in stored(ended)  # positive control: in its History

    erase(worker, eva.id)
    worker()

    assert "Eva Ruiz" not in stored(ended) and "+34600111222" not in stored(ended)
    said = run("flow.run.get", {"id": str(ended.id)}, ctx_for(language="es")).model_dump(mode="json")
    assert "Eva Ruiz" not in json.dumps(said, ensure_ascii=False)
    # What happened stays: cancelled by a no, and who said it.
    assert (ended.status, ended.error_code, ended.error_reason["values"]["who"]) == (
        FlowRun.Status.CANCELLED, "flow.question_rejected", "tester",
    )
    assert [(e["outcome"], e.get("approved"), e.get("by")) for e in ended.log][-1] == ("answered", False, "tester")


def a_history_naming(name: str, at: str) -> list[dict]:
    """The steps of a run as its History keeps them, with every free text a step leaves naming ``name``: an answer's
    note, what the assistant answered and what another app answered when a step failed (and went on)."""
    return [
        {"step": "s1", "kind": "query", "operation": "customer.customer.detail", "outcome": "found", "count": 1,
         "at": at},
        {"step": "s2", "kind": "ask", "outcome": "answered", "approved": True, "by": "tester",
         "note": f"{name} prefers the morning", "at": at},
        {"step": "s3", "kind": "assistant", "outcome": "assistant_answered", "text": f"{name} has two bookings",
         "at": at},
        {"step": "s4", "kind": "command", "operation": "task.task.create", "outcome": "failed", "continued": True,
         "error": {"code": "task.title_taken", "message": f"Call {name} is already a task",
                   "technical": f"IntegrityError: Call {name}"}, "at": at},
    ]


#: How a run about her may have ended, each one keeping its History 90 days (FLOW-F16).
ENDINGS = {
    "finished well": {"status": FlowRun.Status.SUCCEEDED},
    "stopped by its condition": {"status": FlowRun.Status.STOPPED},
    "cancelled by a no": {
        "status": FlowRun.Status.CANCELLED,
        "error_code": "flow.question_rejected",
        "error_reason": {"key": "flow.question_rejected", "values": {"who": "tester", "title": "Call Eva Ruiz?"}},
        "error_message": "Cancelled: tester answered no to «Call Eva Ruiz?».",
    },
    "cancelled as nobody answered": {
        "status": FlowRun.Status.CANCELLED,
        "error_code": "flow.question_expired",
        "error_reason": {"key": "flow.question_expired", "values": {"title": "Call Eva Ruiz?"}},
        "error_message": "Cancelled: nobody answered «Call Eva Ruiz?» in time.",
    },
    "stopped by another app too long ago": {
        "status": FlowRun.Status.FAILED,
        "error_code": "task.title_taken",
        "error_message": "Call Eva Ruiz is already a task",
        "started_at": timezone.now() - dt.timedelta(days=9),
        "finished_at": timezone.now() - dt.timedelta(days=8),
    },
}


@pytest.mark.django_db
@pytest.mark.parametrize("ending", ENDINGS.values(), ids=ENDINGS.keys())
def test_a_run_about_her_that_has_ended_forgets_every_free_text_of_its_history(ending):
    flow = Flow.objects.create(name="Welcome", trigger_kind=Flow.Trigger.EVENT,
                               trigger_event="customer.customer.created", steps=[], enabled=True)
    eva, ana = Customer.objects.create(name="Eva Ruiz"), Customer.objects.create(name="Ana López")
    at = timezone.now().isoformat()
    fields = {"finished_at": timezone.now(), **ending}
    hers = make_run(flow, input={"id": str(eva.id)}, log=a_history_naming("Eva Ruiz", at), **fields)
    others = make_run(flow, input={"id": str(ana.id)}, log=a_history_naming("Ana López", at), **fields)
    kept_by_others = stored(others)
    assert "Eva Ruiz" in stored(hers)  # positive control

    assert run("flow.customer.erase", {"id": str(eva.id)}, system_context(A)).changed == 1

    assert "Eva Ruiz" not in stored(hers)
    assert (hers.status, hers.error_code) == (ending["status"], ending.get("error_code", ""))
    assert [entry["outcome"] for entry in hers.log] == ["found", "answered", "assistant_answered", "failed"]
    assert stored(others) == kept_by_others  # another customer's History is hers to keep
    # A repeated delivery changes nothing.
    assert run("flow.customer.erase", {"id": str(eva.id)}, system_context(A)).changed == 0


@pytest.mark.django_db
def test_a_run_the_erasure_itself_starts_is_not_cancelled_by_it(worker, clock):
    # The erasure first stops what kept her data and only then starts what waits for it: the run it starts, which
    # names the card by its id and waits a day, is not one of those it cancels.
    started, her_id = started_by_her_erasure(worker, [A_DAY, ERASED_TASK])

    assert (started.status, started.input) == (FlowRun.Status.WAITING, {"id": her_id})
    clock(timezone.now() + dt.timedelta(days=2))
    assert run("flow.run.resume_due", {}, system_context(A)).count == 1
    assert list(Task.objects.values_list("title", flat=True)) == [f"Erased {her_id}"]


@pytest.mark.django_db
def test_an_automation_that_starts_on_the_erasure_still_starts(worker):
    started, her_id = started_by_her_erasure(worker, [ERASED_TASK])
    assert started.status == FlowRun.Status.SUCCEEDED
    assert list(Task.objects.values_list("title", flat=True)) == [f"Erased {her_id}"]


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
