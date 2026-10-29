"""Write operations of the WhatsApp inbox: one operation, one transaction, its events in the outbox.

What erplora.com pushes (a message, a delivery status, the channel's state and templates) runs as the
system through ``whatsapp_inbox.receive``, which no role holds; what the team does (send, read,
assign, change the status, link a card, notes, erase) runs as the person.

Nothing waits for erplora.com inside a transaction (WORKBOOK «Reglas que no se rompen»). Sending keeps
the message ``queued`` in a short transaction and hands it over after the COMMIT (``deliver``): a claim
(``message.claim_delivery``, ``sending``), the HTTP call with no transaction and no lock, and the answer
in another short transaction (``message.record_delivery``: ``sent``, ``failed`` with erplora.com's
reason, or still ``sending`` with why, to retry with the same key). Erasing does the same with the
number erplora.com has to forget (``forget``), and a template with its registration and deletion at Meta
(``submit_template``, ``remove_template``). Each hand-over runs in a thread of the process's own
(``base.outbound``), never in the loop that committed: the worker's relay and tick go on for every hub
while erplora.com answers. What a crash or a stopping worker leaves half-way, the worker's
``delivery.resume`` hands over again. A message is never «sent» without Meta's id.
"""

import base64
import binascii
import datetime as dt
import hashlib
import logging
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid7

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import IntegrityError, transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat, Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope, system_context
from live.errors import (
    Conflict,
    InvalidPayload,
    NotFound,
    OperationError,
    PermissionDenied,
)
from live.operations import get, operation
from live.outbox import record_event

from apps.customer.models import Consent, Customer
from apps.customer.phones import InvalidPhone
from apps.customer.queries import find_customer
from apps.customer.services import lock_customers
from apps.whatsapp_inbox import clock, events, gateway, samples
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template, TemplateSample, hub_writes
from apps.whatsapp_inbox.notify_schemas import NotifyIn
from apps.whatsapp_inbox.queries import (
    CAP_REACHED,
    HEADER_SAMPLE_MISSING_CODE,
    META_RATE_LIMITED,
    NOT_CONNECTED,
    SAAS_UNREACHABLE_CODE,
    SEND_REFUSED_CODE,
    SEND_UNKNOWN_CODE,
    TEMPLATE_REFUSED_CODE,
    actor_id,
    channel,
    conversation_out,
    e164,
    find_conversation,
    live_conversations,
    live_templates,
    may_delete_note,
    message_out,
    note_out,
    person_name,
    preview,
    send_blocked,
    sample_out,
    team,
    template_out,
    templates_of,
    templates_of_every_business,
)
from apps.whatsapp_inbox.schemas import (
    AssignIn,
    ChannelConnectIn,
    ChannelConnectOut,
    ChannelDisconnectIn,
    ChannelDisconnectOut,
    ChannelPrepareIn,
    ChannelPrepareOut,
    ChannelSyncIn,
    ChannelSyncOut,
    ClaimDeliveryOut,
    ClaimErasureOut,
    ClaimTemplateDeletionOut,
    ClaimTemplateOut,
    ConversationOut,
    ConversationRefIn,
    CustomerEventIn,
    ErasedOut,
    LinkCustomerIn,
    MergedEventIn,
    MessageOut,
    MessageRefIn,
    NoteAddIn,
    NoteDeletedOut,
    NoteOut,
    NoteRefIn,
    ReactionOut,
    ReceiveIn,
    ReceiveOut,
    RecordDeliveryIn,
    RecordErasureIn,
    RecordOut,
    RecordTemplateDeletionIn,
    RecordTemplateIn,
    ResumeIn,
    ResumeOut,
    SendIn,
    SetStatusIn,
    StatusIn,
    StatusOut,
    TemplateCreateIn,
    TemplateOut,
    TemplateRefIn,
    TemplateSampleOut,
    TemplateSampleUploadIn,
    TemplateUpdateIn,
    TemplateWriteIn,
    template_variables,
)
from base import outbound
from base.files import STORE_ERRORS
from base.operations import hub_id

logger = logging.getLogger(__name__)

#: Only the system context (``*``) holds it: the doors erplora.com calls, the reactions, the deliveries.
RECEIVE = "whatsapp_inbox.receive"
#: How long a delivery may be on its way before the worker hands it over again (gateway: 5 + 15 s).
STUCK_AFTER = dt.timedelta(minutes=2)
#: How many deliveries one pass of the worker takes per hub.
RESUME_BATCH = 50

NOT_A_NUMBER = _("This is not a phone number.")
WINDOW_CLOSED = _(
    "More than 24 hours have passed since the customer's last message: WhatsApp only lets you write to "
    "them with an approved template."
)
SAAS_UNCONFIGURED = _(
    "This server cannot reach erplora.com, so nothing can be sent from it."
)
#: A plan that includes no WhatsApp messages (0, ADR-0474): no month brings any, so not «until next month».
NO_PLAN_MESSAGES = _("Your plan does not include WhatsApp messages: nothing can be sent until you upgrade the plan.")
NOT_RETRYABLE = _("This message cannot be sent again: write a new one.")
MESSAGE_NOT_FOUND = _("That message no longer exists.")
TEMPLATE_NOT_FOUND = _("There is no template called “%(name)s”.")
TEMPLATE_LANGUAGE = _("That template exists in several languages: say which one.")
TEMPLATE_NOT_APPROVED = _(
    "Meta has not approved the template “%(name)s”: it cannot be sent."
)
TEMPLATE_VARIABLES = _("Fill in every variable of the template (%(count)d).")
TEMPLATE_NOT_SENDABLE = _(
    "This template has a photo, video, document or place header, or buttons with something to fill in: send it "
    "from WhatsApp Manager."
)
MARKETING_CONSENT = _("This customer has not agreed to receive marketing by WhatsApp.")
TEMPLATE_EXISTS = _("There is already a template “%(name)s” in that language.")
TEMPLATE_GONE = _("That template no longer exists.")
TEMPLATE_READ_ONLY = _("This template is changed in WhatsApp Manager: the Hub cannot change it.")
TEMPLATE_IN_REVIEW = _("Meta is reviewing this template: wait for its verdict to change it.")
TEMPLATE_SUBMITTING = _("This template is on its way to Meta: wait a moment.")
TEMPLATE_CATEGORY_FIXED = _("Meta only lets you change the category of a template it rejected.")
TEMPLATE_NOT_RETRYABLE = _("There is nothing of this template to hand to Meta again.")
HEADER_FILE_MISSING = _("Choose the header's file: Meta reviews the template with it.")
SAMPLE_NOT_WHOLE = _("The file did not arrive whole. Choose it again.")
SAMPLE_WRONG_TYPE = {
    "IMAGE": _("Choose a JPEG or PNG photo."),
    "VIDEO": _("Choose an MP4 video."),
    "DOCUMENT": _("Choose a PDF document."),
}
SAMPLE_TOO_HEAVY = _("This file weighs more than %(mb)s MB: choose a lighter one.")
SAMPLE_NOT_KEPT = _("The file could not be kept: the business's file store did not answer. Try again in a moment.")
ALREADY_ASSIGNED = _("This conversation is already with %(name)s.")
ONLY_YOURSELF = _("You may only assign conversations to yourself.")
NOBODY_CALLED = _("Nobody in this business is called “%(reference)s”.")
SEVERAL_CALLED = _("Several people match “%(reference)s”: choose one from the list.")
NOT_IN_BUSINESS = _("That person does not work in this business.")
NOT_A_PERSON = _("Only a person can be assigned a conversation.")
NOTE_NOT_FOUND = _("That note no longer exists.")
NOT_INTERNATIONAL = _(
    "“%(phone)s” is not a number in international format (+34600111222): nothing was sent, so that it never "
    "reaches the wrong person."
)
NO_CONVERSATION = _("There is no WhatsApp conversation with %(phone)s in this business: nothing was sent.")
NOTE_NOT_YOURS = _("You may only delete your own notes.")

#: How far each delivery status of Meta is; ``failed`` replaces anything but ``read``.
_STATUS_RANK = {
    Message.Status.QUEUED: 0,
    Message.Status.SENDING: 0,
    Message.Status.SENT: 1,
    Message.Status.DELIVERED: 2,
    Message.Status.READ: 3,
}
_ON_ITS_WAY = (Message.Status.QUEUED, Message.Status.SENDING)
_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
#: A number exactly in international format: a plus, the country and its digits, nothing else.
_INTERNATIONAL = re.compile(r"\+[1-9]\d{6,14}")
#: erplora.com's 409 codes the Hub knows by name → its code, said in its own words when read (queries); any other
#: is «erplora.com did not send it», with Meta's reason as it came.
_REFUSALS = {
    "whatsapp.cap_reached": "whatsapp_inbox.cap_reached",
    "whatsapp.reconnect_needed": "whatsapp_inbox.reconnect_needed",
}
#: erplora.com's 409 codes for a template the Hub says in its own words when read (never blaming ERPlora for
#: Meta: gh:hub#2731); any other is Meta's refusal, with Meta's reason as it came.
_TEMPLATE_REFUSALS = {
    "whatsapp.meta_unreachable": "whatsapp_inbox.meta_unreachable",
    "whatsapp.meta_rate_limited": "whatsapp_inbox.meta_rate_limited",
    "whatsapp.not_connected": "whatsapp_inbox.channel_not_connected",
    "whatsapp.reconnect_needed": "whatsapp_inbox.reconnect_needed",
    HEADER_SAMPLE_MISSING_CODE: HEADER_SAMPLE_MISSING_CODE,
}
_TEMPLATE_ON_ITS_WAY = (Template.SubmitState.QUEUED, Template.SubmitState.SENDING)


