"""The conversations: how a person names one, how every read and write returns it, the inbox's list
and its figures, and the notices of the customers waiting for an answer."""

import datetime as dt
import re
from uuid import UUID

from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.customer.phones import InvalidPhone, candidates, to_e164
from apps.customer.queries.reads import business_country
from apps.customer.queries.contact import holds, sees_contact
from apps.customer.search import normalize
from apps.whatsapp_inbox import clock
from apps.whatsapp_inbox.models.conversations import Conversation, Message, name_key
from apps.whatsapp_inbox.queries.channel import channel, send_blocked
from apps.whatsapp_inbox.queries.reads import actor_id, live_conversations, page, person_name
from apps.whatsapp_inbox.schemas.conversations import (
    AwaitingCountIn,
    AwaitingCountOut,
    ByPhoneIn,
    ByPhoneOut,
    ConversationDetailOut,
    ConversationListIn,
    ConversationPage,
    NoticesIn,
    NoticesOut,
    SummaryIn,
    SummaryOut,
)
from apps.whatsapp_inbox.schemas.fields import ConversationRefIn
from base.ordering import list_order

CONVERSATION_NOT_FOUND = _("That conversation does not exist in this business.")
NO_CONVERSATION_MATCHES = _("No conversation matches “%(reference)s”.")
SEVERAL_CONVERSATIONS_MATCH = _(
    "Several conversations match “%(reference)s”: give the number."
)

CONVERSATION_NOT_FOUND_CODE = "whatsapp_inbox.conversation_not_found"
CONVERSATION_AMBIGUOUS_CODE = "whatsapp_inbox.conversation_ambiguous"

#: What a phone typed in the search box may hold besides digits.
_PHONE_TEXT = re.compile(r"^[\d\s+().\-/]+$")

#: A customer waiting for an answer (WHATSAPP_INBOX-F09): an open conversation whose last message is the customer's, or
#: that an automatic answer marked «Needs attention» because it could not answer her (F20). The summary, the bell's
#: count and the device's notices read this one definition.
AWAITING_REPLY = Q(status=Conversation.Status.OPEN) & (
    Q(last_message_direction=Message.Direction.INBOUND) | Q(needs_attention=True)
)


def _matching_ids(ctx: OperationContext, reference: str) -> list[UUID]:
    """The live conversations ``reference`` names (at most two: one is enough to answer).

    A number (any format) is compared as a number, for whoever sees the customers' contact details. A name is
    compared as people say it (``name_key``: no case, accents, emoji or extra spaces), to the WhatsApp name and to the
    live card's name.
    """
    text = reference.strip()
    by_number = sees_contact(ctx) and _PHONE_TEXT.match(text)
    numbers = candidates(text, business_country(ctx)) if by_number else set()
    rows = live_conversations()
    if numbers:
        return list(rows.filter(phone__in=numbers).values_list("id", flat=True)[:2])
    wanted = name_key(text)
    if not wanted:
        return []
    found = list(rows.filter(contact_search=wanted).order_by("-last_message_at", "id").values_list("id", flat=True)[:2])
    # Cards: narrowed by the first word in their search text, then compared whole.
    first = wanted.split()[0]
    for conversation_id, name in (
        rows.filter(customer__deleted_at__isnull=True, customer__search_text__startswith=first)
        .order_by("-last_message_at", "id")
        .values_list("id", "customer__name")
    ):
        if name_key(name) == wanted and conversation_id not in found:
            found.append(conversation_id)
        if len(found) > 1:
            break
    return found[:2]


