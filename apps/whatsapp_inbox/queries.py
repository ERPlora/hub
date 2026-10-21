"""Read operations of the WhatsApp inbox (``READ ONLY``), and the lookups its commands share.

Every read sees the live conversations only (not erased). A conversation may be named by its id or by
its number (any format) or the name of its customer card or WhatsApp profile (``find_conversation``).
"""

import re
from uuid import UUID

from django.conf import settings
from django.db.models import Count, F, Q, QuerySet, Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.customer.phones import DEFAULT_COUNTRY, InvalidPhone, candidates, to_e164
from apps.customer.search import normalize
from apps.whatsapp_inbox import clock, gateway
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template, name_key
from apps.whatsapp_inbox.schemas import (
    AgentListIn,
    AgentPage,
    ByPhoneIn,
    ByPhoneOut,
    ChannelGetIn,
    ChannelOut,
    ConversationDetailOut,
    ConversationListIn,
    ConversationPage,
    ConversationRefIn,
    MessageListIn,
    MessagePage,
    NoteListIn,
    NotePage,
    PageIn,
    SummaryIn,
    SummaryOut,
    TemplateListIn,
    TemplatePage,
)
from base.models import Membership

CONVERSATION_NOT_FOUND = _("That conversation does not exist in this business.")
NO_CONVERSATION_MATCHES = _("No conversation matches “%(reference)s”.")
SEVERAL_CONVERSATIONS_MATCH = _(
    "Several conversations match “%(reference)s”: give the number."
)

CONVERSATION_NOT_FOUND_CODE = "whatsapp_inbox.conversation_not_found"
CONVERSATION_AMBIGUOUS_CODE = "whatsapp_inbox.conversation_ambiguous"

#: What a phone typed in the search box may hold besides digits.
_PHONE_TEXT = re.compile(r"^[\d\s+().\-/]+$")


def business_country(ctx: OperationContext | None = None) -> str:
    """The country a number without prefix belongs to. Phase 1 has no settings per business: Spain."""
    return DEFAULT_COUNTRY


def e164(raw: str, ctx: OperationContext | None = None, *, from_whatsapp: bool = False) -> str:
    """``raw`` as the conversation's key (E.164). WhatsApp's bare digits are international; a number a
    person typed is national unless it says its country (gh:whatsapp_inbox#279: ``600222333`` is Spain's,
    never +60's).

    Raises ``InvalidPhone`` when it is no number.
    """
    text = (raw or "").strip()
    if from_whatsapp and text.isdigit() and not text.startswith("0"):
        text = f"+{text}"
    number = to_e164(text, business_country(ctx))
    if not number:
        raise InvalidPhone(raw)
    return number


def person_name(user) -> str:
    """A person's name as the inbox shows it: their full name, else their username."""
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username()).strip()


def actor_id(ctx: OperationContext) -> int | None:
    """The calling person's id; ``None`` for the system or a test's string actor."""
    pk = getattr(ctx.actor, "pk", None)
    return pk if isinstance(pk, int) else None


def preview(body: str, filename: str = "", caption: str = "") -> str:
    """The start of a message as the inbox list shows it: its text, else its caption or file name.

    A message with none of them (a photo, a location) leaves it empty: the inbox names it by its type
    (``last_message_kind``), in the reader's language.
    """
    return (body or caption or filename or "").strip()[:160]


# ── Lookups shared with services.py ─────────────────────────────────────────────────────────────


def live_conversations() -> QuerySet:
    return Conversation.objects.filter(erased_at__isnull=True)


def _matching_ids(reference: str) -> list[UUID]:
    """The live conversations ``reference`` names (at most two: one is enough to answer).

    A number (any format) is compared as a number. A name is compared as people say it (``name_key``:
    no case, accents, emoji or extra spaces), to the WhatsApp name and to the live card's name.
    """
    text = reference.strip()
    numbers = candidates(text, business_country()) if _PHONE_TEXT.match(text) else set()
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
        ids = _matching_ids(reference or "")
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


def channel(scope: Scope) -> Channel | None:
    """The number of the business of ``scope`` (phase 1: its host), or ``None`` before erplora.com spoke of it."""
    return Channel.objects.filter(host=scope.key).first()


