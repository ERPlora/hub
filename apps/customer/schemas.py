"""Input and output schemas of the customer app's operations (OpenAPI, live params, 422 per field).

Every field has a description: these schemas are also the JSON Schema of the assistant's tools.
A customer can be named by its ``id`` or, when the id is not known (by voice, by text), by its exact
name, phone or email (``customer``); groups, tags and fields, by their name. Money is in cents.
"""

from datetime import date, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from apps.customer.models import Activity, Purchase
from base.business import currency_decimals

T = TypeVar("T")

#: The largest values of the columns behind ``sort_order`` (int4) and an amount (int8): beyond, a 422.
INT4_MAX = 2_147_483_647
INT8_MAX = 9_223_372_036_854_775_807

INVALID_EMAIL = _("Enter a valid email.")
UNKNOWN_COUNTRY = _("Choose a country from the list.")
CUSTOMER_REF_MISSING = _("Give the customer's id, or their name, phone or email.")
ABSORBED_REF_MISSING = _("Give the duplicate's id, or its name, phone or email.")
GROUP_REF_MISSING = _("Give the group's id or its name.")
TAG_REF_MISSING = _("Give the tag's id or its name.")
FIELD_REF_MISSING = _("Give the field's id or its name.")
OPTIONS_MISSING = _("Add at least one option.")
OWN_KIND = _("That kind is the customer app's own: use another one.")

# How the Customers screens name the data the models do not (the assistant's card names each datum by its title).
DUPLICATE_CUSTOMER = gettext_noop("Duplicate customer")
GROUPS = gettext_noop("Groups")
TAGS = gettext_noop("Tags")
GROUP = gettext_noop("Group")
TAG = gettext_noop("Tag")
GROUP_COLOR = gettext_noop("Group color")
TAG_COLOR = gettext_noop("Tag color")


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except ValidationError:
            raise ValueError(INVALID_EMAIL) from None
    return value


def country_code(value: str) -> str:
    """``value`` as an ISO 3166 alpha-2 code in capitals; empty stays empty; ``ValueError`` if no country."""
    code = value.upper()
    if code and pycountry.countries.get(alpha_2=code) is None:
        raise ValueError(UNKNOWN_COUNTRY)
    return code


def _text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254),
    AfterValidator(_email),
]
Country = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=60),
    AfterValidator(country_code),
]
Reference = _text(200)
Stage = Literal[
    "lead",
    "prospect",
    "first_purchase",
    "active",
    "at_risk",
    "dormant",
    "churned",
    "vip",
]
Source = Literal[
    "walk_in", "website", "phone", "referral", "social", "whatsapp", "import", "other"
]
PreferredChannel = Literal["none", "email", "sms", "whatsapp", "phone"]
FieldType = Literal["text", "number", "date", "boolean", "select", "textarea"]
ConsentChannel = Literal["email", "sms", "whatsapp", "phone", "postal"]
ConsentSource = Literal["counter", "web_form", "phone", "email", "import", "receipt"]
Purpose = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$"
    ),
]

STAGE = "The customer's stage: lead, prospect, first_purchase, active, at_risk, dormant, churned or vip."
SOURCE = "Where the customer came from: walk_in, website, phone, referral, social, whatsapp, import or other."
CHANNEL = (
    "The channel they prefer to be contacted by: none, email, sms, whatsapp or phone."
)


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
    offset: int = Field(description="How many rows were skipped.")


# ── References: an id, or what a person would say ───────────────────────────────────────────────


def _blank(value: str | None) -> bool:
    return not (value or "").strip()


