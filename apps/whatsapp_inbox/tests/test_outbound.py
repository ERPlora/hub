"""What the inbox hands to erplora.com after a COMMIT never holds the worker.

FIX-HUB-WHATSAPP-INBOX-SLOW-SEND-BLOCKS-RELAY. One worker relays the outbox of every hub and runs the scheduled tasks in one loop, and Django ran what a transaction
left for after its COMMIT right there: the message an automation of hub A sends (door 5), the number an erased card
asks erplora.com to forget (door 6), and what the tick hands over again (messages, erasures, templates and their
deletions, doors 5, 6, 8 and 9) held every other delivery, of every hub, and the scheduled tasks while erplora.com did
not answer (up to 20 s a call). They go through ``base.outbound``: a thread of the worker's own makes the call, with
no database connection held while it waits, and each still goes out once, with its own key.

erplora.com answers here only once the test lets it (5 s at most: a worker that waits for it fails the test instead of
hanging), and every delivery of hub B lets it, so the order says who waited for whom. The real pool runs the calls
(``outbound_threads``), on committed data.
"""

import datetime as dt
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
import respx
from django.db import connection
from django.utils import timezone

from apps.whatsapp_inbox import gateway
from apps.whatsapp_inbox.models import Conversation, Message, Template
from apps.whatsapp_inbox.tests.conftest import NOW, B, card, connect, ctx_for, receive, run, system, template
from apps.whatsapp_inbox.tests.test_relay_notify import confirm, salon
from base import catalog, outbound, relay, scheduler, worker
from base.catalog import RegisterResult

SAAS = "http://saas.test"
SEND = f"{SAAS}/internal/whatsapp/send"
ERASE = f"{SAAS}/internal/whatsapp/erase"
REGISTER = f"{SAAS}/internal/whatsapp/templates"
DELETE = f"{SAAS}/internal/whatsapp/templates/delete"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
#: The most a test waits for what the worker's thread hands over.
WAIT_SECONDS = 10
#: erplora.com did not answer: what was on its way stays so, for the tick to hand over again.
UNANSWERED = httpx.Response(503, json={})


def answering_late(monkeypatch, name: str) -> SimpleNamespace:
    """erplora.com's door ``gateway.<name>`` answers once ``.answer`` is set (5 s at most) when ``.armed``;
    ``.timeline`` says, in order, what happened meanwhile and when it came back (``"answered"``), and ``.held``
    whether the thread that waited for it held a database connection meanwhile."""
    timeline: list[str] = []
    held: list[bool] = []
    answer, armed = threading.Event(), threading.Event()
    real = getattr(gateway, name)

    def late(*args, **kwargs):
        if not armed.is_set():
            return real(*args, **kwargs)
        held.append(connection.connection is not None)
        answer.wait(timeout=5)
        reply = real(*args, **kwargs)
        timeline.append("answered")
        return reply

    monkeypatch.setattr(gateway, name, late)
    return SimpleNamespace(timeline=timeline, held=held, answer=answer, armed=armed)


def heard_by_hub_b(monkeypatch, late: SimpleNamespace) -> None:
    """Every delivery of hub B goes on the timeline, and the first one lets erplora.com answer."""
    real = relay.deliver

    def deliver(app_label, event):
        done = real(app_label, event)
        if event.scope_key == B.key:
            late.timeline.append(f"{app_label} got {event.name} in b")
            late.answer.set()
        return done

    monkeypatch.setattr(relay, "deliver", deliver)


def hub_b_writes() -> None:
    """Hub B makes a card meanwhile: its event waits in the same outbox."""
    system("customer.customer.create", {"name": "Bea Ruiz"}, B)


def settled(done: Callable[[], bool]) -> None:
    """What the worker's thread handed over came back and was recorded."""
    deadline = time.monotonic() + WAIT_SECONDS
    while not done() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert done()


def waited_for_nobody(late: SimpleNamespace) -> None:
    assert late.timeline, "erplora.com was never called"
    assert late.timeline[0].endswith("customer.customer.created in b"), late.timeline
    assert late.timeline.count("answered") == 1
    assert late.held == [False]  # it waited on erplora.com with no connection held


# ── The relay: a reaction of hub A that hands something to erplora.com ───────────────────────────────────────────────


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_a_late_send_of_hub_a_never_holds_the_deliveries_of_hub_b(monkeypatch):
    """WHATSAPP_INBOX-F37: confirming an appointment tells the customer through erplora.com; the relay goes on."""
    with respx.mock(assert_all_called=False) as saas:
        door = saas.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
        appointment = salon()
        relay.run(timezone.now())  # the salon's own events: nothing is sent
        late = answering_late(monkeypatch, "send")
        late.armed.set()
        confirm(appointment)  # its event is older than hub B's: the relay hands it over first
        hub_b_writes()
        heard_by_hub_b(monkeypatch, late)

        relay.run(timezone.now())

        settled(lambda: Message.objects.filter(direction="outbound", status=Message.Status.SENT).exists())
    waited_for_nobody(late)
    assert door.call_count == 1
    assert Message.objects.filter(direction="outbound").count() == 1


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_a_late_erasure_of_hub_a_never_holds_the_deliveries_of_hub_b(monkeypatch):
    """WHATSAPP_INBOX-F11: erasing a card asks erplora.com to forget her number; the relay goes on."""
    with respx.mock(assert_all_called=False) as saas:
        door = saas.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
        receive("wamid.1")
        ana = card()
        relay.run(timezone.now())  # her card claims her conversation
        late = answering_late(monkeypatch, "erase")
        late.armed.set()
        run("customer.customer.erase", {"id": str(ana.id), "reason": "Lo pidió por WhatsApp"}, ctx_for("hub_owner"))
        hub_b_writes()
        heard_by_hub_b(monkeypatch, late)

        relay.run(timezone.now())

        settled(lambda: Conversation.objects.get().erase_status == Conversation.EraseStatus.DONE)
    waited_for_nobody(late)
    assert door.call_count == 1


