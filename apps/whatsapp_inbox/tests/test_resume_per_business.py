"""What is handed to erplora.com again goes for its own business (review of hub#151).

Phase 1 shares the tables: a message the Hub sends and a number it asks erplora.com to forget keep the business that
made them (``Message.host``, ``Conversation.erase_host``, 0007). The worker's ``delivery.resume`` (one fixed scope,
``WORKER_SCOPE_SLUG``, base/scheduler.py), «Retry» on a message and erasing an erased number again hand each over for
that business (doors 5 and 6), never for the worker's nor for whoever asks from the shared inbox. A row made before
0007 has no business recorded and goes as the scope that asks, as it did. Asked from a request of another business
(its own ``use_hub``), it goes at once too, where that business's operations run, never in the asker's context.
"""

import datetime as dt
import json
import logging
import time
import uuid
from collections.abc import Callable

import httpx
import pytest
import respx
from live.context import Scope

from apps.whatsapp_inbox import gateway
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, A, B, ctx_for, receive, run, system
from apps.whatsapp_inbox.tests.test_outbound import the_worker_stopping
from base.tenancy import context

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
SEND = f"{SAAS}/internal/whatsapp/send"
ERASE = f"{SAAS}/internal/whatsapp/erase"


def connected(scope: Scope, phone: str) -> None:
    """erplora.com's photo of ``scope``'s number, connected."""
    system(
        "whatsapp_inbox.channel.sync",
        {"version": 1, "status": "connected", "phone_number": phone, "monthly_limit": 150, "templates": None},
        scope,
    )


@respx.mock
def test_one_run_of_the_worker_hands_each_business_s_stuck_message_and_erasure_for_its_own(
    django_capture_on_commit_callbacks, fixed_clock, monkeypatch, settings
):
    businesses = ((A, "+34910000000", "34600111222", "34600111333"), (B, "+34910000001", "34600222111", "34600222333"))
    for scope, number, talking, erased in businesses:
        connected(scope, number)
        # A reply queued whose after-COMMIT delivery never ran (the process died) …
        receive(f"wamid.{scope.key}.in", talking, scope=scope, sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
        conversation = Conversation.objects.get(phone=f"+{talking}")
        run(
            "whatsapp_inbox.message.send",
            {"id": str(conversation.id), "text": f"Hola desde {scope.key}", "client_message_id": str(uuid.uuid7())},
            ctx_for(scope=scope),
        )
        # … and a number erased here that erplora.com was never asked to forget.
        receive(f"wamid.{scope.key}.gone", erased, scope=scope)
        gone = Conversation.objects.get(phone=f"+{erased}")
        run("whatsapp_inbox.conversation.erase", {"id": str(gone.id)}, ctx_for(scope=scope))
    sent = respx.post(SEND).mock(
        side_effect=lambda request: httpx.Response(200, json={"wa_message_id": f"wamid.out.{json.loads(request.content)['to']}"})
    )
    forgotten = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    worker = Scope("host", settings.WORKER_SCOPE_SLUG)
    assert worker.key not in {"a", "b"}

    with django_capture_on_commit_callbacks(execute=True):
        resumed = system("whatsapp_inbox.delivery.resume", {}, worker)

    assert (resumed.messages, resumed.erasures) == (2, 2)
    replies = sorted((body["hub"], body["to"], body["text"]) for body in (json.loads(c.request.content) for c in sent.calls))
    assert replies == [("a", "+34600111222", "Hola desde a"), ("b", "+34600222111", "Hola desde b")]
    numbers = sorted((body["hub"], body["phone"]) for body in (json.loads(c.request.content) for c in forgotten.calls))
    assert numbers == [("a", "+34600111333"), ("b", "+34600222333")]
    assert sorted(Conversation.objects.filter(erased_at__isnull=False).values_list("erase_status", flat=True)) == ["done", "done"]


def opened(scope: Scope, phone: str) -> Conversation:
    """A conversation of ``scope`` whose customer wrote ten minutes ago (the 24 hours are open)."""
    receive(f"wamid.{scope.key}.{phone}", phone, scope=scope, sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
    return Conversation.objects.get(phone=f"+{phone}")


def hubs_at(route) -> list[str]:
    return [json.loads(call.request.content)["hub"] for call in route.calls]


@respx.mock
@pytest.mark.parametrize(("recorded", "goes_for"), [("a", "a"), ("", "b")], ids=["its-business", "before-0007"])
def test_retry_hands_a_message_over_for_the_business_that_sent_it(django_capture_on_commit_callbacks, recorded, goes_for):
    """b's employee retries, from the shared inbox, a reply a sent that has not left: erplora.com sends it for a (from
    a's number), never for b; a message sent before 0007 (no business recorded) is retried as the one who asks."""
    connected(A, "+34910000000")
    connected(B, "+34910000001")
    conversation = opened(A, "34600111222")
    out = run(
        "whatsapp_inbox.message.send",
        {"id": str(conversation.id), "text": "Hola desde a", "client_message_id": str(uuid.uuid7())},
        ctx_for(scope=A),
    )  # queued: its after-COMMIT delivery never ran
    Message.objects.filter(pk=out.id).update(host=recorded)
    sent = respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.out.1"}))

    with django_capture_on_commit_callbacks(execute=True):
        run("whatsapp_inbox.message.retry", {"id": str(out.id)}, ctx_for(scope=B))

    assert hubs_at(sent) == [goes_for]
    assert json.loads(sent.calls.last.request.content)["text"] == "Hola desde a"
    assert Message.objects.get(pk=out.id).status == "sent"


@respx.mock
@pytest.mark.parametrize(("recorded", "goes_for"), [("a", "a"), ("", "b")], ids=["its-business", "before-0007"])
def test_erasing_an_erased_number_again_asks_erplora_to_forget_it_for_the_business_that_erased_it(
    django_capture_on_commit_callbacks, recorded, goes_for
):
    """a erased a number and erplora.com was never asked to forget it; b erases it again from the shared inbox (by its
    id): erplora.com is asked to forget it for a, never for b; an erasure from before 0007 goes as the one who asks."""
    conversation = opened(A, "34600111333")
    run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=A))  # pending at erplora.com
    Conversation.objects.filter(pk=conversation.id).update(erase_host=recorded)
    forgotten = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))

    with django_capture_on_commit_callbacks(execute=True):
        run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=B))

    assert hubs_at(forgotten) == [goes_for]
    assert json.loads(forgotten.calls.last.request.content)["phone"] == "+34600111333"
    assert Conversation.objects.get(pk=conversation.id).erase_status == "done"