def _save(instance, *fields: str) -> None:
    instance.save(
        update_fields=[
            *fields,
            *(["updated_at"] if hasattr(instance, "updated_at") else []),
        ]
    )


def _after_commit(ctx: OperationContext, job, *args) -> None:
    """Run ``job(scope, *args)`` once this command's transaction committed (never after a rollback): outside it, with
    no lock, in a thread of the process's own (``base.outbound``) and in this command's database, so that the
    request, the worker's relay or its tick that committed never waits for erplora.com. A job lost on the way (the
    process stopped) is found again by ``delivery.resume``: each one claims its row first."""
    outbound.after_commit(job, ctx.scope, *args)


def _after_commit_as(host: str, ctx: OperationContext, job, *args) -> None:
    """``_after_commit`` for the business in ``host`` (the row's own), whatever business ``ctx`` runs as. A row made
    before its business was recorded (empty ``host``) goes as ``ctx``'s, as it did."""
    scope = Scope(ctx.scope.kind, host) if host else ctx.scope
    outbound.after_commit(job, scope, *args)


def _conversation_for(phone: str, contact_name: str = "") -> Conversation:
    """The live conversation of ``phone``, locked; created when there is none.

    Two transactions that create it at once meet at the unique index: the second waits for the first
    and then takes its row.
    """
    rows = live_conversations().select_for_update()
    found = rows.filter(phone=phone).first()
    if found is not None:
        return found
    try:
        with transaction.atomic():
            return Conversation.objects.create(phone=phone, contact_name=contact_name)
    except IntegrityError:
        return rows.get(phone=phone)


def _live_card_id(conversation: Conversation) -> UUID | None:
    """The conversation's card if it is still live; a deleted, merged or erased card counts as none."""
    if conversation.customer_id is None:
        return None
    return (
        conversation.customer_id
        if Customer.objects.live().filter(pk=conversation.customer_id).exists()
        else None
    )


def _only_card_of(phone: str) -> UUID | None:
    """The one live card with ``phone``; ``None`` when there is none or several."""
    ids = (
        list(
            Customer.objects.live().filter(phone=phone).values_list("id", flat=True)[:2]
        )
        if phone
        else []
    )
    return ids[0] if len(ids) == 1 else None


def _locked_cards_of(phones) -> dict[str, UUID]:
    """The one live card of each number of ``phones`` (none for a number with none or several), locked in id order
    before the conversations they join.

    Customers' writes and the Hub admin's «Delete» of a card lock the card before what points at it (the deletion
    then leaves its conversations without it): a deletion under way is waited for and its card is no longer there
    to join; one that comes after waits for the join and then leaves the conversation without the card. Each card
    is read again once locked: the write it waited for may have changed its number or taken it out of use.
    """
    wanted = {phone: _only_card_of(phone) for phone in phones if phone}
    lock_customers([card_id for card_id in wanted.values() if card_id is not None])
    return {
        phone: card_id
        for phone, card_id in wanted.items()
        if card_id is not None and _only_card_of(phone) == card_id
    }


def _link_by_phone(ctx: OperationContext, conversation: Conversation, card_id: UUID | None) -> None:
    """Join a conversation without a live card to ``card_id``, the one live card of its number, locked before the
    conversation (``_locked_cards_of``; WHATSAPP_INBOX-F04)."""
    if card_id is None or _live_card_id(conversation) is not None or card_id == conversation.customer_id:
        return
    conversation.customer_id = card_id
    _save(conversation, "customer")
    record_event(
        ctx,
        events.CUSTOMER_LINKED,
        {"id": str(conversation.id), "customer_id": str(card_id)},
    )


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


# ── What erplora.com pushes ─────────────────────────────────────────────────────────────────────


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
def receive_message(ctx: OperationContext, data: ReceiveIn) -> dict:
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
        with transaction.atomic():
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


@operation(
    "whatsapp_inbox.channel.sync",
    kind="command",
    permission=RECEIVE,
    input=ChannelSyncIn,
    output=ChannelSyncOut,
    ai={
        "description": "System only (erplora.com's /internal/whatsapp/channel and the state snapshot): the "
        "number's state, the month's allowance and spend, and the templates Meta holds; an older version is ignored.",
        "risk": "normal",
    },
)
def sync_channel(ctx: OperationContext, data: ChannelSyncIn) -> dict:
    row = _locked_channel(ctx)
    if data.version <= row.version:
        return {"applied": False, "version": row.version}
    now = clock.now()
    row.version = data.version
    row.status = data.status
    row.phone_number = data.phone_number
    row.display_name = data.display_name
    row.monthly_limit = data.monthly_limit
    row.monthly_usage = data.monthly_usage
    row.usage_month = data.usage_month
    row.synced_at = now
    row.save()
    if data.templates is not None:
        _sync_templates(ctx, data.templates, now)
    record_event(ctx, events.CHANNEL_SYNCED, {"version": data.version})
    return {"applied": True, "version": data.version}


def _locked_channel(ctx: OperationContext) -> Channel:
    """The row of the business of ``ctx``, locked; born the first time erplora.com speaks of it (two at once: one
    creates it, the other finds it)."""
    rows = Channel.objects.select_for_update().filter(host=ctx.scope.key)
    row = rows.first()
    if row is None:
        try:
            with transaction.atomic():
                row = Channel.objects.create(host=ctx.scope.key)
        except IntegrityError:
            row = rows.get()
    return row


def _sync_templates(ctx: OperationContext, items, now) -> None:
    """Meta's list replaces the copy (F27, F28): what it no longer lists is «Deleted in WhatsApp Manager».

    Never on what the Hub has not handed over yet (a new template on its way or not accepted keeps what was
    written; an edit waits in its ``draft``), and never bringing back a template deleted here: Meta still
    lists it until the deletion reaches it, or by the same id. Only the business's own templates: another
    business's list never touches them.
    """
    kept = []
    for item in items:
        row = live_templates(ctx.scope).select_for_update().filter(name=item.name, language=item.language).first()
        if row is None:
            deleted = templates_of(ctx.scope).filter(name=item.name, language=item.language, deleted_at__isnull=False)
            if deleted.filter(Q(delete_state=Template.DeleteState.PENDING) | Q(meta_id=item.meta_id)).exists():
                continue
            row = Template(host=ctx.scope.key, name=item.name, language=item.language)
        elif row.status == Template.Status.DRAFT and row.submit_state:
            kept.append(row.pk)
            continue
        row.category = item.category
        row.status = item.status
        header_format = item.header_format if item.header_format is not None else ("TEXT" if item.header else "")
        if header_format != row.header_format:
            row.header_sample = None  # changed in WhatsApp Manager: the file chosen here is no longer its header
        row.header_format = header_format
        row.header = item.header
        row.body = item.body
        row.body_examples = list(item.body_examples)
        row.footer = item.footer
        row.buttons = list(item.buttons)
        row.variables = item.variables
        row.rejected_reason = item.rejected_reason
        row.meta_id = item.meta_id
        row.synced_at = now
        row.save()
        kept.append(row.pk)
    live_templates(ctx.scope).exclude(pk__in=kept).exclude(
        status__in=[Template.Status.DELETED, Template.Status.DRAFT]
    ).update(status=Template.Status.DELETED, synced_at=now)


# ── Connecting the number from Settings (WHATSAPP_INBOX-F01, F02): erplora.com's doors 10–12 ──────
#
# Commands, the three of them, although ``prepare`` writes nothing: a query opens its READ ONLY transaction before
# its first line, and nothing waits for erplora.com inside a transaction. Each asks erplora.com first, before any
# read or write of its own, so no transaction is open while it answers; then ``connect`` and ``disconnect`` keep
# erplora.com's answer in the business's row at once (its photo, pushed meanwhile, says the same with a newer version,
# and the next one still wins).

CONFIGURE = "whatsapp_inbox.configure"
#: The COOP values that keep the window a page opens (Django's default, ``same-origin``, cuts it: Meta's window
#: could never tell this page how it ended).
KEEPS_POPUPS = frozenset({"same-origin-allow-popups", "unsafe-none"})
GRAPH_VERSION = re.compile(r"^v\d{1,3}\.\d{1,3}$")
META_ID = re.compile(r"^\d{1,50}$")
E164 = re.compile(r"^\+[1-9]\d{6,14}$")

