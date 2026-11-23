"""What every schema of the customer app shares: text and choice fields, pages, the messages, titles and marks
of several topics, and naming a card, a group, a tag or a custom field by its id or as a person says it."""

import re
from datetime import date
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, BeforeValidator, StringConstraints, ValidationInfo, WithJsonSchema, field_validator
from pydantic_core import PydanticCustomError

from base.business import currency_decimals
from base.schemas.assistant import names, unless_given

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
CUSTOMER = gettext_noop("Customer")
CUSTOM_FIELD = gettext_noop("Custom field")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id. An open order is Sales's, which Customers does not require: ``customer.order.get`` asks Sales
# for its name, and without Sales the card leaves it out. A card said by its name beside its own card's id is neither
# read nor shown: the write takes the card by the id and never looks at the name (``unless_given``, hub#1272).
A_CUSTOMER = names("customer.customer.detail")
A_CUSTOMER_REFERENCE = names("customer.customer.detail", by="customer")
A_GROUP = names("customer.group.detail")
A_TAG = names("customer.tag.detail")
A_FIELD = names("customer.field.detail")
A_ORDER = names("customer.order.get", by="order_id")
# A card, a group, a tag or a custom field said in words in every other write: read as the write finds it, and said as
# said when the words fit none or several, as the merge does not (hub#1280). Beside its own record's id the write never
# looks at the words, and the card neither reads nor shows them (``unless_given``).
A_CUSTOMER_SAID = names("customer.customer.detail", by="customer", as_said=True)
A_GROUP_SAID = names("customer.group.detail", by="group", as_said=True)
A_TAG_SAID = names("customer.tag.detail", by="tag", as_said=True)
A_FIELD_SAID = names("customer.field.detail", by="field", as_said=True)
#: A group or a tag of the card by its id, each named on the card.
GroupId = Annotated[UUID, Field(json_schema_extra=A_GROUP)]
TagId = Annotated[UUID, Field(json_schema_extra=A_TAG)]


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


#: A day that comes back every year without its year, as vCard writes it: ``--03-14`` is the 14th of March.
YEARLESS_DAY = r"^--(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
_DAY = re.compile(r"(\d{4}|-)-(\d{2})-(\d{2})")


def annual_date(value: object) -> str:
    """A birthday or an anniversary as the card keeps it: ``YYYY-MM-DD``, or ``--MM-DD`` when the year is not known
    (the 29th of February too); none is empty. Refused as any wrong date, so it reads «Enter a valid date.». A ``date``
    is how a separate copy of the business taken while the card kept these as dates gives one back."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    text = value.strip() if isinstance(value, str) else ""
    if isinstance(value, str) and not text:
        return ""
    day = _DAY.fullmatch(text)
    try:
        if day is None:
            raise ValueError(text)
        date(2000 if day[1] == "-" else int(day[1]), int(day[2]), int(day[3]))
    except ValueError:
        raise PydanticCustomError("date_parsing", "Input should be a valid date") from None
    return text


AnnualDate = Annotated[
    str,
    BeforeValidator(annual_date),
    WithJsonSchema(
        {"anyOf": [{"type": "string", "format": "date"}, {"type": "string", "pattern": YEARLESS_DAY}, {"type": "null"}]}
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

ANNUAL_DATE = "YYYY-MM-DD, or --MM-DD when the year is not known (--03-14 is the 14th of March)."
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

    id: UUID | None = Field(None, title=CUSTOMER, description="The customer's id.", json_schema_extra=A_CUSTOMER)
    customer: Reference | None = Field(
        None,
        validate_default=True,
        description=CUSTOMER_REFERENCE,
        json_schema_extra=unless_given(A_CUSTOMER_SAID, "id"),
    )

    _named = field_validator("customer")(_named_unless("id", CUSTOMER_REF_MISSING))


class CustomerOfIn(Schema):
    """The card something belongs to: ``customer_id``, or its exact name, phone or email."""

    customer_id: UUID | None = Field(None, description="The customer's id.", json_schema_extra=A_CUSTOMER)
    customer: Reference | None = Field(
        None,
        validate_default=True,
        description=CUSTOMER_REFERENCE,
        json_schema_extra=unless_given(A_CUSTOMER_SAID, "customer_id"),
    )

    _named = field_validator("customer")(_named_unless("customer_id", CUSTOMER_REF_MISSING))


class GroupRefIn(Schema):
    id: UUID | None = Field(None, title=GROUP, description="The group's id.", json_schema_extra=A_GROUP)
    group: Reference | None = Field(
        None,
        validate_default=True,
        title=GROUP,
        description="The group's current name, when the id is not known.",
        json_schema_extra=unless_given(A_GROUP_SAID, "id"),
    )

    _named = field_validator("group")(_named_unless("id", GROUP_REF_MISSING))


class TagRefIn(Schema):
    id: UUID | None = Field(None, title=TAG, description="The tag's id.", json_schema_extra=A_TAG)
    tag: Reference | None = Field(
        None,
        validate_default=True,
        title=TAG,
        description="The tag's current name, when the id is not known.",
        json_schema_extra=unless_given(A_TAG_SAID, "id"),
    )

    _named = field_validator("tag")(_named_unless("id", TAG_REF_MISSING))


class FieldRefIn(Schema):
    id: UUID | None = Field(None, title=CUSTOM_FIELD, description="The custom field's id.", json_schema_extra=A_FIELD)
    field: Reference | None = Field(
        None,
        validate_default=True,
        description="The custom field's current name, when the id is not known.",
        json_schema_extra=unless_given(A_FIELD_SAID, "id"),
    )

    _named = field_validator("field")(_named_unless("id", FIELD_REF_MISSING))


class DeletedOut(Schema):
    id: UUID = Field(description="The id of what was deleted.")


def _decimals(currency: object) -> int | None:
    """The decimals the server counts ``currency`` in (CLDR: 2 in EUR, 0 in JPY); none without one, so the screen
    paints the amount in the business's currency (a record keeps the currency it was paid in)."""
    return currency_decimals(currency) if isinstance(currency, str) and currency else None
