"""Input and output schemas of the payment app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in whole minor units of the payment's currency (cents in euros), always above 0. A method is named by
its id or, as a person says it (assistant, voice), by its name; a payment by its id or its reference
(``PAY-20261014-0003``). Every input refuses a field it does not declare; an edit changes only the
fields it sends.
"""

import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator
from stdnum import iban as iban_number
from stdnum.exceptions import ValidationError as NumberError

from apps.payment.models import (
    BENEFICIARY_MAX_LENGTH,
    INVOICE_REF_MAX_LENGTH,
    NAME_MAX_LENGTH,
)

T = TypeVar("T")

#: Ninety-nine billion euros in cents: far above any payment, inside a bigint.
MAX_AMOUNT = 9_999_999_999_999
CONCEPT_MAX_LENGTH = 1000
REASON_MAX_LENGTH = 500

AMOUNT_NOT_POSITIVE = _("The amount of a payment must be greater than 0.")
IBAN_INVALID = _(
    "That IBAN is not valid: check the country, the check digits and the length."
)
CURRENCY_UNKNOWN = _("That is not a currency code (ISO 4217, such as EUR).")
SAY_WHICH_METHOD = _("Say which payment method: its id, or its name.")
SAY_WHICH_PAYMENT = _("Say which payment: its id, or its reference.")
REASON_REQUIRED = _(
    "Say why this payment is cancelled: the reason stays on the payment."
)

MethodType = Literal["cash", "transfer", "card", "sepa", "check", "other"]
PaymentStatus = Literal["draft", "approved", "sent", "completed", "cancelled"]
MethodSort = Literal[
    "name",
    "-name",
    "method_type",
    "-method_type",
    "bank_account_ref",
    "-bank_account_ref",
    "is_active",
    "-is_active",
]
PaymentSort = Literal[
    "reference",
    "-reference",
    "payment_date",
    "-payment_date",
    "beneficiary_name",
    "-beneficiary_name",
    "amount",
    "-amount",
    "currency",
    "-currency",
    "status",
    "-status",
    "method_name",
    "-method_name",
    "created_at",
    "-created_at",
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(NAME_MAX_LENGTH, 1)
Said = _text(200, 1)
Beneficiary = _text(BENEFICIARY_MAX_LENGTH, 1)


def _tidy(name: str) -> str:
    """A name as it is kept: single spaces (two names that differ only in spaces are the same name)."""
    return " ".join(name.split())


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


# ── Methods ─────────────────────────────────────────────────────────────────────────────────────


class MethodRefIn(In):
    id: UUID | None = Field(None, description="The payment method's id.")
    method: Said | None = Field(
        None,
        description="The payment method's name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _said(self):
        if self.id is None and self.method is None:
            raise ValueError(str(SAY_WHICH_METHOD))
        return self


class MethodListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Part of the name or of the account."
    )
    method_type: MethodType | None = Field(
        None,
        description="Only this type: cash, transfer, card, sepa, check or other.",
    )
    is_active: bool | None = Field(
        None,
        description="true: only the active ones (the ones a new payment may use); false: only the "
        "deactivated ones. Without it, all.",
    )
    sort: MethodSort = Field("name", description="Order; a leading '-' reverses it.")


class MethodIn(In):
    name: Name = Field(
        description="What the business calls this account, unique (e.g. «BBVA account», «Cash drawer»)."
    )
    method_type: MethodType = Field(
        "transfer",
        description="Where the money leaves from: cash, transfer (a bank account), card, sepa, check or "
        "other.",
    )
    bank_account_ref: _text(NAME_MAX_LENGTH) = Field(
        "",
        description="A reference of the bank account (e.g. the last digits of its IBAN); may be empty.",
    )

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str) -> str:
        return _tidy(value)


class MethodPatchIn(MethodRefIn):
    """Only the fields sent change."""

    name: Name | None = Field(None, description="The new name, unique.")
    method_type: MethodType | None = Field(
        None, description="The new type: cash, transfer, card, sepa, check or other."
    )
    bank_account_ref: _text(NAME_MAX_LENGTH) | None = Field(
        None, description="The new account reference; an empty text clears it."
    )

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str | None) -> str | None:
        return _tidy(value) if value is not None else None


