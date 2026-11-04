"""An automation books and moves the appointment of any professional (FIX-HUB-FLOW-STEP-CANNOT-BOOK-FOR-A-PROFESSIONAL;
WORKBOOK FLOW-F12, FLOW-F28, APPOINTMENT-F01, APPOINTMENT-F04; what WHATSAPP_INBOX-F14, F21 and F22 wait for).

A step runs with the permission of its own operation and the reads of its app, never every permission (FLOW-F12).
Booking and moving an appointment ask for «their own» ones, and an automation has no staff record: Appointments takes
what it was granted for the whole team — as the customer, who books with any professional — and judges it by the
customer's rules (the notice, the hours, never in the past). Three ways run an operation: a plain step, an «Ask the
assistant» step on its own, and the change the assistant proposed once a person says «Approve» (FLOW-F28).

Cancelling needs a person in front, so only the third way makes it (hub#634, ``ASK_FIRST``): an «Ask me first» step that
was granted it, once someone who may cancel anybody's appointment says yes. The yes lends nothing and the step still
runs with its own permission, so the customer's cancellation policy goes on judging it.
"""

import json

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.appointment.models import Appointment
from apps.appointment.tests.conftest import (  # noqa: F401 - anytime is a fixture
    MONDAY,
    anytime,
    at,
    make_appointment,
    make_customer,
    make_member,
    make_service,
    make_settings,
    wall,
)
from apps.flow.models import Flow, FlowRun, Question
from base import assistant as hub_assistant
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import ctx_for, make_flow, run

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime", "no_pauses")]

CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
CREATE = "appointment.appointment.create"
RESCHEDULE = "appointment.appointment.reschedule"
CONFIRM = "appointment.appointment.confirm"
UPDATE = "appointment.appointment.update"
CANCEL = "appointment.appointment.cancel"
#: Whoever manages automations and may book (their own appointments, like any employee): their yes books.
MAY_BOOK = {"flow.view", "flow.manage", "flow.answer", "flow.answer_manager", "appointment.add_own_appointment"}
MANAGES_FLOWS = {"flow.view", "flow.manage", "flow.answer", "flow.answer_manager"}
#: Whoever manages automations and may cancel anybody's appointment; only their own, like any employee; or none.
MAY_CANCEL = MANAGES_FLOWS | {
    "appointment.view_appointment",
    "appointment.view_own_appointment",
    "appointment.change_appointment",
    "appointment.change_own_appointment",
}
ONLY_THEIR_OWN = MANAGES_FLOWS | {"appointment.view_own_appointment", "appointment.change_own_appointment"}
MAY_NOT_CANCEL = MANAGES_FLOWS | {"appointment.view_appointment"}


@pytest.fixture
def salon(db):
    """A customer, a cut and two professionals; Bea's is the appointment the automation books or moves."""
    return type(
        "Salon",
        (),
        {"cut": make_service("Haircut"), "ana": make_member("Ana", "López"), "bea": make_member("Bea", "Ruiz"), "lucia": make_customer()},
    )


def booking(salon, start: str = "10:00") -> dict:
    return {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.bea.id),
        "start": wall(MONDAY, start),
    }


def step(operation: str, *names: str) -> dict:
    return {"id": "s1", "kind": "command", "operation": operation, "params": {name: f"input.{name}" for name in names}}


def run_step(operation: str, data: dict, grants: list[str] | None = None):
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[step(operation, *data)], grants=[operation] if grants is None else grants)
    return run("flow.flow.run", {"id": str(flow.id), "input": data})


def wants(name: str, arguments: dict) -> dict:
    call = {"type": "function_call", "call_id": "call_1", "name": name, "arguments": json.dumps(arguments)}
    return {"output": [call], "continuation": "token-1", "quota": QUOTA}


def said(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA}


def assistant_books(worker, gateway, salon, mode: str, grants: list[str]) -> FlowRun:
    """An automation whose assistant (``mode``) wants to book Lucía with Bea on Monday at ten."""
    tool = {"id": "s1", "kind": "assistant", "prompt": "Book {{input.name}}", "tools": [CREATE], "mode": mode}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[tool], grants=grants)
    gateway.reply(CHAT, json=wants("appointment__appointment__create", booking(salon)))
    gateway.reply(CHAT, json=said("Booked"))
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Lucía"}})
    worker()
    return FlowRun.objects.get(pk=ran.id)