# ── At once, from the context a request of another business runs in (phase 1) ─────────────────────────────────────
#
# FIX-HUB-WHATSAPP-INBOX-RETRY-OF-ANOTHER-BUSINESS-WAITS-FOR-THE-SWEEP. A request on a's host runs in a's context
# (``use_hub``), and phase 1's tables show it b's rows too. What it hands to erplora.com for b runs, after its COMMIT,
# where b's operations run (phase 1's shared database, as the worker's sweep hands it over), at once: never in a's
# context, where b's claim is refused (``HubContextMismatch``) and the delivery waited for the sweep, 2 to 5 minutes
# later. The real pool of ``base.outbound`` makes the call (``outbound_threads``), on committed data, and the clock
# never passes the 2 minutes: no sweep could have sent it.

#: The most a test waits for what the pool's thread hands over.
WAIT_SECONDS = 10


def phase_1_hub(slug: str):
    """A hub of phase 1 (``db_name=""``): its data in the shared tables, with every other business's."""
    from control.models import Hub

    hub, _ = Hub.objects.update_or_create(slug=slug, defaults={"status": Hub.Status.READY, "db_name": ""})
    return hub


def contexts_at(monkeypatch, door: str) -> list[tuple[str, str, str]]:
    """Who each call to erplora.com's ``door`` went for and where its thread worked: (hub, context kind, alias)."""
    seen: list[tuple[str, str, str]] = []
    real = getattr(gateway, door)

    def spied(*args, **kwargs):
        active = context.current()
        seen.append((kwargs["hub"], active.kind, active.alias))
        return real(*args, **kwargs)

    monkeypatch.setattr(gateway, door, spied)
    return seen


def failures(caplog) -> list[str]:
    """What the pool's threads logged as failed (the job raised), with the exception's name."""
    return [
        f"{record.getMessage()} {record.exc_info[0].__name__ if record.exc_info else ''}"
        for record in caplog.records
        if record.name == "base.outbound" and record.levelno >= logging.ERROR
    ]


def handed_over(done: Callable[[], bool], caplog) -> None:
    """Wait, in the shared database, until the pool's thread recorded erplora.com's answer, or a job failed."""
    deadline = time.monotonic() + WAIT_SECONDS
    with context.use_shared_database():
        while not (done() or failures(caplog)) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert failures(caplog) == []
        assert done()