class MethodOut(Schema):
    id: UUID = Field(description="The method's id.")
    name: str = Field(description="Its name.")
    method_type: MethodType = Field(description="Its type.")
    bank_account_ref: str = Field(description="Its account reference; may be empty.")
    is_active: bool = Field(description="Whether a new payment may use it.")
    created_at: dt.datetime = Field(description="When it was created.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class MethodPage(Page[MethodOut]):
    pass


# ── Payments ────────────────────────────────────────────────────────────────────────────────────


class PaymentRefIn(In):
    id: UUID | None = Field(None, description="The payment's id.")
    reference: Said | None = Field(
        None,
        description="The payment's reference (e.g. PAY-20261014-0003), when its id is not known.",
    )

    @field_validator("reference")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _said(self):
        if self.id is None and self.reference is None:
            raise ValueError(str(SAY_WHICH_PAYMENT))
        return self


class CancelIn(PaymentRefIn):
    reason: Annotated[str, StringConstraints(max_length=REASON_MAX_LENGTH)] = Field(
        description="Why the payment is cancelled; required, it stays on the payment."
    )

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(str(REASON_REQUIRED))
        return value.strip()


class PaymentListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the reference, the beneficiary or the supplier's invoice number.",
    )
    reference: str | None = Field(
        None,
        max_length=200,
        description="Part of the reference (its last digits, its date).",
    )
    beneficiary_name: str | None = Field(
        None, max_length=200, description="Part of the beneficiary's name."
    )
    concept: str | None = Field(
        None, max_length=200, description="Part of the concept."
    )
    method_id: UUID | None = Field(
        None, description="Only the payments from this method."
    )
    method: str | None = Field(
        None,
        max_length=200,
        description="Only the payments from the method with this name.",
    )
    status: PaymentStatus | None = Field(
        None,
        description="Only this status: draft, approved, sent, completed or cancelled.",
    )
    currency: str | None = Field(
        None, max_length=3, description="Only this currency (ISO 4217, e.g. EUR)."
    )
    beneficiary_iban: str | None = Field(
        None, max_length=64, description="Only the payments to this IBAN (whole)."
    )
    supplier_invoice_ref: str | None = Field(
        None,
        max_length=INVOICE_REF_MAX_LENGTH,
        description="Only the payments of this supplier's invoice number (whole).",
    )
    payment_date_from: dt.date | None = Field(
        None, description="Paid on this day or later (YYYY-MM-DD)."
    )
    payment_date_to: dt.date | None = Field(
        None, description="Paid on this day or earlier (YYYY-MM-DD)."
    )
    amount_min: int | None = Field(
        None, ge=0, description="Lowest amount, in minor units (cents in euros)."
    )
    amount_max: int | None = Field(
        None, ge=0, description="Highest amount, in minor units (cents in euros)."
    )
    sort: PaymentSort = Field(
        "-payment_date",
        description="Order; a leading '-' reverses it. By default, the newest payment date first.",
    )


class PaymentIn(In):
    method_id: UUID | None = Field(
        None, description="The id of the active payment method the money leaves from."
    )
    method: Said | None = Field(
        None,
        description="The name of the active payment method, when its id is not known (e.g. «Cash drawer»).",
    )
    payment_date: dt.date = Field(
        description="The day of the payment (YYYY-MM-DD); not the day it is recorded."
    )
    amount: int = Field(
        le=MAX_AMOUNT,
        description="The amount in minor units of the currency (cents in euros: 12,50 € is 1250), above 0.",
    )
    beneficiary_name: Beneficiary = Field(
        description="Who receives the money (a supplier, a person)."
    )
    beneficiary_iban: str = Field(
        "",
        max_length=64,
        description="The beneficiary's IBAN, if known; it is checked and kept without spaces.",
    )
    concept: _text(CONCEPT_MAX_LENGTH) = Field(
        "", description="What the payment is for; may be empty."
    )
    supplier_invoice_ref: _text(INVOICE_REF_MAX_LENGTH) = Field(
        "", description="The supplier's invoice number it pays, if any (free text)."
    )
    currency: str | None = Field(
        None,
        max_length=8,
        description="ISO 4217 code (e.g. EUR); without it, the business's currency.",
    )
    idempotency_key: UUID | None = Field(
        None,
        description="A key the caller makes once per payment it means to record. Sent again with the same "
        "payment (a retry, a double tap), it answers the payment already recorded instead of recording "
        "another one; with another payment, it is refused.",
    )

    @field_validator("amount")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(str(AMOUNT_NOT_POSITIVE))
        return value

    @field_validator("beneficiary_iban")
    @classmethod
    def _iban(cls, value: str) -> str:
        if not value.strip():
            return ""
        try:
            return iban_number.validate(value)
        except NumberError:
            raise ValueError(str(IBAN_INVALID)) from None

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        code = (value or "").strip().upper()
        if not code:
            return None
        if len(code) != 3 or pycountry.currencies.get(alpha_3=code) is None:
            raise ValueError(str(CURRENCY_UNKNOWN))
        return code

    @model_validator(mode="after")
    def _said(self):
        if self.method_id is None and self.method is None:
            raise ValueError(str(SAY_WHICH_METHOD))
        return self


class PaymentOut(Schema):
    id: UUID = Field(description="The payment's id.")
    reference: str = Field(description="Its reference, PAY-YYYYMMDD-NNNN.")
    method_id: UUID = Field(description="The id of the method it is paid from.")
    method_name: str = Field(description="The name of that method.")
    payment_date: dt.date = Field(description="The day of the payment.")
    amount: int = Field(description="The amount in minor units of its currency.")
    currency: str = Field(description="Its currency (ISO 4217).")
    currency_decimals: int = Field(
        description="The decimals of its currency as the server counts them (2 in EUR and HUF, 0 in JPY)."
    )
    beneficiary_name: str = Field(description="Who receives it.")
    beneficiary_iban: str = Field(description="The beneficiary's IBAN; may be empty.")
    concept: str = Field(description="What it is for; may be empty.")
    status: PaymentStatus = Field(description="Where it is in its ladder.")
    supplier_invoice_ref: str = Field(
        description="The supplier's invoice number; may be empty."
    )
    cancel_reason: str = Field(
        description="Why it was cancelled; empty unless cancelled."
    )
    approved_by: str = Field(description="Who approved it; empty until approved.")
    approved_at: dt.datetime | None = Field(description="When it was approved.")
    sent_at: dt.datetime | None = Field(description="When it was marked as sent.")
    completed_at: dt.datetime | None = Field(description="When it was marked as completed.")
    cancelled_by: str = Field(description="Who cancelled it; empty unless cancelled.")
    cancelled_at: dt.datetime | None = Field(description="When it was cancelled.")
    created_by: str = Field(description="Who recorded it.")
    updated_by: str = Field(description="Who changed it last.")
    created_at: dt.datetime = Field(description="When it was recorded.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class PaymentPage(Page[PaymentOut]):
    pass
