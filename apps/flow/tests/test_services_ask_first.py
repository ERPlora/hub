"""Cancelling a booking only with a person's yes first (FIX-HUB-FLOW-ASK-ME-FIRST-CANNOT-GRANT-A-CANCELLATION;
WORKBOOK FLOW-F12, FLOW-F28, FLOW-F37, FLOW-F38).

What needs a person in front (``ai.risk == "high"``) is never an automation's, with one exception the market makes:
cancelling a reservation may be granted to an «Ask the assistant» step that asks first («Ask me first»), so a guest
who writes «cancel my table» gets it done once a person says yes (Zapier's Human in the Loop
and n8n's human review gate the irreversible step; Odoo's approval rules gate a button behind an allowed group;
Fresha's AI Concierge cancels within the business's cancellation policy). Never on its own, never as a plain step,
never what is done in person (seating), never money, fiscal records or erasing. The yes is a person's who may cancel
themselves (the old engine's «no elevation»); the change still runs as the automation. Cancelling an appointment is not
in yet: Appointments refuses every change an automation makes («You may only change your own appointments.»), so it
would always fail after the yes.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import system_context
from live.errors import InvalidPayload, PermissionDenied

from apps.flow import gateway as flow_gateway
from apps.flow import queries, recipes
from apps.flow.models import Flow, FlowRun, Question
from base import relay
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import A, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
CANCEL = "reservation.reservation.cancel"
CANCEL_APPOINTMENT = "appointment.appointment.cancel"
#: Whoever manages automations and may cancel a reservation, and whoever manages them but may not.
MAY_CANCEL = {"flow.view", "flow.manage", "flow.answer", "flow.answer_manager", "reservation.view_reservation", "reservation.change_reservation"}
MAY_NOT_CANCEL = {"flow.view", "flow.manage", "flow.answer", "flow.answer_manager", "reservation.view_reservation"}


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
def booked(clock):
    """Ana's pending table for two tomorrow at nine, booked for real in Reservations."""
    from apps.reservation.tests.conftest import make_table, open_week

    clock(NOON)
    open_week()
    return run(
        "reservation.reservation.create",
        {"guest_name": "Ana García", "guest_phone": "600111222", "date": "2026-10-16", "time": "21:00", "party_size": 2, "table_id": str(make_table("5").id)},
        system_context(A),
    )


def assistant(tools=(CANCEL,), **more) -> dict:
    return {"id": "s1", "kind": "assistant", "prompt": "Cancel the table of {{input.name}}", "tools": list(tools)} | more


def document(*steps) -> dict:
    return {"name": "Cancel by message", "trigger": {"kind": "manual"}, "steps": list(steps)}


def said(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA}


def wants(name: str, arguments: dict) -> dict:
    call = {"type": "function_call", "call_id": "call_1", "name": name, "arguments": json.dumps(arguments)}
    return {"output": [call], "continuation": "token-1", "quota": QUOTA}


def status_of(reservation) -> str:
    from apps.reservation.models import Reservation

    return Reservation.objects.get(pk=reservation.id).status


def waiting_cancellation(worker, gateway, booked, **step) -> tuple[FlowRun, Question]:
    """An automation that asks first whose assistant wants to cancel Ana's table: it waits for a yes."""
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[assistant(**step)], grants=[CANCEL])
    gateway.reply(CHAT, json=wants("reservation__reservation__cancel", {"id": str(booked.id), "reason": "She wrote to cancel"}))
    gateway.reply(CHAT, json=said("Cancelled"))
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}})
    worker()
    return FlowRun.objects.get(pk=ran.id), Question.objects.get(run_id=ran.id)


# ── Saving, granting and turning on (FLOW-F12, FLOW-F37) ─────────────────────────────────────────────


def test_ask_me_first_may_be_given_a_cancellation_and_it_is_granted():
    created = run("flow.flow.create", document(assistant()))
    assert run("flow.flow.grant", {"id": str(created.id), "operations": [CANCEL]}).grants == [CANCEL]


def test_on_its_own_it_may_not_be_given_a_cancellation():
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", document(assistant(mode="auto")))
    assert refused.value.code == "flow.high_risk"
    assert refused.value.fields == {
        "steps.0.tools": "«reservation.reservation.cancel» needs a person's yes first: choose «Ask me first»."
    }


def test_a_plain_step_may_still_not_cancel():
    plain = {"id": "s1", "kind": "command", "operation": CANCEL, "params": {"id": "input.reservation_id"}}
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", document(plain))
    assert refused.value.code == "flow.high_risk"
    assert set(refused.value.fields) == {"steps.0.operation"}


def test_a_cancellation_is_granted_only_to_an_automation_that_asks_first_for_it():
    # FLOW-F12: what is granted is what the saved steps need; a cancellation only for a step that asks first.
    for steps in ([assistant(mode="auto", tools=["reservation.reservation.list"])], [assistant(tools=["reservation.reservation.list"])]):
        flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=[])
        with pytest.raises(InvalidPayload) as refused:
            run("flow.flow.grant", {"id": str(flow.id), "operations": [CANCEL]})
        assert refused.value.code == "flow.high_risk"
        assert set(refused.value.fields) == {"operations.0"}


def test_whoever_grants_a_cancellation_may_cancel_themselves():
    created = run("flow.flow.create", document(assistant()))
    with pytest.raises(PermissionDenied):
        run("flow.flow.grant", {"id": str(created.id), "operations": [CANCEL]}, ctx_for(permissions=MAY_NOT_CANCEL))
    assert run("flow.flow.grant", {"id": str(created.id), "operations": [CANCEL]}, ctx_for(permissions=MAY_CANCEL)).grants == [CANCEL]


