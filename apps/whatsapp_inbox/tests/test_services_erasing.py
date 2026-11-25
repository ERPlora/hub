"""Erasing a number's data (WHATSAPP_INBOX-F10): every personal datum blanked, the number freed and erplora.com asked
to forget it after the COMMIT; ``respx`` is the transport to erplora.com only.
"""

import datetime as dt
import json

import httpx
import pytest
import respx
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Conversation, Message, Note
from apps.whatsapp_inbox.tests.conftest import (
    HUB_DB,
    NOW,
    SAAS,
    A,
    answering,
    conv,
    ctx_for,
    events,
    ready,
    receive,
    run,
    send,
    stored,
    system,
)
from base.tenancy.context import current_alias

pytestmark = HUB_DB


# ── WHATSAPP_INBOX-F10 Erase a number's data ────────────────────────────────────────────────────


def test_erasing_a_number_blanks_every_personal_datum_and_frees_it(make_user):
    receive(
        "wamid.1",
        contact_name="Ana",
        media={
            "url": "https://erplora.com/m/1",
            "caption": "foto",
            "filename": "a.jpg",
        },
        payload={"from": "34600111222"},
    )
    c = conv()
    run("whatsapp_inbox.note.add", {"id": str(c.id), "text": "Alérgica al tinte"})
    out = run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    assert out.id == c.id
    c.refresh_from_db()
    assert (
        c.phone,
        c.contact_name,
        c.last_message_preview,
        c.status,
        c.unread_count,
        c.erased_at,
    ) == (
        "",
        "",
        "",
        "closed",
        0,
        NOW,
    )
    message = Message.objects.get()
    assert (
        message.body,
        message.media_url,
        message.media_caption,
        message.media_filename,
        message.payload,
    ) == (
        "",
        "",
        "",
        "",
        {},
    )
    assert (
        message.wa_message_id == "wamid.1"
    )  # kept: a redelivery is never stored again
    assert Note.objects.count() == 0
    assert events("whatsapp_inbox.conversation.erased") == [{"id": str(c.id)}]
    # Twice is harmless.
    run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    assert Conversation.objects.get(pk=c.id).erased_at == NOW
    # A redelivery of an erased message stays erased.
    assert receive("wamid.1").created is False
    assert Conversation.objects.filter(erased_at__isnull=True).count() == 0


ERASE = f"{SAAS}/internal/whatsapp/erase"


@respx.mock
def test_no_notice_of_the_app_keeps_her_number_her_name_or_what_was_said(delivered):
    """The internal history keeps the notices for days after an erasure; they
    carry identifiers only, so erasing the conversation leaves nothing of her there."""
    c = ready(contact_name="Ana Secreta", text="Mi alergia es al tinte")
    answering()
    delivered(lambda: send({"id": str(c.id), "text": "Apuntado, Ana"}))
    run("whatsapp_inbox.note.add", {"id": str(c.id), "text": "Nota sobre Ana"})
    run("whatsapp_inbox.conversation.set_status", {"id": str(c.id), "status": "pending"})
    respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    notices = [json.dumps(e.payload, ensure_ascii=False) for e in OutboxEvent.objects.filter(name__startswith="whatsapp_inbox.")]
    assert len(notices) >= 5
    for said in ("600111222", "Ana Secreta", "alergia", "Apuntado", "Nota sobre"):
        assert not [notice for notice in notices if said in notice], said


@respx.mock
def test_erasing_asks_erplora_to_forget_the_number_after_the_commit(django_capture_on_commit_callbacks):
    receive("wamid.1")
    receive("wamid.2")
    c = conv()
    route = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
        run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
        assert route.call_count == 0
        c.refresh_from_db()
        assert (c.phone, c.erase_status, c.erase_phone) == ("", "pending", "+34600111222")
    assert json.loads(route.calls.last.request.content) == {
        "hub": A.key,
        "phone": "+34600111222",
        "wa_message_ids": ["wamid.1", "wamid.2"],
    }
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone) == ("done", "")


@respx.mock
def test_an_erasure_erplora_does_not_confirm_stays_pending_and_is_asked_again(delivered):
    receive("wamid.1")
    c = conv()
    route = respx.post(ERASE).mock(side_effect=[httpx.ConnectError("refused")])
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone, c.phone) == ("pending", "+34600111222", "")
    route.side_effect = [httpx.Response(200, json={"erased": True})]
    delivered(lambda: run("whatsapp_inbox.conversation.erase", {"id": str(c.id)}))
    c.refresh_from_db()
    assert (c.erase_status, c.erase_phone) == ("done", "")


@respx.mock
def test_the_worker_resumes_what_was_left_for_erplora(delivered, fixed_clock, monkeypatch):
    c = ready()
    stuck = send({"id": str(c.id), "text": "Hola"})  # queued; its COMMIT's delivery never ran
    receive("wamid.X", "34600999888")
    other = Conversation.objects.get(phone="+34600999888")
    run("whatsapp_inbox.conversation.erase", {"id": str(other.id)})  # pending at erplora.com
    answering()
    respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    # Not before 2 minutes: a delivery may still be on its way.
    early = delivered(lambda: system("whatsapp_inbox.delivery.resume"))
    assert early.model_dump() == {"messages": 0, "erasures": 0, "templates": 0, "template_deletions": 0}
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    out = delivered(lambda: system("whatsapp_inbox.delivery.resume"))
    assert out.model_dump() == {"messages": 1, "erasures": 1, "templates": 0, "template_deletions": 0}
    assert stored(stuck).status == "sent"
    other.refresh_from_db()
    assert other.erase_status == "done"


def test_only_owner_and_admin_erase():
    receive("wamid.1")
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            run(
                "whatsapp_inbox.conversation.erase",
                {"id": str(conv().id)},
                ctx_for(role),
            )


def test_an_erased_conversation_is_not_found_by_the_inbox():
    receive("wamid.1")
    c = conv()
    run("whatsapp_inbox.conversation.erase", {"id": str(c.id)})
    for name, payload in (
        ("whatsapp_inbox.conversation.mark_read", {"id": str(c.id)}),
        ("whatsapp_inbox.note.add", {"id": str(c.id), "text": "x"}),
        ("whatsapp_inbox.conversation.set_status", {"id": str(c.id), "status": "open"}),
    ):
        with pytest.raises(NotFound):
            run(name, payload)
