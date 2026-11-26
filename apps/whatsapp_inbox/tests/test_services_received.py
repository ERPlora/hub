"""Receiving from erplora.com (WHATSAPP_INBOX-F03, F04, F34): the customer's messages, the card her number joins the
conversation to and the statuses of what the business sent, against the real Customers app.

The cases of the product's tests are kept: one row per WhatsApp message, the history that does not count as unread,
the echo of the owner's phone and the link by number that only fills.
"""

import datetime as dt

import pydantic
import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.whatsapp_inbox.models.conversations import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, card, conv, ctx_for, events, receive, run, system

pytestmark = HUB_DB


# ── WHATSAPP_INBOX-F03 Receive a message ────────────────────────────────────────────────────────


def test_the_first_message_opens_a_conversation_keyed_by_the_international_number():
    out = receive("wamid.1", "34600111222", contact_name="Ana")
    c = conv()
    assert (c.phone, c.contact_name, c.status, c.unread_count) == (
        "+34600111222",
        "Ana",
        "open",
        1,
    )
    assert (c.last_message_at, c.last_inbound_at, c.last_message_direction) == (
        NOW,
        NOW,
        "inbound",
    )
    assert c.last_message_preview == "Hola, ¿tenéis hora mañana?"
    message = Message.objects.get()
    assert (
        message.direction,
        message.origin,
        message.source,
        message.status,
        message.kind,
    ) == (
        "inbound",
        "customer",
        "live",
        "received",
        "text",
    )
    assert (out.id, out.conversation_id, out.created) == (message.id, c.id, True)
    assert events("whatsapp_inbox.message.received") == [
        {
            "id": str(message.id),
            "conversation_id": str(c.id),
            "direction": "inbound",
            "source": "live",
            # It answers nothing the Hub sent (WHATSAPP_INBOX-F38): empty, never absent.
            "reply_to_message_id": None,
            "reply_id": "",
        }
    ]


def test_a_message_delivered_twice_is_one_message_and_one_unread():
    receive("wamid.DUP")
    again = receive("wamid.DUP", text="otro texto")
    assert again.created is False
    assert Message.objects.count() == 1
    assert Message.objects.get().body == "Hola, ¿tenéis hora mañana?"
    assert conv().unread_count == 1
    assert len(events("whatsapp_inbox.message.received")) == 1


def test_the_same_number_in_any_format_is_one_conversation():
    receive("wamid.1", "34600111222")
    receive("wamid.2", "+34600111222")
    assert Conversation.objects.count() == 1
    assert conv().unread_count == 2


def test_another_country_s_prefix_is_another_person():
    receive("wamid.1", "34600111222")
    receive("wamid.2", "33600111222")
    assert set(Conversation.objects.values_list("phone", flat=True)) == {
        "+34600111222",
        "+33600111222",
    }


def test_an_unreadable_number_is_a_422_on_from():
    # A malformed one never reaches the operation (the schema refuses it); a well-formed number of no
    # country is refused by the operation.
    with pytest.raises(pydantic.ValidationError):
        receive("wamid.1", "12")
    with pytest.raises(InvalidPayload) as excinfo:
        receive("wamid.1", "999123456789")
    assert set(excinfo.value.fields) == {"from"}
    assert Conversation.objects.count() == 0


def test_history_keeps_its_time_and_does_not_count_as_unread():
    receive("wamid.1", sent_at=(NOW - dt.timedelta(hours=1)).isoformat())
    receive(
        "wamid.0",
        source="history",
        text="De marzo",
        sent_at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC).isoformat(),
    )
    c = conv()
    assert c.unread_count == 1
    # An older message never becomes «the last one».
    assert c.last_message_at == NOW - dt.timedelta(hours=1)
    assert c.last_message_preview == "Hola, ¿tenéis hora mañana?"
    old = Message.objects.get(wa_message_id="wamid.0")
    assert (old.source, old.sent_at) == (
        "history",
        dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
    )


def test_a_history_placeholder_is_completed_in_place():
    receive("wamid.H", source="history", type="media_placeholder", text="")
    receive(
        "wamid.H",
        source="history",
        type="image",
        text="",
        media={
            "url": "https://erplora.com/whatsapp/media/h",
            "mime_type": "image/jpeg",
            "caption": "Mi pelo",
        },
        payload={"id": "wamid.H", "type": "image"},
    )
    message = Message.objects.get()
    assert (
        message.kind,
        message.media_url,
        message.media_caption,
        message.payload,
    ) == (
        "image",
        "https://erplora.com/whatsapp/media/h",
        "Mi pelo",
        {"id": "wamid.H", "type": "image"},
    )
    assert conv().unread_count == 0


def test_a_live_message_is_never_rewritten_after_the_fact():
    receive("wamid.L", type="media_placeholder", text="")
    receive("wamid.L", type="image", media={"url": "https://erplora.com/m"})
    assert Message.objects.get().kind == "media_placeholder"


def test_the_owner_s_reply_from_the_phone_is_the_business_s_message_and_not_unread():
    receive("wamid.1", sent_at=(NOW - dt.timedelta(minutes=5)).isoformat())
    receive("wamid.ECHO", direction="outbound", text="Sí, a las 10")
    c = conv()
    assert c.unread_count == 1
    assert c.last_inbound_at == NOW - dt.timedelta(minutes=5)
    assert (c.last_message_direction, c.last_message_preview) == (
        "outbound",
        "Sí, a las 10",
    )
    echo = Message.objects.get(wa_message_id="wamid.ECHO")
    assert (echo.direction, echo.origin, echo.status) == (
        "outbound",
        "phone_app",
        "sent",
    )


