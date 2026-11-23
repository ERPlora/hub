"""Schemas of a customer's card: the list and its filters, creating and editing it, its detail, the totals and
finding it by phone."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.customer.schemas.consent import ConsentStateRow
from apps.customer.schemas.contact import EMAIL, PHONE
from apps.customer.schemas.fields import (
    A_FIELD,
    ANNUAL_DATE,
    CHANNEL,
    CUSTOM_FIELD,
    SOURCE,
    STAGE,
    AnnualDate,
    Country,
    CustomerRefIn,
    Email,
    FieldType,
    Name,
    Page,
    PageIn,
    PreferredChannel,
    Source,
    Stage,
    _text,
)
from base.sensitive import BUSINESS_TOTALS, CUSTOMER_CONTACT

CustomerSort = Literal[
    "name",
    "tax_id",
    "company_name",
    "lifecycle_stage",
    "source",
    "is_active",
    "total_purchases",
    "total_spent",
    "last_purchase_at",
    "created_at",
]


class CustomerFilters(Schema):
    search: str | None = Field(
        None,
        max_length=200,
        description="Text to look for in the name, tax id and company, and the email and phone for whoever sees the "
        "customers' contact details, ignoring case and accents; a phone is found however it is typed.",
    )
    name: str | None = Field(
        None, max_length=200, description="Only customers whose name contains this."
    )
    email: str | None = Field(
        None, max_length=254, description="Only customers whose email contains this.", json_schema_extra=CUSTOMER_CONTACT
    )
    phone: str | None = Field(
        None, max_length=60, description="Only customers whose phone contains these digits.", json_schema_extra=CUSTOMER_CONTACT
    )
    tax_id: str | None = Field(
        None, max_length=32, description="Only customers whose tax id contains this."
    )
    company_name: str | None = Field(
        None, max_length=200, description="Only customers whose company contains this."
    )
    lifecycle_stage: Stage | None = Field(
        None, description=f"Only customers at this stage. {STAGE}"
    )
    source: Source | None = Field(
        None, description=f"Only customers from this source. {SOURCE}"
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) customers."
    )
    purchases_min: int | None = Field(
        None, ge=0, description="Only customers with at least this many purchases."
    )
    purchases_max: int | None = Field(
        None, ge=0, description="Only customers with at most this many purchases."
    )
    spent_min: int | None = Field(
        None, ge=0, description="Only customers who spent at least this, in cents.", json_schema_extra={"money": True}
    )
    spent_max: int | None = Field(
        None, ge=0, description="Only customers who spent at most this, in cents.", json_schema_extra={"money": True}
    )
    last_purchase_from: date | None = Field(
        None, description="Only customers whose last purchase was on or after this day."
    )
    last_purchase_to: date | None = Field(
        None,
        description="Only customers whose last purchase was on or before this day.",
    )
    sort: CustomerSort = Field(
        "name", description="The column to order by; the id breaks ties."
    )
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


class CustomerListIn(CustomerFilters, PageIn):
    pass


class CustomerStatsIn(Schema):
    pass


class ByPhoneIn(Schema):
    phone: str | None = Field(
        None,
        max_length=60,
        description="The number as it was typed or as WhatsApp gives it (digits without +).",
        json_schema_extra=CUSTOMER_CONTACT,
    )


class CustomerIn(Schema):
    name: Name = Field(description="The customer's name: the only thing required.")
    email: Email = Field("", description="Their email.")
    phone: str = Field(
        "",
        max_length=60,
        description="Their phone as typed; it is saved in international format (+34600111222), a number "
        "without prefix being read in the business's country.",
    )
    tax_id: _text(32) = Field("", description="Their tax id (NIF/CIF).")
    company_name: _text(200) = Field("", description="Their company.")
    address: _text(255) = Field("", description="Street and number.")
    city: _text(100) = Field("", description="City.")
    postal_code: _text(20) = Field("", description="Postal code.")
    country: Country = Field(
        "", description="Country, as its ISO 3166 two-letter code (ES, FR)."
    )
    avatar: _text(500) = Field("", description="The address (URL) of their picture.")
    birthday: AnnualDate = Field(None, description=f"Their birthday: {ANNUAL_DATE}")
    anniversary: AnnualDate = Field(None, description=f"An anniversary worth remembering: {ANNUAL_DATE}")
    source: Source = Field("walk_in", description=SOURCE)
    lifecycle_stage: Stage = Field("lead", description=STAGE)
    preferred_channel: PreferredChannel = Field("none", description=CHANNEL)
    notes: _text(10000) = Field("", description="Internal notes about the customer.")


class FieldValueIn(Schema):
    field_id: UUID = Field(title=CUSTOM_FIELD, description="The custom field's id.", json_schema_extra=A_FIELD)
    value: _text(10000) = Field(
        description="The value as text: a number, a date YYYY-MM-DD, true/false, one of a select's options, "
        "or empty to clear it."
    )


class CustomerPatchIn(CustomerRefIn):
    """Only the fields sent change; ``null`` leaves a field as it is (and clears a date)."""

    name: Name | None = Field(None, description="The new name.")
    email: Email | None = Field(None, description="The new email; empty clears it.")
    phone: str | None = Field(
        None, max_length=60, description="The new phone as typed; empty clears it."
    )
    tax_id: _text(32) | None = Field(None, description="The new tax id.")
    company_name: _text(200) | None = Field(None, description="The new company.")
    address: _text(255) | None = Field(None, description="The new street and number.")
    city: _text(100) | None = Field(None, description="The new city.")
    postal_code: _text(20) | None = Field(None, description="The new postal code.")
    country: Country | None = Field(
        None, description="The new country, as its ISO 3166 two-letter code."
    )
    avatar: _text(500) | None = Field(
        None, description="The new address (URL) of their picture."
    )
    birthday: AnnualDate = Field(None, description=f"The new birthday: {ANNUAL_DATE} Null or empty clears it.")
    anniversary: AnnualDate = Field(None, description=f"The new anniversary: {ANNUAL_DATE} Null or empty clears it.")
    source: Source | None = Field(None, description=SOURCE)
    lifecycle_stage: Stage | None = Field(None, description=STAGE)
    preferred_channel: PreferredChannel | None = Field(None, description=CHANNEL)
    notes: _text(10000) | None = Field(None, description="The new internal notes.")
    is_active: bool | None = Field(
        None, description="Whether the customer counts as active."
    )
    field_values: list[FieldValueIn] | None = Field(
        None,
        max_length=200,
        title=gettext_noop("Custom fields"),
        description="The custom fields' values. When sent, every required field must end up with a value.",
    )


class CustomerRow(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    email: str | None = EMAIL
    phone: str | None = PHONE
    tax_id: str = Field(description="Tax id.")
    company_name: str = Field(description="Company.")
    lifecycle_stage: Stage = Field(description=STAGE)
    source: Source = Field(description=SOURCE)
    is_active: bool = Field(description="Whether the customer counts as active.")
    total_purchases: int = Field(description="How many purchases they made.")
    total_spent: int = Field(description="How much they spent, in cents.", json_schema_extra={"money": True})
    last_purchase_at: datetime | None = Field(description="When they last bought.")


CustomerPage = Page[CustomerRow]


class CustomFieldValueOut(Schema):
    field_id: UUID = Field(description="The custom field's id.")
    name: str = Field(description="The field's name.")
    field_type: FieldType = Field(description="The field's type.")
    options: list[str] = Field(description="The choices of a select field.")
    is_required: bool = Field(description="Whether the field is required.")
    sort_order: int = Field(description="The field's place on the card.")
    value: str = Field(description="The customer's value; empty when unset.")


class CustomerDetailOut(CustomerRow):
    address: str = Field(description="Street and number.")
    city: str = Field(description="City.")
    postal_code: str = Field(description="Postal code.")
    country: str = Field(description="Country, ISO 3166 two-letter code.")
    avatar: str = Field(description="The address (URL) of their picture.")
    birthday: AnnualDate = Field(description=f"Birthday: {ANNUAL_DATE} Null when unknown.")
    anniversary: AnnualDate = Field(description=f"Anniversary: {ANNUAL_DATE} Null when unknown.")
    preferred_channel: PreferredChannel = Field(description=CHANNEL)
    notes: str = Field(description="Internal notes.")
    created_at: datetime = Field(description="When the card was created.")
    updated_at: datetime = Field(description="When the card last changed.")
    group_ids: list[UUID] = Field(description="The ids of its groups.")
    tag_ids: list[UUID] = Field(description="The ids of its tags.")
    custom_fields: list[CustomFieldValueOut] = Field(
        description="The active custom fields with its values."
    )
    consent: list[ConsentStateRow] = Field(
        description="Its consent: the last decision per purpose and channel."
    )
    marketing_consent: bool = Field(
        description="Whether some channel has marketing consent granted now."
    )
    consent_date: datetime | None = Field(
        description="When the latest marketing consent in force was given."
    )


class CustomerStatsOut(Schema):
    total: int = Field(description="How many customers there are.")
    active: int = Field(description="How many of them are active.")
    vip: int = Field(description="How many are at the vip stage.")
    total_revenue: int | None = Field(description="What they spent altogether, in cents; empty without the business totals.", json_schema_extra={"money": True, **BUSINESS_TOTALS})


class PhoneMatch(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    email: str | None = EMAIL
    phone: str | None = PHONE


class PhoneMatchOut(Schema):
    rows: list[PhoneMatch] = Field(
        description="The customers with that number, by name; empty if none."
    )