CONNECT_UNCONFIGURED = _("This server is not linked to erplora.com: the number cannot be connected from it.")
CONNECT_SAAS_UNREACHABLE = _("Your hub could not reach erplora.com. Check the connection and try again.")
CONNECT_UNKNOWN = _(
    "erplora.com did not confirm the connection. In a moment «Your number» will say whether it is connected; "
    "if it is not, connect it again."
)
DISCONNECT_UNKNOWN = _(
    "erplora.com did not confirm the disconnection. In a moment «Your number» will say it; if it is still "
    "connected, try again."
)
HUB_UNKNOWN = _("erplora.com does not know this business: a demo cannot connect a WhatsApp number.")
CONNECT_REJECTED = _("Meta did not accept the connection: %(reason)s")
NUMBER_NOT_IN_ACCOUNT = _(
    "The number chosen in Meta's window is not in that WhatsApp Business account: nothing was connected."
)
NUMBER_NOT_CHOSEN = _("That WhatsApp Business account has several numbers: choose one in Meta's window.")
CONNECT_META_UNREACHABLE = _("Meta did not answer: nothing was connected. Try again.")
WHATSAPP_UNAVAILABLE = _("WhatsApp is not available in ERPlora yet.")
SAAS_REFUSED = _("erplora.com did not take the request (%(code)s). Try again later.")

#: erplora.com's refusal at doors 10–12 → (status, the Hub's code, its message). A message with ``%(reason)s``
#: carries erplora.com's (Meta's) own words.
DOOR_REFUSALS = {
    "hub_unknown": (409, "whatsapp_inbox.hub_unknown", HUB_UNKNOWN),
    "whatsapp.meta_rejected": (409, "whatsapp_inbox.meta_rejected", CONNECT_REJECTED),
    "whatsapp.number_not_in_account": (409, "whatsapp_inbox.number_not_in_account", NUMBER_NOT_IN_ACCOUNT),
    "whatsapp.number_not_chosen": (409, "whatsapp_inbox.number_not_chosen", NUMBER_NOT_CHOSEN),
    "whatsapp.meta_rate_limited": (409, "whatsapp_inbox.meta_rate_limited", META_RATE_LIMITED),
    "whatsapp.meta_unreachable": (503, "whatsapp_inbox.meta_unreachable", CONNECT_META_UNREACHABLE),
    "whatsapp.meta_no_token": (503, "whatsapp_inbox.meta_unreachable", CONNECT_META_UNREACHABLE),
    "whatsapp.not_configured": (409, "whatsapp_inbox.whatsapp_unavailable", WHATSAPP_UNAVAILABLE),
}


def _ask_saas(door, unknown=None, **args) -> dict:
    """erplora.com's 200 body at ``door``, or the refusal the screen shows. ``unknown``: the message when the request
    left and no answer came back (by default, as nothing left)."""
    try:
        reply = door(**args)
    except gateway.NotConfigured:
        raise Conflict(str(CONNECT_UNCONFIGURED), code="whatsapp_inbox.saas_unconfigured") from None
    if reply.kind == gateway.ACCEPTED:
        return reply.data
    if reply.kind == gateway.REFUSED:
        status, code, message = DOOR_REFUSALS.get(reply.code, (503, "whatsapp_inbox.saas_refused", SAAS_REFUSED))
        if code == "whatsapp_inbox.saas_refused":
            logger.error("whatsapp_inbox.door.refused status=%s code=%s", reply.http_status, reply.code)
        text = str(message) % {"reason": reply.message or "—", "code": reply.code}
        raise OperationError(text, code=code, status=status)
    logger.warning("whatsapp_inbox.door.%s %s", reply.kind, reply.message)
    if reply.kind == gateway.UNKNOWN and unknown is not None:
        raise OperationError(str(unknown[1]), code=unknown[0], status=503)
    raise OperationError(str(CONNECT_SAAS_UNREACHABLE), code="whatsapp_inbox.saas_unreachable", status=503)


def _not_understood(door: str) -> OperationError:
    logger.error("whatsapp_inbox.door.not_understood door=%s", door)
    return OperationError(str(CONNECT_SAAS_UNREACHABLE), code="whatsapp_inbox.saas_unreachable", status=503)


def _return_page(value) -> str:
    """erplora.com's page Meta brings the code back to: an address of erplora.com's own origin (the one the Hub
    knows, ``SAAS_URL``: same scheme, host and port) without a fragment, or ``""``. Over https; plain http only in
    development (``DEBUG``) with an http ``SAAS_URL``, as erplora.com's own rule (``whatsapp.meta.redirect_uri``)."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        page, known = urlsplit(value), urlsplit(str(getattr(settings, "SAAS_URL", "") or ""))
    except ValueError:
        # An address that cannot be read (an unclosed IPv6 bracket) is no page to bring the code back to.
        return ""
    schemes = ("https", "http") if settings.DEBUG else ("https",)
    if page.scheme not in schemes or not page.netloc or page.fragment or (page.scheme, page.netloc) != (known.scheme, known.netloc):
        return ""
    return value


@operation(
    "whatsapp_inbox.channel.prepare",
    kind="command",
    permission=CONFIGURE,
    input=ChannelPrepareIn,
    output=ChannelPrepareOut,
    ai={
        "description": "Whether the business's WhatsApp number can be connected from Settings now (Meta's window "
        "opens there, and only a person in it connects a number), and why not: WhatsApp not set up on erplora.com "
        "yet, or the window not available yet.",
        "risk": "normal",
    },
)
def prepare_connect(ctx: OperationContext, data: ChannelPrepareIn) -> dict:
    """What Settings opens Meta's window with (erplora.com's door 10), and why it cannot be opened yet."""
    answer = _ask_saas(gateway.config, hub=ctx.scope.key)
    if not isinstance(answer.get("configured"), bool):
        raise _not_understood("config")
    if not answer["configured"]:
        return {"available": False, "reason": "not_configured"}
    ids = {key: answer.get(key) for key in ("app_id", "config_id", "graph_version")}
    if not all(isinstance(value, str) for value in ids.values()) or not (
        META_ID.match(ids["app_id"]) and META_ID.match(ids["config_id"]) and GRAPH_VERSION.match(ids["graph_version"])
    ):
        raise _not_understood("config")
    redirect_uri = _return_page(answer.get("redirect_uri"))
    if not redirect_uri:
        return {"available": False, "reason": "window_unavailable", **ids}
    if getattr(settings, "SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin") not in KEEPS_POPUPS | {None}:
        return {"available": False, "reason": "popups_blocked", **ids}
    return {"available": True, "reason": None, **ids, "redirect_uri": redirect_uri}


@operation(
    "whatsapp_inbox.channel.connect",
    kind="command",
    permission=CONFIGURE,
    input=ChannelConnectIn,
    output=ChannelConnectOut,
    ai={
        "description": "Connect the business's WhatsApp number chosen in Meta's window, with the one-time code that "
        "window returned (it lasts 30 seconds). Only Meta's window in Settings gives that code: to connect a "
        "number, ask the person to press «Connect WhatsApp» in Settings.",
        "risk": "high",
    },
)
def connect_number(ctx: OperationContext, data: ChannelConnectIn) -> dict:
    """Connect the number Meta's window chose (erplora.com's door 11), with what the window gave, as it came; the
    business's row says it at once."""
    answer = _ask_saas(
        gateway.connect, unknown=("whatsapp_inbox.connect_unknown", CONNECT_UNKNOWN), hub=ctx.scope.key, **data.model_dump()
    )
    out = _connected(answer)
    if out is None:
        logger.error("whatsapp_inbox.door.not_understood door=connect")
        raise OperationError(str(CONNECT_UNKNOWN), code="whatsapp_inbox.connect_unknown", status=503)
    row = _locked_channel(ctx)
    row.status = Channel.Status.CONNECTED
    row.phone_number, row.display_name = out.phone_number, out.display_name
    row.save(update_fields=["status", "phone_number", "display_name", "updated_at"])
    record_event(ctx, events.CHANNEL_CONNECTED, {"history_requested": out.history_requested})
    return out


def _connected(answer: dict) -> ChannelConnectOut | None:
    """Door 11's 200 as the Hub keeps it: connected, an E.164 number and WhatsApp's name; anything else, ``None``."""
    try:
        out = ChannelConnectOut.model_validate(answer)
    except ValueError:
        return None
    if answer.get("connected") is not True or not E164.match(out.phone_number) or len(out.display_name) > 200:
        return None
    return out


@operation(
    "whatsapp_inbox.channel.disconnect",
    kind="command",
    permission=CONFIGURE,
    input=ChannelDisconnectIn,
    output=ChannelDisconnectOut,
    ai={
        "description": "Disconnect the business's WhatsApp number (erplora.com stops using it): the inbox no longer "
        "receives nor sends until it is connected again from Settings; the conversations kept stay.",
        "risk": "high",
    },
)
def disconnect_number(ctx: OperationContext, data: ChannelDisconnectIn) -> dict:
    """Disconnect the business's number (erplora.com's door 12). Its answer, whether there was a number or not,
    leaves the business without one at once; the month's figures and the conversations stay."""
    answer = _ask_saas(gateway.disconnect, unknown=("whatsapp_inbox.disconnect_unknown", DISCONNECT_UNKNOWN), hub=ctx.scope.key)
    if not isinstance(answer.get("disconnected"), bool):
        logger.error("whatsapp_inbox.door.not_understood door=disconnect")
        raise OperationError(str(DISCONNECT_UNKNOWN), code="whatsapp_inbox.disconnect_unknown", status=503)
    row = _locked_channel(ctx)
    if row.status != Channel.Status.NOT_CONNECTED or row.phone_number or row.display_name:
        row.status = Channel.Status.NOT_CONNECTED
        row.phone_number = row.display_name = ""
        row.save(update_fields=["status", "phone_number", "display_name", "updated_at"])
        record_event(ctx, events.CHANNEL_DISCONNECTED, {})
    return {"disconnected": answer["disconnected"]}


