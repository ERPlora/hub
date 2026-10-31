"""Input and output schemas of the WhatsApp inbox's operations (OpenAPI, live params, 422 per field).

Every field has a description: these schemas are also the JSON Schema of the assistant's tools and the
contract of erplora.com's doors (WORKBOOK «Contrato con el SaaS»). A conversation can be named by its
``id`` or, when the id is not known (by voice, by text), by its number or by the customer's name
(``conversation``); a person of the team by their id or their name, username or email.
"""

import re
from datetime import datetime
from urllib.parse import urlsplit
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from apps.whatsapp_inbox.models import NAMED_VARIABLE
from base.schemas import names

T = TypeVar("T")

WHICH_CONVERSATION = _(
    "Say which conversation: its id, its number or the customer's name."
)
TEXT_OR_TEMPLATE = _("Write a message or choose a template.")
ONE_ASSIGNEE = _("Choose one person, yourself («me») or nobody.")
ONE_CUSTOMER = _("Choose a customer card, create one or unlink it.")
UNKNOWN_ASSIGNED = _("Choose «me», «none» or a person's id.")
NOT_ERPLORA = _("An attachment must come from erplora.com over https.")
TEMPLATE_NAME_RULE = _("Use lowercase letters, numbers and underscores only.")
TEMPLATE_LANGUAGE_RULE = _("Choose the template's language.")
TEMPLATE_NUMBERING = _("Number the variables 1, 2, 3… in order, without skipping any.")
TEMPLATE_EXAMPLES = _("Write an example for each variable.")
TEMPLATE_NO_VARIABLES = _("The header and the footer cannot have variables.")
TEMPLATE_FILE_NO_TEXT = _("A header with a photo, a video or a document has no text.")
BUTTON_URL = _("A link button needs an https:// address without variables.")
BUTTON_PHONE = _("A call button needs a number with its country code (+34…).")
BUTTON_KINDS = _("At most 2 link buttons and 1 call button.")
BUTTONS_GROUPED = _("Put the quick replies together, before or after the link and call buttons.")

#: An international number as WhatsApp gives it (``34600111222``) or E.164 (``+34600111222``).
INTERNATIONAL = r"^\+?[1-9]\d{6,14}$"
#: E.164 or nothing (the business's own number before it is connected).
E164_OR_EMPTY = r"^(\+[1-9]\d{6,14})?$"


def _text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


