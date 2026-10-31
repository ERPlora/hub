"""Read operations of the WhatsApp inbox (``READ ONLY``), and the lookups its commands share.

Every read sees the live conversations only (not erased). A conversation may be named by its id or by
its number (any format) or the name of its customer card or WhatsApp profile (``find_conversation``).
"""

import datetime as dt
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
from apps.whatsapp_inbox import clock, gateway, samples
from apps.whatsapp_inbox.models import (
    FILE_HEADERS,
    Channel,
    Conversation,
    Message,
    Note,
    Template,
    TemplateSample,
    hub_writes,
    name_key,
)
from apps.whatsapp_inbox.schemas import (
    AgentListIn,
    AgentPage,
    AwaitingCountIn,
    AwaitingCountOut,
    ByPhoneIn,
    ByPhoneOut,
    ChannelGetIn,
    ChannelOut,
    ConversationDetailOut,
    ConversationListIn,
    ConversationPage,
    ConversationRefIn,
    MessageGetOut,
    MessageListIn,
    MessagePage,
    MessageRefIn,
    NoteListIn,
    NotePage,
    NoticesIn,
    NoticesOut,
    PageIn,
    SummaryIn,
    SummaryOut,
    TemplateListIn,
    TemplatePage,
    TemplateSampleOut,
    TemplateSampleRefIn,
)
from base.auth import SAAS_PANEL_PATH
from base.models import HubUser, Membership
from base.queries import hub_user_of

CONVERSATION_NOT_FOUND = _("That conversation does not exist in this business.")
NO_CONVERSATION_MATCHES = _("No conversation matches “%(reference)s”.")
SEVERAL_CONVERSATIONS_MATCH = _(
    "Several conversations match “%(reference)s”: give the number."
)

CONVERSATION_NOT_FOUND_CODE = "whatsapp_inbox.conversation_not_found"
CONVERSATION_AMBIGUOUS_CODE = "whatsapp_inbox.conversation_ambiguous"

# Why a hand-over to erplora.com did not end well. A row keeps only the Hub's code (and, for a refusal of Meta's the
# Hub has no name for, Meta's words as they came): the text is said when the row is read, in the reader's language,
# never in the one of whoever wrote it (the worker writes in English).
NOT_CONNECTED = _(
    "WhatsApp is not connected. Connect the business's number in Settings to receive and send messages."
)
CAP_REACHED = _(
    "You have used every WhatsApp message of your plan this month: nothing can be sent until next month "
    "or until you upgrade the plan."
)
SEND_REFUSED = _("erplora.com did not send the message.")
#: Meta's 190, as erplora.com says it (``whatsapp.reconnect_needed``): only connecting the number again fixes it.
RECONNECT_NEEDED = _("WhatsApp's permission for your number expired: connect it again.")
SAAS_UNREACHABLE = _("erplora.com did not answer: the message has not left. Try again.")
SEND_UNKNOWN = _(
    "erplora.com did not confirm the message. Try again: it is never sent twice."
)
CONVERSATION_ERASED = _("The conversation was erased before the message left.")
TEMPLATE_REFUSED = _("Meta did not accept the template.")
META_UNREACHABLE = _("Meta did not answer. Try again in a few minutes.")
META_RATE_LIMITED = _("Meta asks to wait before trying again. Try again in a few minutes.")
TEMPLATE_SAAS_UNREACHABLE = _("erplora.com did not answer: the template has not left. Try again.")
TEMPLATE_UNKNOWN = _("erplora.com did not confirm the template. Try again: it is never registered twice.")
DELETE_SAAS_UNREACHABLE = _("erplora.com did not answer: Meta still has the template. Try again.")
DELETE_UNKNOWN = _("erplora.com did not confirm that Meta deleted the template. Try again.")
#: The Hub's own code of a hand-over that could not take the header's file: it is no longer in the business's store.
HEADER_SAMPLE_MISSING_CODE = "whatsapp_inbox.header_sample_missing"
HEADER_SAMPLE_MISSING = _("The header's file is no longer in the business's files: choose it again with Edit.")
SAMPLE_NOT_FOUND = _("That file is not among the business's files.")
MESSAGE_HEADER_SAMPLE_MISSING = _(
    "The header's file is no longer in the business's files: send the template again choosing its file."
)

