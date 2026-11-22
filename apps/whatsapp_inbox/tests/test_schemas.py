"""Inputs of the WhatsApp inbox: what each operation takes and the 422 it answers per field.

These schemas are also the assistant's tools and the contract of erplora.com's doors, so every field
has a description and the SaaS's bodies are read exactly as the WORKBOOK writes them.
"""

import datetime as dt
import pkgutil
from importlib import import_module
from uuid import UUID

import pytest
from ninja import Schema
from pydantic import ValidationError

from apps.whatsapp_inbox import schemas
from apps.whatsapp_inbox.schemas.channel import ChannelConnectIn, ChannelSyncIn
from apps.whatsapp_inbox.schemas.conversations import AssignIn, ConversationListIn, LinkCustomerIn
from apps.whatsapp_inbox.schemas.fields import ConversationRefIn
from apps.whatsapp_inbox.schemas.notes import NoteAddIn
from apps.whatsapp_inbox.schemas.received import ReceiveIn, StatusIn
from apps.whatsapp_inbox.schemas.sending import SendIn

ID = UUID("0199e000-0000-7000-8000-000000000001")


def errors(schema, data) -> dict[str, str]:
    with pytest.raises(ValidationError) as excinfo:
        schema.model_validate(data)
    return {
        ".".join(str(p) for p in e["loc"]) or "__all__": e["msg"]
        for e in excinfo.value.errors()
    }


def test_every_field_is_described_for_the_assistant():
    modules = [import_module(f"{schemas.__name__}.{m.name}") for m in pkgutil.iter_modules(schemas.__path__)]
    for module in modules:
        for name in dir(module):
            schema = getattr(module, name)
            if (
                isinstance(schema, type)
                and issubclass(schema, Schema)
                and schema is not Schema
            ):
                for field, info in schema.model_fields.items():
                    assert info.description, f"{name}.{field}"


def test_a_conversation_is_named_by_id_or_by_a_reference():
    assert ConversationRefIn.model_validate({"id": str(ID)}).id == ID
    assert (
        ConversationRefIn.model_validate(
            {"conversation": "+34 600 111 222"}
        ).conversation
        == "+34 600 111 222"
    )
    assert "conversation" in errors(ConversationRefIn, {})
    assert "conversation" in errors(ConversationRefIn, {"conversation": "   "})


def test_lists_page_by_at_most_100():
    assert ConversationListIn.model_validate({}).limit == 50
    assert "limit" in errors(ConversationListIn, {"limit": 101})
    assert "offset" in errors(ConversationListIn, {"offset": -1})


def test_the_list_s_assignment_filter_is_me_none_or_a_person():
    assert ConversationListIn.model_validate({"assigned": "me"}).assigned == "me"
    assert ConversationListIn.model_validate({"assigned": "none"}).assigned == "none"
    person = "01a16000-0000-7000-8000-0000000000a7"
    assert ConversationListIn.model_validate({"assigned": person}).assigned == person
    assert "assigned" in errors(ConversationListIn, {"assigned": "somebody"})
    # A person is someone of the business's database (base.HubUser): control's number no longer names one.
    assert "assigned" in errors(ConversationListIn, {"assigned": "7"})
    assert "status" in errors(ConversationListIn, {"status": "archived"})
    assert "sort" in errors(ConversationListIn, {"sort": "payload"})


KEY = "0199e000-0000-7000-8000-0000000000aa"