def find_conversation(
    ctx: OperationContext,
    conversation_id: UUID | None,
    reference: str | None = None,
    *,
    lock: bool = False,
    live: bool = True,
) -> Conversation:
    """The conversation ``conversation_id`` names or, without it, the one live conversation ``reference``
    names. ``lock`` locks its row until the end of the command; ``live=False`` also finds an erased one,
    by its id only. ``NotFound`` when there is none, ``Conflict`` when the reference fits several."""
    if conversation_id is None:
        ids = _matching_ids(ctx, reference or "")
        if not ids:
            raise NotFound(
                NO_CONVERSATION_MATCHES % {"reference": reference},
                code=CONVERSATION_NOT_FOUND_CODE,
            )
        if len(ids) > 1:
            raise Conflict(
                SEVERAL_CONVERSATIONS_MATCH % {"reference": reference},
                code=CONVERSATION_AMBIGUOUS_CODE,
            )
        conversation_id = ids[0]
    rows = live_conversations() if live else Conversation.objects.all()
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = (
        rows.select_related("customer", "assigned_to")
        .filter(pk=conversation_id)
        .first()
    )
    if found is None:
        raise NotFound(CONVERSATION_NOT_FOUND, code=CONVERSATION_NOT_FOUND_CODE)
    return found


def masked(phone: str) -> str:
    """``phone`` as whoever does not see the customers' contact details reads it, as the shared inboxes mask it: its
    first three and last four digits, the rest dots («+34611222333» → «+346••••2333»); a short one, only the last four."""
    sign, digits = ("+", phone[1:]) if phone.startswith("+") else ("", phone)
    head = digits[:3] if len(digits) > 7 else ""
    hidden = len(digits) - len(head) - 4
    return f"{sign}{head}{'•' * hidden}{digits[-4:]}" if hidden > 0 else ""


def profile_name(ctx: OperationContext, row: Conversation) -> str:
    """Who writes, without a card: the WhatsApp name, else the number, masked to whoever does not see the customers'
    contact details."""
    return row.contact_name or (row.phone if sees_contact(ctx) else masked(row.phone))


def display_name(ctx: OperationContext, row: Conversation) -> str:
    """Who a conversation is with: the live customer card's name, else who writes (``profile_name``)."""
    card = row.customer if row.customer is not None and row.customer.deleted_at is None else None
    return (card.name if card else "") or profile_name(ctx, row)


def conversation_out(ctx: OperationContext, row: Conversation) -> dict:
    """A conversation as every read and write returns it."""
    card = (
        row.customer
        if row.customer is not None and row.customer.deleted_at is None
        else None
    )
    customer_name = card.name if card else ""
    return {
        "id": row.id,
        "phone": row.phone,
        "contact_name": row.contact_name,
        "display_name": display_name(ctx, row),
        "customer_id": card.id if card else None,
        "customer_name": customer_name,
        "assigned_to_id": row.assigned_to_id,
        "assigned_to_name": person_name(row.assigned_to),
        "status": row.status,
        "unread_count": row.unread_count,
        "last_message_at": row.last_message_at,
        "last_message_preview": row.last_message_preview,
        "last_message_direction": row.last_message_direction,
        "last_message_kind": row.last_message_kind,
        "last_inbound_at": row.last_inbound_at,
        "flagged": row.needs_attention,
        "created_at": row.created_at,
    }


def conversation_detail(ctx: OperationContext, row: Conversation) -> dict:
    blocked = send_blocked(channel(ctx.scope))
    return {
        **conversation_out(ctx, row),
        "window_open": row.window_open(clock.now()),
        "window_expires_at": row.window_expires_at(),
        "can_send": blocked is None,
        "send_blocked": blocked,
    }


def _phone_digits(search: str) -> str:
    """The digits of a typed number without its international or trunk prefix (``00``, ``+``, ``0``)."""
    digits = re.sub(r"\D", "", search)
    if search.strip().startswith("00") or digits.startswith("00"):
        return digits[2:]
    return digits[1:] if digits.startswith("0") else digits


def _searched(ctx: OperationContext, rows, search: str):
    """The conversations whose contact's or card's name holds ``search`` or, for whoever sees the customers' contact
    details, whose number holds the digits typed (or whose card's email or phone holds it)."""
    if not search:
        return rows
    if sees_contact(ctx) and _PHONE_TEXT.match(search) and len(re.sub(r"\D", "", search)) >= 3:
        return rows.filter(phone__contains=_phone_digits(search))
    return rows.filter(
        Q(contact_name__icontains=search)
        | Q(customer__name__icontains=search, customer__deleted_at__isnull=True)
        | (holds(ctx, normalize(search), through="customer__") & Q(customer__deleted_at__isnull=True))
    )


