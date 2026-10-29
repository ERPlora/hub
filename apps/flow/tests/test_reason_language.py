"""Why a run stopped, in the language of whoever reads the History (FLOW-F16, FLOW-F25).

The engine keeps each of its own reasons by name and values and says it when it is read, in the reader's language,
as the WhatsApp inbox does with why a message did not leave (hub#384); what an action of another app answered is
said as it answered. What the steps after a failure read (``steps.<id>.error_message``) stays in the automation's
language, the one its steps write in. A run kept before the name was (only its words) says a reason with no values
in the reader's language, and one with values as it was kept.
"""

import uuid

import pytest
from django.utils import translation

from apps.flow import events, queries
from apps.flow.models import Flow, FlowRun, Question

from .conftest import A, TASK_STEP, make_flow, make_run, run, ctx_for

pytestmark = pytest.mark.django_db

NOT_ALLOWED = {
    "en": "It tried to do something you have not allowed it to do («task.task.create»), so it stopped. "
    "Open Permissions and allow what it needs.",
    "es": "Ha intentado hacer algo que no le has permitido («task.task.create»), así que ha parado. "
    "Abre Permisos y concédele lo que necesita.",
}
DELETED = {"en": "Cancelled: the automation was deleted.", "es": "Cancelada: la automatización se borró."}
OTHER = {"en": "es", "es": "en"}


def deliver(name: str = "customer.customer.created", payload: dict | None = None, actor: str = "system"):
    events.react(A, name, payload or {}, event_id=uuid.uuid7(), actor=actor)


def history(flow: Flow, language: str):
    """The History of ``flow`` as a person whose screen is in ``language`` reads it."""
    return run("flow.run.list", {"flow_id": str(flow.id)}, ctx_for(language=language)).rows


@pytest.mark.parametrize("saved", ["es", "en"])
def test_a_step_the_engine_stopped_is_said_in_the_reader_s_language(saved):
    flow = make_flow(grants=[], language=saved)
    deliver()
    read = OTHER[saved]
    [row] = history(flow, read)
    assert (row.error_code, row.error_message) == ("flow.not_allowed", NOT_ALLOWED[read])
    assert row.log[0]["error"] == {"code": "flow.not_allowed", "message": NOT_ALLOWED[read]}


def test_running_or_resuming_it_answers_in_the_language_of_who_does_it():
    flow = make_flow(grants=[], language="en", trigger_kind=Flow.Trigger.MANUAL)
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}}, ctx_for(language="es"))
    assert (ran.status, ran.error_message) == ("failed", NOT_ALLOWED["es"])
    again = run("flow.run.retry", {"id": str(ran.id)}, ctx_for(language="es"))
    assert (again.status, again.error_message) == ("failed", NOT_ALLOWED["es"])
    assert again.log[-1]["error"]["message"] == NOT_ALLOWED["es"]


def test_a_resumed_run_that_now_waits_says_no_reason():
    flow = make_flow(grants=[], language="es", steps=[TASK_STEP, {"id": "s2", "kind": "delay", "seconds": 3600}])
    deliver()
    failed = FlowRun.objects.get()
    Flow.objects.filter(pk=flow.pk).update(grants=["task.task.create"])
    run("flow.run.retry", {"id": str(failed.id)})
    [row] = history(flow, "en")
    assert (row.status, row.error_code, row.error_message) == ("waiting", "", "")


def test_the_steps_after_a_failure_read_it_in_the_automation_s_language():
    flow = make_flow(grants=[], language="es", steps=[TASK_STEP | {"on_error": "continue"}, TASK_STEP | {"id": "s2"}])
    deliver()
    kept = FlowRun.objects.get()
    assert kept.outputs["s1"] == {"failed": True, "error_code": "flow.not_allowed", "error_message": NOT_ALLOWED["es"]}
    [row] = history(flow, "en")
    assert [entry["error"]["message"] for entry in row.log] == [NOT_ALLOWED["en"], NOT_ALLOWED["en"]]


def test_what_an_action_of_another_app_answered_is_said_as_it_answered():
    flow = make_flow(language="es", steps=[TASK_STEP | {"params": {"title": "x", "project": "No such project"}}])
    deliver()
    kept = FlowRun.objects.get()
    tasks_words = "Ese proyecto no existe en este negocio."  # Tasks' own, in the language its step ran in
    assert (kept.error_code, kept.error_message) == ("invalid_field", tasks_words)
    [row] = history(flow, "en")
    assert row.error_message == tasks_words
    assert row.log[0]["error"]["message"] == tasks_words