# ── A plain step (FLOW-F12, APPOINTMENT-F01, APPOINTMENT-F04) ────────────────────────────────────────


def test_a_step_granted_booking_books_with_any_professional(salon):
    result = run_step(CREATE, booking(salon))
    assert result.status == "succeeded", (result.error_code, result.error_message)
    booked = Appointment.objects.get()
    assert (booked.staff_id, booked.start) == (salon.bea.id, at(MONDAY, "10:00"))


def test_a_step_not_granted_booking_books_nothing(salon):
    result = run_step(CREATE, booking(salon), grants=[])
    assert (result.status, result.error_code) == ("failed", "flow.not_allowed")
    assert Appointment.objects.count() == 0


def test_a_step_books_by_the_customers_rules_never_the_front_desks(salon):
    make_settings(min_booking_notice=60 * 24 * 30)
    result = run_step(CREATE, booking(salon))
    assert (result.status, result.error_code) == ("failed", "appointment.too_soon")
    assert Appointment.objects.count() == 0


def test_a_step_granted_moving_moves_any_professionals_appointment(salon):
    beas = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"))
    result = run_step(RESCHEDULE, {"id": str(beas.id), "start": wall(MONDAY, "12:00")})
    assert result.status == "succeeded", (result.error_code, result.error_message)
    assert Appointment.objects.get(pk=beas.id).start == at(MONDAY, "12:00")


def test_a_step_granted_confirming_or_editing_changes_any_professionals_appointment(salon):
    beas = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"), status="pending")
    confirmed = run_step(CONFIRM, {"id": str(beas.id)})
    edited = run_step(UPDATE, {"id": str(beas.id), "notes": "Bring the photo"})
    assert (confirmed.status, edited.status) == ("succeeded", "succeeded"), (confirmed.error_code, edited.error_code)
    beas.refresh_from_db()
    assert (beas.status, beas.notes) == ("confirmed", "Bring the photo")


# ── «Ask the assistant» (FLOW-F28, FLOW-F38) ─────────────────────────────────────────────────────────


def test_the_assistant_on_its_own_books_with_any_professional(gateway, worker, salon):
    ran = assistant_books(worker, gateway, salon, "auto", [CREATE])
    assert Appointment.objects.get().staff_id == salon.bea.id
    assert ran.status == FlowRun.Status.SUCCEEDED
    assert [entry.get("ok") for entry in ran.log if entry.get("outcome") == "assistant_used"] == [True]


def test_the_assistant_books_nothing_it_was_not_granted(gateway, worker, salon):
    assistant_books(worker, gateway, salon, "auto", [])
    assert Appointment.objects.count() == 0
    _, second = gateway.sent(CHAT)
    assert json.loads(second.body["messages"][-1]["content"])["error"]["code"] == "not_available"


def test_the_booking_the_assistant_asked_first_is_made_on_the_yes(gateway, worker, salon):
    ran = assistant_books(worker, gateway, salon, "ask", [CREATE])
    assert ran.status == FlowRun.Status.ASKING
    assert Appointment.objects.count() == 0
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_BOOK, actor="marta"))
    assert Appointment.objects.get().staff_id == salon.bea.id
    worker()
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


# ── Cancelling, only «Ask me first» (hub#634; FLOW-F12, FLOW-F28, FLOW-F37, FLOW-F38, APPOINTMENT-F05, APPOINTMENT-F06) ───


def asking(mode: str = "ask") -> dict:
    return {"id": "s1", "kind": "assistant", "prompt": "Cancel for {{input.name}}", "tools": [CANCEL], "mode": mode}


def plain_cancel() -> dict:
    return {"id": "s1", "kind": "command", "operation": CANCEL, "params": {"id": "input.id"}}


def a_document(step: dict) -> dict:
    return {"name": "Cancel by message", "trigger": {"kind": "manual"}, "steps": [step]}


def assistant_cancels(worker, gateway, beas, mode: str = "ask", grants: tuple[str, ...] = (CANCEL,)) -> FlowRun:
    """An automation whose assistant (``mode``) wants to cancel Bea's appointment and then says so."""
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[asking(mode)], grants=list(grants))
    gateway.reply(CHAT, json=wants("appointment__appointment__cancel", {"id": str(beas.id), "reason": "She wrote to cancel"}))
    gateway.reply(CHAT, json=said("Cancelled"))
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Lucía"}})
    worker()
    return FlowRun.objects.get(pk=ran.id)