@pytest.mark.parametrize(
    "name", ["reservation.reservation.seat", "reservation.reservation.delete", "reservation.reservation.no_show", "sale.order.void", CANCEL_APPOINTMENT]
)
def test_what_is_not_cancelling_a_booking_needs_a_person_in_front_even_asking_first(name):
    # Seating is done at the door (FIX-HUB-FLOW-STEP-RESERVATION-BY-PHONE-DENIED); erasing, a no-show (it may charge
    # the deposit) and money or fiscal records are never decided from an inbox; an appointment, not yet (above).
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", document(assistant(tools=[name])))
    assert refused.value.code in ("flow.high_risk", "invalid_payload")
    assert set(refused.value.fields) == {"steps.0.tools"}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[assistant(tools=[name])], grants=[])
    with pytest.raises(InvalidPayload):
        run("flow.flow.grant", {"id": str(flow.id), "operations": [name]})


def test_what_is_done_in_person_stays_out_even_were_it_listed_to_ask_first(monkeypatch):
    # FIX-HUB-FLOW-STEP-RESERVATION-BY-PHONE-DENIED stays: the exception only reaches what is high risk, never seating.
    monkeypatch.setattr(queries, "ASK_FIRST", queries.ASK_FIRST | {"reservation.reservation.seat"})
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", document(assistant(tools=["reservation.reservation.seat"])))
    assert refused.value.code == "flow.high_risk"
    assert "reservation.reservation.seat" not in queries.ask_first_catalog()


def test_a_recipe_whose_assistant_asks_first_to_cancel_is_offered_and_turned_on(monkeypatch):
    declared = {
        "id": "cancel_by_message",
        "name": "Cancel by message",
        "summary": "Cancels a table when the guest asks, after your yes.",
        "description": "The assistant reads the guest's message and asks you before cancelling.",
        "trigger": {"kind": "manual"},
        "steps": [assistant()],
        "grants": {CANCEL: "Cancels the table after your yes."},
    }
    reservation = queries.active_apps()["reservation"]
    monkeypatch.setattr(recipes, "declarations", lambda: [(reservation, declared)])
    offered, set_aside = recipes.shelf()
    assert ([recipe.ref for recipe in offered], set_aside) == (["reservation/cancel_by_message"], [])
    done = run("flow.recipe.enable", {"recipe": "reservation/cancel_by_message"})
    assert done.created is True
    assert done.flow.grants == [CANCEL] and done.flow.enabled is True


def test_the_catalog_offers_a_cancellation_only_to_ask_first():
    actions = {action.name: action for action in run("flow.catalog.read", {}).actions}
    assert actions[CANCEL].ask_first is True and actions[CANCEL].assistant is True
    assert actions["reservation.reservation.create"].ask_first is False
    assert not {"reservation.reservation.seat", "reservation.reservation.delete", "sale.order.void", CANCEL_APPOINTMENT} & set(actions)


# ── Running it (FLOW-F38, FLOW-F29) ──────────────────────────────────────────────────────────────────


def test_a_yes_from_someone_who_may_cancel_cancels_the_reservation(gateway, worker, booked):
    ran, question = waiting_cancellation(worker, gateway, booked)
    assert ran.status == FlowRun.Status.ASKING
    assert status_of(booked) == "pending"
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL, actor="marta"))
    assert status_of(booked) == "cancelled"
    worker()
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_a_no_cancels_nothing(gateway, worker, booked):
    ran, question = waiting_cancellation(worker, gateway, booked)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": False}, ctx_for(permissions=MAY_NOT_CANCEL))
    assert status_of(booked) == "pending"
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.CANCELLED


def test_a_yes_from_someone_who_may_not_cancel_is_refused_and_the_question_waits(gateway, worker, booked):
    # «No elevation»: the yes lends nothing the person may not do; it says why and waits for someone who may.
    ran, question = waiting_cancellation(worker, gateway, booked)
    with pytest.raises(PermissionDenied) as refused:
        worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_NOT_CANCEL))
    assert refused.value.code == "flow.approval_beyond_you"
    assert refused.value.message == "Only someone who may do it themselves can say yes to «Cancel a reservation»."
    assert status_of(booked) == "pending"
    assert Question.objects.get(pk=question.id).status == Question.Status.PENDING
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.ASKING


def test_on_its_own_a_cancellation_that_slipped_in_is_never_offered_nor_made(gateway, worker, booked):
    # Written straight in the table, as an old row or a raw admin edit could leave it.
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[assistant(mode="auto")], grants=[CANCEL])
    gateway.reply(CHAT, json=wants("reservation__reservation__cancel", {"id": str(booked.id)}))
    gateway.reply(CHAT, json=said("I could not"))
    worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}})
    worker()
    first, second = gateway.sent(CHAT)
    assert first.body["tools"] == []
    assert json.loads(second.body["messages"][-1]["content"])["error"]["code"] == "not_available"
    assert status_of(booked) == "pending"


def test_asking_first_the_cancellation_is_offered_to_the_assistant(gateway, worker, booked):
    waiting_cancellation(worker, gateway, booked)
    [first] = gateway.sent(CHAT)
    assert [tool["name"] for tool in first.body["tools"]] == ["reservation__reservation__cancel"]


def test_a_plain_cancel_step_that_slipped_in_cancels_nothing(booked):
    plain = {"id": "s1", "kind": "command", "operation": CANCEL, "params": {"id": "input.reservation_id"}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[plain], grants=[CANCEL])
    result = run("flow.flow.run", {"id": str(flow.id), "input": {"reservation_id": str(booked.id)}})
    assert (result.status, result.error_code) == ("failed", "flow.high_risk")
    assert status_of(booked) == "pending"