def test_a_run_cancelled_while_it_waited_is_said_in_the_reader_s_language():
    flow = make_flow(language="es", trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "delay", "seconds": 3600}])
    run("flow.flow.run", {"id": str(flow.id), "input": {}})
    run("flow.flow.delete", {"id": str(flow.id)})
    assert FlowRun.objects.get().error_message == DELETED["es"]
    [row] = history(flow, "en")
    assert (row.error_code, row.error_message) == ("flow.deleted", DELETED["en"])


def test_a_no_is_said_in_the_reader_s_language_with_who_and_what_was_asked():
    flow = make_flow(language="es", trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "ask", "title": "Refund {{input.amount}}?"}])
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {"amount": "12,50 €"}})
    question = Question.objects.get(run_id=ran.id)
    run("flow.question.answer", {"id": str(question.id), "approve": False})
    assert FlowRun.objects.get().error_message == "Cancelada: tester contestó que no a «Refund 12,50 €?»."
    [row] = history(flow, "en")
    assert row.error_message == "Cancelled: tester answered no to «Refund 12,50 €?»."


def test_a_chain_too_long_says_how_long_in_the_reader_s_language():
    first = make_flow("First", trigger_event="task.task.created", language="es")
    other = make_flow("Other", trigger_event="task.task.created", steps=[], grants=[])
    too_deep = make_run(other, chain=[str(uuid.uuid7()) for _ in range(7)])
    deliver("task.task.created", {"id": "t"}, actor=f"flow_run:{too_deep.id}")
    [row] = history(first, "en")
    assert (row.error_code, row.error_message) == (
        "flow.loop_stopped",
        "A chain of 9 automations started it, more than the 8 allowed, so it stopped before doing anything.",
    )


def test_a_call_that_answered_an_error_is_said_in_the_reader_s_language(django_capture_on_commit_callbacks):
    origin = "https://api.example.com"
    step = {"id": "s1", "kind": "http", "method": "POST", "url": f"{origin}/orders", "timeout": 5}
    flow = make_flow(language="es", trigger_kind=Flow.Trigger.MANUAL, steps=[step], grants=[f"http:{origin}"])
    with django_capture_on_commit_callbacks(execute=False):
        ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    system = ctx_for(permissions={"flow.system"})
    run("flow.run.record_call", {"id": str(ran.id), "kind": "status", "status": 503, "body": {}}, system)
    assert FlowRun.objects.get().error_message == "«api.example.com» respondió 503, así que se ha parado."
    [row] = history(flow, "en")
    assert (row.error_code, row.error_message) == ("flow.http_status", "«api.example.com» answered 503, so it stopped.")


def test_a_run_kept_before_its_reason_had_a_name_still_says_something():
    flow = make_flow(language="es")
    make_run(flow, status=FlowRun.Status.CANCELLED, error_code="flow.deleted", error_message=DELETED["es"])
    failed = {"code": "flow.not_allowed", "message": NOT_ALLOWED["es"]}
    make_run(
        flow,
        status=FlowRun.Status.FAILED,
        error_code="flow.not_allowed",
        error_message=NOT_ALLOWED["es"],
        log=[{"step": "s1", "kind": "command", "operation": "task.task.create", "outcome": "failed", "error": failed}],
    )
    rows = {row.error_code: row for row in history(flow, "en")}
    assert rows["flow.deleted"].error_message == DELETED["en"]
    # Its values (which action) were not kept: it is said as it was.
    assert rows["flow.not_allowed"].error_message == NOT_ALLOWED["es"]
    assert rows["flow.not_allowed"].log[0]["error"] == failed


def test_every_reason_of_the_engine_is_said_in_english_and_in_spanish():
    values = {
        "name": "task.task.create",
        "operation": "task.task.create",
        "host": "api.example.com",
        "status": 503,
        "seconds": 5,
        "n": 6,
        "who": "Ana",
        "title": "Refund?",
        "count": 9,
        "max": 8,
    }
    assert len(queries.REASONS) >= 25  # positive control: the engine's reasons are all named
    for key in queries.REASONS:
        reason = {"key": key, "values": values}
        with translation.override("en"):
            english = queries.say(reason)
        with translation.override("es"):
            spanish = queries.say(reason)
        assert english and spanish and english != spanish, key
