"""Write operations of the WhatsApp inbox: one operation, one transaction, its events in the outbox.

What erplora.com pushes (a message, a delivery status, the channel's state and templates) runs as the
system through ``whatsapp_inbox.receive``, which no role holds; what the team does (send, read,
assign, change the status, link a card, notes, erase) runs as the person.

Nothing waits for erplora.com inside a transaction (WORKBOOK «Reglas que no se rompen»). Sending keeps
the message ``queued`` in a short transaction and hands it over after the COMMIT (``deliver``): a claim
(``message.claim_delivery``, ``sending``), the HTTP call with no transaction and no lock, and the answer
in another short transaction (``message.record_delivery``: ``sent``, ``failed`` with erplora.com's
reason, or still ``sending`` with why, to retry with the same key). Erasing does the same with the
number erplora.com has to forget (``forget``). What a crash leaves half-way, the worker's
``delivery.resume`` hands over again (phase 2). A message is never «sent» without Meta's id.
"""

import datetime as dt
import re
from functools import partial
from uuid import UUID

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
from apps.whatsapp_inbox import clock, events, gateway
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.queries import (
    actor_id,
    channel,
    conversation_out,
    e164,
    find_conversation,
    live_conversations,
    may_delete_note,
    message_out,
    note_out,
    person_name,
    preview,
    send_blocked,
    team,
)
from apps.whatsapp_inbox.schemas import (
    AssignIn,
    ChannelSyncIn,
    ChannelSyncOut,
    ClaimDeliveryOut,
    ClaimErasureOut,
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
    ResumeIn,
    ResumeOut,
    SendIn,
    SetStatusIn,
    StatusIn,
    StatusOut,
)

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
NOT_CONNECTED = _(
    "WhatsApp is not connected. Connect the business's number in erplora.com to receive and send messages."
)
SAAS_UNCONFIGURED = _(
    "This server cannot reach erplora.com, so nothing can be sent from it."
)
CAP_REACHED = _(
    "You have used every WhatsApp message of your plan this month: nothing can be sent until next month "
    "or until you upgrade the plan."
)
SEND_REFUSED = _("erplora.com did not send the message.")
SAAS_UNREACHABLE = _("erplora.com did not answer: the message has not left. Try again.")
SEND_UNKNOWN = _(
    "erplora.com did not confirm the message. Try again: it is never sent twice."
)
NOT_RETRYABLE = _("This message cannot be sent again: write a new one.")
MESSAGE_NOT_FOUND = _("That message no longer exists.")
CONVERSATION_ERASED = _("The conversation was erased before the message left.")
TEMPLATE_NOT_FOUND = _("There is no template called “%(name)s”.")
TEMPLATE_LANGUAGE = _("That template exists in several languages: say which one.")
TEMPLATE_NOT_APPROVED = _(
    "Meta has not approved the template “%(name)s”: it cannot be sent."
)
TEMPLATE_VARIABLES = _("Fill in every variable of the template (%(count)d).")
MARKETING_CONSENT = _("This customer has not agreed to receive marketing by WhatsApp.")
ALREADY_ASSIGNED = _("This conversation is already with %(name)s.")
ONLY_YOURSELF = _("You may only assign conversations to yourself.")
NOBODY_CALLED = _("Nobody in this business is called “%(reference)s”.")
SEVERAL_CALLED = _("Several people match “%(reference)s”: choose one from the list.")
NOT_IN_BUSINESS = _("That person does not work in this business.")
NOT_A_PERSON = _("Only a person can be assigned a conversation.")
NOTE_NOT_FOUND = _("That note no longer exists.")
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
#: erplora.com's 409 codes the Hub knows by name; any other is «erplora.com did not send it».
_REFUSALS = {"whatsapp.cap_reached": "whatsapp_inbox.cap_reached"}


def _save(instance, *fields: str) -> None:
    instance.save(
        update_fields=[
            *fields,
            *(["updated_at"] if hasattr(instance, "updated_at") else []),
        ]
    )


def _after_commit(ctx: OperationContext, job, *args) -> None:
    """Run ``job(scope, *args)`` once this command's transaction committed: outside it, with no lock.

    Phase 1 runs it at the end of the request; phase 2 also from the worker (``delivery.resume``), and
    the job enters ``use_hub(hub)`` itself, since it runs outside the request that chose the hub.
    """
    transaction.on_commit(partial(job, ctx.scope, *args), robust=True)


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


