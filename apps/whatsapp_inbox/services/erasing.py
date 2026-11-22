"""Erasing a conversation (WHATSAPP_INBOX-F10, F11): here at once, and the number erplora.com has to
forget after the COMMIT."""

from uuid import UUID

from live.context import OperationContext, Scope, system_context
from live.operations import get, operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events, gateway
from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.queries.conversations import find_conversation
from apps.whatsapp_inbox.schemas.deliveries import RecordOut
from apps.whatsapp_inbox.schemas.erasing import ClaimErasureOut, ErasedOut, RecordErasureIn
from apps.whatsapp_inbox.schemas.fields import ConversationRefIn
from base import outbound

from .writes import RECEIVE, _after_commit, _save


def _erase(ctx: OperationContext, conversation: Conversation) -> None:
    """Empty every personal datum of ``conversation`` once, and ask erplora.com to forget its number
    after the COMMIT until it confirms; again changes nothing here and asks erplora.com again."""
    if conversation.erased_at is None:
        conversation.messages.update(
            body="",
            media_url="",
            media_mime_type="",
            media_filename="",
            media_caption="",
            payload={},
            reply_to="",
            reply_id="",
            error_message="",
            template_variables=[],
        )
        conversation.notes.all().delete()
        conversation.erase_phone = conversation.phone
        conversation.erase_status = Conversation.EraseStatus.PENDING
        conversation.phone = ""
        conversation.contact_name = ""
        conversation.last_message_preview = ""
        conversation.customer = None
        conversation.assigned_to = None
        conversation.status = Conversation.Status.CLOSED
        conversation.unread_count = 0
        conversation.erased_at = clock.now()
        conversation.save()
        record_event(ctx, events.ERASED, {"id": str(conversation.id)})
    if conversation.erase_status == Conversation.EraseStatus.PENDING:
        _after_commit(ctx, forget, conversation.id)


def forget(scope: Scope, conversation_id: UUID) -> None:
    """Ask erplora.com to forget an erased conversation's number and messages (door 6), outside any
    transaction; its confirmation is recorded in a transaction of its own."""
    system = system_context(scope)
    claim = get("whatsapp_inbox.conversation.claim_erasure")
    claimed = claim(system, ConversationRefIn(id=conversation_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    try:
        confirmed = gateway.erase(
            hub=scope.key, phone=claimed.phone, wa_message_ids=claimed.wa_message_ids
        )
    except gateway.NotConfigured:
        confirmed = False
    record = get("whatsapp_inbox.conversation.record_erasure")
    record(system, RecordErasureIn(id=conversation_id, confirmed=confirmed))


@operation(
    "whatsapp_inbox.conversation.claim_erasure",
    kind="command",
    permission=RECEIVE,
    input=ConversationRefIn,
    output=ClaimErasureOut,
    ai={
        "description": "System only: takes an erased conversation whose number erplora.com has not forgotten yet, "
        "with the WhatsApp ids of its messages.",
        "risk": "normal",
    },
)
def claim_erasure(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = (
        Conversation.objects.select_for_update(skip_locked=True)
        .filter(pk=data.id, erase_status=Conversation.EraseStatus.PENDING)
        .first()
    )
    if conversation is None:
        return {"claimed": False}
    ids = list(
        conversation.messages.exclude(wa_message_id__isnull=True)
        .order_by("sent_at", "id")
        .values_list("wa_message_id", flat=True)
    )
    return {"claimed": True, "phone": conversation.erase_phone, "wa_message_ids": ids}


@operation(
    "whatsapp_inbox.conversation.record_erasure",
    kind="command",
    permission=RECEIVE,
    input=RecordErasureIn,
    output=RecordOut,
    ai={
        "description": "System only: records that erplora.com confirmed it forgot an erased conversation's number "
        "(then the Hub forgets it too); unconfirmed, it is asked again.",
        "risk": "normal",
    },
)
def record_erasure(ctx: OperationContext, data: RecordErasureIn) -> dict:
    conversation = Conversation.objects.select_for_update().filter(pk=data.id).first()
    if conversation is None:
        return {"status": None}
    if data.confirmed and conversation.erase_status == Conversation.EraseStatus.PENDING:
        conversation.erase_status = Conversation.EraseStatus.DONE
        conversation.erase_phone = ""
        _save(conversation, "erase_status", "erase_phone")
    return {"status": conversation.erase_status}


@operation(
    "whatsapp_inbox.conversation.erase",
    kind="command",
    permission="whatsapp_inbox.erase",
    input=ConversationRefIn,
    output=ErasedOut,
    ai={
        "asks": {
            "en": (
                "erase all of Nuria's WhatsApp data, she asked us to",
                "delete this number's chat under GDPR",
                "wipe the messages and notes of +34 600 111 222",
            ),
            "es": (
                "borra todos sus datos de WhatsApp a Nuria, nos lo ha pedido",
                "elimina el chat de este número por protección de datos",
                "borra los datos del +34 600 111 222 en WhatsApp",
            ),
        },
        "description": "Erases a number's WhatsApp data at the person's request (GDPR): the number, the name, "
        "every text, attachment and note of the conversation, here and at erplora.com. Irreversible; if they "
        "write again, a new conversation starts.",
        "risk": "high",
    },
)
def erase(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = find_conversation(
        ctx, data.id, data.conversation, lock=True, live=data.id is None
    )
    _erase(ctx, conversation)
    return {"id": conversation.id}
