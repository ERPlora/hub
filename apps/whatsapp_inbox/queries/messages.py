"""The messages of a conversation: its thread, one message, and the options the business last offered
the customer."""

import datetime as dt

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.queries.channel import channel, send_blocked
from apps.whatsapp_inbox.queries.conversations import display_name, find_conversation
from apps.whatsapp_inbox.queries.reads import page, person_name
from apps.whatsapp_inbox.queries.reasons import message_reason
from apps.whatsapp_inbox.schemas.messages import MessageGetOut, MessageListIn, MessagePage, MessageRefIn

MESSAGE_NOT_FOUND = _("That message no longer exists.")


def message_out(row: Message) -> dict:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "direction": row.direction,
        "origin": row.origin,
        "source": row.source,
        "kind": row.kind,
        "body": row.body,
        "media_url": row.media_url,
        "media_mime_type": row.media_mime_type,
        "media_filename": row.media_filename,
        "media_caption": row.media_caption,
        "template_name": row.template_name,
        "status": row.status,
        "error_code": row.error_code,
        "error_message": message_reason(row),
        "wa_message_id": row.wa_message_id,
        "reply_to": row.reply_to,
        "reply_id": row.reply_id,
        "sent_by_name": person_name(row.sent_by),
        "sent_at": row.sent_at,
        "status_at": row.status_at,
    }


@operation(
    "whatsapp_inbox.message.list",
    kind="query",
    permission="whatsapp_inbox.view",
    input=MessageListIn,
    output=MessagePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the messages of Nuria's chat",
                "read me the WhatsApp thread with Jorge",
                "were our last messages to Elena delivered and read?",
            ),
            "es": (
                "enséñame los mensajes del chat de Nuria",
                "léeme el hilo de WhatsApp con Jorge",
                "¿le han llegado a Elena nuestros mensajes y los ha leído?",
            ),
        },
        "description": "The messages of a WhatsApp conversation (named by its id, number or customer's name), "
        "newest first: who said what and when, attachments, and whether each one sent was delivered and read."
    },
)
def list_messages(ctx: OperationContext, params: MessageListIn) -> dict:
    conversation = find_conversation(ctx, params.id, params.conversation)
    rows = (
        Message.objects.filter(conversation=conversation)
        .select_related("sent_by")
        .order_by("-sent_at", "-id")
    )
    return page(rows, params, message_out)


@operation(
    "whatsapp_inbox.message.get",
    kind="query",
    permission="whatsapp_inbox.view",
    input=MessageRefIn,
    output=MessageGetOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "open the message Nuria just sent",
                "what did that WhatsApp message say and when did it arrive?",
                "which options did we give her in the message she is answering?",
            ),
            "es": (
                "abre el mensaje que acaba de mandar Nuria",
                "¿qué decía ese mensaje de WhatsApp y cuándo llegó?",
                "¿qué opciones le dimos en el mensaje al que responde?",
            ),
        },
        "description": "One WhatsApp message by its id (the one an automation started on): what it says, who said it "
        "and when, its conversation's exact international number, what to call the customer, whether anything "
        "can be sent now and the options the business last offered her, which she may be answering."
    },
)
def get_message(ctx: OperationContext, data: MessageRefIn) -> dict:
    row = (
        Message.objects.select_related("sent_by", "conversation__customer")
        .filter(pk=data.id, conversation__erased_at__isnull=True)
        .first()
    )
    if row is None:
        raise NotFound(str(MESSAGE_NOT_FOUND), code="whatsapp_inbox.message_not_found")
    return {
        **message_out(row),
        "phone": row.conversation.phone,
        "display_name": display_name(ctx, row.conversation),
        "can_send": send_blocked(channel(ctx.scope)) is None,
        "options": last_offered(row),
    }


#: How long a list the business offered stays the one an answer like «the 2nd» points to (WHATSAPP_INBOX-F19).
OFFER_MEMORY = dt.timedelta(hours=24)


def last_offered(message: Message) -> str:
    """What the business last wrote her from the Hub, in the 24 hours before ``message``: the list of options she may be
    answering by its number (WHATSAPP_INBOX-F19), or ``""``. Ordered by when the Hub recorded each one, not by Meta's
    clock; never what the owner wrote from the phone, nor what did not get to her. Anything the Hub writes her later
    (a booking done, another question, a template) takes its place, so a list is forgotten once it was answered."""
    last = (
        Message.objects.filter(
            conversation_id=message.conversation_id,
            direction=Message.Direction.OUTBOUND,
            origin=Message.Origin.HUB,
            created_at__lt=message.created_at,
            created_at__gte=message.created_at - OFFER_MEMORY,
        )
        .exclude(status=Message.Status.FAILED)
        .exclude(body="")
        .order_by("-created_at", "-id")
        .values_list("body", flat=True)
        .first()
    )
    return last or ""
