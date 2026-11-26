"""The models of a WhatsApp conversation, its messages and its notes: keys, defaults, the database guards (one row
per message, one live conversation per number), Meta's 24-hour window and the searchable contact name."""

import datetime as dt

from apps.whatsapp_inbox.models.conversations import Conversation, Message, Note
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, violates

pytestmark = HUB_DB


def conversation(phone="+34600111222", **fields):
    return Conversation.objects.create(phone=phone, **fields)


def message(conv, wa_id="wamid.1", **fields):
    return Message.objects.create(
        conversation=conv, wa_message_id=wa_id, sent_at=NOW, **fields
    )


def test_keys_are_uuid7():
    conv = conversation()
    msg = message(conv)
    note = Note.objects.create(conversation=conv, text="Llamar mañana")
    assert {obj.pk.version for obj in (conv, msg, note)} == {7}


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


def test_the_window_is_24_hours_from_the_customer_s_last_message():
    conv = conversation()
    assert conv.window_open(NOW) is False  # she never wrote
    conv.last_inbound_at = NOW - dt.timedelta(hours=23, minutes=59)
    assert conv.window_open(NOW) is True
    assert conv.window_expires_at() == NOW + dt.timedelta(minutes=1)
    conv.last_inbound_at = NOW - dt.timedelta(hours=24)
    assert conv.window_open(NOW) is False


def test_deleting_a_conversation_takes_its_messages_and_notes():
    conv = conversation()
    message(conv)
    Note.objects.create(conversation=conv, text="x")
    conv.delete()
    assert (Message.objects.count(), Note.objects.count()) == (0, 0)


def test_str():
    conv = conversation(contact_name="Ana")
    assert str(conv) == "Ana (+34600111222)"


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