def _named_unless(id_field: str, message):
    """A reference field's check: without the id, the reference must say something.

    A field validator (run on its default too), so the 422 lands under the reference's own field.
    """

    def check(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get(id_field) is None and _blank(value):
            raise ValueError(message)
        return value

    return check


CUSTOMER_REFERENCE = "The customer's exact name, phone or email, when the id is not known."


class CustomerRefIn(Schema):
    """A card by its ``id`` or by its exact name, phone or email (``customer``); the id wins."""

    id: UUID | None = Field(None, description="The customer's id.")
    customer: Reference | None = Field(None, validate_default=True, description=CUSTOMER_REFERENCE)

    _named = field_validator("customer")(_named_unless("id", CUSTOMER_REF_MISSING))


class CustomerOfIn(Schema):
    """The card something belongs to: ``customer_id``, or its exact name, phone or email."""

    customer_id: UUID | None = Field(None, description="The customer's id.")
    customer: Reference | None = Field(None, validate_default=True, description=CUSTOMER_REFERENCE)

    _named = field_validator("customer")(_named_unless("customer_id", CUSTOMER_REF_MISSING))


class GroupRefIn(Schema):
    id: UUID | None = Field(None, description="The group's id.")
    group: Reference | None = Field(
        None, validate_default=True, title=GROUP, description="The group's current name, when the id is not known."
    )

    _named = field_validator("group")(_named_unless("id", GROUP_REF_MISSING))


class TagRefIn(Schema):
    id: UUID | None = Field(None, description="The tag's id.")
    tag: Reference | None = Field(
        None, validate_default=True, title=TAG, description="The tag's current name, when the id is not known."
    )

    _named = field_validator("tag")(_named_unless("id", TAG_REF_MISSING))


class FieldRefIn(Schema):
    id: UUID | None = Field(None, description="The custom field's id.")
    field: Reference | None = Field(
        None, validate_default=True, description="The custom field's current name, when the id is not known."
    )

    _named = field_validator("field")(_named_unless("id", FIELD_REF_MISSING))


# ── Customers: inputs ───────────────────────────────────────────────────────────────────────────


CustomerSort = Literal[
    "name",
    "email",
    "phone",
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
        description="Text to look for in the name, email, phone, tax id and company, ignoring case and "
        "accents; a phone is found however it is typed.",
    )
    name: str | None = Field(
        None, max_length=200, description="Only customers whose name contains this."
    )
    email: str | None = Field(
        None, max_length=254, description="Only customers whose email contains this."
    )
    phone: str | None = Field(
        None,
        max_length=60,
        description="Only customers whose phone contains these digits.",
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


class CustomerExportIn(CustomerFilters):
    pass


class CustomerStatsIn(Schema):
    pass


class ByPhoneIn(Schema):
    phone: str | None = Field(
        None,
        max_length=60,
        description="The number as it was typed or as WhatsApp gives it (digits without +).",
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
    birthday: date | None = Field(None, description="Their birthday.")
    anniversary: date | None = Field(
        None, description="An anniversary worth remembering."
    )
    source: Source = Field("walk_in", description=SOURCE)
    lifecycle_stage: Stage = Field("lead", description=STAGE)
    preferred_channel: PreferredChannel = Field("none", description=CHANNEL)
    notes: _text(10000) = Field("", description="Internal notes about the customer.")


class FieldValueIn(Schema):
    field_id: UUID = Field(description="The custom field's id.")
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
    birthday: date | None = Field(None, description="The new birthday; null clears it.")
    anniversary: date | None = Field(
        None, description="The new anniversary; null clears it."
    )
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


class ImportRowIn(Schema):
    """One row of a CSV, as text: the service checks each row on its own."""

    name: str = Field("", max_length=1000, description="Name (required on each row).")
    email: str = Field("", max_length=1000, description="Email.")
    phone: str = Field("", max_length=1000, description="Phone as typed.")
    tax_id: str = Field("", max_length=1000, description="Tax id.")
    company_name: str = Field("", max_length=1000, description="Company.")
    address: str = Field("", max_length=1000, description="Street and number.")
    city: str = Field("", max_length=1000, description="City.")
    postal_code: str = Field("", max_length=1000, description="Postal code.")
    country: str = Field(
        "", max_length=1000, description="Country, as its two-letter code."
    )
    avatar: str = Field(
        "", max_length=1000, description="Address (URL) of the picture."
    )
    birthday: str = Field("", max_length=1000, description="Birthday, YYYY-MM-DD.")
    anniversary: str = Field(
        "", max_length=1000, description="Anniversary, YYYY-MM-DD."
    )
    lifecycle_stage: str = Field(
        "", max_length=1000, description=f"Stage; empty is active. {STAGE}"
    )
    source: str = Field(
        "", max_length=1000, description=f"Source; empty is import. {SOURCE}"
    )
    preferred_channel: str = Field("", max_length=1000, description=CHANNEL)
    notes: str = Field("", max_length=10000, description="Internal notes.")


class ImportIn(Schema):
    rows: list[ImportRowIn] = Field(
        min_length=1,
        max_length=50,
        title=gettext_noop("Rows to import"),
        description="One to fifty rows of the file.",
    )


class SetGroupsIn(CustomerRefIn):
    group_ids: list[UUID] = Field(
        [], max_length=200, title=GROUPS, description="The ids of the groups the customer is in."
    )
    groups: list[Reference] = Field(
        [], max_length=200, description="The names of the groups the customer is in."
    )


class SetTagsIn(CustomerRefIn):
    tag_ids: list[UUID] = Field(
        [], max_length=200, title=TAGS, description="The ids of the tags the customer has."
    )
    tags: list[Reference] = Field(
        [], max_length=200, description="The names of the tags the customer has."
    )


class MergeIn(CustomerRefIn):
    """``id``/``customer`` is the card that stays; ``absorbed_id``/``absorbed`` the duplicate."""

    absorbed_id: UUID | None = Field(
        None, title=DUPLICATE_CUSTOMER, description="The duplicate's id: it is merged into the other card."
    )
    absorbed: Reference | None = Field(
        None,
        validate_default=True,
        title=DUPLICATE_CUSTOMER,
        description="The duplicate's exact name, phone or email.",
    )

    _absorbed_named = field_validator("absorbed")(_named_unless("absorbed_id", ABSORBED_REF_MISSING))


class EraseIn(CustomerRefIn):
    reason: _text(500) = Field(
        "", description="Why the data is erased; kept in the audit entry."
    )


# ── Notes, activity, consent, orders and purchases: inputs ───────────────────────────────────────


class NoteIn(CustomerOfIn):
    content: _text(5000, 1) = Field(title=gettext_noop("Note"), description="The note.")
    title: _text(200) = Field(
        "", description="A title of the caller's own; empty shows «Note added»."
    )
    author_name: _text(200) = Field(
        "",
        title=gettext_noop("Author"),
        description="The author's name, when it is not the person signed in.",
    )


def _own_kinds() -> set[str]:
    return set(Activity.Kind.values)


class ActivityIn(CustomerOfIn):
    kind: str = Field(
        max_length=40,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$",
        description="The caller's key for the entry, e.g. appointment.visit.",
    )
    title: _text(200, 1) = Field(
        description="The entry's title, in the caller's words."
    )
    text: _text(5000) = Field("", description="Details of the entry.")
    data: dict[str, Any] = Field(
        {}, description="Data of the caller's own about the entry."
    )
    related_id: _text(64) = Field(
        "", description="The id of what the entry is about in the calling app."
    )
    related_type: _text(40) = Field(
        "", description="The type of what the entry is about, e.g. appointment."
    )

    @field_validator("kind")
    @classmethod
    def _not_ours(cls, value: str) -> str:
        if value in _own_kinds():
            raise ValueError(OWN_KIND)
        return value


class ActivityListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the entries."
    )


class ConsentGrantIn(CustomerOfIn):
    channel: ConsentChannel = Field(
        description="The channel: email, sms, whatsapp, phone or postal."
    )
    notice_text: _text(2000, 1) = Field(
        description="The exact words shown to the customer, stored as proof."
    )
    notice_version: _text(60) = Field("", description="The version of those words.")
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


class OrderLinkIn(Schema):
    order_id: UUID = Field(title=gettext_noop("Open order"), description="The open order's id in the sale app.")
    customer_id: UUID | None = Field(
        None, description="The customer's id; without a customer the link is removed."
    )
    customer: Reference | None = Field(
        None, description="The customer's exact name, phone or email."
    )


class OrderIn(Schema):
    order_id: UUID = Field(description="The order's id in the sale app.")


class OrderListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=60, description="A piece of the order's id."
    )


PurchaseSort = Literal["recorded_at", "amount", "status"]


class PurchaseListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=60, description="A piece of the sale's id."
    )
    status: Literal["confirmed", "voided", "refunded"] | None = Field(
        None, description="Only paid (confirmed), voided or refund lines."
    )
    recorded_from: date | None = Field(
        None, description="Only purchases on or after this day."
    )
    recorded_to: date | None = Field(
        None, description="Only purchases on or before this day."
    )
    sort: PurchaseSort = Field(
        "recorded_at", description="The column to order by; the id breaks ties."
    )
    descending: bool = Field(True, description="Newest (or highest) first.")


class DivergencesIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the customers' names."
    )


class PurchaseRecordIn(Schema):
    customer_id: UUID | None = Field(
        None, description="The sale's customer; without one nothing is recorded."
    )
    sale_id: UUID | None = Field(
        None,
        description="The sale's id; the same sale counts once. Empty: a manual entry.",
    )
    total: int = Field(ge=0, le=INT8_MAX, strict=True, description="The sale's total, in whole cents.")
    currency: _text(3) = Field("", description="The ISO 4217 currency of the sale.")
    purchased_at: datetime | None = Field(
        None, description="When the sale was paid, if not now."
    )


class PurchaseRefundIn(Schema):
    sale_id: UUID = Field(description="The refunded sale's id.")
    refund_id: UUID = Field(description="The refund's id; the same refund counts once.")
    total: int = Field(ge=0, le=INT8_MAX, strict=True, description="What came back, in whole cents.")
    reason: _text(500) = Field("", description="Why it was refunded.")
    refunded_at: datetime | None = Field(None, description="When it was refunded, if not now.")


class PurchaseVoidIn(Schema):
    sale_id: UUID = Field(description="The voided sale's id.")
    reason: _text(500) = Field("", description="Why the sale was voided.")


# ── Groups, tags and custom fields: inputs ──────────────────────────────────────────────────────


class GroupListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Text to look for in the name and description.",
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) groups."
    )
    color: str | None = Field(
        None, max_length=20, description="Only groups of this color."
    )
    customers_min: int | None = Field(
        None, ge=0, description="Only groups with at least this many customers."
    )
    customers_max: int | None = Field(
        None, ge=0, description="Only groups with at most this many customers."
    )
    sort: Literal[
        "name", "description", "color", "sort_order", "is_active", "customer_count"
    ] = Field("name", description="The column to order by; the id breaks ties.")
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


class GroupIn(Schema):
    name: _text(100, 1) = Field(
        description="The group's name, unique among the active groups."
    )
    description: _text(1000) = Field("", description="What the group is for.")
    color: _text(20, 1) = Field(
        "primary", title=GROUP_COLOR, description="The group's color, a name of the theme (primary)."
    )
    sort_order: int = Field(0, ge=0, le=INT4_MAX, description="Its place in the lists, lowest first.")


class GroupPatchIn(GroupRefIn):
    name: _text(100, 1) | None = Field(None, description="The new name.")
    description: _text(1000) | None = Field(None, description="The new description.")
    color: _text(20, 1) | None = Field(None, title=GROUP_COLOR, description="The new color.")
    sort_order: int | None = Field(None, ge=0, le=INT4_MAX, description="The new place in the lists.")
    is_active: bool | None = Field(
        None, description="Whether the group is offered on the cards."
    )


class TagListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the name."
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) tags."
    )
    color: str | None = Field(
        None, max_length=20, description="Only tags of this color."
    )
    sort: Literal["name", "color", "is_active", "customer_count"] = Field(
        "name", description="The column to order by; the id breaks ties."
    )
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


class TagIn(Schema):
    name: _text(60, 1) = Field(
        description="The tag's name, unique among the active tags."
    )
    color: _text(20, 1) = Field(
        "primary", title=TAG_COLOR, description="The tag's color, a name of the theme (primary)."
    )


class TagPatchIn(TagRefIn):
    name: _text(60, 1) | None = Field(None, description="The new name.")
    color: _text(20, 1) | None = Field(None, title=TAG_COLOR, description="The new color.")
    is_active: bool | None = Field(
        None, description="Whether the tag is offered on the cards."
    )


class FieldListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the name."
    )
    field_type: FieldType | None = Field(None, description="Only fields of this type.")
    is_required: bool | None = Field(
        None, description="Only required (true) or optional (false) fields."
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) fields."
    )
    sort: Literal["name", "field_type", "is_required", "sort_order", "is_active"] = (
        Field("name", description="The column to order by; the id breaks ties.")
    )
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


def _options(value: list[str], info: ValidationInfo) -> list[str]:
    """A select's options, trimmed, without empties or repeats; no options for the other types."""
    kept = list(dict.fromkeys(option.strip() for option in value if option.strip()))
    field_type = info.data.get("field_type")
    if field_type == "select" and not kept:
        raise ValueError(OPTIONS_MISSING)
    if field_type not in (None, "select"):
        return []
    return kept


Options = Annotated[
    list[Annotated[str, StringConstraints(max_length=100)]], Field(max_length=100)
]


class FieldIn(Schema):
    name: _text(100, 1) = Field(
        description="The field's name, unique among the active fields."
    )
    field_type: FieldType = Field(
        "text", description="Its type: text, number, date, boolean, select or textarea."
    )
    options: Options = Field([], description="The choices of a select field.")
    is_required: bool = Field(
        False, description="Whether every card must have a value when saved in full."
    )
    sort_order: int = Field(0, ge=0, le=INT4_MAX, description="Its place on the card, lowest first.")

    _check_options = field_validator("options")(_options)


