"""Schemas of the emails of an invoice (INVOICE-F26): sending one, their log and what the platform runs on them."""

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import BeforeValidator

from apps.customer.schemas.fields import Email
from apps.invoice.models import InvoiceEmail
from apps.invoice.schemas.fields import InvoiceRefIn, _blank_to_none
from apps.sale.schemas.fields import AttemptKey
from base.sensitive import CUSTOMER_CONTACT

EmailStatus = Literal[*InvoiceEmail.Status.values]


class SendEmailIn(InvoiceRefIn):
    to: Annotated[Email | None, BeforeValidator(_blank_to_none)] = Field(
        None,
        title=gettext_noop("Send to"),
        description="The one email address it goes to; without it, the one on the customer's card.",
    )
    attempt_key: AttemptKey | None = Field(
        None,
        description="A key of the caller's own for THIS email (a new one per email, the same on a retry): asking again "
        "with it never sends twice.",
    )


class EmailListIn(InvoiceRefIn):
    """The emails of an invoice."""


class InvoiceEmailOut(Schema):
    id: UUID
    to: str | None = Field(
        description="The address it goes to; empty once the customer's personal data was erased.",
        json_schema_extra=CUSTOMER_CONTACT,
    )
    status: EmailStatus = Field(description="queued and sending: on its way; sent: the mail server took it; failed.")
    requested_at: dt.datetime
    sent_at: dt.datetime | None = Field(description="When the mail server took it; none until then.")
    reason: str = Field(description="Why it was not sent, in the reader's language; empty otherwise.")


class EmailListOut(Schema):
    customer_email: str | None = Field(
        description="The email on the customer's card, the one proposed; empty without one.",
        json_schema_extra=CUSTOMER_CONTACT,
    )
    emails: list[InvoiceEmailOut] = Field(description="The newest first.")


# ── What only the platform runs ─────────────────────────────────────────────────────────────────


class EmailRefIn(Schema):
    id: UUID = Field(description="Id of the email.")


class EmailClaimOut(Schema):
    claimed: bool = Field(description="False when it was taken already, or there is nothing left to send.")
    invoice_id: UUID | None = None
    to: str = ""


class EmailRecordIn(EmailRefIn):
    failure: str = Field("", max_length=60, description="Why it was not sent; empty when the mail server took it.")


class EmailRecordOut(Schema):
    status: EmailStatus | None


class EmailResumeIn(Schema):
    """What stopped half-way."""


class EmailResumeOut(Schema):
    resumed: int = Field(description="How many that nobody took were handed over again.")
    unconfirmed: int = Field(description="How many that stopped while they were sent were told as not confirmed.")


class ForgetCustomerIn(Schema):
    """The payload of ``customer.customer.erased``."""

    id: UUID = Field(description="The customer's card whose personal data was erased.")


class ForgottenOut(Schema):
    forgotten: int = Field(description="How many emails lost their address.")
