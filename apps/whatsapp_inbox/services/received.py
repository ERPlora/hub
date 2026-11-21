"""What erplora.com pushes about messages: a message received (WHATSAPP_INBOX-F03) and a delivery status
(F34), run as the system through ``whatsapp_inbox.receive``."""

from django.db import IntegrityError
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.customer.phones import InvalidPhone
from apps.whatsapp_inbox import clock, events
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.queries.reads import e164, preview
from apps.whatsapp_inbox.schemas import ReceiveIn, ReceiveOut, StatusIn, StatusOut

from .writes import NOT_A_NUMBER, RECEIVE, _conversation_for, _link_by_phone, _locked_cards_of

#: How far each delivery status of Meta is; ``failed`` replaces anything but ``read``.
_STATUS_RANK = {
    Message.Status.QUEUED: 0,
    Message.Status.SENDING: 0,
    Message.Status.SENT: 1,
    Message.Status.DELIVERED: 2,
    Message.Status.READ: 3,
}


def _media_fields(data: ReceiveIn) -> dict:
    media = data.media
    return {
        "media_url": media.url if media else "",
        "media_mime_type": media.mime_type if media else "",
        "media_filename": media.filename if media else "",
        "media_caption": media.caption if media else "",
    }


def _tapped(data: ReceiveIn) -> tuple[str, str, str]:
    """``(reply_to, reply_id, text)`` of a message: the option she tapped and the message it answers, as
    erplora.com lifted them or, when it did not, read from Meta's object (WHATSAPP_INBOX-F38)."""
    payload = data.payload if isinstance(data.payload, dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    reply_to = data.reply_to or str(context.get("id") or "")
    option_id, title = (data.reply.id, data.reply.title) if data.reply else ("", "")
    if data.reply is None and data.type == "button" and isinstance(payload.get("button"), dict):
        option_id, title = str(payload["button"].get("payload") or ""), str(payload["button"].get("text") or "")
    elif data.reply is None and data.type == "interactive" and isinstance(payload.get("interactive"), dict):
        interactive = payload["interactive"]
        chosen = interactive.get("button_reply") or interactive.get("list_reply")
        if isinstance(chosen, dict):
            option_id, title = str(chosen.get("id") or ""), str(chosen.get("title") or "")
    return reply_to[:255], option_id[:256], data.text or title


def _received(ctx: OperationContext, message: Message) -> None:
    """``whatsapp_inbox.message.received``, saying which message the Hub sent it answers (never absent:
    empty when it answers nothing this Hub sent) and the option tapped."""
    asked = (
        Message.objects.filter(
            conversation_id=message.conversation_id, wa_message_id=message.reply_to, origin=Message.Origin.HUB
        )
        .values_list("id", flat=True)
        .first()
        if message.reply_to
        else None
    )
    record_event(
        ctx,
        events.MESSAGE_RECEIVED,
        {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "direction": message.direction,
            # An automatic answer starts on a live message only, never on the old chats connecting brought (F21).
            "source": message.source,
            "reply_to_message_id": str(asked) if asked else None,
            "reply_id": message.reply_id,
        },
    )


def _redelivered(ctx: OperationContext, message: Message, data: ReceiveIn) -> dict:
    """The same WhatsApp message again: nothing changes, unless it completes a history placeholder."""
    completes = (
        data.source == Message.Source.HISTORY
        and message.kind == "media_placeholder"
        and data.type != "media_placeholder"
        and message.conversation.erased_at is None
    )
    if completes:
        message.reply_to, message.reply_id, message.body = _tapped(data)
        message.kind = data.type
        message.payload = data.payload
        for field, value in _media_fields(data).items():
            setattr(message, field, value)
        message.save()
        _received(ctx, message)
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "created": False,
    }