class FieldPatchIn(FieldRefIn):
    name: _text(100, 1) | None = Field(None, description="The new name.")
    field_type: FieldType | None = Field(
        None, description="The new type; not possible once cards have values."
    )
    options: Options | None = Field(
        None, description="The new choices of a select field."
    )
    is_required: bool | None = Field(None, description="Whether it is required.")
    sort_order: int | None = Field(None, ge=0, le=INT4_MAX, description="The new place on the card.")
    is_active: bool | None = Field(
        None, description="Whether the field is shown on the cards."
    )

    @field_validator("options")
    @classmethod
    def _check_options(
        cls, value: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        if value is None:
            return None
        # The type may come from the stored field: the service checks a select keeps an option.
        return list(dict.fromkeys(option.strip() for option in value if option.strip()))


# ── Outputs ─────────────────────────────────────────────────────────────────────────────────────


class CustomerRow(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    email: str = Field(description="Email.")
    phone: str = Field(description="Phone, in international format.")
    tax_id: str = Field(description="Tax id.")
    company_name: str = Field(description="Company.")
    lifecycle_stage: Stage = Field(description=STAGE)
    source: Source = Field(description=SOURCE)
    is_active: bool = Field(description="Whether the customer counts as active.")
    total_purchases: int = Field(description="How many purchases they made.")
    total_spent: int = Field(description="How much they spent, in cents.")
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


class ConsentStateRow(Schema):
    purpose: str = Field(description="What the consent is for.")
    channel: ConsentChannel | Literal[""] = Field(
        description="The channel; empty for a permission that is not about reaching the person (health data)."
    )
    state: Literal["granted", "withdrawn"] = Field(
        description="The last decision: granted or withdrawn."
    )
    contact_point: str = Field(description="The address it was given or withdrawn for.")
    source: ConsentSource = Field(description="Where it was decided.")
    notice_version: str = Field(description="The version of the words shown.")
    occurred_at: datetime = Field(description="When the customer said it.")
    recorded_by: str = Field(description="Who wrote it down.")
    evidence: str = Field(description="The outside reference that backs it.")


class CustomerDetailOut(CustomerRow):
    address: str = Field(description="Street and number.")
    city: str = Field(description="City.")
    postal_code: str = Field(description="Postal code.")
    country: str = Field(description="Country, ISO 3166 two-letter code.")
    avatar: str = Field(description="The address (URL) of their picture.")
    birthday: date | None = Field(description="Birthday.")
    anniversary: date | None = Field(description="Anniversary.")
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
    total_revenue: int = Field(description="What they spent altogether, in cents.")


class PhoneMatch(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    email: str = Field(description="Email.")
    phone: str = Field(description="Phone, in international format.")


class PhoneMatchOut(Schema):
    rows: list[PhoneMatch] = Field(
        description="The customers with that number, by name; empty if none."
    )


class ExportOut(Schema):
    filename: str = Field(description="The file's name.")
    content_type: str = Field(description="The file's type.")
    rows: int = Field(description="How many customers it holds.")
    csv: str = Field(description="The file's contents, CSV with a header row.")


class ImportRowOut(Schema):
    index: int = Field(description="The row's position in the block sent, from 0.")
    id: UUID | None = Field(
        description="The new customer's id; empty when the row was skipped."
    )
    errors: dict[str, str] = Field(description="Why the row was skipped, per column.")
    warnings: dict[str, str] = Field(
        description="What to review on a created row, per column."
    )


class ImportOut(Schema):
    created: int = Field(description="How many rows became customers.")
    skipped: int = Field(description="How many rows were skipped.")
    rows: list[ImportRowOut] = Field(description="The result of each row.")


class DeletedOut(Schema):
    id: UUID = Field(description="The id of what was deleted.")


class ErasedOut(Schema):
    id: UUID = Field(
        description="The id of the customer whose personal data was erased."
    )


def _decimals(currency: object) -> int | None:
    """The decimals the server counts ``currency`` in (CLDR: 2 in EUR, 0 in JPY); none without one, so the screen
    paints the amount in the business's currency (a record keeps the currency it was paid in)."""
    return currency_decimals(currency) if isinstance(currency, str) and currency else None


class ActivityRow(Schema):
    id: UUID = Field(description="The entry's id.")
    customer_id: UUID = Field(description="The customer's id.")
    kind: str = Field(
        description="The entry's key: note_added, purchase_recorded, consent_granted… or another app's."
    )
    title: str = Field(description="Its title, when the writer gave one.")
    text: str = Field(description="The note, the words shown or the reason.")
    data: dict[str, Any] = Field(
        description="Its data: amounts, channel, the merged card…"
    )
    currency_decimals: int | None = Field(
        description="The decimals of the currency its data carries, as the server counts them (2 in EUR, 0 in "
        "JPY); empty when it carries none."
    )
    related_id: str = Field(description="The id of what it is about.")
    related_type: str = Field(description="The type of what it is about.")
    actor: str = Field(description="Who did it.")
    created_at: datetime = Field(description="When.")

    @staticmethod
    def resolve_currency_decimals(entry: Activity) -> int | None:
        return _decimals((entry.data or {}).get("currency"))


ActivityPage = Page[ActivityRow]


class ConsentRow(Schema):
    id: UUID = Field(description="The fact's id.")
    customer_id: UUID = Field(description="The customer's id.")
    purpose: str = Field(description="What it is for.")
    channel: ConsentChannel | Literal[""] = Field(
        description="The channel; empty for a permission that is not about reaching the person (health data)."
    )
    state: Literal["granted", "withdrawn"] = Field(description="What was decided.")
    contact_point: str = Field(description="The address it was decided for.")
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


class OrderCustomerOut(Schema):
    order_id: UUID = Field(description="The order's id.")
    customer_id: UUID | None = Field(
        description="Its customer; empty when it has none."
    )


class OrderRow(Schema):
    order_id: UUID = Field(description="The order's id.")
    customer_id: UUID = Field(description="The customer's id.")
    linked_at: datetime = Field(description="When the customer was put on the order.")


OrderPage = Page[OrderRow]


class PurchaseRow(Schema):
    id: UUID = Field(description="The entry's id.")
    customer_id: UUID = Field(description="The customer's id.")
    sale_id: UUID | None = Field(description="The sale's id; empty for a manual entry.")
    amount: int = Field(description="The amount, in cents; negative on a refund line.")
    currency: str = Field(description="The currency.")
    currency_decimals: int | None = Field(
        description="The decimals of its currency as the server counts them (0 in JPY); empty without a currency."
    )
    status: Literal["confirmed", "voided", "refunded"] = Field(
        description="Paid (confirmed), voided, or a refund of the sale (refunded)."
    )
    recorded_at: datetime = Field(description="When it was paid.")
    voided_at: datetime | None = Field(description="When it was voided.")
    void_reason: str = Field(description="Why it was voided.")

    @staticmethod
    def resolve_currency_decimals(purchase: Purchase) -> int | None:
        return _decimals(purchase.currency)


PurchasePage = Page[PurchaseRow]


class DivergenceRow(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    total_purchases: int = Field(description="Purchases on the card.")
    total_spent: int = Field(description="Spent on the card, in cents.")
    ledger_purchases: int = Field(description="Paid purchases in its history.")
    ledger_spent: int = Field(description="Paid amount in its history, in cents.")


DivergencePage = Page[DivergenceRow]


class PurchaseRecordOut(Schema):
    sale_id: UUID | None = Field(description="The sale's id.")
    recorded: bool = Field(
        description="Whether it was recorded now (false: no customer, not live, or already in)."
    )


class PurchaseRefundOut(Schema):
    sale_id: UUID = Field(description="The sale's id.")
    refund_id: UUID = Field(description="The refund's id.")
    refunded: bool = Field(
        description="Whether it was recorded now (false: the sale is not on a card, voided, or the refund already in)."
    )


class PurchaseVoidOut(Schema):
    sale_id: UUID = Field(description="The sale's id.")
    voided: bool = Field(
        description="Whether it was voided now (false: unknown or already voided)."
    )


class GroupRow(Schema):
    id: UUID = Field(description="The group's id.")
    name: str = Field(description="Name.")
    description: str = Field(description="Description.")
    color: str = Field(description="Color.")
    sort_order: int = Field(description="Place in the lists.")
    is_active: bool = Field(description="Whether it is offered on the cards.")
    customer_count: int = Field(description="How many customers are in it.")


GroupPage = Page[GroupRow]


class TagRow(Schema):
    id: UUID = Field(description="The tag's id.")
    name: str = Field(description="Name.")
    color: str = Field(description="Color.")
    is_active: bool = Field(description="Whether it is offered on the cards.")
    customer_count: int = Field(description="How many customers have it.")


TagPage = Page[TagRow]


class FieldRow(Schema):
    id: UUID = Field(description="The field's id.")
    name: str = Field(description="Name.")
    field_type: FieldType = Field(description="Type.")
    options: list[str] = Field(description="The choices of a select field.")
    is_required: bool = Field(description="Whether it is required.")
    sort_order: int = Field(description="Place on the card.")
    is_active: bool = Field(description="Whether it is shown on the cards.")


FieldPage = Page[FieldRow]


# Health data (CUSTOMER-F32): its own block, never on the card, the list, the export or the assistant.

HealthTestResult = Literal["", "negative", "positive"]


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