_SORTS = {
    "last_message_at": "last_message_at",
    "contact": "sort_name",
    "status": "status",
    "unread_count": "unread_count",
    "assigned_to": "assigned_to__username",
}


@operation(
    "whatsapp_inbox.conversation.list",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ConversationListIn,
    output=ConversationPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me all the WhatsApp conversations",
                "which chats assigned to me are unread?",
                "list the closed conversations of the inbox",
            ),
            "es": (
                "muéstrame todas las conversaciones de la bandeja",
                "¿qué chats tengo asignados sin leer?",
                "enséñame las conversaciones cerradas de WhatsApp",
            ),
        },
        "description": "Lists the business's WhatsApp conversations, latest activity first: search by the "
        "customer's or profile's name or by the number written any way; filter by status (open, pending, "
        "closed), assignment (me, none, a person) or unread."
    },
)
def list_conversations(ctx: OperationContext, params: ConversationListIn) -> dict:
    rows = _searched(ctx, live_conversations().select_related("customer", "assigned_to"), (params.search or "").strip())
    if params.status:
        rows = rows.filter(status=params.status)
    if params.assigned == "me":
        rows = rows.filter(assigned_to_id=actor_id(ctx))
    elif params.assigned == "none":
        rows = rows.filter(assigned_to__isnull=True)
    elif params.assigned:
        rows = rows.filter(assigned_to_id=UUID(params.assigned))
    if params.unread is True:
        rows = rows.filter(unread_count__gt=0)
    elif params.unread is False:
        rows = rows.filter(unread_count=0)
    if params.customer_id:
        rows = rows.filter(customer_id=params.customer_id)
    # A conversation without a name sorts by its number only for whoever sees it: the order would tell it.
    number = "phone" if sees_contact(ctx) else Value("")
    rows = rows.annotate(
        sort_name=Lower(
            Coalesce(
                NullIf("customer__name", Value("")),
                NullIf("contact_name", Value("")),
                number,
            )
        )
    )
    order = rows.order_by(*list_order(_SORTS[params.sort], descending=params.dir == "desc", nulls_last=True))
    return page(order, params, lambda row: conversation_out(ctx, row))


@operation(
    "whatsapp_inbox.conversation.detail",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ConversationRefIn,
    output=ConversationDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "open Nuria's WhatsApp conversation",
                "who has Jorge's chat and what status is it in?",
                "can I still write freely to Elena or only with a template?",
            ),
            "es": (
                "abre el chat de WhatsApp de Nuria",
                "¿quién lleva la conversación de Jorge y en qué estado está?",
                "¿a Elena todavía le puedo escribir sin plantilla?",
            ),
        },
        "description": "One WhatsApp conversation, named by its id, its number or the customer's name: its "
        "customer card, who has it, its status, and whether a free text can be sent now (within 24 hours of "
        "the customer's last message) or only an approved template."
    },
)
def conversation_get(ctx: OperationContext, data: ConversationRefIn) -> dict:
    return conversation_detail(ctx, find_conversation(ctx, data.id, data.conversation))


@operation(
    "whatsapp_inbox.conversation.by_phone",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ByPhoneIn,
    output=ByPhoneOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is there a WhatsApp chat with +34 600 123 456?",
                "find the live conversation of +44 7700 900123",
                "has +34 622 000 111 written to us on WhatsApp?",
            ),
            "es": (
                "¿tenemos un chat abierto con el +34 600 123 456?",
                "busca la conversación del +34 622 000 111",
                "¿nos ha escrito por WhatsApp el +34 699 555 444?",
            ),
        },
        "description": "The live conversation of an exact international number (+34600111222), or none. A "
        "number not in international format matches nobody: used to tell a customer something by WhatsApp."
    },
)
def conversation_by_phone(ctx: OperationContext, data: ByPhoneIn) -> dict:
    text = data.phone.strip()
    if not re.fullmatch(r"\+[1-9]\d{6,14}", text):
        return {"phone_is_international": False, "phone": "", "conversation_id": None}
    try:
        number = to_e164(text, business_country(ctx))
    except InvalidPhone:
        return {"phone_is_international": False, "phone": "", "conversation_id": None}
    found = (
        live_conversations().filter(phone=number).values_list("id", flat=True).first()
    )
    return {"phone_is_international": True, "phone": number, "conversation_id": found}