def send_blocked(row: Channel | None) -> str | None:
    """Why nothing can be sent now: no connected number, no SaaS to send through, the month spent."""
    if row is None or row.status != Channel.Status.CONNECTED:
        return "not_connected"
    if not gateway.configured():
        return "unconfigured"
    if row.cap_reached(clock.business_month()):
        return "cap_reached"
    return None


def conversation_out(row: Conversation) -> dict:
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
        "display_name": customer_name or row.contact_name or row.phone,
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
        "created_at": row.created_at,
    }


def conversation_detail(ctx: OperationContext, row: Conversation) -> dict:
    blocked = send_blocked(channel(ctx.scope))
    return {
        **conversation_out(row),
        "window_open": row.window_open(clock.now()),
        "window_expires_at": row.window_expires_at(),
        "can_send": blocked is None,
        "send_blocked": blocked,
    }


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
        "error_message": row.error_message,
        "wa_message_id": row.wa_message_id,
        "reply_to": row.reply_to,
        "reply_id": row.reply_id,
        "sent_by_name": person_name(row.sent_by),
        "sent_at": row.sent_at,
        "status_at": row.status_at,
    }


def may_delete_note(ctx: OperationContext, note: Note) -> bool:
    """The author deletes their own note; whoever may assign deletes anybody's."""
    mine = note.author_id is not None and note.author_id == actor_id(ctx)
    return mine or ctx.has("whatsapp_inbox.assign")


def note_out(ctx: OperationContext, row: Note) -> dict:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "text": row.text,
        "author_id": row.author_id,
        "author_name": row.author_name,
        "created_at": row.created_at,
        "can_delete": may_delete_note(ctx, row),
    }


def page(rows: QuerySet, params: PageIn, convert=None) -> dict:
    """One page of ``rows`` (already ordered with the id as the tie-break) and how many there are."""
    found = list(rows[params.offset : params.offset + params.limit])
    return {
        "rows": [convert(row) for row in found] if convert else found,
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _phone_digits(search: str) -> str:
    """The digits of a typed number without its international or trunk prefix (``00``, ``+``, ``0``)."""
    digits = re.sub(r"\D", "", search)
    if search.strip().startswith("00") or digits.startswith("00"):
        return digits[2:]
    return digits[1:] if digits.startswith("0") else digits


# ── Conversations ───────────────────────────────────────────────────────────────────────────────

_SORTS = {
    "last_message_at": "last_message_at",
    "contact": "sort_name",
    "phone": "phone",
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
        "description": "Lists the business's WhatsApp conversations, latest activity first: search by the "
        "customer's or profile's name or by the number written any way; filter by status (open, pending, "
        "closed), assignment (me, none, a person) or unread."
    },
)
def list_conversations(ctx: OperationContext, params: ConversationListIn) -> dict:
    rows = live_conversations().select_related("customer", "assigned_to")
    search = (params.search or "").strip()
    if search:
        if _PHONE_TEXT.match(search) and len(re.sub(r"\D", "", search)) >= 3:
            rows = rows.filter(phone__contains=_phone_digits(search))
        else:
            rows = rows.filter(
                Q(contact_name__icontains=search)
                | Q(customer__name__icontains=search, customer__deleted_at__isnull=True)
                | Q(
                    customer__search_text__contains=normalize(search),
                    customer__deleted_at__isnull=True,
                )
            )
    if params.status:
        rows = rows.filter(status=params.status)
    if params.assigned == "me":
        rows = rows.filter(assigned_to_id=actor_id(ctx))
    elif params.assigned == "none":
        rows = rows.filter(assigned_to__isnull=True)
    elif params.assigned:
        rows = rows.filter(assigned_to_id=int(params.assigned))
    if params.unread is True:
        rows = rows.filter(unread_count__gt=0)
    elif params.unread is False:
        rows = rows.filter(unread_count=0)
    if params.customer_id:
        rows = rows.filter(customer_id=params.customer_id)
    rows = rows.annotate(
        sort_name=Lower(
            Coalesce(
                NullIf("customer__name", Value("")),
                NullIf("contact_name", Value("")),
                "phone",
            )
        )
    )
    column = _SORTS[params.sort]
    descending = params.dir == "desc"
    expression = F(column).desc(nulls_last=True) if descending else F(column).asc(nulls_last=True)
    order = rows.order_by(expression, "-id" if descending else "id")
    return page(order, params, conversation_out)


