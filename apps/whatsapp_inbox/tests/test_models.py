"""Models of the WhatsApp inbox: keys, defaults and the database guards (one row per message, one live
conversation per number, one channel row, one template per name and language)."""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import NOW

pytestmark = pytest.mark.django_db


def conversation(phone="+34600111222", **fields):
    return Conversation.objects.create(phone=phone, **fields)


def message(conv, wa_id="wamid.1", **fields):
    return Message.objects.create(
        conversation=conv, wa_message_id=wa_id, sent_at=NOW, **fields
    )


def violates(constraint, create):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        create()
    return constraint in str(excinfo.value)


def test_keys_are_uuid7():
    conv = conversation()
    msg = message(conv)
    note = Note.objects.create(conversation=conv, text="Llamar mañana")
    tpl = Template.objects.create(name="recordatorio", language="es")
    channel = Channel.objects.create()
    assert {obj.pk.version for obj in (conv, msg, note, tpl, channel)} == {7}


def test_defaults():
    conv = conversation()
    assert (
        conv.status,
        conv.unread_count,
        conv.customer,
        conv.assigned_to,
        conv.erased_at,
    ) == (
        "open",
        0,
        None,
        None,
        None,
    )
    msg = message(conv)
    assert (msg.direction, msg.origin, msg.source, msg.kind, msg.status) == (
        "inbound",
        "customer",
        "live",
        "text",
        "received",
    )
    assert msg.payload == {}
    channel = Channel.objects.create()
    assert (
        channel.status,
        channel.monthly_limit,
        channel.monthly_usage,
        channel.version,
    ) == (
        "not_connected",
        0,
        0,
        0,
    )
    tpl = Template.objects.create(name="recordatorio", language="es")
    assert (tpl.category, tpl.status, tpl.variables) == ("UTILITY", "APPROVED", 0)


def test_one_row_per_whatsapp_message():
    conv = conversation()
    message(conv)
    assert violates("whatsapp_inbox_message_wa_id_unique", lambda: message(conv))


def test_one_live_conversation_per_number_and_an_erased_one_frees_it():
    first = conversation()
    assert violates("whatsapp_inbox_conversation_phone_unique", conversation)
    first.erased_at = NOW
    first.phone = ""
    first.save()
    # Erased conversations never compete for a number (several erased ones keep an empty phone).
    conversation()
    erased_again = conversation(phone="+34600999888", erased_at=NOW)
    erased_again.phone = ""
    erased_again.save()


def test_a_client_message_id_is_used_once():
    conv = conversation()
    key = "0199e000-0000-7000-8000-000000000001"
    message(conv, "wamid.1", client_message_id=key, direction="outbound", origin="hub")
    assert violates(
        "whatsapp_inbox_message_client_id_unique",
        lambda: message(
            conv, "wamid.2", client_message_id=key, direction="outbound", origin="hub"
        ),
    )
    # Received messages carry none, and many of them do.
    message(conv, "wamid.3")
    message(conv, "wamid.4")


def test_one_channel_row():
    Channel.objects.create()
    assert violates("whatsapp_inbox_channel_singleton", Channel.objects.create)


def test_one_template_per_name_and_language():
    Template.objects.create(name="recordatorio", language="es")
    Template.objects.create(name="recordatorio", language="en")
    assert violates(
        "whatsapp_inbox_template_live_name_language_unique",
        lambda: Template.objects.create(name="recordatorio", language="es"),
    )


def test_a_template_deleted_here_frees_its_name_and_language():
    Template.objects.create(name="recordatorio", language="es", deleted_at=NOW, delete_state="done")
    Template.objects.create(name="recordatorio", language="es")
    assert Template.objects.filter(name="recordatorio", language="es").count() == 2


def test_one_save_of_a_template_per_key():
    key = uuid.uuid7()
    Template.objects.create(name="uno", language="es", submit_key=key)
    assert violates(
        "whatsapp_inbox_template_submit_key_unique",
        lambda: Template.objects.create(name="dos", language="es", submit_key=key),
    )


@pytest.mark.parametrize(
    ("fields", "handled"),
    [
        ({}, True),
        ({"header_format": "TEXT", "header": "Tu cita"}, True),
        ({"header_format": "TEXT", "header": "Hola {{1}}"}, False),
        ({"header_format": "IMAGE"}, False),
        ({"category": "AUTHENTICATION"}, False),
        ({"buttons": [{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "URL", "text": "Web", "url": "https://p.test"}]}, True),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "https://p.test/{{1}}"}]}, False),
        ({"buttons": [{"type": "COPY_CODE", "text": "Copiar"}]}, False),
    ],
)
def test_the_hub_handles_templates_it_can_write_and_fill(fields, handled):
    row = Template.objects.create(name="t", language="es", **fields)
    assert row.supported is handled
    assert Template.objects.get(pk=row.pk).supported is handled


def test_the_window_is_24_hours_from_the_customer_s_last_message():
    conv = conversation()
    assert conv.window_open(NOW) is False  # she never wrote
    conv.last_inbound_at = NOW - dt.timedelta(hours=23, minutes=59)
    assert conv.window_open(NOW) is True
    assert conv.window_expires_at() == NOW + dt.timedelta(minutes=1)
    conv.last_inbound_at = NOW - dt.timedelta(hours=24)
    assert conv.window_open(NOW) is False


def test_the_cap_is_the_platform_s_figure_of_this_month():
    channel = Channel(monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    assert channel.cap_reached("2026-10") is True
    # Another month's figure counts as nothing spent: November starts again even before the SaaS speaks.
    assert channel.cap_reached("2026-11") is False
    channel.monthly_usage = 149
    assert channel.cap_reached("2026-10") is False
    # 0 = no cap.
    assert (
        Channel(monthly_limit=0, monthly_usage=900, usage_month="2026-10").cap_reached(
            "2026-10"
        )
        is False
    )


def test_deleting_a_conversation_takes_its_messages_and_notes():
    conv = conversation()
    message(conv)
    Note.objects.create(conversation=conv, text="x")
    conv.delete()
    assert (Message.objects.count(), Note.objects.count()) == (0, 0)


def test_str():
    conv = conversation(contact_name="Ana")
    assert str(conv) == "Ana (+34600111222)"
    assert str(Template(name="recordatorio", language="es")) == "recordatorio (es)"


def test_a_message_queued_by_the_hub_has_no_whatsapp_id_until_it_leaves():
    conv = conversation()
    key_1, key_2 = "0199e000-0000-7000-8000-000000000011", "0199e000-0000-7000-8000-000000000012"
    first = Message.objects.create(
        conversation=conv, direction="outbound", origin="hub", status="queued", client_message_id=key_1, sent_at=NOW
    )
    Message.objects.create(
        conversation=conv, direction="outbound", origin="hub", status="sending", client_message_id=key_2, sent_at=NOW
    )
    assert first.wa_message_id is None
    assert first.template_variables == []
    assert {choice for choice, _ in Message.Status.choices} >= {"queued", "sending"}


def test_a_conversation_remembers_what_erplora_still_has_to_forget():
    conv = conversation(contact_name="Ana 🌸")
    assert (conv.erase_status, conv.erase_phone, conv.last_message_kind) == ("", "", "")
    assert {choice for choice, _ in Conversation.EraseStatus.choices} == {"", "pending", "done"}


def test_the_contact_s_name_is_kept_searchable_without_accents_or_emoji():
    conv = conversation(contact_name="  Ána  López 🌸 ")
    assert conv.contact_search == "ana lopez"
    conv.contact_name = "Bea"
    conv.save()
    conv.refresh_from_db()
    assert conv.contact_search == "bea"