Reference = _text(200)
ConversationStatus = Literal["open", "pending", "closed"]
TemplateCategory = Literal["UTILITY", "MARKETING", "AUTHENTICATION"]
#: What the Hub makes: an authentication template needs Meta's code button, made in WhatsApp Manager.
WritableCategory = Literal["UTILITY", "MARKETING"]
TemplateStatus = Literal[
    "DRAFT", "APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "DELETED"
]
#: Meta's verdicts erplora.com reports (``DRAFT`` is the Hub's own: Meta never had it).
MetaTemplateStatus = Literal["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "DELETED"]
HeaderFormat = Literal["", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION"]
#: What the form writes: none or a text (derived from ``header`` when empty), or a photo, a video or a document.
WritableHeaderFormat = Literal["", "TEXT", "IMAGE", "VIDEO", "DOCUMENT"]
#: The headers with a file.
FileHeaderFormat = Literal["IMAGE", "VIDEO", "DOCUMENT"]
FILE_HEADER_FORMATS = ("IMAGE", "VIDEO", "DOCUMENT")
SubmitState = Literal["", "queued", "sending", "failed"]
SortDir = Literal["asc", "desc"]

CONVERSATION_REFERENCE = (
    "The conversation's number (any format: +34 600 111 222, 600111222) or the name of the customer or "
    "of their WhatsApp profile, when the id is not known."
)

# The assistant's card names a template header's file by this read (base/assistant.py ``REFERS``), run as whoever
# asks, never by its id: by the name it was chosen with, as the template's sheet shows it. Whoever sends reads it.
A_SAMPLE = names("whatsapp_inbox.template_sample.detail")


# ── Pages: every list is paginated, limit ≤ 100 ─────────────────────────────────────────────────


class PageIn(Schema):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return, at most 100."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped.")


# ── References ──────────────────────────────────────────────────────────────────────────────────


class ConversationRefIn(Schema):
    """A conversation by its ``id`` or by its number or customer's name (``conversation``); the id wins."""

    id: UUID | None = Field(None, description="The conversation's id.")
    conversation: Reference | None = Field(
        None, validate_default=True, description=CONVERSATION_REFERENCE
    )

    @field_validator("conversation")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("id") is None and _blank(value):
            raise ValueError(WHICH_CONVERSATION)
        return value


class ConversationPageIn(ConversationRefIn, PageIn):
    pass


# ── Conversations ───────────────────────────────────────────────────────────────────────────────


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


class ConversationListIn(PageIn):
    search: _text(120) | None = Field(
        None,
        description="Part of the contact's or customer's name, or of the number written in any format "
        "(600 111, +34 600 111 222, 0034600111222).",
    )
    status: ConversationStatus | None = Field(
        None, description="Only open, pending or closed conversations."
    )
    assigned: _text(40) | None = Field(
        None,
        description="«me» (assigned to the caller), «none» (nobody) or a person's id.",
    )
    unread: bool | None = Field(
        None, description="True: only those with unread messages."
    )
    customer_id: UUID | None = Field(
        None, description="Only the conversations of this customer card."
    )
    sort: Literal[
        "last_message_at", "contact", "phone", "status", "unread_count", "assigned_to"
    ] = Field(
        "last_message_at",
        description="Column to sort by; the latest activity by default.",
    )
    dir: SortDir = Field("desc", description="Sort direction.")

    @field_validator("assigned")
    @classmethod
    def _assigned(cls, value: str | None) -> str | None:
        if value is None or value in ("me", "none") or _is_uuid(value):
            return value
        raise ValueError(UNKNOWN_ASSIGNED)


class ConversationOut(Schema):
    id: UUID = Field(description="The conversation's id.")
    phone: str = Field(
        description="The customer's number, international format (empty once erased)."
    )
    contact_name: str = Field(
        description="The name of the customer's WhatsApp profile."
    )
    display_name: str = Field(
        description="What the inbox calls it: the card's name, the profile's or the number."
    )
    customer_id: UUID | None = Field(description="The customer card it is joined to.")
    customer_name: str = Field(description="That card's name.")
    assigned_to_id: UUID | None = Field(description="The person it is assigned to.")
    assigned_to_name: str = Field(description="That person's name.")
    status: ConversationStatus = Field(
        description="open, pending (waiting for the customer) or closed."
    )
    unread_count: int = Field(
        description="Messages from the customer nobody has read yet."
    )
    last_message_at: datetime | None = Field(
        description="When the last message was said."
    )
    last_message_preview: str = Field(description="The start of the last message.")
    last_message_direction: str = Field(
        description="inbound (customer) or outbound (business)."
    )
    last_message_kind: str = Field(description="Meta's type of the last message (text, image, location…).")
    last_inbound_at: datetime | None = Field(
        description="The customer's last message: the 24-hour window runs from it."
    )
    flagged: bool = Field(
        False,
        description="«Needs attention»: an automatic answer could not answer the customer, so she waits for a person "
        "until somebody answers or its status changes.",
    )
    created_at: datetime = Field(description="When the customer first wrote.")


class ConversationPage(Page[ConversationOut]):
    pass


class ConversationDetailOut(ConversationOut):
    window_open: bool = Field(
        description="Whether free text may be sent now (24 hours from the customer's last message)."
    )
    window_expires_at: datetime | None = Field(
        description="When the 24-hour window closes."
    )
    can_send: bool = Field(
        description="Whether the business can send now (number connected, allowance left)."
    )
    send_blocked: Literal["not_connected", "cap_reached", "unconfigured"] | None = (
        Field(description="Why nothing can be sent now, if so.")
    )


class ByPhoneIn(Schema):
    phone: _text(32, 1) = Field(
        description="The exact number, international format (+34600111222)."
    )


class ByPhoneOut(Schema):
    phone_is_international: bool = Field(
        description="Whether the number was in international format."
    )
    phone: str = Field(
        description="The number as compared (E.164), empty when it was not one."
    )
    conversation_id: UUID | None = Field(
        description="Its live conversation in this business, if any."
    )


class SummaryIn(Schema):
    pass


class SummaryOut(Schema):
    open: int = Field(description="Open conversations.")
    unread_conversations: int = Field(description="Conversations with unread messages.")
    awaiting_reply: int = Field(
        description="Open conversations whose last message is the customer's."
    )
    cap_reached: bool = Field(
        description="Whether this month's messages of the plan are spent (always when it includes none)."
    )


class AwaitingCountIn(Schema):
    pass


class AwaitingCountOut(Schema):
    count: int = Field(
        description="Open conversations whose last message is the customer's: customers waiting for an answer."
    )


class NoticesIn(Schema):
    since: datetime | None = Field(
        None, description="Only the customers who wrote from this instant on; empty = the last 24 hours."
    )
    limit: int = Field(20, ge=1, le=100, description="How many, the newest first (1 to 100).")


class NoticeOut(Schema):
    id: UUID = Field(description="The conversation's id.")
    at: datetime = Field(description="When the customer wrote her last message, still unanswered.")
    display_name: str = Field(description="Who: the customer card's name, else her WhatsApp name, else her number.")
    last_message_preview: str = Field(
        description="What she wrote last (empty for a photo or a location without a caption)."
    )


class NoticesOut(Schema):
    rows: list[NoticeOut] = Field(description="The customers left waiting for an answer, the newest first.")


class AssignIn(ConversationRefIn):
    assignee_id: UUID | None = Field(
        None,
        title=gettext_noop("Assigned to"),
        description="The id of the person to assign it to.",
        json_schema_extra=names("base.hub_user.get"),
    )
    unassign: bool = Field(
        False, title=gettext_noop("Remove assignment"), description="True: assign it to nobody."
    )
    assignee: Reference | None = Field(
        None,
        validate_default=True,
        title=gettext_noop("Assigned to"),
        description="The person's name, username or email, or «me» for the caller, when the id is not known.",
    )
    only_if_unassigned: bool = Field(
        False,
        title=gettext_noop("Only if unassigned"),
        description="True («Assign to me»): refuse instead of taking it from somebody else.",
    )

    @field_validator("assignee")
    @classmethod
    def _one(cls, value: str | None, info: ValidationInfo) -> str | None:
        given = [
            info.data.get("assignee_id") is not None,
            bool(info.data.get("unassign")),
            not _blank(value),
        ]
        if sum(given) != 1:
            raise ValueError(ONE_ASSIGNEE)
        return value


class SetStatusIn(ConversationRefIn):
    status: ConversationStatus = Field(
        description="open, pending (waiting for the customer) or closed (done)."
    )


class LinkCustomerIn(ConversationRefIn):
    customer_id: UUID | None = Field(
        None, description="The id of the customer card to join it to."
    )
    create: bool = Field(
        False,
        title=gettext_noop("Create card"),
        description="True: create a card with the WhatsApp name and number, and join it.",
    )
    unlink: bool = Field(
        False, title=gettext_noop("Unlink"), description="True: take the card off the conversation."
    )
    customer: Reference | None = Field(
        None,
        validate_default=True,
        description="The card's exact name, phone or email, when its id is not known.",
    )

    @field_validator("customer")
    @classmethod
    def _one(cls, value: str | None, info: ValidationInfo) -> str | None:
        given = [
            info.data.get("customer_id") is not None,
            bool(info.data.get("create")),
            bool(info.data.get("unlink")),
            not _blank(value),
        ]
        if sum(given) != 1:
            raise ValueError(ONE_CUSTOMER)
        return value


class ErasedOut(Schema):
    id: UUID = Field(description="The erased conversation.")


# ── Messages ────────────────────────────────────────────────────────────────────────────────────


class MessageListIn(ConversationPageIn):
    pass


class MessageOut(Schema):
    id: UUID = Field(description="The message's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    direction: Literal["inbound", "outbound"] = Field(
        description="inbound (customer) or outbound (business)."
    )
    origin: Literal["customer", "phone_app", "hub"] = Field(
        description="customer, phone_app (the owner's WhatsApp Business app) or hub (sent from here)."
    )
    source: Literal["live", "history"] = Field(
        description="live, or history brought by connecting the number."
    )
    kind: str = Field(
        description="Meta's type: text, image, audio, video, document, sticker, location, template…"
    )
    body: str = Field(description="The text.")
    media_url: str = Field(description="The attachment, at erplora.com.")
    media_mime_type: str = Field(description="The attachment's type.")
    media_filename: str = Field(description="The attachment's file name.")
    media_caption: str = Field(description="The attachment's caption.")
    template_name: str = Field(description="The template used, for a template message.")
    status: Literal["received", "queued", "sending", "sent", "delivered", "read", "failed"] = Field(
        description="Where it is."
    )
    error_code: str = Field(description="Meta's error code when it was not delivered.")
    error_message: str = Field(description="Meta's reason when it was not delivered.")
    wa_message_id: str | None = Field(description="WhatsApp's id of the message; none while it has not left.")
    reply_to: str = Field(description="WhatsApp's id of the message it answers.")
    reply_id: str = Field("", description="The id of the option the customer tapped, for a button or list reply.")
    sent_by_name: str = Field(description="Who sent it from the Hub.")
    sent_at: datetime = Field(description="When it was said.")
    status_at: datetime | None = Field(description="When its status last changed.")


class MessagePage(Page[MessageOut]):
    pass


class MessageGetOut(MessageOut):
    """A message with what an automation needs to answer it: its conversation's exact number and her name."""

    phone: str = Field(description="Its conversation's number, exactly in international format (+34600111222).")
    display_name: str = Field(
        description="What to call the customer: her card's name, her WhatsApp profile's or, with neither, her number."
    )
    can_send: bool = Field(
        description="Whether anything can be sent now (the number connected and the month's messages not spent)."
    )


class FlaggedOut(Schema):
    id: UUID = Field(description="The conversation's id.")
    flagged: bool = Field(
        description="true: it is marked «Needs attention»; false: it was not, being closed or pending."
    )


class TemplateSendIn(Schema):
    name: _text(512, 1) = Field(
        description="The template's name, as Meta has it (recordatorio_cita)."
    )
    language: _text(15) | None = Field(
        None, description="Its language (es, en); needed when it exists in several."
    )
    variables: list[_text(1024)] = Field(
        default_factory=list,
        max_length=20,
        description="The values of {{1}}, {{2}}… in order.",
    )
    header_sample: UUID | None = Field(
        None,
        title=gettext_noop("File"),
        description="For a template whose header is a photo, a video or a document: the id "
        "whatsapp_inbox.template_sample.upload answered for the file to send; without it, the template's own file.",
        json_schema_extra=A_SAMPLE,
    )


class SendIn(Schema):
    id: UUID | None = Field(None, description="The conversation's id.")
    to: _text(32) | None = Field(
        None,
        title=gettext_noop("Phone"),
        description="A number to write to (a template to somebody who has not written yet).",
    )
    conversation: Reference | None = Field(
        None, validate_default=True, description=CONVERSATION_REFERENCE
    )
    template: TemplateSendIn | None = Field(
        None,
        title=gettext_noop("Template"),
        description="An approved template; the only way to write after the 24-hour window.",
    )
    text: _text(4096) | None = Field(
        None,
        validate_default=True,
        description="The message, within 24 hours of the customer's last message.",
    )
    client_message_id: UUID = Field(
        description="A key of the caller's own for THIS message (a new UUID per message, the same on a retry): "
        "sending again with it never sends twice.",
        json_schema_extra={"attempt_key": True},
    )

    @field_validator("conversation")
    @classmethod
    def _target(cls, value: str | None, info: ValidationInfo) -> str | None:
        if (
            info.data.get("id") is None
            and _blank(info.data.get("to"))
            and _blank(value)
        ):
            raise ValueError(WHICH_CONVERSATION)
        return value

    @field_validator("text")
    @classmethod
    def _one(cls, value: str | None, info: ValidationInfo) -> str | None:
        if _blank(value) == (info.data.get("template") is None):
            raise ValueError(TEXT_OR_TEMPLATE)
        return value or None


def _from_erplora(url: str) -> str:
    """An attachment's URL is erplora.com's own, over https (the local SaaS's origin in development)."""
    saas = urlsplit(str(getattr(settings, "SAAS_URL", "") or ""))
    given = urlsplit(url)
    secure = given.scheme == "https" or (settings.DEBUG and given.scheme == saas.scheme)
    if not secure or not saas.netloc or (given.scheme, given.netloc) != (saas.scheme, saas.netloc):
        raise ValueError(NOT_ERPLORA)
    return url


class ReceiveMediaIn(Schema):
    url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000, pattern=r"^https?://\S+$")] = Field(
        description="Where erplora.com serves the attachment: its own origin, over https."
    )
    mime_type: _text(120) = Field("", description="Its MIME type.")
    filename: _text(255) = Field("", description="Its file name (documents).")
    caption: _text(4096) = Field(
        "", description="The caption the customer wrote with it."
    )

    @field_validator("url")
    @classmethod
    def _erplora(cls, value: str) -> str:
        return _from_erplora(value)