# ── The tick: what was left on its way, handed over again ────────────────────────────────────────────────────────────


@contextmanager
def the_worker_stopping() -> Iterator[None]:
    """What commits meanwhile is never handed over by the worker that took it: it was on its way out (a deploy)."""
    running = outbound._pool
    stopped = outbound.Pool()
    stopped.stop(grace=0)
    outbound._pool = stopped
    try:
        yield
    finally:
        outbound._pool = running


@dataclass(frozen=True)
class Stuck:
    """Something the inbox left on its way to erplora.com: its door, what erplora.com answers at last, how it is
    made (a real operation) and how it reads once recorded, and the key every attempt goes with (doors 5 and 8)."""

    door: str
    url: str
    answer: dict
    make: Callable[[], Callable[[], bool]]
    key: Callable[[], str] | None = None


def a_reply() -> Callable[[], bool]:
    connect()
    receive("wamid.1", sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    sent = run(
        "whatsapp_inbox.message.send",
        {"id": str(Conversation.objects.get().id), "text": "Sí, a las 10", "client_message_id": str(uuid.uuid7())},
    )
    return lambda: Message.objects.get(pk=sent.id).status == Message.Status.SENT


def a_reply_key() -> str:
    return str(Message.objects.get(origin=Message.Origin.HUB).client_message_id)


def an_erased_number() -> Callable[[], bool]:
    receive("wamid.1")
    run("whatsapp_inbox.conversation.erase", {"id": str(Conversation.objects.get().id)})
    return lambda: Conversation.objects.get().erase_status == Conversation.EraseStatus.DONE


def a_new_template() -> Callable[[], bool]:
    connect()
    made = run(
        "whatsapp_inbox.template.create",
        {
            "name": "recordatorio_cita",
            "language": "es",
            "category": "UTILITY",
            "body": "Hola {{1}}, te esperamos el {{2}}.",
            "body_examples": ["Ana", "viernes"],
            "submit_key": str(uuid.uuid7()),
        },
    )
    return lambda: Template.objects.get(pk=made.id).submit_state == Template.SubmitState.NONE


def a_deleted_template() -> Callable[[], bool]:
    connect(templates=[template()])
    approved = Template.objects.get(name="recordatorio")
    run("whatsapp_inbox.template.delete", {"id": str(approved.id)})
    return lambda: Template.objects.get(pk=approved.id).delete_state == Template.DeleteState.DONE


STUCK = [
    pytest.param(Stuck("send", SEND, {"wa_message_id": "wamid.OUT"}, a_reply, a_reply_key), id="message"),
    pytest.param(Stuck("erase", ERASE, {"erased": True}, an_erased_number), id="erasure"),
    pytest.param(
        Stuck(
            "submit_template",
            REGISTER,
            {"meta_id": "meta-1", "status": "PENDING"},
            a_new_template,
            lambda: str(Template.objects.get().submit_key),
        ),
        id="template",
    ),
    pytest.param(Stuck("delete_template", DELETE, {"deleted": True}, a_deleted_template), id="template-deletion"),
]


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("stuck", STUCK)
def test_what_the_tick_hands_over_again_never_holds_the_relay(stuck, fixed_clock, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    late = answering_late(monkeypatch, stuck.door)
    with respx.mock(assert_all_called=False) as saas:
        door = saas.post(stuck.url).mock(return_value=UNANSWERED)
        with the_worker_stopping():
            done = stuck.make()
        assert not done()
        door.mock(return_value=httpx.Response(200, json=stuck.answer))
        monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))  # past its 2 minutes
        hub_b_writes()
        heard_by_hub_b(monkeypatch, late)
        late.armed.set()
        now = timezone.now()
        scheduler.sync(now - dt.timedelta(minutes=6))  # whatsapp_inbox.resume_deliveries (every 5 min) is due

        # One tick of the worker's real loop: the scheduled tasks (the inbox's hands it over again), then the relay.
        stop = threading.Event()
        assert worker.run(stop, tick_seconds=0, wait=lambda _seconds: stop.set() or True, clock=lambda: now) == 0

        settled(done)
    waited_for_nobody(late)
    assert [call.response.status_code for call in door.calls][-1:] == [200]
    assert sum(call.response.status_code == 200 for call in door.calls) == 1
    if stuck.key is not None:  # never twice at erplora.com: every attempt with the same key
        assert {call.request.headers["Idempotency-Key"] for call in door.calls} == {stuck.key()}