def test_send_takes_one_text_or_one_template():
    text = SendIn.model_validate({"id": str(ID), "text": "  Hola  ", "client_message_id": KEY})
    assert text.text == "Hola" and text.template is None
    template = SendIn.model_validate(
        {"conversation": "Ana", "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]}, "client_message_id": KEY}
    )
    assert template.template.name == "recordatorio" and template.template.language is None
    assert errors(SendIn, {"id": str(ID), "client_message_id": KEY}) == {
        "text": "Value error, Write a message or choose a template."
    }
    assert "text" in errors(SendIn, {"id": str(ID), "text": "Hola", "template": {"name": "x"}, "client_message_id": KEY})
    assert "text" in errors(SendIn, {"id": str(ID), "text": "x" * 4097, "client_message_id": KEY})


def test_send_goes_to_a_conversation_or_to_a_number():
    to = SendIn.model_validate({"to": "+34600111222", "template": {"name": "x"}, "client_message_id": KEY})
    assert to.to == "+34600111222"
    assert errors(SendIn, {"text": "Hola", "client_message_id": KEY}) == {
        "conversation": "Value error, Say which conversation: its id, its number or the customer's name."
    }


def test_assign_takes_one_person_or_nobody():
    assert AssignIn.model_validate({"id": str(ID), "assignee": "me"}).assignee == "me"
    person = UUID("01a16000-0000-7000-8000-0000000000a7")
    assert AssignIn.model_validate({"id": str(ID), "assignee_id": str(person)}).assignee_id == person
    assert AssignIn.model_validate({"id": str(ID), "unassign": True}).unassign is True
    assert "assignee" in errors(AssignIn, {"id": str(ID)})
    assert "assignee" in errors(
        AssignIn, {"id": str(ID), "assignee": "me", "unassign": True}
    )


def test_link_customer_takes_a_card_create_or_unlink():
    assert (
        LinkCustomerIn.model_validate({"id": str(ID), "create": True}).create is True
    )
    assert (
        LinkCustomerIn.model_validate(
            {"id": str(ID), "customer": "Ana López"}
        ).customer
        == "Ana López"
    )
    assert "customer" in errors(LinkCustomerIn, {"id": str(ID)})
    assert "customer" in errors(
        LinkCustomerIn, {"id": str(ID), "create": True, "unlink": True}
    )


def test_a_note_says_something():
    assert "text" in errors(NoteAddIn, {"id": str(ID), "text": "  "})
    assert "text" in errors(NoteAddIn, {"id": str(ID), "text": "x" * 5001})


def test_the_inbound_body_is_erplora_s_contract():
    body = ReceiveIn.model_validate(
        {
            "wa_message_id": "wamid.1",
            "from": "34600111222",
            "type": "image",
            "media": {
                "url": "https://erplora.com/whatsapp/media/abc",
                "mime_type": "image/jpeg",
            },
            "sent_at": "2026-10-15T10:00:00Z",
            "payload": {"id": "wamid.1"},
        }
    )
    assert (body.from_, body.direction, body.source, body.contact_name, body.text) == (
        "34600111222",
        "inbound",
        "live",
        "",
        "",
    )
    assert body.media.url == "https://erplora.com/whatsapp/media/abc"
    assert body.sent_at == dt.datetime(2026, 10, 15, 10, tzinfo=dt.UTC)
    assert "wa_message_id" in errors(ReceiveIn, {"from": "34600111222"})
    assert "from" in errors(ReceiveIn, {"wa_message_id": "wamid.1"})
    assert "direction" in errors(
        ReceiveIn, {"wa_message_id": "w", "from": "1", "direction": "sideways"}
    )
    assert "media.url" in errors(
        ReceiveIn, {"wa_message_id": "w", "from": "1", "media": {"url": "ftp://x"}}
    )


def test_the_status_body_moves_through_meta_s_four_statuses():
    assert (
        StatusIn.model_validate({"wa_message_id": "w", "status": "read"}).status
        == "read"
    )
    failed = StatusIn.model_validate(
        {
            "wa_message_id": "w",
            "status": "failed",
            "error": {"code": "131047", "message": "Re-engagement"},
        }
    )
    assert failed.error.code == "131047"
    assert "status" in errors(StatusIn, {"wa_message_id": "w", "status": "received"})


def test_the_channel_body_carries_a_version_and_maybe_the_templates():
    body = ChannelSyncIn.model_validate({"version": 3, "status": "connected"})
    assert (body.templates, body.monthly_limit, body.usage_month) == (None, 0, "")
    assert "usage_month" in errors(
        ChannelSyncIn, {"version": 1, "status": "connected", "usage_month": "10/2026"}
    )
    assert "version" in errors(ChannelSyncIn, {"version": -1, "status": "connected"})
    assert "templates.0.category" in errors(
        ChannelSyncIn,
        {
            "version": 1,
            "status": "connected",
            "templates": [{"name": "x", "language": "es", "category": "PROMO"}],
        },
    )


def test_send_requires_a_key_of_the_caller_s_own():
    assert set(errors(SendIn, {"id": str(ID), "text": "Hola"})) == {"client_message_id"}


def test_numbers_from_erplora_are_international_or_a_422():
    assert "from" in errors(ReceiveIn, {"wa_message_id": "w", "from": "3460011122233344455"})
    assert "from" in errors(ReceiveIn, {"wa_message_id": "w", "from": "+0034600111222"})
    assert ReceiveIn.model_validate({"wa_message_id": "w", "from": "+34600111222"}).from_ == "+34600111222"
    assert "phone_number" in errors(ChannelSyncIn, {"version": 1, "status": "connected", "phone_number": "910 000 000"})
    assert "phone_number" in errors(ChannelSyncIn, {"version": 1, "status": "connected", "phone_number": "+349100000000000000"})
    assert ChannelSyncIn.model_validate({"version": 1, "status": "connected", "phone_number": "+34910000000"}).phone_number


def test_an_attachment_comes_from_erplora_over_https_only(settings):
    settings.SAAS_URL = "https://erplora.com"
    settings.DEBUG = False
    good = {"wa_message_id": "w", "from": "34600111222", "media": {"url": "https://erplora.com/whatsapp/media/1"}}
    assert ReceiveIn.model_validate(good).media.url == "https://erplora.com/whatsapp/media/1"
    for url in ("https://evil.example/whatsapp/media/1", "http://erplora.com/whatsapp/media/1", "https://erplora.com.evil.example/x"):
        assert "media.url" in errors(ReceiveIn, {**good, "media": {"url": url}}), url


def test_local_development_takes_the_local_saas_s_own_origin(settings):
    settings.SAAS_URL = "http://localhost:8001"
    settings.DEBUG = True
    local = {"wa_message_id": "w", "from": "34600111222", "media": {"url": "http://localhost:8001/whatsapp/media/1"}}
    assert ReceiveIn.model_validate(local).media.url.startswith("http://localhost:8001/")


# ── WHATSAPP_INBOX-F01 What Meta's window gave (door 11, as erplora.com reads it) ───────────────

WINDOW = {"code": " AQD-one-time ", "waba_id": "102290129340398"}


def test_meta_s_window_gives_a_code_and_its_account_and_the_rest_may_be_missing():
    data = ChannelConnectIn.model_validate(WINDOW)
    assert (data.code, data.event, data.waba_id, data.phone_number_id, data.business_id) == (
        "AQD-one-time",
        "FINISH",
        "102290129340398",
        "",
        "",
    )
    coexistence = {**WINDOW, "event": "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"}
    assert ChannelConnectIn.model_validate(coexistence).event == "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("code", "x" * 2049),
        ("waba_id", "abc"),
        ("waba_id", ""),
        ("phone_number_id", "10654-0352"),
        ("business_id", "1" * 51),
        # A window that did not finish never connects anything.
        ("event", "CANCEL"),
        ("event", "ERROR"),
    ],
)
def test_what_the_window_did_not_give_is_never_sent_to_erplora(field, value):
    assert field in errors(ChannelConnectIn, {**WINDOW, field: value})