# ── Sending (WHATSAPP_INBOX-F32, F33): kept here, handed to erplora.com after the COMMIT ─────────


def _blocked_error(reason: str, row: Channel | None = None) -> OperationError:
    if reason == "unconfigured":
        return Conflict(str(SAAS_UNCONFIGURED), code="whatsapp_inbox.saas_unconfigured")
    if reason == "cap_reached":
        # The same published code either way; only the reason said differs.
        spent = NO_PLAN_MESSAGES if row is not None and row.monthly_limit == 0 else CAP_REACHED
        return Conflict(str(spent), code="whatsapp_inbox.cap_reached")
    return Conflict(str(NOT_CONNECTED), code="whatsapp_inbox.channel_not_connected")


def _template_for(ctx: OperationContext, data: SendIn) -> Template:
    wanted = data.template
    rows = live_templates(ctx.scope).filter(name=wanted.name)
    if wanted.language:
        rows = rows.filter(language=wanted.language)
    found = list(rows[:2])
    if not found:
        raise NotFound(
            str(TEMPLATE_NOT_FOUND % {"name": wanted.name}),
            code="whatsapp_inbox.template_not_found",
        )
    if len(found) > 1:
        raise InvalidPayload(
            str(TEMPLATE_LANGUAGE), fields={"template": str(TEMPLATE_LANGUAGE)}
        )
    template = found[0]
    if template.status != Template.Status.APPROVED:
        raise Conflict(
            str(TEMPLATE_NOT_APPROVED % {"name": template.name}),
            code="whatsapp_inbox.template_not_approved",
        )
    if not template.supported:
        raise Conflict(str(TEMPLATE_NOT_SENDABLE), code="whatsapp_inbox.template_not_sendable")
    if len(wanted.variables) != template.variables:
        message = str(TEMPLATE_VARIABLES % {"count": template.variables})
        raise InvalidPayload(message, fields={"template": message})
    return template


def _marketing_allowed(card_id: UUID | None) -> bool:
    """Whether that live card has the WhatsApp marketing consent in force (its last fact)."""
    if card_id is None:
        return False
    latest = (
        Consent.objects.filter(
            customer_id=card_id, purpose="marketing", channel=Consent.Channel.WHATSAPP
        )
        .order_by("-occurred_at", "-created_at", "-id")
        .first()
    )
    return latest is not None and latest.state == Consent.State.GRANTED


def _rendered(body: str, variables: list[str]) -> str:
    def value(match: re.Match) -> str:
        index = int(match.group(1))
        return variables[index - 1] if 0 < index <= len(variables) else match.group(0)

    return _VARIABLE.sub(value, body)


def _target(ctx: OperationContext, data: SendIn) -> tuple[Conversation | None, str]:
    """The conversation the message goes to (locked) and its number; ``None`` for a number never written to."""
    if data.id is not None or data.conversation:
        conversation = find_conversation(data.id, data.conversation, lock=True)
        return conversation, conversation.phone
    try:
        phone = e164(data.to or "", ctx)
    except InvalidPhone:
        raise InvalidPayload(
            str(NOT_A_NUMBER), fields={"to": str(NOT_A_NUMBER)}
        ) from None
    return live_conversations().select_for_update().filter(phone=phone).first(), phone


def _sent_message(key: UUID) -> Message | None:
    return (
        Message.objects.select_related("sent_by").filter(client_message_id=key).first()
    )


@operation(
    "whatsapp_inbox.message.send",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=SendIn,
    output=MessageOut,
    expose_api=True,
    ai={
        "description": "Sends a WhatsApp message to a customer («reply to Ana», «send the reminder template to "
        "+34 600 111 222»): free text only within 24 hours of the customer's last message, otherwise an approved "
        "template with its variables; marketing templates only to customers who consented. Give a new "
        "client_message_id per message (the same one if you retry it): it really goes out, once.",
        "risk": "high",
    },
)
def send_message(ctx: OperationContext, data: SendIn) -> dict:
    already = _sent_message(data.client_message_id)
    if already is not None:
        return message_out(already)
    conversation, phone = _target(ctx, data)
    blocked = send_blocked(channel(ctx.scope))
    if blocked:
        raise _blocked_error(blocked, channel(ctx.scope))
    now = clock.now()
    template = None
    if data.template is None:
        if conversation is None or not conversation.window_open(now):
            raise Conflict(str(WINDOW_CLOSED), code="whatsapp_inbox.window_closed")
    else:
        template = _template_for(ctx, data)
        if template.category == Template.Category.MARKETING:
            card_id = _live_card_id(conversation) if conversation is not None else None
            if not _marketing_allowed(card_id or _only_card_of(phone)):
                raise Conflict(
                    str(MARKETING_CONSENT),
                    code="whatsapp_inbox.marketing_consent_missing",
                )
    if conversation is None:
        card_id = _locked_cards_of([phone]).get(phone)
        conversation = _conversation_for(phone)
        _link_by_phone(ctx, conversation, card_id)
    variables = list(data.template.variables) if template else []
    return _queue_message(ctx, conversation, data.text, template, variables, data.client_message_id, now)


def _queue_message(
    ctx: OperationContext,
    conversation: Conversation,
    text: str | None,
    template: Template | None,
    variables: list[str],
    key: UUID,
    now: dt.datetime,
) -> dict:
    """Keep the message ``queued`` in ``conversation`` and hand it to erplora.com after the COMMIT (``deliver``):
    the one way out of the Hub, for the inbox (F32, F33) and for an automation (``notify``)."""
    body = text if template is None else _rendered(template.body, variables)
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=Message.Direction.OUTBOUND,
                origin=Message.Origin.HUB,
                kind="text" if template is None else "template",
                body=body,
                template_name=template.name if template else "",
                template_language=template.language if template else "",
                template_variables=variables,
                status=Message.Status.QUEUED,
                status_at=now,
                client_message_id=key,
                sent_by=ctx.actor if actor_id(ctx) is not None else None,
                sent_at=now,
                host=ctx.scope.key,
            )
    except IntegrityError:
        # The same key at the same time: the other one kept it and hands it over.
        return message_out(_sent_message(key))
    conversation.last_message_at = now
    conversation.last_message_preview = preview(body)
    conversation.last_message_kind = message.kind
    conversation.last_message_direction = Message.Direction.OUTBOUND
    conversation.unread_count = 0
    conversation.save()
    record_event(
        ctx,
        events.MESSAGE_SENT,
        {"id": str(message.id), "conversation_id": str(conversation.id)},
    )
    _after_commit(ctx, deliver, message.id)
    return message_out(message)


@operation(
    "whatsapp_inbox.message.retry",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=MessageRefIn,
    output=MessageOut,
    expose_api=True,
    ai={
        "description": "Hands a message that has not left (erplora.com did not answer or did not confirm it) to "
        "erplora.com again, with the same key: it is never sent twice.",
        "risk": "high",
    },
)
def retry_message(ctx: OperationContext, data: MessageRefIn) -> dict:
    message = (
        Message.objects.select_for_update(of=("self",))
        .select_related("sent_by")
        .filter(pk=data.id, conversation__erased_at__isnull=True)
        .first()
    )
    if message is None:
        raise NotFound(str(MESSAGE_NOT_FOUND), code="whatsapp_inbox.message_not_found")
    if message.origin != Message.Origin.HUB or message.status not in _ON_ITS_WAY:
        raise Conflict(str(NOT_RETRYABLE), code="whatsapp_inbox.not_retryable")
    message.error_code = message.error_message = ""
    message.save(update_fields=["error_code", "error_message"])
    _after_commit_as(message.host, ctx, deliver, message.id)
    return message_out(message)


def _exact_number(raw: str, ctx: OperationContext) -> str:
    """``raw`` when it is a number written exactly in international format; ``InvalidPayload`` otherwise (a
    national or half-typed number is never guessed: it could be somebody else's, gh:whatsapp_inbox#279)."""
    text = (raw or "").strip()
    message = str(NOT_INTERNATIONAL % {"phone": text})
    if not _INTERNATIONAL.fullmatch(text):
        raise InvalidPayload(message, fields={"phone": message})
    try:
        return e164(text, ctx)
    except InvalidPhone:
        raise InvalidPayload(message, fields={"phone": message}) from None


def _in_language(ctx: OperationContext, data: NotifyIn) -> NotifyIn:
    """``data`` with its template's language, when the template exists in several and one is the caller's."""
    wanted = data.template
    if wanted is None or wanted.language:
        return data
    languages = set(live_templates(ctx.scope).filter(name=wanted.name).values_list("language", flat=True))
    own = [code for code in languages if code == ctx.language or code.startswith(f"{ctx.language}_")]
    if len(languages) < 2 or len(own) != 1:
        return data
    return data.model_copy(update={"template": wanted.model_copy(update={"language": own[0]})})