class ReceiveReplyIn(Schema):
    id: _text(256) = Field("", description="The id of the option the customer tapped (a quick reply's payload, a button's or a list row's id).")
    title: _text(1024) = Field("", description="Its text, as she saw it.")


class ReceiveIn(Schema):
    wa_message_id: _text(255, 1) = Field(
        description="WhatsApp's id of the message (wamid…)."
    )
    from_: Annotated[str, StringConstraints(strip_whitespace=True, pattern=INTERNATIONAL)] = Field(
        alias="from", description="The customer's international number as WhatsApp gives it (34600111222), with or without +."
    )
    contact_name: _text(200) = Field(
        "", description="The name of the customer's WhatsApp profile."
    )
    direction: Literal["inbound", "outbound"] = Field(
        "inbound",
        description="inbound (the customer) or outbound (the owner's reply from the phone app).",
    )
    source: Literal["live", "history"] = Field(
        "live", description="live, or history brought by connecting the number."
    )
    type: _text(32) = Field("text", description="Meta's message type.")
    text: _text(65536) = Field(
        "", description="The text, or the caption lifted out of Meta's object."
    )
    media: ReceiveMediaIn | None = Field(
        None, description="The attachment, kept by erplora.com."
    )
    reply_to: _text(255) = Field(
        "", description="WhatsApp's id of the message this one answers."
    )
    reply: ReceiveReplyIn | None = Field(
        None, description="The option she tapped, for a button or interactive reply; read from Meta's object when missing."
    )
    sent_at: datetime | None = Field(
        None, description="When it was said (Meta's time); now when missing."
    )
    payload: dict = Field(
        default_factory=dict, description="Meta's own message object, verbatim."
    )


