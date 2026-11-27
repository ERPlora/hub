"""Schemas of a customer's consent: granting and withdrawing it, its state per purpose and channel, and its
history."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.fields import ConsentChannel, ConsentSource, CustomerOfIn, Page, PageIn, Purpose, _text
from base.sensitive import CUSTOMER_CONTACT


class ConsentGrantIn(CustomerOfIn):
    channel: ConsentChannel = Field(
        description="The channel: email, sms, whatsapp, phone or postal."
    )
    purpose: Purpose = Field(
        "marketing", description="What the consent is for; marketing by default."
    )
    source: ConsentSource = Field(
        "counter",
        description="Where it was given: counter, web_form, phone, email, import or receipt.",
    )
    evidence: _text(500) = Field(
        "", description="An outside reference that backs it (a signed form, a ticket)."
    )
    occurred_at: datetime | None = Field(
        None, description="When the customer said it, if not now."
    )


class ConsentWithdrawIn(CustomerOfIn):
    channel: ConsentChannel = Field(
        description="The channel: email, sms, whatsapp, phone or postal."
    )
    purpose: Purpose = Field(
        "marketing", description="What the consent was for; marketing by default."
    )
    source: ConsentSource = Field(
        "counter",
        description="Where it was withdrawn: counter, web_form, phone, email, import or receipt.",
    )
    reason: _text(500) = Field(
        "", description="Why, if the customer said; never required."
    )
    evidence: _text(500) = Field("", description="An outside reference that backs it.")
    occurred_at: datetime | None = Field(
        None, description="When the customer said it, if not now."
    )


class ConsentStateIn(CustomerOfIn):
    pass


class ConsentHistoryIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the facts."
    )


class ConsentStateRow(Schema):
    purpose: str = Field(description="What the consent is for.")
    channel: ConsentChannel | Literal[""] = Field(
        description="The channel; empty for a permission that is not about reaching the person (health data)."
    )
    state: Literal["granted", "withdrawn"] = Field(
        description="The last decision: granted or withdrawn."
    )
    contact_point: str | None = Field(None, description="The address it was given or withdrawn for.", json_schema_extra=CUSTOMER_CONTACT)
    source: ConsentSource = Field(description="Where it was decided.")
    notice_version: str = Field(description="The version of the words shown.")
    occurred_at: datetime = Field(description="When the customer said it.")
    recorded_by: str = Field(description="Who wrote it down.")
    evidence: str = Field(description="The outside reference that backs it.")


class ConsentRow(Schema):
    id: UUID = Field(description="The fact's id.")
    customer_id: UUID = Field(description="The customer's id.")
    purpose: str = Field(description="What it is for.")
    channel: ConsentChannel | Literal[""] = Field(
        description="The channel; empty for a permission that is not about reaching the person (health data)."
    )
    state: Literal["granted", "withdrawn"] = Field(description="What was decided.")
    contact_point: str | None = Field(None, description="The address it was decided for.", json_schema_extra=CUSTOMER_CONTACT)
    source: ConsentSource = Field(description="Where it was decided.")
    notice_text: str = Field(description="The exact words shown.")
    notice_version: str = Field(description="Their version.")
    evidence: str = Field(description="The outside reference that backs it.")
    reason: str = Field(description="Why it was withdrawn, if said.")
    recorded_by: str = Field(description="Who wrote it down.")
    occurred_at: datetime = Field(description="When the customer said it.")
    created_at: datetime = Field(description="When it was written down.")


ConsentPage = Page[ConsentRow]


class ConsentStateOut(Schema):
    customer_id: UUID = Field(description="The customer's id.")
    rows: list[ConsentStateRow] = Field(
        description="The last decision per purpose and channel."
    )