@operation(
    "whatsapp_inbox.conversation.detail",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ConversationRefIn,
    output=ConversationDetailOut,
    expose_api=True,
    ai={
        "description": "One WhatsApp conversation, named by its id, its number or the customer's name: its "
        "customer card, who has it, its status, and whether a free text can be sent now (within 24 hours of "
        "the customer's last message) or only an approved template."
    },
)
def conversation_get(ctx: OperationContext, data: ConversationRefIn) -> dict:
    return conversation_detail(ctx, find_conversation(data.id, data.conversation))


@operation(
    "whatsapp_inbox.conversation.by_phone",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ByPhoneIn,
    output=ByPhoneOut,
    expose_api=True,
    ai={
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
        "description": "How the WhatsApp inbox stands: open conversations, those with unread messages, those "
        "waiting for an answer from the business, and whether this month's messages of the plan are spent."
    },
)
def conversation_summary(ctx: OperationContext, data: SummaryIn) -> dict:
    counts = live_conversations().aggregate(
        open=Count("id", filter=Q(status=Conversation.Status.OPEN)),
        unread_conversations=Count("id", filter=Q(unread_count__gt=0)),
        awaiting_reply=Count(
            "id",
            filter=Q(
                status=Conversation.Status.OPEN,
                last_message_direction=Message.Direction.INBOUND,
            ),
        ),
    )
    row = channel(ctx.scope)
    return {
        **counts,
        "cap_reached": bool(row and row.cap_reached(clock.business_month())),
    }


# ── Thread and notes ────────────────────────────────────────────────────────────────────────────


@operation(
    "whatsapp_inbox.message.list",
    kind="query",
    permission="whatsapp_inbox.view",
    input=MessageListIn,
    output=MessagePage,
    expose_api=True,
    ai={
        "description": "The messages of a WhatsApp conversation (named by its id, number or customer's name), "
        "newest first: who said what and when, attachments, and whether each one sent was delivered and read."
    },
)
def list_messages(ctx: OperationContext, params: MessageListIn) -> dict:
    conversation = find_conversation(params.id, params.conversation)
    rows = (
        Message.objects.filter(conversation=conversation)
        .select_related("sent_by")
        .order_by("-sent_at", "-id")
    )
    return page(rows, params, message_out)


@operation(
    "whatsapp_inbox.note.list",
    kind="query",
    permission="whatsapp_inbox.view",
    input=NoteListIn,
    output=NotePage,
    expose_api=True,
    ai={
        "description": "The internal notes of a WhatsApp conversation, newest first: what the team wrote about it."
    },
)
def list_notes(ctx: OperationContext, params: NoteListIn) -> dict:
    conversation = find_conversation(params.id, params.conversation)
    rows = Note.objects.filter(conversation=conversation).order_by("-created_at", "-id")
    return page(rows, params, lambda note: note_out(ctx, note))


# ── Templates, channel and team ─────────────────────────────────────────────────────────────────


def templates_of(scope: Scope) -> QuerySet:
    """The templates of the business of ``scope`` (phase 1: its host), and only those."""
    return Template.objects.filter(host=scope.key)


def live_templates(scope: Scope) -> QuerySet:
    """The business's templates not deleted here."""
    return templates_of(scope).filter(deleted_at__isnull=True)


def listed_templates(scope: Scope) -> QuerySet:
    """What Settings lists: the business's live templates and the ones deleted here that Meta has not deleted yet."""
    return templates_of(scope).filter(
        Q(deleted_at__isnull=True) | Q(delete_state=Template.DeleteState.PENDING)
    )


def template_editable(row: Template) -> bool:
    """Whether the Hub may change it now: content it handles, not under Meta's review, not gone."""
    return (
        row.supported
        and row.deleted_at is None
        and row.status not in (Template.Status.PENDING, Template.Status.DISABLED, Template.Status.DELETED)
    )


