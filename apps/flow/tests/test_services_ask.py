"""«Ask someone first» (WORKBOOK FLOW-F28, F29 and F30; old hub HUB-F96, HUB-F100, HUB-F101; the old module's
flows-f18 and flows-f24).

A run that reaches the step leaves its question — title and details filled in at that moment — in «Waiting
for you» and waits. Only the role it was asked of answers it (whoever runs the business always can); a yes
carries the run on, a no does what the step says, and a question nobody answered in time is closed by the
minute's sweep, which does what the step says for silence. Every decision is taken once. The cases are the
old hub's `flow_approval_step.rs`, `flow_approval_once.rs` and `flow_approval_expiry.rs`; the actions are the
real ones of Tasks.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pydantic
import pytest
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied

from apps.flow.models import Flow, FlowRun, Question
from apps.task.models import Task

from .conftest import A, TASK_STEP, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
AFTER = TASK_STEP | {"id": "s2", "params": {"title": "After the answer"}}


def ask(**over):
    return {"id": "s1", "kind": "ask", "title": "Refund {{input.amount}} to {{input.name}}?", **over}


def _flow(*steps, **fields):
    return make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=list(steps), grants=["task.task.create"], **fields)


def _asked(step=None, *more, data=None, **fields):
    flow = _flow(step or ask(), *(more or (AFTER,)), **fields)
    ran = run("flow.flow.run", {"id": str(flow.id), "input": data or {"amount": "12,50 €", "name": "Ana"}})
    return flow, FlowRun.objects.get(pk=ran.id), Question.objects.get(run_id=ran.id)


def _answer(question, approve=True, note="", ctx=None):
    return run("flow.question.answer", {"id": str(question.id), "approve": approve, "note": note}, ctx or ctx_for())


def _inbox(ctx):
    return [row.id for row in run("flow.question.list", {}, ctx).rows]


def _sweep():
    return run("flow.question.expire_due", {}, system_context(A))


# --- Asking (FLOW-F28) -------------------------------------------------------------------------------


def test_a_run_stops_on_its_question_with_the_text_filled_in_and_needs_no_permission(clock):
    clock(NOON)
    flow, ran, question = _asked(ask(details="Sale {{input.name}}", role="manager", hours=24))
    assert flow.grants == ["task.task.create"]  # asking is no action: nothing to allow
    assert ran.status == FlowRun.Status.ASKING
    assert (question.title, question.details, question.role, question.status) == (
        "Refund 12,50 € to Ana?",
        "Sale Ana",
        "manager",
        Question.Status.PENDING,
    )
    assert question.expires_at == NOON + dt.timedelta(hours=24)
    assert ran.log[-1] | {"at": None} == {
        "step": "s1",
        "kind": "ask",
        "outcome": "asking",
        "role": "manager",
        "until": (NOON + dt.timedelta(hours=24)).isoformat(),
        "at": None,
    }
    assert not Task.objects.exists()


def test_by_default_it_asks_whoever_runs_the_business_and_waits_three_days(clock):
    clock(NOON)
    _, _, question = _asked()
    assert question.role == ""
    assert question.expires_at == NOON + dt.timedelta(hours=72)
    assert (question.on_no, question.on_timeout) == ("stop", "no")


@pytest.mark.parametrize("bad", [{"hours": 0}, {"hours": 721}, {"title": ""}, {"title": "   "}, {"role": "owner"}])
def test_a_question_without_text_or_outside_one_hour_and_thirty_days_is_not_saved(bad):
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [ask(**bad)]})


def test_its_text_may_not_read_a_secret():
    with pytest.raises(pydantic.ValidationError, match="only go in «Call another system»"):
        run("flow.flow.create", {"steps": [ask(title="Key {{secret.STRIPE_KEY}}")]})


def test_no_condition_may_compare_with_a_secret_or_the_call_key():
    # A condition's data are refused as no data of the automation; what it compares with was let through.
    cond = {"id": "s1", "kind": "condition", "when": {"input.total": {"eq": "{{secret.STRIPE_KEY}}"}}}
    with pytest.raises(pydantic.ValidationError, match="only go in «Call another system»"):
        run("flow.flow.create", {"steps": [cond]})
    only_if = TASK_STEP | {"run_if": {"input.total": {"eq": "{{run.idempotency_key}}"}}}
    with pytest.raises(pydantic.ValidationError, match="only go in «Call another system»"):
        run("flow.flow.create", {"steps": [only_if]})


def test_editing_the_automation_does_not_change_a_question_already_asked(clock):
    clock(NOON)
    flow, ran, question = _asked()
    run("flow.flow.update", {"id": str(flow.id), "steps": [ask(title="Something else")]})
    question.refresh_from_db()
    assert question.title == "Refund 12,50 € to Ana?"
    _answer(question)
    assert Task.objects.filter(title="After the answer").count() == 1


# --- Who sees and answers it (FLOW-F29) ----------------------------------------------------------------


def test_waiting_for_you_lists_only_what_each_person_may_answer(clock):
    clock(NOON)
    _, _, to_admins = _asked()
    _, _, to_managers = _asked(ask(role="manager"))
    _, _, to_employees = _asked(ask(role="employee"))
    assert _inbox(ctx_for("hub_admin")) == [to_admins.id, to_managers.id, to_employees.id]
    assert _inbox(ctx_for("hub_manager")) == [to_managers.id, to_employees.id]
    assert _inbox(ctx_for("hub_employee")) == [to_employees.id]
    row = run("flow.question.list", {}, ctx_for("hub_employee")).rows[0]
    assert (row.title, row.flow_name, row.role, row.on_no, row.on_timeout) == (
        "Refund 12,50 € to Ana?",
        "Welcome",
        "employee",
        "stop",
        "no",
    )


def test_a_person_without_any_answer_permission_has_no_inbox():
    with pytest.raises(PermissionDenied):
        run("flow.question.list", {}, ctx_for(permissions={"task.view"}))


def test_only_the_role_it_was_asked_of_answers_and_whoever_runs_the_business_always_can(clock):
    clock(NOON)
    _, _, question = _asked(ask(role="manager"))
    with pytest.raises(PermissionDenied) as refused:
        _answer(question, ctx=ctx_for("hub_employee"))
    assert refused.value.code == "flow.question_not_yours"
    question.refresh_from_db()
    assert question.status == Question.Status.PENDING
    _answer(question, ctx=ctx_for("hub_manager"))
    _, _, to_admins = _asked()
    with pytest.raises(PermissionDenied):
        _answer(to_admins, ctx=ctx_for("hub_manager"))
    _answer(to_admins, ctx=ctx_for("hub_owner"))


def test_a_yes_carries_the_run_on_and_leaves_the_answer_for_the_next_steps(clock, make_user):
    clock(NOON)
    marta = make_user("marta", first_name="Marta")
    later = TASK_STEP | {"id": "s2", "run_if": {"steps.s1.approved": {"eq": True}}, "params": {"title": "Approved by {{steps.s1.answered_by}}: {{steps.s1.note}}"}}
    _, ran, question = _asked(ask(), later)
    answered = _answer(question, note="ok, go", ctx=ctx_for(actor=marta))
    assert answered.status == "succeeded"
    assert list(Task.objects.values_list("title", flat=True)) == ["Approved by Marta: ok, go"]
    question.refresh_from_db()
    assert (question.status, question.decided_by, question.note) == (Question.Status.APPROVED, "Marta", "ok, go")
    ran.refresh_from_db()
    assert [entry["outcome"] for entry in ran.log] == ["asking", "answered", "done"]
    assert ran.log[1] | {"at": None} == {"step": "s1", "kind": "ask", "outcome": "answered", "approved": True, "by": "Marta", "note": "ok, go", "at": None}


def test_a_no_ends_the_run_and_the_steps_after_it_never_run(clock):
    clock(NOON)
    _, ran, question = _asked()
    answered = _answer(question, approve=False, note="too much")
    assert answered.status == "cancelled"
    ran.refresh_from_db()
    assert ran.error_code == "flow.question_rejected"
    assert ran.error_message == "Cancelled: tester answered no to «Refund 12,50 € to Ana?»."
    assert not Task.objects.exists()


def test_a_no_with_carry_on_runs_the_next_steps_saying_it_was_no(clock):
    clock(NOON)
    later = TASK_STEP | {"id": "s2", "run_if": {"steps.s1.approved": {"eq": False}}, "params": {"title": "They said no"}}
    _, _, question = _asked(ask(on_no="continue"), later)
    assert _answer(question, approve=False).status == "succeeded"
    assert list(Task.objects.values_list("title", flat=True)) == ["They said no"]


def test_deciding_twice_does_it_once_and_the_second_is_refused_by_name(clock):
    clock(NOON)
    _, _, question = _asked()
    _answer(question)
    with pytest.raises(Conflict) as refused:
        _answer(question, approve=False)
    assert refused.value.code == "flow.question_decided"
    assert Task.objects.count() == 1


def test_a_question_past_its_time_is_too_late_even_before_the_sweep(clock):
    clock(NOON)
    _, _, question = _asked(ask(hours=1))
    clock(NOON + dt.timedelta(hours=1))
    with pytest.raises(Conflict) as refused:
        _answer(question)
    assert refused.value.code == "flow.question_expired"
    assert not Task.objects.exists()


def test_a_paused_automation_refuses_a_yes_in_the_person_s_language_and_keeps_the_question(clock):
    # flows#166: the old tray said why in English.
    clock(NOON)
    flow, _, question = _asked()
    run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": False})
    with pytest.raises(Conflict) as refused:
        _answer(question, ctx=ctx_for(language="es"))
    assert refused.value.code == "flow.disabled"
    assert refused.value.message == "Esta automatización está en pausa: enciéndela para ejecutarla."
    question.refresh_from_db()
    assert question.status == Question.Status.PENDING
    # A no that ends the run is still taken.
    assert _answer(question, approve=False).status == "cancelled"


def test_an_unknown_question_is_not_found():
    with pytest.raises(NotFound):
        run("flow.question.answer", {"id": "0199f6a0-6b1f-7c3e-9a51-3f1b2c4d5e6f", "approve": True})


def test_deleting_the_automation_cancels_its_question(clock):
    clock(NOON)
    flow, ran, question = _asked()
    run("flow.flow.delete", {"id": str(flow.id)})
    ran.refresh_from_db()
    question.refresh_from_db()
    assert (ran.status, question.status) == (FlowRun.Status.CANCELLED, Question.Status.CANCELLED)
    assert _inbox(ctx_for()) == []
    with pytest.raises(Conflict) as refused:
        _answer(question)
    assert refused.value.code == "flow.question_decided"


# --- Nobody answered in time (FLOW-F30) -----------------------------------------------------------------


def test_by_default_a_question_nobody_answered_counts_as_a_no_and_the_run_ends(clock):
    clock(NOON)
    _, ran, question = _asked(ask(hours=2))
    clock(NOON + dt.timedelta(hours=1))
    assert _sweep().count == 0
    clock(NOON + dt.timedelta(hours=2))
    assert _sweep().count == 1
    ran.refresh_from_db()
    question.refresh_from_db()
    assert (question.status, question.decided_by) == (Question.Status.EXPIRED, "")
    assert (ran.status, ran.error_code) == (FlowRun.Status.CANCELLED, "flow.question_expired")
    assert ran.error_message == "Cancelled: nobody answered «Refund 12,50 € to Ana?» in time."
    assert ran.log[-1]["outcome"] == "expired"
    assert not Task.objects.exists()
    assert _sweep().count == 0  # a second sweep finds nothing


def test_silence_counted_as_a_no_does_what_a_no_does(clock):
    clock(NOON)
    _asked(ask(hours=1, on_no="continue"))
    clock(NOON + dt.timedelta(hours=1))
    _sweep()
    assert Task.objects.filter(title="After the answer").count() == 1


def test_silence_can_stop_the_run_even_when_a_no_would_carry_on(clock):
    clock(NOON)
    _, ran, _ = _asked(ask(hours=1, on_no="continue", on_timeout="stop"))
    clock(NOON + dt.timedelta(hours=1))
    _sweep()
    ran.refresh_from_db()
    assert ran.status == FlowRun.Status.CANCELLED
    assert not Task.objects.exists()


def test_silence_can_carry_on_saying_nobody_answered(clock):
    clock(NOON)
    later = TASK_STEP | {"id": "s2", "run_if": {"steps.s1.expired": {"eq": True}}, "params": {"title": "Nobody answered"}}
    _, ran, _ = _asked(ask(hours=1, on_timeout="continue"), later)
    clock(NOON + dt.timedelta(hours=1))
    _sweep()
    ran.refresh_from_db()
    assert ran.status == FlowRun.Status.SUCCEEDED
    assert list(Task.objects.values_list("title", flat=True)) == ["Nobody answered"]


def test_an_expired_question_is_refused_as_expired_not_as_answered(clock):
    clock(NOON)
    _, _, question = _asked(ask(hours=1))
    clock(NOON + dt.timedelta(hours=1))
    _sweep()
    with pytest.raises(Conflict) as refused:
        _answer(question)
    assert refused.value.code == "flow.question_expired"


def test_silence_that_would_carry_on_a_paused_automation_cancels_it(clock):
    clock(NOON)
    flow, ran, _ = _asked(ask(hours=1, on_timeout="continue"))
    run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": False})
    clock(NOON + dt.timedelta(hours=1))
    _sweep()
    ran.refresh_from_db()
    assert (ran.status, ran.error_code) == (FlowRun.Status.CANCELLED, "flow.paused")
    assert not Task.objects.exists()


def test_the_sweep_runs_every_minute_as_the_platform_only():
    from apps.flow.apps import FlowConfig

    task = next(task for task in FlowConfig.scheduled_tasks if task["operation"] == "flow.question.expire_due")
    assert task["cron"] == "* * * * *"
    with pytest.raises(PermissionDenied):
        run("flow.question.expire_due", {}, ctx_for())


def test_try_it_says_what_it_would_ask_and_that_the_answer_is_not_known_yet():
    steps = [
        ask(details="for {{input.name}}"),
        {"id": "s2", "kind": "condition", "when": {"steps.s1.approved": {"eq": True}}},
    ]
    tried = run(
        "flow.flow.test",
        {"document": '{"trigger": {"kind": "manual"}, "steps": ' + __import__("json").dumps(steps) + "}"},
    )
    first, second = tried.steps
    assert (first.outcome, first.params) == (
        "would_ask",
        {"title": "Refund  to ?", "details": "for ", "role": "", "hours": 72},
    )
    assert second.outcome == "cannot_tell"
    assert not Question.objects.exists()