class ReceiveOut(Schema):
    id: UUID = Field(description="The message's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    created: bool = Field(
        description="False when this message was already here (a repeated delivery)."
    )


class StatusErrorIn(Schema):
    code: _text(64) = Field("", description="Meta's error code (131047…).")
    message: _text(500) = Field("", description="Meta's reason.")


class StatusIn(Schema):
    wa_message_id: _text(255, 1) = Field(
        description="WhatsApp's id of a message the Hub sent."
    )
    client_message_id: UUID | None = Field(
        None, description="The Hub's key of the message (the Idempotency-Key it was sent with): matches a status that arrives before erplora.com's answer."
    )
    status: Literal["sent", "delivered", "read", "failed"] = Field(
        description="What Meta reported."
    )
    error: StatusErrorIn | None = Field(
        None, description="Why it was not delivered, for failed."
    )
    status_at: datetime | None = Field(None, description="When Meta reported it.")


class StatusOut(Schema):
    updated: bool = Field(
        description="Whether the message changed (an unknown id or an older status changes nothing)."
    )
    status: str | None = Field(description="The message's status now.")


class MessageRefIn(Schema):
    id: UUID = Field(description="The message's id.")


class ClaimDeliveryOut(Schema):
    claimed: bool = Field(description="Whether this delivery may go now (queued or sending, nobody else on it).")
    to: str = Field("", description="The number it goes to.")
    text: str | None = Field(None, description="The text, for a text message.")
    template: dict | None = Field(None, description="name, language and variables, for a template.")
    client_message_id: UUID | None = Field(None, description="Its Idempotency-Key.")