def queued_by(scope: Scope, phone: str) -> Message:
    """A reply ``scope`` sent whose delivery after the COMMIT never ran (the worker was stopping): on its way."""
    conversation = opened(scope, phone)
    with the_worker_stopping():
        out = run(
            "whatsapp_inbox.message.send",
            {"id": str(conversation.id), "text": f"Hola desde {scope.key}", "client_message_id": str(uuid.uuid7())},
            ctx_for(scope=scope),
        )
    message = Message.objects.get(pk=out.id)
    assert (message.host, message.status) == (scope.key, Message.Status.QUEUED)
    return message


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_retry_from_another_business_s_request_hands_the_message_over_at_once(monkeypatch, caplog):
    """WHATSAPP_INBOX-F34: a's employee taps «Retry» on b's reply that has not left: erplora.com sends it at once,
    for b, from the shared database where b's operations run; nothing is refused nor left for the sweep."""
    with respx.mock(assert_all_called=False) as saas:
        sent = saas.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.out.b"}))
        connected(A, "+34910000000")
        connected(B, "+34910000001")
        message = queued_by(B, "34600222111")
        calls = contexts_at(monkeypatch, "send")
        hub_a = phase_1_hub("a")
        caplog.clear()
        monkeypatch.setattr(context, "_test_fallback", None)  # as in production: a request runs in its hub

        with context.use_hub(hub_a):
            run("whatsapp_inbox.message.retry", {"id": str(message.id)}, ctx_for(scope=A))

        handed_over(lambda: Message.objects.get(pk=message.id).status == Message.Status.SENT, caplog)
    assert hubs_at(sent) == ["b"]
    assert json.loads(sent.calls.last.request.content)["text"] == "Hola desde b"
    assert calls == [("b", context.SHARED, "default")]


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_erasing_again_from_another_business_s_request_asks_erplora_to_forget_at_once(monkeypatch, caplog):
    """WHATSAPP_INBOX-F10/F11: b erased a number and erplora.com was never asked to forget it; a's employee erases it
    again from the shared inbox: erplora.com is asked at once, for b, from the shared database."""
    with respx.mock(assert_all_called=False) as saas:
        forgotten = saas.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
        conversation = opened(B, "34600222333")
        with the_worker_stopping():
            run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=B))
        assert Conversation.objects.filter(pk=conversation.id, erase_host="b", erase_status="pending").exists()
        calls = contexts_at(monkeypatch, "erase")
        hub_a = phase_1_hub("a")
        caplog.clear()
        monkeypatch.setattr(context, "_test_fallback", None)

        with context.use_hub(hub_a):
            run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=A))

        handed_over(lambda: Conversation.objects.get(pk=conversation.id).erase_status == "done", caplog)
    assert hubs_at(forgotten) == ["b"]
    assert json.loads(forgotten.calls.last.request.content)["phone"] == "+34600222333"
    assert calls == [("b", context.SHARED, "default")]


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_the_sweep_run_in_a_business_s_context_hands_each_stuck_message_over_where_its_business_runs(
    fixed_clock, monkeypatch, caplog
):
    """The sweep in a hub of phase 1's context (phase 2's scheduler runs each hub's tasks under ``use_hub``) sees every
    business's stuck message in the shared tables: a's goes in a's context, b's in the shared database, both at once."""
    with respx.mock(assert_all_called=False) as saas:
        sent = saas.post(SEND).mock(
            side_effect=lambda request: httpx.Response(
                200, json={"wa_message_id": f"wamid.out.{json.loads(request.content)['hub']}"}
            )
        )
        connected(A, "+34910000000")
        connected(B, "+34910000001")
        stuck = [queued_by(A, "34600111222"), queued_by(B, "34600222111")]
        calls = contexts_at(monkeypatch, "send")
        monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))  # past their 2 minutes
        hub_a = phase_1_hub("a")
        caplog.clear()
        monkeypatch.setattr(context, "_test_fallback", None)

        with context.use_hub(hub_a):
            resumed = system("whatsapp_inbox.delivery.resume", {}, A)

        assert resumed.messages == 2
        handed_over(
            lambda: sorted(Message.objects.filter(pk__in=[m.id for m in stuck]).values_list("status", flat=True))
            == [Message.Status.SENT, Message.Status.SENT],
            caplog,
        )
    assert sorted(hubs_at(sent)) == ["a", "b"]
    assert sorted(calls) == [("a", context.HUB, "default"), ("b", context.SHARED, "default")]