@operation(
    "whatsapp_inbox.message.notify",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=NotifyIn,
    output=MessageOut,
    expose_api=True,
    ai={
        "description": "Tells a customer something by WhatsApp (an appointment or a reservation confirmed…), only in "
        "the live conversation of exactly that international number (+34600111222): never a new conversation, "
        "never a number written any other way. Free text within 24 hours of the customer's last message, "
        "otherwise the approved template given. What an automation is granted to write to a customer.",
        "risk": "normal",
    },
)
def notify(ctx: OperationContext, data: NotifyIn) -> dict:
    key = data.client_message_id or uuid7()
    already = _sent_message(key) if data.client_message_id else None
    if already is not None:
        return message_out(already)
    phone = _exact_number(data.phone, ctx)
    row = channel(ctx.scope)
    blocked = send_blocked(row)
    if blocked:
        raise _blocked_error(blocked, row)
    conversation = live_conversations().select_for_update().filter(phone=phone).first()
    if conversation is None:
        raise Conflict(str(NO_CONVERSATION % {"phone": phone}), code="whatsapp_inbox.no_conversation")
    now = clock.now()
    template = None
    if not data.text or not conversation.window_open(now):
        if data.template is None:
            raise Conflict(str(WINDOW_CLOSED), code="whatsapp_inbox.window_closed")
        template = _template_for(ctx, _in_language(ctx, data))
        if template.category == Template.Category.MARKETING and not _marketing_allowed(
            _live_card_id(conversation) or _only_card_of(phone)
        ):
            raise Conflict(str(MARKETING_CONSENT), code="whatsapp_inbox.marketing_consent_missing")
    variables = list(data.template.variables) if template else []
    return _queue_message(ctx, conversation, data.text if template is None else None, template, variables, key, now)


def deliver(scope: Scope, message_id: UUID) -> None:
    """Hand a queued message to erplora.com (WORKBOOK «Contrato con el SaaS», door 5), with no
    transaction and no lock around the HTTP call; its answer is recorded in a transaction of its own."""
    system = system_context(scope)
    claim = get("whatsapp_inbox.message.claim_delivery")
    claimed = claim(system, MessageRefIn(id=message_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    try:
        reply = gateway.send(
            hub=scope.key,
            to=claimed.to,
            idempotency_key=str(claimed.client_message_id),
            text=claimed.text,
            template=claimed.template,
        )
    except gateway.NotConfigured:
        reply = gateway.Reply(
            kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set."
        )
    record = get("whatsapp_inbox.message.record_delivery")
    record(
        system,
        RecordDeliveryIn(
            id=message_id,
            kind=reply.kind,
            wa_message_id=reply.wa_message_id,
            code=reply.code,
            message=reply.message,
        ),
    )


@operation(
    "whatsapp_inbox.message.claim_delivery",
    kind="command",
    permission=RECEIVE,
    input=MessageRefIn,
    output=ClaimDeliveryOut,
    ai={
        "description": "System only: takes a queued message to hand it to erplora.com (nobody else is on it), "
        "marking it as sending.",
        "risk": "normal",
    },
)
def claim_delivery(ctx: OperationContext, data: MessageRefIn) -> dict:
    message = (
        Message.objects.select_for_update(of=("self",), skip_locked=True)
        .select_related("conversation")
        .filter(pk=data.id, origin=Message.Origin.HUB, status__in=_ON_ITS_WAY)
        .first()
    )
    if message is None:
        return {"claimed": False}
    if message.conversation.erased_at is not None:
        message.status = Message.Status.FAILED
        message.error_code = "whatsapp_inbox.conversation_erased"
        message.error_message = ""
        message.save(update_fields=["status", "error_code", "error_message"])
        return {"claimed": False}
    message.status = Message.Status.SENDING
    message.status_at = clock.now()
    message.save(update_fields=["status", "status_at"])
    template = (
        {
            "name": message.template_name,
            "language": message.template_language,
            "variables": message.template_variables,
        }
        if message.kind == "template"
        else None
    )
    return {
        "claimed": True,
        "to": message.conversation.phone,
        "text": message.body if template is None else None,
        "template": template,
        "client_message_id": message.client_message_id,
    }


@operation(
    "whatsapp_inbox.message.record_delivery",
    kind="command",
    permission=RECEIVE,
    input=RecordDeliveryIn,
    output=RecordOut,
    ai={
        "description": "System only: records erplora.com's answer to a send: sent with Meta's id, refused with "
        "its reason, or still sending (no answer) to retry with the same key.",
        "risk": "normal",
    },
)
def record_delivery(ctx: OperationContext, data: RecordDeliveryIn) -> dict:
    message = Message.objects.select_for_update().filter(pk=data.id).first()
    if message is None:
        return {"status": None}
    on_its_way = message.status in _ON_ITS_WAY
    if data.kind == gateway.SENT:
        if not message.wa_message_id:
            message.wa_message_id = data.wa_message_id
        if on_its_way:
            message.status = Message.Status.SENT
            message.error_code = message.error_message = ""
    elif not on_its_way:
        return {"status": message.status}  # a status from Meta already settled it
    elif data.kind == gateway.REFUSED:
        message.status = Message.Status.FAILED
        message.error_code = _REFUSALS.get(data.code, SEND_REFUSED_CODE)
        message.error_message = data.message[:500] if message.error_code == SEND_REFUSED_CODE else ""
    else:
        message.status = Message.Status.SENDING
        message.error_code = SEND_UNKNOWN_CODE if data.kind == gateway.UNKNOWN else SAAS_UNREACHABLE_CODE
        message.error_message = ""
    message.status_at = clock.now()
    message.save(
        update_fields=[
            "status",
            "status_at",
            "wa_message_id",
            "error_code",
            "error_message",
        ]
    )
    record_event(
        ctx,
        events.MESSAGE_STATUS_CHANGED,
        {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "status": message.status,
        },
    )
    return {"status": message.status}


@operation(
    "whatsapp_inbox.delivery.resume",
    kind="command",
    permission=RECEIVE,
    input=ResumeIn,
    output=ResumeOut,
    ai={
        "description": "System only (the worker's scheduled task): hands erplora.com again the messages, erasures, "
        "templates and template deletions whose delivery after the COMMIT never ended.",
        "risk": "normal",
    },
)
def resume_deliveries(ctx: OperationContext, data: ResumeIn) -> dict:
    """Hand erplora.com again what was left: every business's, each for its own (phase 1's worker runs on one fixed
    scope). A message or an erasure made before its business was recorded (0007) goes as ``ctx``'s, as it did."""
    cutoff = clock.now() - STUCK_AFTER
    messages = list(
        Message.objects.select_for_update(skip_locked=True)
        .filter(origin=Message.Origin.HUB, status__in=_ON_ITS_WAY, status_at__lt=cutoff)
        .order_by("status_at", "id")
        .values_list("id", "host")[:RESUME_BATCH]
    )
    erasures = list(
        Conversation.objects.select_for_update(skip_locked=True)
        .filter(erase_status=Conversation.EraseStatus.PENDING, erased_at__lt=cutoff)
        .order_by("erased_at", "id")
        .values_list("id", "erase_host")[:RESUME_BATCH]
    )
    # Every business's, each handed over as its own (phase 1's worker runs on one fixed scope).
    templates = list(
        templates_of_every_business().select_for_update(skip_locked=True)
        .filter(submit_state__in=_TEMPLATE_ON_ITS_WAY, submit_at__lt=cutoff, deleted_at__isnull=True)
        .order_by("submit_at", "id")
        .values_list("id", "host")[:RESUME_BATCH]
    )
    deletions = list(
        templates_of_every_business().select_for_update(skip_locked=True)
        .filter(delete_state=Template.DeleteState.PENDING, deleted_at__lt=cutoff)
        .order_by("deleted_at", "id")
        .values_list("id", "host")[:RESUME_BATCH]
    )
    for message_id, host in messages:
        _after_commit_as(host, ctx, deliver, message_id)
    for conversation_id, host in erasures:
        _after_commit_as(host, ctx, forget, conversation_id)
    for template_id, host in templates:
        _after_commit_as(host, ctx, submit_template, template_id)
    for template_id, host in deletions:
        _after_commit_as(host, ctx, remove_template, template_id)
    return {
        "messages": len(messages),
        "erasures": len(erasures),
        "templates": len(templates),
        "template_deletions": len(deletions),
    }


# ── The team's work on a conversation ───────────────────────────────────────────────────────────


@operation(
    "whatsapp_inbox.conversation.mark_read",
    kind="command",
    permission="whatsapp_inbox.view",
    input=ConversationRefIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "description": "Marks a WhatsApp conversation as read: its unread counter goes back to zero.",
        "risk": "normal",
    },
)
def mark_read(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = find_conversation(data.id, data.conversation, lock=True)
    if conversation.unread_count:
        conversation.unread_count = 0
        _save(conversation, "unread_count")
        record_event(ctx, events.CONVERSATION_READ, {"id": str(conversation.id)})
    return conversation_out(conversation)


def _assignee(ctx: OperationContext, data: AssignIn):
    """The person ``data`` names (a member of this business), or ``None`` to unassign."""
    if data.unassign:
        return None
    people = team(ctx)
    if data.assignee_id is not None:
        member = people.filter(user_id=data.assignee_id).first()
        if member is None:
            raise InvalidPayload(
                str(NOT_IN_BUSINESS), fields={"assignee": str(NOT_IN_BUSINESS)}
            )
        return member.user
    reference = (data.assignee or "").strip()
    if reference.lower() == "me":
        me = actor_id(ctx)
        if me is None:
            raise InvalidPayload(
                str(NOT_A_PERSON), fields={"assignee": str(NOT_A_PERSON)}
            )
        member = people.filter(user_id=me).first()
        if member is None:
            raise InvalidPayload(
                str(NOT_IN_BUSINESS), fields={"assignee": str(NOT_IN_BUSINESS)}
            )
        return member.user
    matches = list(
        people.annotate(
            full_name=Lower(Concat("user__first_name", Value(" "), "user__last_name"))
        )
        .filter(
            Q(user__username__iexact=reference)
            | Q(user__email__iexact=reference)
            | Q(full_name=reference.lower())
            | Q(user__first_name__iexact=reference)
        )
        .order_by("id")[:2]
    )
    if not matches:
        message = str(NOBODY_CALLED % {"reference": reference})
        raise InvalidPayload(message, fields={"assignee": message})
    if len(matches) > 1:
        message = str(SEVERAL_CALLED % {"reference": reference})
        raise InvalidPayload(message, fields={"assignee": message})
    return matches[0].user


@operation(
    "whatsapp_inbox.conversation.assign",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=AssignIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "description": "Assigns a WhatsApp conversation to a person of the team («assign Ana's conversation to "
        "Luis», «take it»: assignee me), or to nobody. Only managers assign somebody else or take it from "
        "somebody; «only if unassigned» never takes it from anybody.",
        "risk": "normal",
    },
)
def assign(ctx: OperationContext, data: AssignIn) -> dict:
    conversation = find_conversation(data.id, data.conversation, lock=True)
    person = _assignee(ctx, data)
    me = actor_id(ctx)
    target = person.pk if person is not None else None
    taken = (
        conversation.assigned_to_id is not None
        and conversation.assigned_to_id != target
    )
    if not ctx.has("whatsapp_inbox.assign"):
        # Without the permission one only takes a free conversation, or lets one's own go.
        if conversation.assigned_to_id not in (None, me):
            raise Conflict(
                str(ALREADY_ASSIGNED % {"name": person_name(conversation.assigned_to)}),
                code="whatsapp_inbox.already_assigned",
            )
        if target not in (None, me):
            raise PermissionDenied(str(ONLY_YOURSELF))
    elif data.only_if_unassigned and taken:
        raise Conflict(
            str(ALREADY_ASSIGNED % {"name": person_name(conversation.assigned_to)}),
            code="whatsapp_inbox.already_assigned",
        )
    if conversation.assigned_to_id != target:
        conversation.assigned_to = person
        _save(conversation, "assigned_to")
        record_event(
            ctx, events.ASSIGNED, {"id": str(conversation.id), "assigned_to_id": target}
        )
    return conversation_out(conversation)


@operation(
    "whatsapp_inbox.conversation.set_status",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=SetStatusIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "description": "Marks a WhatsApp conversation open, pending (waiting for the customer) or closed (done); "
        "a new message from the customer opens it again.",
        "risk": "high",
    },
)
def set_status(ctx: OperationContext, data: SetStatusIn) -> dict:
    conversation = find_conversation(data.id, data.conversation, lock=True)
    if conversation.status != data.status:
        conversation.status = data.status
        _save(conversation, "status")
        record_event(
            ctx,
            events.STATUS_CHANGED,
            {"id": str(conversation.id), "status": data.status},
        )
    return conversation_out(conversation)


