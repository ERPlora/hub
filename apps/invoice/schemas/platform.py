import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict, model_validator

from apps.invoice.schemas import MAX_AMOUNT, _text

# ── ERPlora's own invoices, posted by the SaaS to its platform hub ──────────────────────────────────────────
# The body of ``POST /internal/platform/invoices``: ``platform_payload()`` of the SaaS's billing/services.py, field by
# field. A key the SaaS adds later is ignored; one it drops is a 422.


class _PlatformPart(Schema):
    model_config = ConfigDict(extra="ignore")


class PlatformRectificationIn(_PlatformPart):
    type: Literal["R1", "R2", "R3", "R4"] = Field(description="VeriFactu's type of the rectifying invoice.")
    reason: _text(255) = Field("", description="Why it rectifies (printed and declared).")


class PlatformBusinessIn(_PlatformPart):
    id: UUID | None = Field(None, description="The hub the invoice bills for.")
    name: _text(255) = Field("", description="Its name.")


class PlatformRecipientIn(_PlatformPart):
    name: _text(255) = Field("", description="The payer's name or company name.")
    tax_id: _text(50) = Field("", description="The payer's tax ID, empty without one.")
    tax_id_type: _text(20) = Field("", description="Stripe's type of that tax ID (eu_vat, gb_business_id…).")
    tax_id_verified: bool = Field(False, description="Whether VIES confirmed it.")
    vat_consultation_number: _text(64) = Field("", description="The VIES consultation that backed it.")
    address: _text(500) = Field("", description="The payer's address.")
    city: _text(100) = Field("", description="Its city.")
    postal_code: _text(20) = Field("", description="Its postal code.")
    country: _text(2) = Field("", description="Its country, ISO 3166-1 alpha-2.")
    email: _text(254) = Field("", description="Its e-mail.")


class PlatformLineIn(_PlatformPart):
    position: int = Field(ge=1, description="Its place on the invoice, from 1.")
    description: _text(255) = Field("", description="What it bills.")
    item_kind: _text(20) = Field("", description="plan or module.")
    item_slug: _text(80) = Field("", description="Which plan or module.")
    quantity: int = Field(1, ge=1, description="How many.")
    proration: bool = Field(False, description="Whether it is a proration.")
    period_start: dt.date | None = Field(None, description="First day it bills.")
    period_end: dt.date | None = Field(None, description="Last day it bills.")
    tax_category: _text(80) | None = Field(None, description="Its tax category.")
    tax_treatment: _text(20) = Field("", description="Its tax treatment; empty = the invoice's.")
    tax_rate: Decimal = Field(description="Its VAT rate, %.")
    net_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its base, in cents with its sign.")
    tax_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its tax, in cents with its sign.")
    total_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its total, in cents with its sign.")
    discount_cents: int = Field(
        0, ge=0, le=MAX_AMOUNT, description="Its discount without VAT, in cents; net_cents is already discounted."
    )


class PlatformRectifiedIn(_PlatformPart):
    id: UUID = Field(description="The SaaS's id of the invoice it rectifies.")
    number: _text(60) = Field("", description="Its number.")
    issued_on: dt.date | None = Field(None, description="Its issue date.")


class PlatformInvoiceIn(_PlatformPart):
    id: UUID = Field(description="The SaaS's id of the invoice: the key that makes posting it again harmless.")
    kind: Literal["invoice", "credit_note"] = Field(description="An invoice or a credit note (rectifying).")
    series: Literal["ERP", "ERPR"] = Field(description="ERP for invoices, ERPR for credit notes.")
    number: _text(60, min_length=1) = Field(description="Its number as the SaaS gave it, such as ERP-2026-00123.")
    issued_on: dt.date = Field(description="Its issue date.")
    stripe_invoice_id: _text(255) = Field("", description="Stripe's invoice it records.")
    stripe_source_id: _text(255) = Field("", description="What made a credit note in Stripe.")
    rectification: PlatformRectificationIn | None = Field(None, description="A credit note's type and reason.")
    currency: _text(3, min_length=3) = Field("EUR", description="ISO 4217 currency.")
    language: _text(8) = Field("es", description="The language its document is printed in.")
    net_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its base, in cents with its sign.")
    tax_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its tax, in cents with its sign.")
    total_cents: int = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Its total, in cents with its sign.")
    tax_treatment: _text(20, min_length=1) = Field(
        description="domestic, oss, reverse_charge, not_subject or exempt."
    )
    tax_country: _text(2) = Field("", description="The country whose tax applies.")
    tax_rate: Decimal = Field(description="Its VAT rate, %.")
    vat_included_reconciled: bool = Field(False, description="The tax was taken out of the amount charged.")
    vat_included_because_unverified: bool = Field(
        False, description="Charged with VAT because VIES did not confirm the tax ID."
    )
    business: PlatformBusinessIn = Field(description="The hub it bills for.")
    recipient: PlatformRecipientIn = Field(description="The payer, as it was on the issue date.")
    lines: list[PlatformLineIn] = Field(min_length=1, max_length=200, description="Its lines.")
    rectifies: PlatformRectifiedIn | None = Field(None, description="The invoice a credit note rectifies.")

    @model_validator(mode="after")
    def _credit_note_names_its_invoice(self):
        if self.kind == "credit_note" and (self.rectifies is None or self.rectification is None):
            raise ValueError("A credit note carries its rectification and the invoice it rectifies.")
        return self


class PlatformRefIn(Schema):
    id: UUID = Field(description="The SaaS's id of the invoice.")


class PlatformHealthIn(Schema):
    pass


class PlatformErrorOut(Schema):
    code: str = Field(description="The AEAT's code.")
    message: str = Field(description="The AEAT's message.")


class PlatformInvoiceOut(Schema):
    status: Literal["issuing", "issued", "accepted", "accepted_with_errors", "rejected"] = Field(
        description="issuing (no record yet), issued (sealed, on its way to the AEAT), or the AEAT's answer."
    )
    qr: str = Field(description="The AEAT's verification link of its record (its QR); empty while issuing.")
    error: PlatformErrorOut | None = Field(description="What the AEAT said of a rejected or flawed record.")
    already: bool = Field(False, description="True when it was issued before (nothing new was written).")


class PlatformDocumentOut(Schema):
    invoice_id: UUID
    number: str
    html: str = Field(description="Its A4 document, a whole HTML page in its own language.")


class PlatformHealthOut(Schema):
    ready: bool = Field(description="Whether the platform hub can issue ERPlora's invoices now.")
    detail: str = Field(description="What is missing, empty when ready.")
