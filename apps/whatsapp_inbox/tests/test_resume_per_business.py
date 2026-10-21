"""The worker hands a stuck message and a pending erasure to erplora.com for their own business (review of hub#151).

Phase 1's worker runs ``delivery.resume`` on one fixed scope (``WORKER_SCOPE_SLUG``, base/scheduler.py) and phase 1
shares the tables: a message the Hub sends and a number it asks erplora.com to forget keep the business that made
them, and the resumption hands each over for that business (doors 5 and 6), never for the worker's.
"""

import datetime as dt
import json
import uuid

import httpx
import pytest
import respx
from live.context import Scope

from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.tests.conftest import NOW, A, B, ctx_for, receive, run, system

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