@pytest.mark.parametrize("status", ["pending", "closed"])
def test_the_customer_writing_again_reopens_the_conversation(status):
    receive("wamid.1")
    Conversation.objects.update(status=status)
    receive(
        "wamid.0", source="history", sent_at=(NOW - dt.timedelta(days=9)).isoformat()
    )
    assert conv().status == status  # the past does not reopen anything
    receive("wamid.2")
    assert conv().status == "open"


def test_an_attachment_is_kept_by_its_url_and_named_in_the_preview():
    receive(
        "wamid.P",
        type="document",
        text="",
        media={
            "url": "https://erplora.com/whatsapp/media/doc",
            "mime_type": "application/pdf",
            "filename": "presupuesto.pdf",
        },
    )
    message = Message.objects.get()
    assert (message.media_url, message.media_mime_type, message.media_filename) == (
        "https://erplora.com/whatsapp/media/doc",
        "application/pdf",
        "presupuesto.pdf",
    )
    assert (conv().last_message_preview, conv().last_message_kind) == ("presupuesto.pdf", "document")


def test_a_message_without_text_keeps_its_type_for_the_inbox_to_name():
    receive("wamid.L", type="location", text="")
    assert (conv().last_message_preview, conv().last_message_kind) == ("", "location")


def test_a_reaction_is_kept_without_counting_nor_becoming_the_last_message():
    receive("wamid.1", text="¿Mañana a las 10?")
    out = receive("wamid.R", type="reaction", text="👍", reply_to="wamid.1")
    c = conv()
    assert (c.unread_count, c.last_message_preview, c.last_message_kind) == (1, "¿Mañana a las 10?", "text")
    reaction = Message.objects.get(pk=out.id)
    assert (reaction.kind, reaction.body, reaction.reply_to) == ("reaction", "👍", "wamid.1")


def test_receiving_is_the_system_s_alone():
    from live.operations import get

    op = get("whatsapp_inbox.message.receive")
    for role in ("hub_owner", "hub_admin", "hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            op(
                ctx_for(role),
                op.input.model_validate({"wa_message_id": "w", "from": "34600111222"}),
            )


def test_after_an_erasure_the_number_starts_a_new_conversation():
    receive("wamid.1")
    first = conv()
    run("whatsapp_inbox.conversation.erase", {"id": str(first.id)})
    receive("wamid.2")
    assert conv().id != first.id
    assert conv().unread_count == 1


# ── WHATSAPP_INBOX-F04 Recognise the customer by her number ─────────────────────────────────────


def test_a_number_on_exactly_one_card_joins_the_conversation_to_it():
    ana = card("Ana López", "600 111 222")
    receive("wamid.1", "34600111222")
    assert conv().customer_id == ana.id
    assert events("whatsapp_inbox.conversation.customer_linked") == [
        {"id": str(conv().id), "customer_id": str(ana.id)}
    ]


def test_a_number_that_keeps_its_leading_zero_abroad_is_recognised():
    """An Italian landline keeps its 0 after +39, on the card and on WhatsApp."""
    gianni = card("Gianni Rossi", "+39 06 1234 5678")
    receive("wamid.1", "390612345678")
    assert (conv().phone, conv().customer_id) == ("+390612345678", gianni.id)


def test_two_cards_with_the_number_join_it_to_nobody():
    card("Ana López", "600111222")
    card("Ana L.", "+34 600 111 222")
    receive("wamid.1", "34600111222")
    assert conv().customer_id is None


def test_the_link_somebody_made_is_kept():
    other = card("Marta", "600999888")
    card("Ana López", "600111222")
    receive("wamid.1", "34600111222")
    run(
        "whatsapp_inbox.conversation.link_customer",
        {"id": str(conv().id), "customer_id": str(other.id)},
    )
    receive("wamid.2", "34600111222")
    assert conv().customer_id == other.id


# ── WHATSAPP_INBOX-F34 Delivery statuses ────────────────────────────────────────────────────────


def sent_message(wa_id="wamid.OUT") -> Message:
    receive("wamid.IN")
    return Message.objects.create(
        conversation=conv(),
        direction="outbound",
        origin="hub",
        status="sent",
        wa_message_id=wa_id,
        sent_at=NOW,
    )


def status(wa_id, value, **fields):
    return system(
        "whatsapp_inbox.message.update_status",
        {"wa_message_id": wa_id, "status": value, **fields},
    )


def test_a_status_only_moves_forward():
    message = sent_message()
    assert status("wamid.OUT", "delivered").model_dump() == {
        "updated": True,
        "status": "delivered",
    }
    assert status("wamid.OUT", "read").status == "read"
    late = status("wamid.OUT", "delivered")
    assert (late.updated, late.status) == (False, "read")
    assert (
        status("wamid.OUT", "failed", error={"code": "131047", "message": "x"}).updated
        is False
    )
    message.refresh_from_db()
    assert message.status == "read"
    assert len(events("whatsapp_inbox.message.status_changed")) == 2


def test_failed_replaces_sent_or_delivered_with_meta_s_reason():
    sent_message()
    status("wamid.OUT", "delivered")
    out = status(
        "wamid.OUT",
        "failed",
        error={"code": "131047", "message": "More than 24 hours"},
        status_at=NOW.isoformat(),
    )
    assert out.status == "failed"
    message = Message.objects.get(wa_message_id="wamid.OUT")
    assert (message.error_code, message.error_message, message.status_at) == (
        "131047",
        "More than 24 hours",
        NOW,
    )


def test_an_unknown_message_changes_nothing():
    assert status("wamid.NOBODY", "read").model_dump() == {
        "updated": False,
        "status": None,
    }
