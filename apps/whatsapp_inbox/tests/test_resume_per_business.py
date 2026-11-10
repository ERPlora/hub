"""Every delivery and erasure is resumed as the business of the active database (hub#1053)."""

import datetime as dt
import json
import uuid

import httpx
import pytest
import respx
from live.context import Scope

from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, ctx_for, receive, run, system
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = [
    pytest.mark.django_db(databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]

SAAS = "http://saas.test"
SEND = f"{SAAS}/internal/whatsapp/send"
ERASE = f"{SAAS}/internal/whatsapp/erase"


def connected(hub, phone: str) -> None:
    scope = Scope("host", hub.slug)
    with use_hub(hub):
        system(
            "whatsapp_inbox.channel.sync",
            {"version": 1, "status": "connected", "phone_number": phone, "monthly_limit": 150, "templates": None},
            scope,
        )


def opened(hub, phone: str) -> Conversation:
    scope = Scope("host", hub.slug)
    with use_hub(hub):
        receive(f"wamid.{hub.slug}.{phone}", phone, scope=scope, sent_at=(NOW - dt.timedelta(minutes=10)).isoformat())
        return Conversation.objects.get(phone=f"+{phone}")


def hubs_at(route) -> list[str]:
    return [json.loads(call.request.content)["hub"] for call in route.calls]


@respx.mock
def test_each_worker_pass_hands_only_its_own_stuck_message_and_erasure(hub_a, hub_b, django_capture_on_commit_callbacks, fixed_clock, monkeypatch):
    for hub, number, talking, erased in (
        (hub_a, "+34910000000", "34600111222", "34600111333"),
        (hub_b, "+34910000001", "34600222111", "34600222333"),
    ):
        connected(hub, number)
        conversation = opened(hub, talking)
        with use_hub(hub):
            run(
                "whatsapp_inbox.message.send",
                {"id": str(conversation.id), "text": f"Hola desde {hub.slug}", "client_message_id": str(uuid.uuid7())},
                ctx_for(scope=Scope("host", hub.slug)),
            )
        gone = opened(hub, erased)
        with use_hub(hub):
            run("whatsapp_inbox.conversation.erase", {"id": str(gone.id)}, ctx_for(scope=Scope("host", hub.slug)))
    sent = respx.post(SEND).mock(
        side_effect=lambda request: httpx.Response(200, json={"wa_message_id": f"wamid.out.{json.loads(request.content)['to']}"})
    )
    forgotten = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))

    for hub in (hub_a, hub_b):
        with use_hub(hub) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
            resumed = system("whatsapp_inbox.delivery.resume", {}, Scope("host", hub.slug))
        assert (resumed.messages, resumed.erasures) == (1, 1)

    replies = sorted((body["hub"], body["to"], body["text"]) for body in (json.loads(c.request.content) for c in sent.calls))
    assert replies == [("tenant-a", "+34600111222", "Hola desde tenant-a"), ("tenant-b", "+34600222111", "Hola desde tenant-b")]
    numbers = sorted((body["hub"], body["phone"]) for body in (json.loads(c.request.content) for c in forgotten.calls))
    assert numbers == [("tenant-a", "+34600111333"), ("tenant-b", "+34600222333")]
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            assert Conversation.objects.get(erased_at__isnull=False).erase_status == "done"


@respx.mock
def test_retry_hands_a_message_over_for_the_active_business(hub_a, django_capture_on_commit_callbacks):
    connected(hub_a, "+34910000000")
    conversation = opened(hub_a, "34600111222")
    with use_hub(hub_a):
        out = run(
            "whatsapp_inbox.message.send",
            {"id": str(conversation.id), "text": "Hola desde A", "client_message_id": str(uuid.uuid7())},
            ctx_for(scope=Scope("host", hub_a.slug)),
        )
    from apps.whatsapp_inbox import gateway
    assert gateway.configured()
    assert out.status == Message.Status.QUEUED
    sent = respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.out.1"}))

    with use_hub(hub_a) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
        run("whatsapp_inbox.message.retry", {"id": str(out.id)}, ctx_for(scope=Scope("host", hub_a.slug)))

    with use_hub(hub_a):
        current = Message.objects.get(pk=out.id)
        assert (current.status, current.error_code, current.error_message) == ("sent", "", "")
    assert hubs_at(sent) == ["tenant-a"]
    assert json.loads(sent.calls.last.request.content)["text"] == "Hola desde A"
    with use_hub(hub_a):
        assert Message.objects.get(pk=out.id).status == "sent"


@respx.mock
def test_erasing_an_erased_number_again_asks_erplora_to_forget_it_for_the_active_business(hub_a, django_capture_on_commit_callbacks):
    conversation = opened(hub_a, "34600111333")
    with use_hub(hub_a):
        run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=Scope("host", hub_a.slug)))
    forgotten = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))

    with use_hub(hub_a) as active, django_capture_on_commit_callbacks(execute=True, using=active.alias):
        run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}, ctx_for(scope=Scope("host", hub_a.slug)))

    assert hubs_at(forgotten) == ["tenant-a"]
    assert json.loads(forgotten.calls.last.request.content)["phone"] == "+34600111333"
    with use_hub(hub_a):
        assert Conversation.objects.get(pk=conversation.id).erase_status == "done"