@operation(
    "whatsapp_inbox.message.receive",
    kind="command",
    permission=RECEIVE,
    input=ReceiveIn,
    output=ReceiveOut,
    ai={
        "description": "System only (erplora.com's /internal/whatsapp/inbound): stores a WhatsApp message of a "
        "customer, or the owner's reply from the phone, in the conversation of its number, once per WhatsApp id.",
        "risk": "normal",
    },
)
def receive_message(ctx: OperationContext, data: ReceiveIn) -> dict:  # noqa: C901
    try:
        phone = e164(data.from_, ctx, from_whatsapp=True)
    except InvalidPhone:
        raise InvalidPayload(
            str(NOT_A_NUMBER), fields={"from": str(NOT_A_NUMBER)}
        ) from None
    existing = (
        Message.objects.select_related("conversation")
        .filter(wa_message_id=data.wa_message_id)
        .first()
    )
    if existing is not None:
        return _redelivered(ctx, existing, data)
    inbound = data.direction == Message.Direction.INBOUND
    card_id = _locked_cards_of([phone]).get(phone)
    conversation = _conversation_for(phone, data.contact_name if inbound else "")
    # A twin delivered at the same time committed while this one waited for the conversation's lock.
    existing = (
        Message.objects.select_related("conversation")
        .filter(wa_message_id=data.wa_message_id)
        .first()
    )
    if existing is not None:
        return _redelivered(ctx, existing, data)
    said = data.sent_at or clock.now()
    kind = data.type or "text"
    reply_to, reply_id, text = _tapped(data)
    try:
        with atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=data.direction,
                origin=Message.Origin.CUSTOMER if inbound else Message.Origin.PHONE_APP,
                source=data.source,
                kind=kind,
                body=text,
                status=Message.Status.RECEIVED if inbound else Message.Status.SENT,
                wa_message_id=data.wa_message_id,
                reply_to=reply_to,
                reply_id=reply_id,
                payload=data.payload,
                sent_at=said,
                **_media_fields(data),
            )
    except IntegrityError:
        existing = Message.objects.select_related("conversation").get(
            wa_message_id=data.wa_message_id
        )
        return _redelivered(ctx, existing, data)

    # A reaction (👍 to a message) annotates the message it answers: it is not news to read.
    if kind != "reaction":
        if inbound:
            if data.source == Message.Source.LIVE:
                conversation.unread_count += 1
                if conversation.status != Conversation.Status.OPEN:
                    conversation.status = Conversation.Status.OPEN
                    record_event(
                        ctx,
                        events.STATUS_CHANGED,
                        {"id": str(conversation.id), "status": "open"},
                    )
            if (
                conversation.last_inbound_at is None
                or said > conversation.last_inbound_at
            ):
                conversation.last_inbound_at = said
            if data.contact_name:
                conversation.contact_name = data.contact_name
        if conversation.last_message_at is None or said >= conversation.last_message_at:
            conversation.last_message_at = said
            conversation.last_message_preview = preview(
                message.body, message.media_filename, message.media_caption
            )
            conversation.last_message_kind = kind
            conversation.last_message_direction = message.direction
        if not inbound and data.source == Message.Source.LIVE:
            conversation.needs_attention = False  # the business answered from its phone (F20)
        conversation.save()
    _link_by_phone(ctx, conversation, card_id)
    _received(ctx, message)
    return {"id": message.id, "conversation_id": conversation.id, "created": True}


@operation(
    "whatsapp_inbox.message.update_status",
    kind="command",
    permission=RECEIVE,
    input=StatusIn,
    output=StatusOut,
    ai={
        "description": "System only (erplora.com's /internal/whatsapp/status): records that a message the Hub "
        "sent was delivered, read or failed, matched by WhatsApp's id or by the Hub's key; a status only moves forward.",
        "risk": "normal",
    },
)
def update_status(ctx: OperationContext, data: StatusIn) -> dict:
    message = (
        Message.objects.select_for_update()
        .filter(wa_message_id=data.wa_message_id)
        .first()
    )
    if message is None and data.client_message_id is not None:
        # A status that arrives before erplora.com's own answer to the send: the key finds it.
        message = (
            Message.objects.select_for_update()
            .filter(client_message_id=data.client_message_id)
            .first()
        )
        if message is not None and not message.wa_message_id:
            message.wa_message_id = data.wa_message_id
    if message is None or message.direction != Message.Direction.OUTBOUND:
        return {"updated": False, "status": message.status if message else None}
    current, new = message.status, data.status
    if new == Message.Status.FAILED:
        moves = current not in (Message.Status.FAILED, Message.Status.READ)
    else:
        moves = current != Message.Status.FAILED and _STATUS_RANK[
            new
        ] > _STATUS_RANK.get(current, 0)
    if not moves:
        if message.wa_message_id != data.wa_message_id or message.status != current:
            message.save(update_fields=["wa_message_id"])
        return {"updated": False, "status": current}
    message.status = new
    message.status_at = data.status_at or clock.now()
    if new == Message.Status.FAILED and data.error is not None:
        message.error_code = data.error.code
        message.error_message = data.error.message
    elif new != Message.Status.FAILED:
        message.error_code = message.error_message = ""
    message.save(
        update_fields=[
            "status",
            "status_at",
            "error_code",
            "error_message",
            "wa_message_id",
        ]
    )
    record_event(
        ctx,
        events.MESSAGE_STATUS_CHANGED,
        {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "status": new,
        },
    )
    return {"updated": True, "status": new}