@pytest.fixture
def beas(salon):
    """Bea's appointment on Monday at ten, far enough ahead of any cancellation notice."""
    return make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"))


def status_of(appointment) -> str:
    return Appointment.objects.get(pk=appointment.id).status


def test_ask_me_first_may_be_given_cancelling_an_appointment():
    created = run("flow.flow.create", a_document(asking()))
    assert run("flow.flow.grant", {"id": str(created.id), "operations": [CANCEL]}).grants == [CANCEL]


def test_the_catalog_offers_cancelling_an_appointment_only_to_ask_first():
    action = {action.name: action for action in run("flow.catalog.read", {}).actions}[CANCEL]
    assert (action.ask_first, action.assistant) == (True, True)


def test_on_its_own_it_may_not_be_given_cancelling_an_appointment():
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", a_document(asking("auto")))
    assert refused.value.code == "flow.high_risk"
    assert set(refused.value.fields) == {"steps.0.tools"}


def test_a_plain_step_may_not_be_given_cancelling_an_appointment():
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", a_document(plain_cancel()))
    assert refused.value.code == "flow.high_risk"
    assert set(refused.value.fields) == {"steps.0.operation"}


def test_cancelling_an_appointment_is_not_granted_to_a_step_that_does_it_on_its_own():
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[asking("auto")], grants=[])
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.grant", {"id": str(flow.id), "operations": [CANCEL]})
    assert refused.value.code == "flow.high_risk"


def test_whoever_cannot_change_appointments_cannot_grant_cancelling_one():
    created = run("flow.flow.create", a_document(asking()))
    with pytest.raises(PermissionDenied):
        run("flow.flow.grant", {"id": str(created.id), "operations": [CANCEL]}, ctx_for(permissions=MAY_NOT_CANCEL))


def test_before_the_yes_nothing_is_cancelled_and_the_assistant_was_offered_it(gateway, worker, beas):
    ran = assistant_cancels(worker, gateway, beas)
    assert ran.status == FlowRun.Status.ASKING
    assert status_of(beas) == "confirmed"
    [first] = gateway.sent(CHAT)
    assert [tool["name"] for tool in first.body["tools"]] == ["appointment__appointment__cancel"]


def test_the_yes_of_who_may_cancel_cancels_any_professionals_appointment(gateway, worker, beas):
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL, actor="marta"))
    beas.refresh_from_db()
    assert (beas.status, beas.cancellation_reason) == ("cancelled", "She wrote to cancel")
    worker()
    finished = FlowRun.objects.get(pk=ran.id)
    assert finished.status == FlowRun.Status.SUCCEEDED
    assert [entry.get("ok") for entry in finished.log if entry.get("outcome") == "assistant_used"] == [True]


def test_after_the_yes_the_step_still_runs_with_only_its_own_permission(gateway, worker, beas, monkeypatch):
    # Never every permission (FLOW-F12): Appointments takes «its own» as the whole team's, nothing more is lent.
    seen = []
    made = hub_assistant.run_tool
    monkeypatch.setattr(hub_assistant, "run_tool", lambda ctx, op, arguments: seen.append(ctx) or made(ctx, op, arguments))
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL, actor="marta"))
    assert status_of(beas) == "cancelled"
    [step] = seen
    assert step.has("appointment.change_own_appointment")
    for beyond in ("appointment.change_appointment", "appointment.delete_appointment", "flow.manage"):
        assert not step.has(beyond)


def test_a_no_cancels_nothing(gateway, worker, beas):
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": False}, ctx_for(permissions=MAY_NOT_CANCEL))
    assert status_of(beas) == "confirmed"
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.CANCELLED