@operation(
    "whatsapp_inbox.conversation.summary",
    kind="query",
    permission="whatsapp_inbox.view",
    input=SummaryIn,
    output=SummaryOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how is the WhatsApp inbox doing?",
                "give me a summary of the inbox",
                "give me the inbox figures: open, unread and waiting chats",
            ),
            "es": (
                "¿cómo va la bandeja de WhatsApp?",
                "dame un resumen de la bandeja de entrada",
                "¿cuántos chats hay abiertos, sin leer o esperándonos?",
            ),
        },
        "description": "How the WhatsApp inbox stands: open conversations, those with unread messages, those "
        "waiting for an answer from the business, and whether this month's messages of the plan are spent."
    },
)
def conversation_summary(ctx: OperationContext, data: SummaryIn) -> dict:
    counts = live_conversations().aggregate(
        open=Count("id", filter=Q(status=Conversation.Status.OPEN)),
        unread_conversations=Count("id", filter=Q(unread_count__gt=0)),
        awaiting_reply=Count("id", filter=AWAITING_REPLY),
    )
    row = channel(ctx.scope)
    return {
        **counts,
        "cap_reached": bool(row and row.cap_reached(clock.allowance_month())),
    }


@operation(
    "whatsapp_inbox.conversation.count_awaiting_reply",
    kind="query",
    permission="whatsapp_inbox.view",
    input=AwaitingCountIn,
    output=AwaitingCountOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many WhatsApp conversations are awaiting a reply?",
                "how many chats still need our reply?",
                "count the conversations waiting for an answer",
            ),
            "es": (
                "¿cuántos chats de WhatsApp esperan que les respondamos?",
                "¿a cuánta gente le debemos una respuesta por WhatsApp?",
                "¿cuántas conversaciones siguen sin respuesta?",
            ),
        },
        "description": "How many WhatsApp customers are waiting for an answer from the business: open "
        "conversations whose last message is the customer's."
    },
)
def count_awaiting_reply(ctx: OperationContext, data: AwaitingCountIn) -> dict:
    return {"count": live_conversations().filter(AWAITING_REPLY).count()}


#: How far back the device's notices go when nobody says (the shell tells each one once, as it comes).
NOTICES_WINDOW = dt.timedelta(hours=24)


@operation(
    "whatsapp_inbox.conversation.notices",
    kind="query",
    permission="whatsapp_inbox.view",
    input=NoticesIn,
    output=NoticesOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who has written to us on WhatsApp lately?",
                "any WhatsApp notices from customers waiting?",
                "what did the last people who wrote on WhatsApp say?",
            ),
            "es": (
                "¿quién nos ha escrito últimamente por WhatsApp?",
                "¿hay avisos de WhatsApp de gente esperando?",
                "¿qué dijeron los últimos que escribieron por WhatsApp?",
            ),
        },
        "description": "The WhatsApp customers left waiting for an answer lately, the newest first: who, what she "
        "wrote last and when (each new message of hers is news again)."
    },
)
def notices(ctx: OperationContext, data: NoticesIn) -> dict:
    """Each conversation waiting for an answer whose customer wrote since ``data.since``, by her last message: the
    device tells each (conversation, message instant) once, so a customer writing again is told again."""
    since = data.since or clock.now() - NOTICES_WINDOW
    rows = (
        live_conversations()
        .filter(AWAITING_REPLY, last_inbound_at__gte=since)
        .select_related("customer")
        .order_by("-last_inbound_at", "-id")[: data.limit]
    )
    return {
        "rows": [
            {
                "id": row.id,
                "at": row.last_inbound_at,
                "display_name": display_name(ctx, row),
                "last_message_preview": row.last_message_preview,
            }
            for row in rows
        ]
    }
