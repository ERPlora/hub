"""An automation books and moves the appointment of any professional (FIX-HUB-FLOW-STEP-CANNOT-BOOK-FOR-A-PROFESSIONAL;
WORKBOOK FLOW-F12, FLOW-F28, APPOINTMENT-F01, APPOINTMENT-F04; what WHATSAPP_INBOX-F14, F21 and F22 wait for).

A step runs with the permission of its own operation and the reads of its app, never every permission (FLOW-F12).
Booking and moving an appointment ask for «their own» ones, and an automation has no staff record: Appointments takes
what it was granted for the whole team — as the customer, who books with any professional — and judges it by the
customer's rules (the notice, the hours, never in the past). Three ways run an operation: a plain step, an «Ask the
assistant» step on its own, and the change the assistant proposed once a person says «Approve» (FLOW-F28).
"""

import json

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

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
from apps.flow import gateway as flow_gateway
from apps.flow.models import Flow, FlowRun, Question
from base import relay
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import ctx_for, make_flow, run

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]

CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
CREATE = "appointment.appointment.create"
RESCHEDULE = "appointment.appointment.reschedule"
CONFIRM = "appointment.appointment.confirm"
UPDATE = "appointment.appointment.update"
#: Whoever manages automations and may book (their own appointments, like any employee): their yes books.
MAY_BOOK = {"flow.view", "flow.manage", "flow.answer", "flow.answer_manager", "appointment.add_own_appointment"}


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


@pytest.fixture
def worker(monkeypatch, django_capture_on_commit_callbacks):
    """One pass of the outbox relay, as the worker runs it every tick (base.relay)."""
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def tick():
        with django_capture_on_commit_callbacks(execute=True):
            return relay.run(timezone.now())

    def request(name, data, ctx=None):
        with django_capture_on_commit_callbacks(execute=True):
            return run(name, data, ctx)

    tick.request = request
    return tick


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