class RecordDeliveryIn(Schema):
    id: UUID = Field(description="The message handed to erplora.com.")
    kind: Literal["sent", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    wa_message_id: str = Field("", description="Meta's id, when it was sent.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="erplora.com's reason, or what went wrong.")


class RecordOut(Schema):
    status: str | None = Field(description="The status now.")


class ClaimErasureOut(Schema):
    claimed: bool = Field(description="Whether erplora.com still has to forget it (and nobody else is asking).")
    phone: str = Field("", description="The number erplora.com has to forget.")
    wa_message_ids: list[str] = Field(default_factory=list, description="The WhatsApp ids of its messages.")


class RecordErasureIn(Schema):
    id: UUID = Field(description="The erased conversation.")
    confirmed: bool = Field(description="Whether erplora.com confirmed it forgot the number.")


class ResumeIn(Schema):
    pass


class ResumeOut(Schema):
    messages: int = Field(description="Messages handed to erplora.com again.")
    erasures: int = Field(description="Erasures asked to erplora.com again.")
    templates: int = Field(0, description="Templates handed to erplora.com again.")
    template_deletions: int = Field(0, description="Template deletions asked to erplora.com again.")


class ClaimTemplateOut(Schema):
    claimed: bool = Field(description="Whether this hand-over may go now (nobody else on it).")
    template: dict | None = Field(None, description="What goes to erplora.com: the template as door 8 takes it.")
    submit_key: UUID | None = Field(None, description="Its Idempotency-Key.")


class RecordTemplateIn(Schema):
    id: UUID = Field(description="The template handed to erplora.com.")
    submit_key: UUID = Field(description="The key it was handed with: an answer to an older save changes nothing.")
    kind: Literal["accepted", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    meta_id: str = Field("", description="Meta's id, when accepted.")
    status: str = Field("", description="Meta's verdict, when accepted.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="The reason, or what went wrong.")


class ClaimTemplateDeletionOut(Schema):
    claimed: bool = Field(description="Whether Meta still has to delete it (and nobody else is asking).")
    name: str = Field("", description="Its name.")
    language: str = Field("", description="Its language.")
    meta_id: str = Field("", description="Meta's id.")


class RecordTemplateDeletionIn(Schema):
    id: UUID = Field(description="The template deleted here.")
    kind: Literal["accepted", "refused", "unreachable", "unknown"] = Field(description="How erplora.com answered.")
    code: str = Field("", description="erplora.com's code, when it refused.")
    message: str = Field("", description="The reason, or what went wrong.")


# ── Notes ───────────────────────────────────────────────────────────────────────────────────────


class NoteListIn(ConversationPageIn):
    pass


class NoteAddIn(ConversationRefIn):
    text: _text(5000, 1) = Field(description="The note; the customer never sees it.")


class NoteRefIn(Schema):
    id: UUID = Field(description="The note's id.")


class NoteOut(Schema):
    id: UUID = Field(description="The note's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    text: str = Field(description="The note.")
    author_id: UUID | None = Field(description="Who wrote it.")
    author_name: str = Field(description="Their name when they wrote it.")
    created_at: datetime = Field(description="When.")
    can_delete: bool = Field(description="Whether the caller may delete it.")


class NotePage(Page[NoteOut]):
    pass


class NoteDeletedOut(Schema):
    id: UUID = Field(description="The deleted note.")


# ── Templates and channel ───────────────────────────────────────────────────────────────────────

#: A variable of a template's text, as Meta writes it: ``{{1}}``.
TEMPLATE_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_ANY_VARIABLE = re.compile(r"\{\{.*?\}\}")


def template_variables(text: str) -> int:
    """How many variables ``text`` takes (the highest ``{{n}}``)."""
    return max((int(n) for n in TEMPLATE_VARIABLE.findall(text or "")), default=0)


class TemplateButtonIn(Schema):
    type: Literal["QUICK_REPLY", "URL", "PHONE_NUMBER"] = Field(
        description="QUICK_REPLY (an answer the customer taps), URL (opens a link) or PHONE_NUMBER (calls)."
    )
    text: _text(25, 1) = Field(description="What the button says, up to 25 characters.")
    url: _text(2000) = Field(
        "", validate_default=True, description="For URL: the https:// address it opens (no variables)."
    )
    phone_number: _text(16) = Field(
        "", validate_default=True, description="For PHONE_NUMBER: the number it calls, E.164 (+34910000000)."
    )

    @field_validator("url")
    @classmethod
    def _link(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("type") == "URL" and (not value.startswith("https://") or _ANY_VARIABLE.search(value)):
            raise ValueError(BUTTON_URL)
        return value if info.data.get("type") == "URL" else ""

    @field_validator("phone_number")
    @classmethod
    def _call(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("type") == "PHONE_NUMBER" and not re.fullmatch(r"\+[1-9]\d{6,14}", value):
            raise ValueError(BUTTON_PHONE)
        return value if info.data.get("type") == "PHONE_NUMBER" else ""


class TemplateWriteIn(Schema):
    """What the form writes of a template; the rules are Meta's, checked here to say them under each field."""

    category: WritableCategory = Field(
        "UTILITY", description="UTILITY (about something the customer asked or booked) or MARKETING (offers)."
    )
    header_format: WritableHeaderFormat = Field(
        "",
        description="Its header: empty or TEXT (the text of header, if any), or IMAGE, VIDEO or DOCUMENT with the file "
        "of header_sample.",
    )
    header: _text(60) = Field("", description="An optional title in bold, up to 60 characters, without variables.")
    header_sample: UUID | None = Field(
        None,
        description="For an IMAGE, VIDEO or DOCUMENT header: the id whatsapp_inbox.template_sample.upload answered "
        "for its file (Meta reviews the template with it; the same one again keeps it).",
        json_schema_extra=A_SAMPLE,
    )
    body: _text(1024, 1) = Field(description="The text, up to 1024 characters, with {{1}}, {{2}}… where the variables go.")
    body_examples: list[_text(1024)] = Field(
        default_factory=list, max_length=100, description="An example of each variable, in order: Meta reviews the template with them."
    )
    footer: _text(60) = Field("", description="An optional small line at the end, up to 60 characters, without variables.")
    buttons: list[TemplateButtonIn] = Field(
        default_factory=list, max_length=10,
        description="Up to 10 buttons: quick replies together, at most 2 links and 1 call.",
    )
    submit_key: UUID = Field(
        description="A key of the caller's own for THIS save (a new UUID per save, the same on a retry): saving "
        "again with it never registers the template twice.",
        json_schema_extra={"attempt_key": True},
    )

    @field_validator("header", "footer")
    @classmethod
    def _plain(cls, value: str, info: ValidationInfo) -> str:
        if _ANY_VARIABLE.search(value):
            raise ValueError(TEMPLATE_NO_VARIABLES)
        if info.field_name == "header" and value and info.data.get("header_format") in FILE_HEADER_FORMATS:
            raise ValueError(TEMPLATE_FILE_NO_TEXT)
        return value

    @field_validator("body")
    @classmethod
    def _numbered(cls, value: str) -> str:
        numbers = {int(n) for n in TEMPLATE_VARIABLE.findall(value)}
        if NAMED_VARIABLE.search(value) or (numbers and numbers != set(range(1, max(numbers) + 1))):
            raise ValueError(TEMPLATE_NUMBERING)
        return value

    @field_validator("body_examples")
    @classmethod
    def _examples(cls, value: list[str], info: ValidationInfo) -> list[str]:
        body = info.data.get("body")
        if body is not None and (len(value) != template_variables(body) or any(not example for example in value)):
            raise ValueError(TEMPLATE_EXAMPLES)
        return value

    @field_validator("buttons")
    @classmethod
    def _grouped(cls, value: list[TemplateButtonIn]) -> list[TemplateButtonIn]:
        kinds = [button.type for button in value]
        if kinds.count("URL") > 2 or kinds.count("PHONE_NUMBER") > 1:
            raise ValueError(BUTTON_KINDS)
        quick = [kind == "QUICK_REPLY" for kind in kinds]
        if sum(1 for before, after in zip(quick, quick[1:]) if before != after) > 1:
            raise ValueError(BUTTONS_GROUPED)
        return value


class TemplateCreateIn(TemplateWriteIn):
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=512)] = Field(
        description="Its name at Meta: lowercase letters, numbers and underscores (recordatorio_cita); it never changes."
    )
    language: Annotated[str, StringConstraints(strip_whitespace=True, max_length=15)] = Field(
        description="Its language code at Meta (es, es_ES, en_US, ca…); it never changes."
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]+", value):
            raise ValueError(TEMPLATE_NAME_RULE)
        return value

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2,4})?", value):
            raise ValueError(TEMPLATE_LANGUAGE_RULE)
        return value


class TemplateUpdateIn(TemplateWriteIn):
    id: UUID = Field(description="The template's id in the Hub; its name and language do not change.")


class TemplateRefIn(Schema):
    id: UUID = Field(description="The template's id in the Hub.")


#: A 25 MB document in base64 is 34 952 536 characters; a little more still reads «too heavy» under its field.
MAX_SAMPLE_BASE64 = 36_000_000


class TemplateSampleUploadIn(Schema):
    header_format: FileHeaderFormat = Field(
        description="The header it is for: IMAGE (a JPEG or PNG photo, 5 MB at most), VIDEO (an MP4, 16 MB) or "
        "DOCUMENT (a PDF, 25 MB)."
    )
    name: _text(255, 1) = Field(description="The file's name, as Meta shows it in its review (carta.pdf).")
    content_base64: str = Field(
        max_length=MAX_SAMPLE_BASE64, title=gettext_noop("File"), description="The file, in base64."
    )


class TemplateSampleRefIn(Schema):
    id: UUID = Field(description="The file's id, as whatsapp_inbox.template_sample.upload answered it.")


class TemplateSampleOut(Schema):
    id: UUID = Field(description="The file's id: give it as header_sample when creating or changing the template.")
    header_format: FileHeaderFormat = Field(description="IMAGE, VIDEO or DOCUMENT, as its bytes say.")
    content_type: str = Field(description="image/jpeg, image/png, video/mp4 or application/pdf.")
    size: int = Field(description="Its size in bytes.")
    name: str = Field(description="The name it was chosen with.")
    url: str = Field(
        description="Where the Hub shows it to the hub's people (/p/media/…, opened only with a session of this hub); "
        "empty when it cannot."
    )


class TemplateButtonOut(Schema):
    type: str = Field(description="QUICK_REPLY, URL, PHONE_NUMBER, or another of Meta's (made in WhatsApp Manager).")
    text: str = Field(description="What the button says.")
    url: str = Field("", description="The address a URL button opens.")
    phone_number: str = Field("", description="The number a PHONE_NUMBER button calls.")


class TemplateDraftOut(Schema):
    category: TemplateCategory = Field(description="The category of the edit.")
    header_format: HeaderFormat = Field("", description="The header type of the edit.")
    header: str = Field(description="The header of the edit.")
    header_sample: TemplateSampleOut | None = Field(None, description="The header's file of the edit.")
    body: str = Field(description="The text of the edit.")
    body_examples: list[str] = Field(description="Its examples.")
    footer: str = Field(description="Its footer.")
    buttons: list[TemplateButtonOut] = Field(description="Its buttons.")


class TemplateListIn(PageIn):
    search: _text(120) | None = Field(None, description="Part of the template's name.")
    status: TemplateStatus | None = Field(
        None, description="Only templates in this state at Meta (APPROVED to send)."
    )
    category: TemplateCategory | None = Field(
        None, description="Only UTILITY, MARKETING or AUTHENTICATION templates."
    )
    language: _text(15) | None = Field(
        None, description="Only templates in this language."
    )
    sendable: bool | None = Field(
        None,
        description="true: only the ones the Hub sends as they are (approved, not being deleted, a photo, video or "
        "document header only with its own file): what an automation may send.",
    )
    fillable: bool | None = Field(
        None,
        description="true: the ones the inbox can send (approved, not being deleted), a photo, video or document "
        "header asking for its file when it has none of its own.",
    )


class TemplateOut(Schema):
    id: UUID = Field(description="The template's id in the Hub.")
    name: str = Field(description="Its name at Meta.")
    language: str = Field(description="Its language.")
    category: TemplateCategory = Field(
        description="UTILITY, MARKETING or AUTHENTICATION."
    )
    status: TemplateStatus = Field(description="What Meta says of it (DRAFT: Meta never had it).")
    header_format: HeaderFormat = Field(
        description="Its header: none, TEXT, IMAGE, VIDEO or DOCUMENT (a file), or LOCATION (made in WhatsApp Manager)."
    )
    header: str = Field(description="Its header text.")
    header_sample: TemplateSampleOut | None = Field(
        description="The file of its IMAGE, VIDEO or DOCUMENT header when it was chosen here (none for one made in "
        "WhatsApp Manager)."
    )
    body: str = Field(description="Its text, with {{1}}… where the variables go.")
    body_examples: list[str] = Field(description="An example of each variable.")
    footer: str = Field(description="Its footer.")
    buttons: list[TemplateButtonOut] = Field(description="Its buttons.")
    variables: int = Field(description="How many variables it takes.")
    rejected_reason: str = Field(description="Meta's reason when it rejected it.")
    meta_id: str = Field(description="Meta's id; empty while Meta never had it.")
    synced_at: datetime | None = Field(description="When erplora.com last reported it.")
    draft: TemplateDraftOut | None = Field(description="An edit waiting to reach Meta; the template above is what Meta has.")
    submit_state: SubmitState = Field(description="Its hand-over to Meta: queued, sending (to retry) or failed (fix it).")
    submit_error_code: str = Field(description="Why the last hand-over or deletion did not end well.")
    submit_error: str = Field(description="The reason, in words.")
    editable: bool = Field(description="Whether it can be changed here (else only in WhatsApp Manager).")
    sendable: bool = Field(description="Whether the Hub can send it now.")
    supported: bool = Field(
        description="Whether the Hub fills it when sending, whatever Meta says of it (else it is only sent and "
        "changed from WhatsApp Manager: a file or place header, named variables, a code…)."
    )
    deleting: bool = Field(description="Deleted here, still being deleted at Meta.")


class TemplatePage(Page[TemplateOut]):
    pass


class SyncTemplateIn(Schema):
    name: _text(512, 1) = Field(description="The template's name at Meta.")
    language: _text(15, 1) = Field(description="Its language code.")
    category: TemplateCategory = Field(
        "UTILITY", description="UTILITY, MARKETING or AUTHENTICATION."
    )
    status: MetaTemplateStatus = Field("APPROVED", description="Meta's verdict.")
    header_format: HeaderFormat | None = Field(
        None, description="Its header: none, TEXT, IMAGE, VIDEO, DOCUMENT or LOCATION; TEXT when missing and there is a header text."
    )
    header: _text(200) = Field("", description="Its header text.")
    body: _text(4096) = Field("", description="Its body with {{n}} placeholders.")
    body_examples: list[_text(1024)] = Field(default_factory=list, max_length=100, description="The examples Meta holds.")
    footer: _text(200) = Field("", description="Its footer.")
    buttons: list[dict] = Field(
        default_factory=list, max_length=10, description="Meta's buttons: {type, text, url?, phone_number?}."
    )
    variables: int = Field(
        0, ge=0, le=100, description="How many variables the body takes."
    )
    rejected_reason: _text(500) = Field(
        "", description="Meta's reason for a rejection."
    )
    meta_id: _text(64) = Field("", description="Meta's id of the template.")


class ChannelSyncIn(Schema):
    version: int = Field(
        ge=0,
        description="erplora.com's version of this state; an older one is ignored.",
    )
    status: Literal["not_connected", "connected", "reconnect_needed"] = Field(
        description="The number's state."
    )
    phone_number: Annotated[str, StringConstraints(strip_whitespace=True, pattern=E164_OR_EMPTY)] = Field(
        "", description="The business's number, E.164 (+34910000000), empty while not connected."
    )
    display_name: _text(200) = Field("", description="The name WhatsApp shows for it.")
    monthly_limit: int = Field(
        0, ge=0, description="Messages the plan includes each month; 0 = none (never «unlimited»)."
    )
    monthly_usage: int = Field(
        0, ge=0, description="Messages sent this month, as erplora.com counts them."
    )
    usage_month: Annotated[
        str, StringConstraints(pattern=r"^(\d{4}-(0[1-9]|1[0-2]))?$")
    ] = Field("", description="The month that figure counts, YYYY-MM.")
    templates: list[SyncTemplateIn] | None = Field(
        None,
        max_length=1000,
        description="Every template of the account; null leaves them as they are.",
    )


class ChannelSyncOut(Schema):
    applied: bool = Field(
        description="False when an equal or newer version was already here."
    )
    version: int = Field(description="The version the Hub holds now.")


class ChannelGetIn(Schema):
    pass


class ChannelOut(Schema):
    status: Literal["not_connected", "connected", "reconnect_needed"] = Field(
        description="The number's state."
    )
    phone_number: str = Field(description="The business's number.")
    display_name: str = Field(description="The name WhatsApp shows for it.")
    monthly_limit: int = Field(
        description="Messages the plan includes each month; 0 = none (never «unlimited»)."
    )
    monthly_usage: int = Field(
        description="Messages sent this month (0 when erplora.com has not counted this month yet)."
    )
    cap_reached: bool = Field(
        description="Whether this month's messages are spent: always when the plan includes none (once "
        "erplora.com said so)."
    )
    synced_at: datetime | None = Field(description="When erplora.com last reported.")
    manage_url: str = Field(
        description="Where the number is connected and managed: erplora.com."
    )
    plans_url: str = Field(
        description="Where the plan is upgraded for more WhatsApp messages: erplora.com's plans; empty when "
        "this server is not linked to erplora.com."
    )


# ── Connecting the number from Settings (WHATSAPP_INBOX-F01, F02; erplora.com's doors 10–12) ────

#: An id of Meta (an account, a number, a portfolio): digits only.
META_ID = r"^\d{1,50}$"
META_ID_OR_EMPTY = r"^\d{0,50}$"


class ChannelPrepareIn(Schema):
    pass


class ChannelPrepareOut(Schema):
    available: bool = Field(
        description="Whether Meta's window (WhatsApp Embedded Signup) can be opened from Settings now."
    )
    reason: Literal["not_configured", "window_unavailable", "popups_blocked"] | None = Field(
        None,
        description="Why not: WhatsApp is not set up on erplora.com (not_configured), erplora.com has no page "
        "to bring Meta's answer back (window_unavailable), or this Hub's pages cut the windows they open "
        "(popups_blocked).",
    )
    app_id: str = Field("", description="The id of ERPlora's app at Meta (public).")
    config_id: str = Field("", description="The id of the Embedded Signup configuration (public).")
    graph_version: str = Field("", description="The version of Meta's Graph API, e.g. v25.0.")
    redirect_uri: str = Field(
        "", description="erplora.com's page Meta's window returns the one-time code to (https)."
    )


class ChannelConnectIn(Schema):
    code: _text(2048, 1) = Field(
        title=gettext_noop("Meta connection code"),
        description="The one-time code Meta's window returned (it lasts 30 seconds).",
    )
    event: Annotated[str, StringConstraints(pattern=r"^FINISH[A-Z_]{0,58}$")] = Field(
        "FINISH",
        title=gettext_noop("How Meta's window finished"),
        description="How Meta's window finished (FINISH, or FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING for a "
        "number of the WhatsApp Business app); a window cancelled or failed connects nothing.",
    )
    waba_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID)] = Field(
        title=gettext_noop("WhatsApp Business account"),
        description="The WhatsApp Business account chosen in Meta's window.",
    )
    phone_number_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID_OR_EMPTY)] = Field(
        "",
        title=gettext_noop("Your number"),
        description="The number chosen in Meta's window (empty: the account's only number).",
    )
    business_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID_OR_EMPTY)] = Field(
        "", title=gettext_noop("Business portfolio at Meta"), description="The business portfolio at Meta."
    )