SEND_REFUSED_CODE = "whatsapp_inbox.send_refused"
TEMPLATE_REFUSED_CODE = "whatsapp_inbox.template_refused"
SAAS_UNREACHABLE_CODE = "whatsapp_inbox.saas_unreachable"
SEND_UNKNOWN_CODE = "whatsapp_inbox.send_unknown"
#: A message's code → the Hub's words for it.
_MESSAGE_REASONS = {
    "whatsapp_inbox.meta_unreachable": META_UNREACHABLE,
    HEADER_SAMPLE_MISSING_CODE: MESSAGE_HEADER_SAMPLE_MISSING,
    "whatsapp_inbox.cap_reached": CAP_REACHED,
    "whatsapp_inbox.channel_not_connected": NOT_CONNECTED,
    "whatsapp_inbox.reconnect_needed": RECONNECT_NEEDED,
    SAAS_UNREACHABLE_CODE: SAAS_UNREACHABLE,
    SEND_UNKNOWN_CODE: SEND_UNKNOWN,
    "whatsapp_inbox.conversation_erased": CONVERSATION_ERASED,
}
#: A template's code → the Hub's words for it (the same for a hand-over and for a deletion).
_TEMPLATE_REASONS = {
    "whatsapp_inbox.meta_unreachable": META_UNREACHABLE,
    "whatsapp_inbox.meta_rate_limited": META_RATE_LIMITED,
    "whatsapp_inbox.channel_not_connected": NOT_CONNECTED,
    "whatsapp_inbox.reconnect_needed": RECONNECT_NEEDED,
    HEADER_SAMPLE_MISSING_CODE: HEADER_SAMPLE_MISSING,
}

#: What a phone typed in the search box may hold besides digits.
_PHONE_TEXT = re.compile(r"^[\d\s+().\-/]+$")
#: erplora.com's plans (its Store), where the owner upgrades for more WhatsApp messages (ADR-0474: no packs).
PLANS_PATH = f"{SAAS_PANEL_PATH}/store/plans"


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


def person_name(person: HubUser | None) -> str:
    """A person's name as the inbox shows it: their full name, else their username."""
    if person is None:
        return ""
    return (person.name or person.username).strip()


def actor_id(ctx: OperationContext) -> UUID | None:
    """The calling person's id in the business's database (``base.HubUser``), read only; ``None`` for the system, an
    API key, a test's string actor or a person it does not know yet (whom nothing is assigned to)."""
    person = hub_user_of(ctx)
    return None if person is None else person.pk


def preview(body: str, filename: str = "", caption: str = "") -> str:
    """The start of a message as the inbox list shows it: its text, else its caption or file name.

    A message with none of them (a photo, a location) leaves it empty: the inbox names it by its type
    (``last_message_kind``), in the reader's language.
    """
    return (body or caption or filename or "").strip()[:160]


# ── Lookups shared with services.py ─────────────────────────────────────────────────────────────


def live_conversations() -> QuerySet:
    return Conversation.objects.filter(erased_at__isnull=True)


#: A customer waiting for an answer (WHATSAPP_INBOX-F09): an open conversation whose last message is the customer's, or
#: that an automatic answer marked «Needs attention» because it could not answer her (F20). The summary, the bell's
#: count and the device's notices read this one definition.
AWAITING_REPLY = Q(status=Conversation.Status.OPEN) & (
    Q(last_message_direction=Message.Direction.INBOUND) | Q(needs_attention=True)
)
MESSAGE_NOT_FOUND = _("That message no longer exists.")


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


def display_name(row: Conversation) -> str:
    """Who a conversation is with: the live customer card's name, else the WhatsApp name, else the number."""
    card = row.customer if row.customer is not None and row.customer.deleted_at is None else None
    return (card.name if card else "") or row.contact_name or row.phone


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
        "display_name": display_name(row),
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
        **conversation_out(row),
        "window_open": row.window_open(clock.now()),
        "window_expires_at": row.window_expires_at(),
        "can_send": blocked is None,
        "send_blocked": blocked,
    }


def message_reason(row: Message) -> str:
    """Why it did not go well, in the reader's language: the Hub's words for its own codes (a row written before
    the code alone was kept says it so too); a refusal it has no name for, as Meta or erplora.com said it."""
    own = _MESSAGE_REASONS.get(row.error_code)
    if own is not None:
        return str(own)
    if row.error_code == SEND_REFUSED_CODE and not row.error_message:
        return str(SEND_REFUSED)
    return row.error_message


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


def may_delete_note(ctx: OperationContext, note: Note, me: UUID | None) -> bool:
    """The author deletes their own note; whoever may assign deletes anybody's. ``me`` is the caller's person
    (:func:`actor_id`), read once by whoever asks about several notes."""
    mine = note.author_id is not None and note.author_id == me
    return mine or ctx.has("whatsapp_inbox.assign")


