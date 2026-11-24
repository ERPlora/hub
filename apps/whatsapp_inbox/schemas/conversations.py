"""Schemas of the conversations: list, detail, counters and notices; assign, close, flag, join a customer card."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.customer.schemas.contact import PHONE
from apps.whatsapp_inbox.schemas.fields import A_CUSTOMER, ConversationRefIn, Page, PageIn, Reference, _blank, _text
from base.schemas.assistant import names
from base.sensitive import CUSTOMER_CONTACT

ONE_ASSIGNEE = _("Choose one person, yourself («me») or nobody.")
ONE_CUSTOMER = _("Choose a customer card, create one or unlink it.")
UNKNOWN_ASSIGNED = _("Choose «me», «none» or a person's id.")

ConversationStatus = Literal["open", "pending", "closed"]
SortDir = Literal["asc", "desc"]


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


class ConversationListIn(PageIn):
    search: _text(120) | None = Field(
        None,
        description="Part of the contact's or customer's name or, for whoever sees the customers' contact details, of "
        "the number written in any format (600 111, +34 600 111 222, 0034600111222).",
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
        "last_message_at", "contact", "status", "unread_count", "assigned_to"
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
    phone: str | None = PHONE
    contact_name: str = Field(
        description="The name of the customer's WhatsApp profile."
    )
    display_name: str = Field(
        description="What the inbox calls it: the card's name, the profile's or the number (to whoever does not see "
        "the customers' contact details, masked: its first three and last four digits)."
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
        description="The exact number, international format (+34600111222).",
        json_schema_extra=CUSTOMER_CONTACT,
    )


class ByPhoneOut(Schema):
    phone_is_international: bool = Field(
        description="Whether the number was in international format."
    )
    phone: str | None = Field(
        None, description="The number as compared (E.164), empty when it was not one.", json_schema_extra=CUSTOMER_CONTACT
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
    display_name: str = Field(
        description="Who: the customer card's name, else her WhatsApp name, else her number (masked to whoever does not "
        "see the customers' contact details)."
    )
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
        None, description="The id of the customer card to join it to.", json_schema_extra=A_CUSTOMER
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
        description="The card's name (or a part of it), phone or email, when its id is not known.",
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


class FlaggedOut(Schema):
    id: UUID = Field(description="The conversation's id.")
    flagged: bool = Field(
        description="true: it is marked «Needs attention»; false: it was not, being closed or pending."
    )
