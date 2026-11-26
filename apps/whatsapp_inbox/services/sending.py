"""Sending (WHATSAPP_INBOX-F32, F33): a message or a notice is kept ``queued`` in a short transaction and
handed to erplora.com after the COMMIT (``deliveries.deliver``)."""

import datetime as dt
import re
from uuid import UUID, uuid7

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from live.operations import atomic, operation
from live.outbox import record_event

from apps.customer.models import Consent
from apps.customer.phones import InvalidPhone
from apps.whatsapp_inbox import clock, events, samples
from apps.whatsapp_inbox.models.channel import Channel
from apps.whatsapp_inbox.models.conversations import Conversation, Message
from apps.whatsapp_inbox.models.templates import Template, TemplateSample
from apps.whatsapp_inbox.notify_schemas import NotifyIn
from apps.whatsapp_inbox.queries.channel import channel, send_blocked
from apps.whatsapp_inbox.queries.conversations import find_conversation
from apps.whatsapp_inbox.queries.messages import MESSAGE_NOT_FOUND, message_out
from apps.whatsapp_inbox.queries.reads import e164, live_conversations, preview
from apps.whatsapp_inbox.queries.reasons import CAP_REACHED, NOT_CONNECTED
from apps.whatsapp_inbox.queries.templates import live_templates
from apps.whatsapp_inbox.schemas.messages import MessageOut, MessageRefIn
from apps.whatsapp_inbox.schemas.sending import SendIn
from base.services.sessions import acting_hub_user

from .deliveries import _ON_ITS_WAY, deliver
from .writes import (
    NOT_A_NUMBER,
    _after_commit,
    _conversation_for,
    _link_by_phone,
    _live_card_id,
    _locked_cards_of,
    _only_card_of,
)

WINDOW_CLOSED = _(
    "More than 24 hours have passed since the customer's last message: WhatsApp only lets you write to "
    "them with an approved template."
)
SAAS_UNCONFIGURED = _(
    "This server cannot reach erplora.com, so nothing can be sent from it."
)
#: A plan that includes no WhatsApp messages (0): no month brings any, so not «until next month».
NO_PLAN_MESSAGES = _("Your plan does not include WhatsApp messages: nothing can be sent until you upgrade the plan.")
NOT_RETRYABLE = _("This message cannot be sent again: write a new one.")
TEMPLATE_NOT_FOUND = _("There is no template called “%(name)s”.")
TEMPLATE_LANGUAGE = _("That template exists in several languages: say which one.")
TEMPLATE_NOT_APPROVED = _(
    "Meta has not approved the template “%(name)s”: it cannot be sent."
)
TEMPLATE_VARIABLES = _("Fill in every variable of the template (%(count)d).")
TEMPLATE_NOT_SENDABLE = _(
    "This template has a place header, or a header or buttons with something to fill in: send it from WhatsApp "
    "Manager."
)
MARKETING_CONSENT = _("This customer has not agreed to receive marketing by WhatsApp.")

SEND_HEADER_FILE_MISSING = _("Choose the header's file: the template is sent with it.")
NO_HEADER_FILE = _("This template's header has no file.")

NOT_INTERNATIONAL = _(
    "“%(phone)s” is not a number in international format (+34600111222): nothing was sent, so that it never "
    "reaches the wrong person."
)
NO_CONVERSATION = _("There is no WhatsApp conversation with %(phone)s in this business: nothing was sent.")

_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
#: A number exactly in international format: a plus, the country and its digits, nothing else.
_INTERNATIONAL = re.compile(r"\+[1-9]\d{6,14}")


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
        conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
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
        "asks": {
            "en": (
                "reply to Nuria: see you tomorrow at 10",
                "send the reminder template to +34 600 111 222",
                "write to Jorge on WhatsApp that we open at 9",
            ),
            "es": (
                "responde a Nuria: nos vemos mañana a las 10",
                "envía la plantilla de recordatorio al +34 600 111 222",
                "escríbele a Jorge por WhatsApp que abrimos a las 9",
                "responde por WhatsApp a Nuria que su cita sigue en pie",
            ),
        },
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
    sample = _file_to_send(ctx, template, data.template.header_sample) if template else None
    # Somebody of the business answers from the inbox: she waits no more (F20); an automation's notice leaves the mark.
    conversation.needs_attention = False
    return _queue_message(ctx, conversation, data.text, template, variables, data.client_message_id, now, sample)


def _file_to_send(ctx: OperationContext, template: Template, chosen: UUID | None) -> TemplateSample | None:
    """The file a template's photo, video or document header goes with (F33): the one chosen, else the template's own;
    one of this business's kept files of the header's kind. ``None`` for any other header."""
    if template.header_format not in samples.FILE_HEADERS:
        if chosen is not None:
            raise InvalidPayload(str(NO_HEADER_FILE), fields={"header_sample": str(NO_HEADER_FILE)})
        return None
    wanted = chosen or template.header_sample_id
    sample = (
        TemplateSample.objects.filter(pk=wanted, header_format=template.header_format).first()
        if wanted
        else None
    )
    if sample is None:
        raise InvalidPayload(str(SEND_HEADER_FILE_MISSING), fields={"header_sample": str(SEND_HEADER_FILE_MISSING)})
    return sample


def _queue_message(  # noqa: PLR0913, PLR0917
    ctx: OperationContext,
    conversation: Conversation,
    text: str | None,
    template: Template | None,
    variables: list[str],
    key: UUID,
    now: dt.datetime,
    sample: TemplateSample | None = None,
) -> dict:
    """Keep the message ``queued`` in ``conversation`` and hand it to erplora.com after the COMMIT (``deliver``):
    the one way out of the Hub, for the inbox (F32, F33) and for an automation (``notify``)."""
    body = text if template is None else _rendered(template.body, variables)
    try:
        with atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=Message.Direction.OUTBOUND,
                origin=Message.Origin.HUB,
                kind="text" if template is None else "template",
                body=body,
                template_name=template.name if template else "",
                template_language=template.language if template else "",
                template_variables=variables,
                header_sample=sample,
                media_mime_type=sample.content_type if sample else "",
                media_filename=sample.name if sample else "",
                status=Message.Status.QUEUED,
                status_at=now,
                client_message_id=key,
                sent_by=acting_hub_user(ctx),
                sent_at=now,
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
        "asks": {
            "en": (
                "retry the WhatsApp message that didn't go out",
                "resend the failed message to Nuria",
                "that message got stuck, try it again",
            ),
            "es": (
                "reintenta el WhatsApp que no se envió",
                "vuelve a mandar el mensaje fallido a Nuria",
                "ese mensaje se quedó atascado, pruébalo otra vez",
            ),
        },
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


def _exact_number(raw: str, ctx: OperationContext) -> str:
    """``raw`` when it is a number written exactly in international format; ``InvalidPayload`` otherwise (a
    national or half-typed number is never guessed: it could be somebody else's)."""
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
        "asks": {
            "en": (
                "let Nuria know on WhatsApp that her order is ready",
                "notify +34 600 111 222 on WhatsApp that the table is booked",
                "tell Jorge on WhatsApp his appointment moved to Friday",
            ),
            "es": (
                "manda un aviso por WhatsApp a Nuria: ya puede recoger su pedido",
                "notifica al +34 600 111 222 por WhatsApp que tiene la mesa reservada",
                "dile a Jorge por WhatsApp que su cita pasa al viernes",
            ),
        },
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
    sample = _file_to_send(ctx, template, data.template.header_sample) if template else None
    return _queue_message(
        ctx, conversation, data.text if template is None else None, template, variables, key, now, sample
    )
