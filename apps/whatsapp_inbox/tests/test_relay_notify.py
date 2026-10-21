"""«The customer gets the notice when the salon confirms» (WHATSAPP_INBOX-F23, FLOW-F31), end to end through the
worker's real outbox relay (``base/relay.py``; ``apps/task/tests/test_relay.py`` is the pattern).

The inbox's factory automation is turned on as the owner does it; Citas' real operation confirms the appointment and
records its event; one tick of the worker's real loop hands it to Automatizaciones, whose run reads the card, finds
the conversation of exactly that number, reads the appointment and sends through ``whatsapp_inbox.message.notify``:
the message is in the conversation and erplora.com's door 5 (``respx``, Meta beyond it) was called once. A second
tick sends nothing; another business sends through its own number; without a conversation of exactly that number,
or with the month spent, nothing leaves and the reason is in the automation's history.
"""

import datetime as dt
import json
import threading

import httpx
import pytest
import respx
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import get

from apps.appointment.tests.conftest import MONDAY, at, make_appointment, make_member, make_service
from apps.appointment.tests.conftest import ctx_for as appointment_ctx
from apps.customer.models import Customer
from apps.flow.models import FlowRun
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import B, NOW, connect, ctx_for, receive, run, system, template
from base import catalog, worker
from base.catalog import RegisterResult

pytestmark = pytest.mark.django_db

SEND = "http://saas.test/internal/whatsapp/send"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
REF = "whatsapp_inbox/appointment_confirmed"
ANA = "+34600111222"
#: The approved Utility template the recipe goes with after the customer's 24 hours.
CONFIRMED = template("appointment_confirmed", variables=4, body="Confirmada: {{1}} a las {{2}}, {{3}} con {{4}}.")


@pytest.fixture
def tick(monkeypatch, django_capture_on_commit_callbacks):
    """One turn of the worker's real loop, without the SaaS's catalogue and, inside the test's transaction,
    without releasing its connection; what the run leaves for after its COMMIT (the delivery) runs too."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def run_once() -> None:
        stop = threading.Event()
        now = timezone.now()

        def wait(seconds: float) -> bool:
            stop.set()
            return True

        with django_capture_on_commit_callbacks(execute=True):
            assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now + dt.timedelta(seconds=1)) == 0

    return run_once


@pytest.fixture
def door():
    with respx.mock(assert_all_called=False) as mock:
        yield mock.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))


def salon(phone: str = "600111222", *, minutes_ago: int = 10, templates=(CONFIRMED,), **channel):
    """The owner's business: its number connected, Lucía's conversation (her last message ``minutes_ago``), her card
    made by Customers, a pending appointment of hers with Ana and the inbox's automation turned on."""
    connect(templates=list(templates), **channel)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=minutes_ago)).isoformat())
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": phone}, ctx_for("hub_owner"))
    run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner"))
    cut = make_service("Haircut", price=2000, duration=30)
    ana = make_member("Ana", "López")
    return make_appointment(Customer.objects.get(pk=card.id), ana, [cut], at(MONDAY, "10:00"), status="pending")


def confirm(appointment, scope=None) -> None:
    op = get("appointment.appointment.confirm")
    ctx = appointment_ctx("hub_admin", **({"scope": scope} if scope else {}))
    op(ctx, op.input.model_validate({"id": str(appointment.id)}))


def outbound() -> list[Message]:
    return list(Message.objects.filter(direction="outbound").select_related("conversation").order_by("created_at"))


def test_confirming_tells_the_customer_once_in_her_conversation_through_erplora(tick, door):
    appointment = salon()
    confirm(appointment)
    assert OutboxEvent.objects.filter(name="appointment.appointment.confirmed").count() == 1
    assert not outbound()  # nothing is sent inside the request that confirmed

    tick()

    run_row = FlowRun.objects.get()
    assert (run_row.event_name, run_row.status) == ("appointment.appointment.confirmed", "succeeded")
    [message] = outbound()
    assert (message.conversation.phone, message.kind, message.status, message.host) == (ANA, "text", "sent", "a")
    assert message.body.startswith("Confirmed! We are expecting you on Monday, ")
    assert message.body.endswith(" at 10:00 for your Haircut with Ana López.")
    assert [json.loads(call.request.content)["to"] for call in door.calls] == [ANA]
    assert OutboxEvent.objects.filter(name="whatsapp_inbox.message.sent").count() == 1

    tick()
    assert (FlowRun.objects.count(), len(outbound()), door.call_count) == (1, 1, 1)


def test_after_the_24_hours_it_goes_with_the_approved_utility_template(tick, door):
    confirm(salon(minutes_ago=3 * 24 * 60))
    tick()
    [message] = outbound()
    assert (message.kind, message.template_name) == ("template", "appointment_confirmed")
    sent = json.loads(door.calls.last.request.content)["template"]
    assert sent["name"] == "appointment_confirmed"
    assert sent["variables"][1:] == ["10:00", "Haircut", "Ana López"]


def test_without_a_conversation_of_exactly_that_number_nothing_leaves_and_the_history_says_why(tick, door):
    confirm(salon(phone="600111223"))  # Lucía's card has a number that never wrote: not Ana's conversation
    tick()
    run_row = FlowRun.objects.get()
    assert run_row.status == "stopped"
    assert [entry["step"] for entry in run_row.log if entry["outcome"] == "stopped"] == ["s4"]
    assert not outbound() and door.call_count == 0


def test_with_the_month_spent_nothing_leaves_and_the_history_says_why(tick, door):
    confirm(salon(monthly_limit=150, monthly_usage=150))
    tick()
    run_row = FlowRun.objects.get()
    assert (run_row.status, run_row.error_code) == ("failed", "whatsapp_inbox.cap_reached")
    assert not outbound() and door.call_count == 0


def test_another_business_tells_its_customer_through_its_own_number(tick, door):
    appointment = salon()
    system(
        "whatsapp_inbox.channel.sync",
        {"version": 1, "status": "connected", "phone_number": "+34910000001", "templates": [CONFIRMED]},
        B,
    )
    confirm(appointment, scope=B)
    tick()
    [message] = outbound()
    assert message.host == "b"
    assert json.loads(door.calls.last.request.content)["hub"] == "b"
    sent = OutboxEvent.objects.get(name="whatsapp_inbox.message.sent")
    assert (sent.scope_kind, sent.scope_key) == (B.kind, B.key)