def _redelivered(ctx: OperationContext, message: Message, data: ReceiveIn) -> dict:
    """The same WhatsApp message again: nothing changes, unless it completes a history placeholder."""
    completes = (
        data.source == Message.Source.HISTORY
        and message.kind == "media_placeholder"
        and data.type != "media_placeholder"
        and message.conversation.erased_at is None
    )
    if completes:
        message.kind = data.type
        message.body = data.text
        message.payload = data.payload
        for field, value in _media_fields(data).items():
            setattr(message, field, value)
        message.save()
        record_event(
            ctx,
            events.MESSAGE_RECEIVED,
            {
                "id": str(message.id),
                "conversation_id": str(message.conversation_id),
                "direction": message.direction,
            },
        )
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
        phone = e164(data.from_, ctx)
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
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=data.direction,
                origin=Message.Origin.CUSTOMER if inbound else Message.Origin.PHONE_APP,
                source=data.source,
                kind=kind,
                body=data.text,
                status=Message.Status.RECEIVED if inbound else Message.Status.SENT,
                wa_message_id=data.wa_message_id,
                reply_to=data.reply_to,
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
    record_event(
        ctx,
        events.MESSAGE_RECEIVED,
        {
            "id": str(message.id),
            "conversation_id": str(conversation.id),
            "direction": message.direction,
        },
    )
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
    rows = Channel.objects.select_for_update()
    row = rows.first()
    if row is None:
        try:
            with transaction.atomic():
                row = Channel.objects.create()
        except IntegrityError:
            row = rows.get()
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
        kept = []
        for item in data.templates:
            template, _created = Template.objects.update_or_create(
                name=item.name,
                language=item.language,
                defaults={
                    "category": item.category,
                    "status": item.status,
                    "header": item.header,
                    "body": item.body,
                    "footer": item.footer,
                    "variables": item.variables,
                    "rejected_reason": item.rejected_reason,
                    "meta_id": item.meta_id,
                    "synced_at": now,
                },
            )
            kept.append(template.pk)
        Template.objects.exclude(pk__in=kept).exclude(
            status=Template.Status.DELETED
        ).update(status=Template.Status.DELETED, synced_at=now)
    record_event(ctx, events.CHANNEL_SYNCED, {"version": data.version})
    return {"applied": True, "version": data.version}


# ── Sending (WHATSAPP_INBOX-F32, F33): kept here, handed to erplora.com after the COMMIT ─────────


def _blocked_error(reason: str) -> OperationError:
    if reason == "unconfigured":
        return Conflict(str(SAAS_UNCONFIGURED), code="whatsapp_inbox.saas_unconfigured")
    if reason == "cap_reached":
        return Conflict(str(CAP_REACHED), code="whatsapp_inbox.cap_reached")
    return Conflict(str(NOT_CONNECTED), code="whatsapp_inbox.channel_not_connected")


def _template_for(data: SendIn) -> Template:
    wanted = data.template
    rows = Template.objects.filter(name=wanted.name)
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
    blocked = send_blocked(channel())
    if blocked:
        raise _blocked_error(blocked)
    now = clock.now()
    template = None
    if data.template is None:
        if conversation is None or not conversation.window_open(now):
            raise Conflict(str(WINDOW_CLOSED), code="whatsapp_inbox.window_closed")
    else:
        template = _template_for(data)
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
    body = data.text if template is None else _rendered(template.body, variables)
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
                client_message_id=data.client_message_id,
                sent_by=ctx.actor if actor_id(ctx) is not None else None,
                sent_at=now,
            )
    except IntegrityError:
        # The same key at the same time: the other one kept it and hands it over.
        return message_out(_sent_message(data.client_message_id))
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
    _after_commit(ctx, deliver, message.id)
    return message_out(message)


def deliver(scope: Scope, message_id: UUID) -> None:
    """Hand a queued message to erplora.com (WORKBOOK «Contrato con el SaaS», door 5), with no
    transaction and no lock around the HTTP call; its answer is recorded in a transaction of its own."""
    system = system_context(scope)
    claim = get("whatsapp_inbox.message.claim_delivery")
    claimed = claim(system, MessageRefIn(id=message_id))
    if not claimed.claimed:
        return
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
        message.error_message = str(CONVERSATION_ERASED)
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
        message.error_code = _REFUSALS.get(data.code, "whatsapp_inbox.send_refused")
        message.error_message = (data.message or str(SEND_REFUSED))[:500]
    else:
        message.status = Message.Status.SENDING
        unknown = data.kind == gateway.UNKNOWN
        message.error_code = (
            "whatsapp_inbox.send_unknown"
            if unknown
            else "whatsapp_inbox.saas_unreachable"
        )
        message.error_message = str(SEND_UNKNOWN if unknown else SAAS_UNREACHABLE)
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
        "description": "System only (the worker's scheduled task, phase 2): hands erplora.com again the messages "
        "and erasures whose delivery after the COMMIT never ended.",
        "risk": "normal",
    },
)
def resume_deliveries(ctx: OperationContext, data: ResumeIn) -> dict:
    cutoff = clock.now() - STUCK_AFTER
    messages = list(
        Message.objects.select_for_update(skip_locked=True)
        .filter(origin=Message.Origin.HUB, status__in=_ON_ITS_WAY, status_at__lt=cutoff)
        .order_by("status_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    erasures = list(
        Conversation.objects.select_for_update(skip_locked=True)
        .filter(erase_status=Conversation.EraseStatus.PENDING, erased_at__lt=cutoff)
        .order_by("erased_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    for message_id in messages:
        _after_commit(ctx, deliver, message_id)
    for conversation_id in erasures:
        _after_commit(ctx, forget, conversation_id)
    return {"messages": len(messages), "erasures": len(erasures)}


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