@operation(
    "whatsapp_inbox.conversation.link_customer",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=LinkCustomerIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "description": "Joins a WhatsApp conversation to a customer card (by id or by the card's exact name, phone "
        "or email), creates the card from the WhatsApp name and number, or takes the card off.",
        "risk": "normal",
    },
)
def link_customer(ctx: OperationContext, data: LinkCustomerIn) -> dict:
    # The card chosen before the conversation (``_locked_cards_of``): one the Hub admin deletes is waited for and gone.
    chosen = None
    if not (data.unlink or data.create):
        chosen = find_customer(data.customer_id, data.customer, lock=True)
    conversation = find_conversation(data.id, data.conversation, lock=True)
    if data.unlink:
        card = None
    elif data.create:
        create = get("customer.customer.create")
        made = create(
            ctx,
            create.input.model_validate(
                {
                    "name": conversation.contact_name or conversation.phone,
                    "phone": conversation.phone,
                    "source": "whatsapp",
                }
            ),
        )
        card = Customer.objects.get(pk=made.id)
    else:
        card = chosen
    if conversation.customer_id != (card.id if card else None):
        conversation.customer = card
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(card.id) if card else None},
        )
    return conversation_out(conversation)


# ── Erasing (WHATSAPP_INBOX-F10, F11): here at once, at erplora.com after the COMMIT ─────────────