@pytest.mark.parametrize("permissions", [MAY_NOT_CANCEL, ONLY_THEIR_OWN], ids=["no_permission", "only_their_own"])
def test_the_yes_of_who_may_not_cancel_any_appointment_is_refused_and_the_question_waits(gateway, worker, beas, permissions):
    # «No elevation»: whoever only changes their own never cancels Bea's by saying yes to the automation that may.
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    with pytest.raises(PermissionDenied) as refused:
        worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=permissions))
    assert refused.value.code == "flow.approval_beyond_you"
    assert status_of(beas) == "confirmed"
    assert Question.objects.get(pk=question.id).status == Question.Status.PENDING
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.ASKING


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_a_yes_to_the_assistant_s_change_is_not_of_the_roles_that_do_not_run_the_business(gateway, worker, beas, role):
    # FLOW-F29: a change the assistant wants is asked of whoever runs the business, even of a manager who may cancel.
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    with pytest.raises(PermissionDenied) as refused:
        worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(role))
    assert refused.value.code == "flow.question_not_yours"
    assert status_of(beas) == "confirmed"


def test_not_granted_it_is_neither_offered_nor_made(gateway, worker, beas):
    ran = assistant_cancels(worker, gateway, beas, grants=())
    assert status_of(beas) == "confirmed"
    assert not Question.objects.filter(run_id=ran.id).exists()
    first, second = gateway.sent(CHAT)
    assert first.body["tools"] == []
    assert json.loads(second.body["messages"][-1]["content"])["error"]["code"] == "not_available"


def test_a_grant_withdrawn_after_asking_makes_nothing_on_the_yes(gateway, worker, beas):
    ran = assistant_cancels(worker, gateway, beas)
    Flow.objects.filter(pk=ran.flow_id).update(grants=[])
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL))
    assert status_of(beas) == "confirmed"


def test_on_its_own_a_cancellation_that_slipped_in_is_never_offered_nor_made(gateway, worker, beas):
    # Written straight in the table, as an old row or a raw admin edit could leave it.
    ran = assistant_cancels(worker, gateway, beas, mode="auto")
    first, second = gateway.sent(CHAT)
    assert first.body["tools"] == []
    assert json.loads(second.body["messages"][-1]["content"])["error"]["code"] == "not_available"
    assert status_of(beas) == "confirmed"
    assert not Question.objects.filter(run_id=ran.id).exists()


def test_a_plain_cancel_step_that_slipped_in_cancels_nothing(beas):
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[plain_cancel()], grants=[CANCEL])
    result = run("flow.flow.run", {"id": str(flow.id), "input": {"id": str(beas.id)}})
    assert (result.status, result.error_code) == ("failed", "flow.high_risk")
    assert status_of(beas) == "confirmed"


@pytest.mark.parametrize(
    ("rules", "code"),
    [
        ({"allow_customer_cancellation": False}, "appointment.customer_cancellation_disabled"),
        ({"cancellation_notice_hours": 24 * 365}, "appointment.cancellation_notice_required"),
    ],
    ids=["not_allowed", "too_late"],
)
def test_after_the_yes_the_customers_cancellation_policy_still_judges_it(gateway, worker, beas, rules, code):
    # A person of the team may cancel outside the policy; an automation never, whoever said yes (APPOINTMENT-F06).
    make_settings(**rules)
    ran = assistant_cancels(worker, gateway, beas)
    question = Question.objects.get(run_id=ran.id)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL))
    worker()
    assert status_of(beas) == "confirmed"
    _, second = gateway.sent(CHAT)
    assert json.loads(second.body["messages"][-1]["content"])["error"]["code"] == code


def test_the_card_of_the_yes_says_which_appointment_it_cancels(gateway, worker, beas, salon):
    # Saying yes blind to what cannot be undone is no yes: the card names the appointment, for whoever may read it.
    assistant_cancels(worker, gateway, beas)
    [row] = run("flow.question.list", {}, ctx_for(permissions=MAY_CANCEL)).rows
    assert row.action == "Cancel an appointment"
    said_values = [field.value for field in row.fields]
    assert any(salon.lucia.name in str(value) and "10:00" in str(value) and "Bea" in str(value) for value in said_values), said_values
    assert not any(str(beas.id) in str(value) for value in said_values)
    [hidden] = run("flow.question.list", {}, ctx_for(permissions=ONLY_THEIR_OWN)).rows
    assert not any(salon.lucia.name in str(field.value) for field in hidden.fields)
    [spanish] = run("flow.question.list", {}, ctx_for(permissions=MAY_CANCEL, language="es")).rows
    assert spanish.action == "Anular una cita"
    assert [field.label for field in spanish.fields if salon.lucia.name in str(field.value)] == ["Cita"]