def template_sendable(row: Template) -> bool:
    return row.supported and row.deleted_at is None and row.status == Template.Status.APPROVED


def _buttons_out(buttons) -> list[dict]:
    return [
        {
            "type": str(button.get("type", "")),
            "text": str(button.get("text", "")),
            "url": str(button.get("url", "") or ""),
            "phone_number": str(button.get("phone_number", "") or ""),
        }
        for button in buttons or []
        if isinstance(button, dict)
    ]


def template_out(row: Template) -> dict:
    draft = row.draft
    return {
        "id": row.id,
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "header_format": row.header_format,
        "header": row.header,
        "body": row.body,
        "body_examples": list(row.body_examples or []),
        "footer": row.footer,
        "buttons": _buttons_out(row.buttons),
        "variables": row.variables,
        "rejected_reason": row.rejected_reason,
        "meta_id": row.meta_id,
        "synced_at": row.synced_at,
        "draft": {**draft, "buttons": _buttons_out(draft.get("buttons"))} if draft else None,
        "submit_state": row.submit_state,
        "submit_error_code": row.submit_error_code,
        "submit_error": row.submit_error,
        "editable": template_editable(row),
        "sendable": template_sendable(row),
        "deleting": row.delete_state == Template.DeleteState.PENDING,
    }


@operation(
    "whatsapp_inbox.template.list",
    kind="query",
    permission="whatsapp_inbox.reply",
    input=TemplateListIn,
    output=TemplatePage,
    expose_api=True,
    ai={
        "description": "The business's WhatsApp message templates as Meta judged them (APPROVED ones can be "
        "sent), with their text and how many variables they take; search by name."
    },
)
def list_templates(ctx: OperationContext, params: TemplateListIn) -> dict:
    rows = listed_templates(ctx.scope)
    if params.search:
        rows = rows.filter(name__icontains=params.search.strip())
    for field in ("status", "category", "language"):
        value = getattr(params, field)
        if value:
            rows = rows.filter(**{field: value})
    if params.sendable is not None:
        sendable = Q(status=Template.Status.APPROVED, supported=True, deleted_at__isnull=True)
        rows = rows.filter(sendable if params.sendable else ~sendable)
    return page(rows.order_by("name", "language", "id"), params, template_out)


@operation(
    "whatsapp_inbox.channel.get",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ChannelGetIn,
    output=ChannelOut,
    expose_api=True,
    ai={
        "description": "The business's WhatsApp number as erplora.com reports it (connected or not) and the "
        "messages sent this month against the plan's allowance."
    },
)
def channel_get(ctx: OperationContext, data: ChannelGetIn) -> dict:
    row = channel(ctx.scope) or Channel(host=ctx.scope.key)
    month = clock.business_month()
    return {
        "status": row.status,
        "phone_number": row.phone_number,
        "display_name": row.display_name,
        "monthly_limit": row.monthly_limit,
        "monthly_usage": row.monthly_usage if row.usage_month == month else 0,
        "cap_reached": row.cap_reached(month),
        "synced_at": row.synced_at,
        "manage_url": str(getattr(settings, "SAAS_URL", "") or ""),
    }


def team(ctx: OperationContext) -> QuerySet:
    """The memberships of the people of this business (phase 1: the host's)."""
    return Membership.objects.filter(
        host=ctx.scope.key, user__is_active=True
    ).select_related("user")


@operation(
    "whatsapp_inbox.agent.list",
    kind="query",
    permission="whatsapp_inbox.reply",
    input=AgentListIn,
    output=AgentPage,
    ai={
        "description": "The people of the business a WhatsApp conversation can be assigned to; search by name."
    },
)
def list_agents(ctx: OperationContext, params: AgentListIn) -> dict:
    rows = team(ctx)
    if params.search:
        text = params.search.strip()
        rows = rows.filter(
            Q(user__first_name__icontains=text)
            | Q(user__last_name__icontains=text)
            | Q(user__username__icontains=text)
            | Q(user__email__icontains=text)
        )
    rows = rows.order_by("user__first_name", "user__last_name", "user__username", "id")
    return page(
        rows,
        params,
        lambda m: {"id": m.user_id, "name": person_name(m.user), "role": m.role},
    )