class ChannelConnectOut(Schema):
    connected: bool = Field(description="Whether erplora.com connected the number.")
    phone_number: str = Field(description="The connected number, E.164.")
    display_name: str = Field(description="The name WhatsApp shows for it.")
    history_requested: bool = Field(
        description="For a number of the WhatsApp Business app: whether its contacts and chats were asked of Meta."
    )


class ChannelDisconnectIn(Schema):
    pass


class ChannelDisconnectOut(Schema):
    disconnected: bool = Field(
        description="False when erplora.com had no number connected for this business."
    )


# ── People of the team ──────────────────────────────────────────────────────────────────────────


class AgentListIn(PageIn):
    search: _text(120) | None = Field(
        None, description="Part of the person's name, username or email."
    )


class AgentOut(Schema):
    id: UUID = Field(description="The person's id.")
    name: str = Field(description="Their name.")
    role: str = Field(description="Their role in the business.")


class AgentPage(Page[AgentOut]):
    pass


# ── Reactions to Customers ──────────────────────────────────────────────────────────────────────


class CustomerEventIn(Schema):
    id: UUID = Field(description="The customer card the event is about.")


class MergedEventIn(Schema):
    id: UUID = Field(description="The card that stays.")
    absorbed_id: UUID = Field(description="The duplicate merged into it.")


class ReactionOut(Schema):
    count: int = Field(description="How many conversations changed.")