def note_out(ctx: OperationContext, row: Note, me: UUID | None) -> dict:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "text": row.text,
        "author_id": row.author_id,
        "author_name": row.author_name,
        "created_at": row.created_at,
        "can_delete": may_delete_note(ctx, row, me),
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
        rows = rows.filter(assigned_to_id=UUID(params.assigned))
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
        awaiting_reply=Count("id", filter=AWAITING_REPLY),
    )
    row = channel(ctx.scope)
    return {
        **counts,
        "cap_reached": bool(row and row.cap_reached(clock.business_month())),
    }


@operation(
    "whatsapp_inbox.conversation.count_awaiting_reply",
    kind="query",
    permission="whatsapp_inbox.view",
    input=AwaitingCountIn,
    output=AwaitingCountOut,
    expose_api=True,
    ai={
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
                "display_name": display_name(row),
                "last_message_preview": row.last_message_preview,
            }
            for row in rows
        ]
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
    "whatsapp_inbox.message.get",
    kind="query",
    permission="whatsapp_inbox.view",
    input=MessageRefIn,
    output=MessageGetOut,
    expose_api=True,
    ai={
        "description": "One WhatsApp message by its id (the one an automation started on): what it says, who said it "
        "and when, its conversation's exact international number, what to call the customer and whether anything "
        "can be sent now."
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
        "display_name": display_name(row.conversation),
        "can_send": send_blocked(channel(ctx.scope)) is None,
    }


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
    me = actor_id(ctx)
    return page(rows, params, lambda note: note_out(ctx, note, me))


# ── Templates, channel and team ─────────────────────────────────────────────────────────────────


def templates_of(scope: Scope) -> QuerySet:
    """The templates of the business of ``scope`` (phase 1: its host), and only those."""
    return Template.objects.filter(host=scope.key)


def templates_of_every_business() -> QuerySet:
    """Every business's templates, only for the worker's ``delivery.resume``: phase 1 runs it on one fixed scope
    (``WORKER_SCOPE_SLUG``) over the shared table, and it hands each template over as its own business (``host``);
    phase 2 runs it in each hub's database, which holds that hub's alone."""
    return Template.objects.all()


def live_templates(scope: Scope) -> QuerySet:
    """The business's templates not deleted here."""
    return templates_of(scope).filter(deleted_at__isnull=True)


def listed_templates(scope: Scope) -> QuerySet:
    """What Settings lists: the business's live templates and the ones deleted here that Meta has not deleted yet."""
    return templates_of(scope).filter(
        Q(deleted_at__isnull=True) | Q(delete_state=Template.DeleteState.PENDING)
    )


def template_editable(row: Template) -> bool:
    """Whether the Hub may change it now: content it writes (``hub_writes``: what it sends, or a file header chosen
    here), not under Meta's review, not gone."""
    return (
        hub_writes(row)
        and row.deleted_at is None
        and row.status not in (Template.Status.PENDING, Template.Status.DISABLED, Template.Status.DELETED)
    )


def template_fillable(row: Template) -> bool:
    """Whether the inbox can send it now (F33): approved and filled by the Hub, a file header with a file chosen."""
    return row.supported and row.deleted_at is None and row.status == Template.Status.APPROVED


def template_sendable(row: Template) -> bool:
    """Whether it goes as it is, with nothing to choose: a file header only with its own file (an automation's)."""
    return template_fillable(row) and (row.header_format not in FILE_HEADERS or row.header_sample_id is not None)


#: The approved templates the Hub fills (``template_fillable``), and those that go as they are (``template_sendable``).
_FILLABLE = Q(status=Template.Status.APPROVED, supported=True, deleted_at__isnull=True)
_SENDABLE = _FILLABLE & ~Q(header_format__in=FILE_HEADERS, header_sample__isnull=True)


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


def template_reason(row: Template) -> str:
    """Why its last hand-over or deletion did not end well, in the reader's language (as ``message_reason``); with
    no answer, the deletion's words while it is being deleted and the hand-over's otherwise."""
    code = row.submit_error_code
    own = _TEMPLATE_REASONS.get(code)
    if own is not None:
        return str(own)
    deleting = row.delete_state == Template.DeleteState.PENDING
    if code == SAAS_UNREACHABLE_CODE:
        return str(DELETE_SAAS_UNREACHABLE if deleting else TEMPLATE_SAAS_UNREACHABLE)
    if code == SEND_UNKNOWN_CODE:
        return str(DELETE_UNKNOWN if deleting else TEMPLATE_UNKNOWN)
    if code == TEMPLATE_REFUSED_CODE and not row.submit_error:
        return str(TEMPLATE_REFUSED)
    return row.submit_error


