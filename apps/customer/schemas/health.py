"""Health data (CUSTOMER-F32): its own block, never on the card, the list, the export or the assistant."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.fields import ConsentSource, CustomerOfIn, _text

HealthTestResult = Literal["", "negative", "positive"]

#: What the assistant reads on every free text of a card it may write: with no tool for health data, a note, the card's
#: notes, a custom field or an entry of its activity is where it would put an allergy, out of the block and of the
#: permission it needs. Only that block is out of its reach: an allergy marked on a dish for the kitchen is no datum of
#: the card, and «no tool» said of every allergy made it turn that down too.
NOT_FOR_HEALTH_DATA = (
    "Never for allergies, sensitivity tests or other health data: those go only in the «Health and allergies» block of "
    "the customer's card in Customers (/customer/customers), with the customer's own explicit permission, which only "
    "that screen records. No tool of yours writes that block: tell the person to do it there. An allergy to mark on a "
    "dish someone will eat is not kept on the card: it goes on that dish's line, with a tool you find by searching for "
    "it."
)


class HealthDetailIn(CustomerOfIn):
    pass


class HealthGrantIn(CustomerOfIn):
    notice_text: _text(2000, 1) = Field(
        description="The exact words read to the customer, stored as proof."
    )
    notice_version: _text(60) = Field("", description="The version of those words.")
    source: ConsentSource = Field(
        "counter",
        description="Where it was given: counter, web_form, phone, email, import or receipt.",
    )
    evidence: _text(500) = Field(
        "", description="An outside reference that backs it (a signed form)."
    )
    occurred_at: datetime | None = Field(
        None, description="When the customer said it, if not now."
    )


class HealthWithdrawIn(CustomerOfIn):
    source: ConsentSource = Field(
        "counter",
        description="Where it was withdrawn: counter, web_form, phone, email, import or receipt.",
    )
    reason: _text(500) = Field("", description="Why, if the customer said; never required.")


class HealthIn(CustomerOfIn):
    allergies: _text(2000) = Field(
        "", description="Allergies and sensitivities, as the customer tells them."
    )
    sensitivity_test_on: date | None = Field(
        None, description="The day of the last sensitivity (patch) test."
    )
    sensitivity_test_result: HealthTestResult = Field(
        "", description="Its result: negative, positive or empty while unread."
    )


class HealthOut(Schema):
    customer_id: UUID = Field(description="The customer's id.")
    consent: Literal["none", "granted", "withdrawn"] = Field(
        description="The last decision on the permission to keep health data; none if never asked."
    )
    consent_at: datetime | None = Field(description="When that decision was said.")
    consent_by: str = Field(description="Who wrote it down.")
    notice_text: str = Field(description="The exact words the customer said yes to.")
    allergies: str = Field(description="Allergies and sensitivities.")
    sensitivity_test_on: date | None = Field(description="The day of the last sensitivity test.")
    sensitivity_test_result: HealthTestResult = Field(description="Its result.")
    updated_at: datetime | None = Field(description="When the health data last changed.")
    updated_by: str = Field(description="Who changed it.")