def _erase(ctx: OperationContext, conversation: Conversation) -> None:
    """Empty every personal datum of ``conversation`` once, and ask erplora.com to forget its number
    after the COMMIT until it confirms; again changes nothing here and asks erplora.com again, for the business
    that erased it (``erase_host``), whoever asks from the shared inbox."""
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
        conversation.erase_host = ctx.scope.key
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
        _after_commit_as(conversation.erase_host, ctx, forget, conversation.id)


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
        "description": "Erases a number's WhatsApp data at the person's request (GDPR): the number, the name, "
        "every text, attachment and note of the conversation, here and at erplora.com. Irreversible; if they "
        "write again, a new conversation starts.",
        "risk": "high",
    },
)
def erase(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = find_conversation(
        data.id, data.conversation, lock=True, live=data.id is None
    )
    _erase(ctx, conversation)
    return {"id": conversation.id}


# ── Notes (WHATSAPP_INBOX-F36) ──────────────────────────────────────────────────────────────────


@operation(
    "whatsapp_inbox.note.add",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=NoteAddIn,
    output=NoteOut,
    expose_api=True,
    ai={
        "description": "Leaves an internal note on a WhatsApp conversation for the team; the customer never sees it.",
        "risk": "normal",
    },
)
def add_note(ctx: OperationContext, data: NoteAddIn) -> dict:
    conversation = find_conversation(data.id, data.conversation)
    author = ctx.actor if actor_id(ctx) is not None else None
    note = Note.objects.create(
        conversation=conversation,
        text=data.text,
        author=author,
        author_name=person_name(author),
        created_at=clock.now(),
    )
    record_event(
        ctx,
        events.NOTE_ADDED,
        {"id": str(note.id), "conversation_id": str(conversation.id)},
    )
    return note_out(ctx, note)


@operation(
    "whatsapp_inbox.note.delete",
    kind="command",
    permission="whatsapp_inbox.reply",
    input=NoteRefIn,
    output=NoteDeletedOut,
    expose_api=True,
    ai={
        "description": "Deletes an internal note of a WhatsApp conversation: one's own, or anybody's for a manager.",
        "risk": "high",
    },
)
def delete_note(ctx: OperationContext, data: NoteRefIn) -> dict:
    note = (
        Note.objects.select_for_update()
        .filter(pk=data.id, conversation__erased_at__isnull=True)
        .first()
    )
    if note is None:
        raise NotFound(str(NOTE_NOT_FOUND), code="whatsapp_inbox.note_not_found")
    if not may_delete_note(ctx, note):
        raise PermissionDenied(str(NOTE_NOT_YOURS))
    conversation_id = note.conversation_id
    note.delete()
    record_event(
        ctx,
        events.NOTE_DELETED,
        {"id": str(data.id), "conversation_id": str(conversation_id)},
    )
    return {"id": data.id}


# ── Templates (WHATSAPP_INBOX-F29…F31): kept here, handed to erplora.com after the COMMIT ─────────


def _content(data: TemplateWriteIn) -> dict:
    """What the form wrote, as the template keeps it and door 8 takes it: a header with a file names it (its text is
    refused by ``TemplateWriteIn``); any other is a text header when it has one."""
    with_file = data.header_format in samples.FILE_HEADERS
    return {
        "category": data.category,
        "header_format": data.header_format if with_file else ("TEXT" if data.header else ""),
        "header": data.header,
        "header_sample": str(data.header_sample) if with_file else None,
        "body": data.body,
        "body_examples": list(data.body_examples),
        "footer": data.footer,
        "buttons": [{field: value for field, value in button.model_dump().items() if value} for button in data.buttons],
    }


def _apply(row: Template, content: dict) -> None:
    for field in ("category", "header", "body", "body_examples", "footer", "buttons"):
        setattr(row, field, content[field])
    # An edit kept before headers had files carries neither: a text header or none.
    row.header_format = content.get("header_format", "TEXT" if row.header else "")
    row.header_sample_id = content.get("header_sample")
    row.variables = template_variables(row.body)


def _header_file(ctx: OperationContext, data: TemplateWriteIn) -> None:
    """A header with a file names one of this business's, of its kind (``upload_sample``)."""
    if data.header_format not in samples.FILE_HEADERS:
        return
    kept = data.header_sample is not None and TemplateSample.objects.filter(
        pk=data.header_sample, host=ctx.scope.key, header_format=data.header_format
    ).exists()
    if not kept:
        message = str(HEADER_FILE_MISSING)
        raise InvalidPayload(message, fields={"header_sample": message})


def _no_template_without_a_number(ctx: OperationContext) -> None:
    blocked = send_blocked(channel(ctx.scope))
    if blocked in ("not_connected", "unconfigured"):
        raise _blocked_error(blocked)


def _queue(ctx: OperationContext, row: Template, key: UUID, event: str) -> None:
    row.submit_state = Template.SubmitState.QUEUED
    row.submit_key = key
    row.submit_error_code = row.submit_error = ""
    row.submit_at = clock.now()
    row.save()
    record_event(ctx, event, {"id": str(row.id)})
    _after_commit(ctx, submit_template, row.id)


def _sample_bytes(data: TemplateSampleUploadIn) -> tuple[bytes, str]:
    """The file and its type, if it is one Meta takes for its header; else the refusal under its field."""

    def refuse(message) -> InvalidPayload:
        return InvalidPayload(str(message), fields={"content_base64": str(message)})

    try:
        content = base64.b64decode(data.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise refuse(SAMPLE_NOT_WHOLE) from None
    kind = samples.sniff(content[:16])
    if kind is None or kind[0] != data.header_format:
        raise refuse(SAMPLE_WRONG_TYPE[data.header_format])
    limit = samples.MAX_BYTES[data.header_format]
    if len(content) > limit:
        raise refuse(SAMPLE_TOO_HEAVY % {"mb": limit // samples.MB})
    return content, kind[1]


@operation(
    "whatsapp_inbox.template_sample.upload",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateSampleUploadIn,
    output=TemplateSampleOut,
    expose_api=True,
    ai={
        "description": "Keeps the file of a WhatsApp template's header the person attached (a JPEG or PNG photo up "
        "to 5 MB, an MP4 video up to 16 MB or a PDF up to 25 MB) and answers its id, to give as header_sample when "
        "creating or changing the template: Meta reviews the template with it.",
        "risk": "normal",
    },
)
def upload_sample(ctx: OperationContext, data: TemplateSampleUploadIn) -> dict:
    """F29: keep the header's file in the hub's store, named by its content (``samples.sample_key``)."""
    content, content_type = _sample_bytes(data)
    sha = hashlib.sha256(content).hexdigest()
    key = samples.sample_key(hub_id(ctx.scope), sha, content_type)
    store = storages["hub_files"]
    try:
        if not store.exists(key):
            key = store.save(key, ContentFile(content))
    except STORE_ERRORS as exc:
        raise OperationError(str(SAMPLE_NOT_KEPT), code="whatsapp_inbox.sample_not_kept", status=503) from exc
    row = TemplateSample.objects.create(
        host=ctx.scope.key,
        header_format=data.header_format,
        key=key,
        sha256=sha,
        content_type=content_type,
        size=len(content),
        name=data.name,
    )
    record_event(ctx, events.TEMPLATE_SAMPLE_UPLOADED, {"id": str(row.id)})
    return sample_out(row)


@operation(
    "whatsapp_inbox.template.create",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateCreateIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "description": "Creates a WhatsApp message template (name, language, utility or marketing, header, text with "
        "{{1}}… and an example of each, footer, buttons) and sends it to Meta for review. Give a new submit_key per "
        "save (the same one if you retry it): it is registered once.",
        "risk": "high",
    },
)
def create_template(ctx: OperationContext, data: TemplateCreateIn) -> dict:
    already = templates_of(ctx.scope).filter(submit_key=data.submit_key).first()
    if already is not None:
        return template_out(already)
    _no_template_without_a_number(ctx)
    _header_file(ctx, data)
    exists = Conflict(str(TEMPLATE_EXISTS % {"name": data.name}), code="whatsapp_inbox.template_exists")
    if live_templates(ctx.scope).filter(name=data.name, language=data.language).exists():
        raise exists
    row = Template(host=ctx.scope.key, name=data.name, language=data.language, status=Template.Status.DRAFT)
    _apply(row, _content(data))
    try:
        with transaction.atomic():
            _queue(ctx, row, data.submit_key, events.TEMPLATE_CREATED)
    except IntegrityError:
        # The same save at the same time (its key), or the name just taken by another.
        twin = templates_of(ctx.scope).filter(submit_key=data.submit_key).first()
        if twin is None:
            raise exists from None
        return template_out(twin)
    return template_out(row)


def _changeable(row: Template, content: dict) -> None:
    if not hub_writes(row) or row.status in (Template.Status.DISABLED, Template.Status.DELETED):
        raise Conflict(str(TEMPLATE_READ_ONLY), code="whatsapp_inbox.template_read_only")
    if row.status == Template.Status.PENDING:
        raise Conflict(str(TEMPLATE_IN_REVIEW), code="whatsapp_inbox.template_in_review")
    in_flight = row.submit_state == Template.SubmitState.QUEUED or (
        row.submit_state == Template.SubmitState.SENDING and not row.submit_error_code
    )
    if in_flight:
        raise Conflict(str(TEMPLATE_SUBMITTING), code="whatsapp_inbox.template_submitting")
    judged = row.status not in (Template.Status.DRAFT, Template.Status.REJECTED)
    if judged and content["category"] != row.category:
        raise Conflict(str(TEMPLATE_CATEGORY_FIXED), code="whatsapp_inbox.template_category_fixed")


@operation(
    "whatsapp_inbox.template.update",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateUpdateIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "description": "Changes a WhatsApp template (not its name or language) and sends it to Meta for review "
        "again; until Meta takes the change, the approved one keeps being the one sent. Not while Meta reviews it.",
        "risk": "high",
    },
)
def update_template(ctx: OperationContext, data: TemplateUpdateIn) -> dict:
    row = live_templates(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    if row.submit_key == data.submit_key:
        return template_out(row)  # the same save again
    _no_template_without_a_number(ctx)
    content = _content(data)
    _changeable(row, content)
    _header_file(ctx, data)
    if row.status == Template.Status.DRAFT:
        _apply(row, content)  # Meta never had it: what is written is the template
        row.draft = None
    else:
        row.draft = content  # Meta's stays the one sent until it takes the edit
    try:
        with transaction.atomic():
            _queue(ctx, row, data.submit_key, events.TEMPLATE_UPDATED)
    except IntegrityError:
        raise Conflict(str(TEMPLATE_SUBMITTING), code="whatsapp_inbox.template_submitting") from None
    return template_out(row)


@operation(
    "whatsapp_inbox.template.retry",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateRefIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "description": "Hands a template that did not reach Meta (or a deletion Meta has not confirmed) to "
        "erplora.com again: never registered twice.",
        "risk": "normal",
    },
)
def retry_template(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None or (row.deleted_at is not None and row.delete_state != Template.DeleteState.PENDING):
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    if row.delete_state == Template.DeleteState.PENDING:
        row.submit_error_code = row.submit_error = ""
        row.save(update_fields=["submit_error_code", "submit_error"])
        _after_commit(ctx, remove_template, row.id)
        return template_out(row)
    if row.submit_state == Template.SubmitState.FAILED:
        # Refused: the same key would get the same answer; a transient refusal goes again as a new save.
        _queue(ctx, row, uuid7(), events.TEMPLATE_UPDATED)
    elif row.submit_state in _TEMPLATE_ON_ITS_WAY:
        _queue(ctx, row, row.submit_key, events.TEMPLATE_UPDATED)
    else:
        raise Conflict(str(TEMPLATE_NOT_RETRYABLE), code="whatsapp_inbox.not_retryable")
    return template_out(row)


@operation(
    "whatsapp_inbox.template.delete",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateRefIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "description": "Deletes a WhatsApp template here and at Meta (that language only). Irreversible: an approved "
        "template takes days to be approved again.",
        "risk": "high",
    },
)
def delete_template(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = live_templates(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    # Meta may have it unless it never left the Hub (or it left and Meta refused it).
    at_meta = bool(row.meta_id) or row.status != Template.Status.DRAFT or row.submit_state == Template.SubmitState.SENDING
    row.deleted_at = clock.now()
    row.delete_state = Template.DeleteState.PENDING if at_meta else Template.DeleteState.DONE
    row.submit_state = Template.SubmitState.NONE
    row.submit_error_code = row.submit_error = ""
    row.save()
    record_event(ctx, events.TEMPLATE_DELETED, {"id": str(row.id)})
    if at_meta:
        _after_commit(ctx, remove_template, row.id)
    return template_out(row)


def submit_template(scope: Scope, template_id: UUID) -> None:
    """Hand a template to erplora.com (door 8) with no transaction and no lock around the HTTP call; its
    answer is recorded in a transaction of its own. A header's file is read from the store then too, with no
    connection held: one no longer there is said with its own code (fixed with Edit), the store not answering is
    «nothing left», to send again."""
    system = system_context(scope)
    claimed = get("whatsapp_inbox.template.claim_submit")(system, TemplateRefIn(id=template_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    template, reply = _with_its_file(claimed.template)
    if reply is None:
        try:
            reply = gateway.submit_template(
                hub=scope.key, idempotency_key=str(claimed.submit_key), template=template
            )
        except gateway.NotConfigured:
            reply = gateway.Reply(kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set.")
    get("whatsapp_inbox.template.record_submit")(
        system,
        RecordTemplateIn(
            id=template_id,
            submit_key=claimed.submit_key,
            kind=reply.kind,
            meta_id=reply.meta_id,
            status=reply.status,
            code=reply.code,
            message=reply.message,
        ),
    )


def _with_its_file(template: dict) -> tuple[dict, gateway.Reply | None]:
    """Door 8's body with the header's file in base64 (``sample_key`` → ``header_sample``), or the reply of a file
    that could not be read."""
    key = template.pop("sample_key", None)
    name = template.pop("sample_name", "")
    if key is None:
        return template, None
    missing = gateway.Reply(kind=gateway.REFUSED, code=HEADER_SAMPLE_MISSING_CODE)
    if not key:
        return template, missing
    try:
        with storages["hub_files"].open(key, "rb") as kept:
            content = kept.read()
    except FileNotFoundError:
        logger.error("whatsapp_inbox.template.sample_missing key=%s", key)
        return template, missing
    except STORE_ERRORS:
        logger.exception("whatsapp_inbox.template.sample_unreadable key=%s", key)
        return template, gateway.Reply(kind=gateway.UNREACHABLE, message="The hub's file store did not answer.")
    sample = {"name": name, "content_base64": base64.b64encode(content).decode("ascii")}
    return {**template, "header_sample": sample}, None


def remove_template(scope: Scope, template_id: UUID) -> None:
    """Ask erplora.com to delete a template deleted here at Meta (door 9), outside any transaction."""
    system = system_context(scope)
    claimed = get("whatsapp_inbox.template.claim_delete")(system, TemplateRefIn(id=template_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    try:
        reply = gateway.delete_template(
            hub=scope.key, name=claimed.name, language=claimed.language, meta_id=claimed.meta_id
        )
    except gateway.NotConfigured:
        reply = gateway.Reply(kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set.")
    get("whatsapp_inbox.template.record_delete")(
        system, RecordTemplateDeletionIn(id=template_id, kind=reply.kind, code=reply.code, message=reply.message)
    )


@operation(
    "whatsapp_inbox.template.claim_submit",
    kind="command",
    permission=RECEIVE,
    input=TemplateRefIn,
    output=ClaimTemplateOut,
    ai={"description": "System only: takes a template to hand to erplora.com (nobody else is on it).", "risk": "normal"},
)
def claim_submit(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = (
        templates_of(ctx.scope).select_for_update(skip_locked=True)
        .filter(pk=data.id, submit_state__in=_TEMPLATE_ON_ITS_WAY, deleted_at__isnull=True)
        .first()
    )
    if row is None:
        return {"claimed": False}
    row.submit_state = Template.SubmitState.SENDING
    row.submit_at = clock.now()
    row.save(update_fields=["submit_state", "submit_at"])
    content = dict(row.draft or {
        "category": row.category,
        "header_format": row.header_format,
        "header": row.header,
        "header_sample": str(row.header_sample_id) if row.header_sample_id else None,
        "body": row.body,
        "body_examples": row.body_examples,
        "footer": row.footer,
        "buttons": row.buttons,
    })
    header_format = content.pop("header_format", "")
    sample_id = content.pop("header_sample", None)
    template = {"name": row.name, "language": row.language, **content, "meta_id": row.meta_id}
    if header_format in samples.FILE_HEADERS:
        # Read after the claim's COMMIT, with no connection held (``submit_template``): the key, not the bytes.
        sample = TemplateSample.objects.filter(pk=sample_id, host=row.host).first() if sample_id else None
        template.update(header_format=header_format)
        if sample is not None:
            template.update(sample_key=sample.key, sample_name=sample.name)
        else:
            template.update(sample_key="", sample_name="")
    return {"claimed": True, "template": template, "submit_key": row.submit_key}


def _template_failure(kind: str, code: str, message: str) -> tuple[str, str]:
    """The Hub's code of a hand-over or deletion that did not end well and, for a refusal of Meta's it has no name
    for, Meta's reason as it came; the Hub's own words are said when the row is read (queries.template_reason)."""
    if kind == gateway.REFUSED:
        known = _TEMPLATE_REFUSALS.get(code)
        if known:
            return known, ""
        return TEMPLATE_REFUSED_CODE, message[:500]
    return (SEND_UNKNOWN_CODE if kind == gateway.UNKNOWN else SAAS_UNREACHABLE_CODE), ""


@operation(
    "whatsapp_inbox.template.record_submit",
    kind="command",
    permission=RECEIVE,
    input=RecordTemplateIn,
    output=RecordOut,
    ai={
        "description": "System only: records erplora.com's answer to a template: Meta took it (its id and verdict), "
        "refused it with its reason, or no answer (to retry with the same key).",
        "risk": "normal",
    },
)
def record_submit(ctx: OperationContext, data: RecordTemplateIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        return {"status": None}
    if row.submit_key != data.submit_key or row.submit_state not in _TEMPLATE_ON_ITS_WAY:
        return {"status": row.status}  # an answer to an older save, or the template was deleted meanwhile
    if data.kind == gateway.ACCEPTED:
        if row.draft:
            _apply(row, row.draft)
            row.draft = None
        row.status = data.status
        row.meta_id = data.meta_id
        row.rejected_reason = ""
        row.submit_state = Template.SubmitState.NONE
        row.submit_error_code = row.submit_error = ""
    else:
        row.submit_error_code, row.submit_error = _template_failure(data.kind, data.code, data.message)
        row.submit_state = (
            Template.SubmitState.FAILED if data.kind == gateway.REFUSED else Template.SubmitState.SENDING
        )
    row.submit_at = clock.now()
    row.save()
    record_event(ctx, events.TEMPLATE_UPDATED, {"id": str(row.id)})
    return {"status": row.status}


@operation(
    "whatsapp_inbox.template.claim_delete",
    kind="command",
    permission=RECEIVE,
    input=TemplateRefIn,
    output=ClaimTemplateDeletionOut,
    ai={"description": "System only: takes a template deleted here that Meta still has to delete.", "risk": "normal"},
)
def claim_delete(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = (
        templates_of(ctx.scope).select_for_update(skip_locked=True)
        .filter(pk=data.id, delete_state=Template.DeleteState.PENDING)
        .first()
    )
    if row is None:
        return {"claimed": False}
    return {"claimed": True, "name": row.name, "language": row.language, "meta_id": row.meta_id}


@operation(
    "whatsapp_inbox.template.record_delete",
    kind="command",
    permission=RECEIVE,
    input=RecordTemplateDeletionIn,
    output=RecordOut,
    ai={
        "description": "System only: records that erplora.com deleted a template at Meta; unconfirmed, it is asked again.",
        "risk": "normal",
    },
)
def record_delete(ctx: OperationContext, data: RecordTemplateDeletionIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None or row.delete_state != Template.DeleteState.PENDING:
        return {"status": row.delete_state if row else None}
    if data.kind == gateway.ACCEPTED:
        row.delete_state = Template.DeleteState.DONE
        row.submit_error_code = row.submit_error = ""
    else:
        row.submit_error_code, row.submit_error = _template_failure(data.kind, data.code, data.message)
    row.save(update_fields=["delete_state", "submit_error_code", "submit_error"])
    record_event(ctx, events.TEMPLATE_UPDATED, {"id": str(row.id)})
    return {"status": row.delete_state}


# ── Reactions to Customers (events.py) ──────────────────────────────────────────────────────────


@operation(
    "whatsapp_inbox.conversation.claim_for_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.created/updated): joins the conversations of the card's "
        "number that have no live card to it, when no other live card has that number.",
        "risk": "normal",
    },
)
def claim_for_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    # The card before its number's conversations (``_locked_cards_of``); one the Hub admin deleted claims nothing.
    if not lock_customers([data.id]):
        return {"count": 0}
    card = Customer.objects.live().filter(pk=data.id).first()
    if card is None or not card.phone or _only_card_of(card.phone) != card.id:
        return {"count": 0}
    rows = list(
        live_conversations()
        .select_for_update(of=("self",))
        .filter(
            Q(customer__isnull=True) | Q(customer__deleted_at__isnull=False),
            phone=card.phone,
        )
    )
    for conversation in rows:
        conversation.customer = card
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(card.id)},
        )
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.move_customer",
    kind="command",
    permission=RECEIVE,
    input=MergedEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.merged): the conversations of the absorbed card follow the "
        "card that stays.",
        "risk": "normal",
    },
)
def move_customer(ctx: OperationContext, data: MergedEventIn) -> dict:
    # The card that stays before the conversations that move to it; one the Hub admin deleted takes nothing.
    if data.id == data.absorbed_id or not lock_customers([data.id]):
        return {"count": 0}
    rows = list(
        Conversation.objects.select_for_update().filter(customer_id=data.absorbed_id)
    )
    for conversation in rows:
        conversation.customer_id = data.id
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(data.id)},
        )
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.release_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.deleted): the conversations of the deleted card are left "
        "without it, and another live card of their number, if there is exactly one, claims them.",
        "risk": "normal",
    },
)
def release_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    phones = live_conversations().filter(customer_id=data.id).values_list("phone", flat=True)
    claims = _locked_cards_of(sorted(set(phones)))
    rows = list(live_conversations().select_for_update().filter(customer_id=data.id))
    for conversation in rows:
        conversation.customer = None
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": None},
        )
        _link_by_phone(ctx, conversation, claims.get(conversation.phone))
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.erase_for_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.erased): erases every conversation of the erased card, as "
        "erasing a number does, here and at erplora.com.",
        "risk": "high",
    },
)
def erase_for_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    rows = list(live_conversations().select_for_update().filter(customer_id=data.id))
    for conversation in rows:
        _erase(ctx, conversation)
    return {"count": len(rows)}