def sample_out(sample: TemplateSample | None) -> dict | None:
    if sample is None:
        return None
    return {
        "id": sample.id,
        "header_format": sample.header_format,
        "content_type": sample.content_type,
        "size": sample.size,
        "name": sample.name,
        "url": samples.sample_url(sample.key),
    }


def _its_own(row: Template) -> TemplateSample | None:
    """The template's header file, only if it is its business's (phase 1 shares the tables)."""
    sample = row.header_sample
    return sample if sample is not None and sample.host == row.host else None


def _draft_out(row: Template) -> dict | None:
    draft = row.draft
    if not draft:
        return None
    sample = draft.get("header_sample")
    kept = TemplateSample.objects.filter(pk=sample, host=row.host).first() if sample else None
    return {
        **draft,
        "header_format": draft.get("header_format", "TEXT" if draft.get("header") else ""),
        "header_sample": sample_out(kept),
        "buttons": _buttons_out(draft.get("buttons")),
    }


def template_out(row: Template) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "header_format": row.header_format,
        "header": row.header,
        "header_sample": sample_out(_its_own(row)),
        "body": row.body,
        "body_examples": list(row.body_examples or []),
        "footer": row.footer,
        "buttons": _buttons_out(row.buttons),
        "variables": row.variables,
        "rejected_reason": row.rejected_reason,
        "meta_id": row.meta_id,
        "synced_at": row.synced_at,
        "draft": _draft_out(row),
        "submit_state": row.submit_state,
        "submit_error_code": row.submit_error_code,
        "submit_error": template_reason(row),
        "editable": template_editable(row),
        "sendable": template_sendable(row),
        "supported": row.supported,
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
    rows = listed_templates(ctx.scope).select_related("header_sample")
    if params.search:
        rows = rows.filter(name__icontains=params.search.strip())
    for field in ("status", "category", "language"):
        value = getattr(params, field)
        if value:
            rows = rows.filter(**{field: value})
    if params.sendable is not None:
        rows = rows.filter(_SENDABLE if params.sendable else ~_SENDABLE)
    if params.fillable is not None:
        rows = rows.filter(_FILLABLE if params.fillable else ~_FILLABLE)
    return page(rows.order_by("name", "language", "id"), params, template_out)


@operation(
    "whatsapp_inbox.template_sample.detail",
    kind="query",
    # Whoever sends chooses the file (F33), so whoever sends reads it: the assistant's card names it by this read.
    permission="whatsapp_inbox.reply",
    input=TemplateSampleRefIn,
    output=TemplateSampleOut,
    expose_api=True,
    ai={
        "description": "One file of a WhatsApp template's header by its id (the one whatsapp_inbox.template_sample."
        "upload answered): its name, whether it is a photo, a video or a document, and its size."
    },
)
def template_sample_detail(ctx: OperationContext, data: TemplateSampleRefIn) -> dict:
    """F29, F33: a header's file as its upload answered it, only of the business that asks (phase 1 shares the
    tables, as ``Template``)."""
    sample = TemplateSample.objects.filter(pk=data.id, host=ctx.scope.key).first()
    if sample is None:
        raise NotFound(str(SAMPLE_NOT_FOUND), code="whatsapp_inbox.sample_not_found")
    return sample_out(sample)


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
        "plans_url": plans_url(),
    }


def plans_url() -> str:
    """erplora.com's plans, where more WhatsApp messages are bought by upgrading; empty without erplora.com."""
    saas = str(getattr(settings, "SAAS_URL", "") or "").rstrip("/")
    return f"{saas}{PLANS_PATH}" if saas else ""


def team_roles(ctx: OperationContext) -> dict[str, str]:
    """``{username: role}`` of whoever has access to this business: control's memberships of the scope's host, read
    first (a query never joins two databases)."""
    return dict(
        Membership.objects.filter(host=ctx.scope.key, user__is_active=True).values_list("user__username", "role")
    )


def team(ctx: OperationContext, roles: dict[str, str] | None = None) -> QuerySet[HubUser]:
    """The people of this business in its own database (``base.HubUser``) who are still in it and have access to it."""
    return HubUser.objects.filter(username__in=list(team_roles(ctx) if roles is None else roles), is_active=True)


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
    roles = team_roles(ctx)
    rows = team(ctx, roles)
    if params.search:
        text = params.search.strip()
        rows = rows.filter(Q(name__icontains=text) | Q(username__icontains=text) | Q(email__icontains=text))
    rows = rows.order_by("name", "username", "id")
    return page(
        rows,
        params,
        lambda person: {"id": person.pk, "name": person_name(person), "role": roles[person.username]},
    )
