"""Schemas of the till's settings, payment methods, departments (the open price's sections) and quick notes."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.sale.schemas.fields import (
    A_DEPARTMENT,
    A_QUICK_NOTE,
    SAY_WHICH_DEPARTMENT_ROW,
    SAY_WHICH_QUICK_NOTE,
    Closed,
    DocumentType,
    MethodType,
    Page,
    PageIn,
    SortDir,
    _text,
)
from apps.tax.schemas import A_TAX_CATEGORY


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


class SettingsFields(Schema):
    allow_cash: bool = Field(description="Cash methods may be used to charge.")
    allow_card: bool = Field(description="Card methods may be used to charge.")
    allow_transfer: bool = Field(
        description="Bank transfer methods may be used to charge."
    )
    show_products: bool = Field(description="The till offers Inventory's products.")
    show_services: bool = Field(
        description="The till offers the services of the Services app."
    )
    require_customer: bool = Field(description="Every sale needs a customer.")
    allow_discounts: bool = Field(description="Line and ticket discounts may be given.")
    max_discount_percent: int = Field(
        ge=0,
        le=100,
        description="The biggest discount (each one, in %) given without a manager; 100 = no cap.",
    )
    enable_parked_tickets: bool = Field(
        description="Checks may be parked and picked up again."
    )
    default_tax_included: bool = Field(description="Prices include VAT.")
    auto_invoice_with_tax_id: bool = Field(
        description="The charge starts as an invoice when the customer has a tax id."
    )
    default_document_type: DocumentType = Field(
        description="The document the charge starts with: ticket or invoice."
    )
    receipt_header: str = Field(
        max_length=1000,
        description="Lines the paper adds under the issuer's name, tax ID and address; without an issuer, first line "
        "the name, the rest the address.",
    )
    receipt_footer: str = Field(max_length=1000, description="Receipt footer.")
    receipt_footer_image: str = Field(
        max_length=500,
        description="Address (URL) of an image printed under the footer.",
    )
    receipt_marketing_url: str = Field(
        max_length=500,
        description="Address the promotional QR of the receipt opens; empty = none.",
    )
    receipt_marketing_text: str = Field(
        max_length=200, description="Caption of the promotional QR."
    )


class SettingsOut(SettingsFields):
    updated_at: datetime | None = Field(
        description="When they were last saved; empty while the factory values apply."
    )


class SettingsPatchIn(Closed):
    """Only the fields sent change; the rest keep their value."""

    allow_cash: bool | None = Field(
        None, description="Cash methods may be used to charge."
    )
    allow_card: bool | None = Field(
        None, description="Card methods may be used to charge."
    )
    allow_transfer: bool | None = Field(
        None, description="Bank transfer methods may be used to charge."
    )
    show_products: bool | None = Field(
        None, description="The till offers Inventory's products."
    )
    show_services: bool | None = Field(
        None, description="The till offers the services of the Services app."
    )
    require_customer: bool | None = Field(
        None, description="Every sale needs a customer."
    )
    allow_discounts: bool | None = Field(
        None, description="Line and ticket discounts may be given."
    )
    max_discount_percent: int | None = Field(
        None,
        ge=0,
        le=100,
        description="The biggest discount (each one, in %) given without a manager; 100 = no cap.",
    )
    enable_parked_tickets: bool | None = Field(
        None, description="Checks may be parked and picked up again."
    )
    default_tax_included: bool | None = Field(None, description="Prices include VAT.")
    auto_invoice_with_tax_id: bool | None = Field(
        None,
        description="The charge starts as an invoice when the customer has a tax id.",
    )
    default_document_type: DocumentType | None = Field(
        None, description="The document the charge starts with."
    )
    receipt_header: str | None = Field(
        None,
        max_length=1000,
        description="Lines the paper adds under the issuer's name, tax ID and address; without an issuer, first line "
        "the name, the rest the address.",
    )
    receipt_footer: str | None = Field(
        None, max_length=1000, description="Receipt footer."
    )
    receipt_footer_image: str | None = Field(
        None,
        max_length=500,
        description="Address (URL) of an image printed under the footer.",
    )
    receipt_marketing_url: str | None = Field(
        None,
        max_length=500,
        description="Address the promotional QR opens; empty = none.",
    )
    receipt_marketing_text: str | None = Field(
        None, max_length=200, description="Caption of the promotional QR."
    )


# ── Payment methods ───────────────────────────────────────────────────────────────────────────────


class PaymentMethodListIn(PageIn):
    search: str | None = Field(None, max_length=60, description="Part of the name.")


class PaymentMethodOut(Schema):
    id: UUID = Field(description="The method's id.")
    name: str = Field(description="Its name as stored.")
    display_name: str = Field(
        description="Its name in the reader's language (the factory ones are translated)."
    )
    type: MethodType = Field(description="cash, card, transfer or other.")
    sort_order: int = Field(description="Position in the charge sheet.")
    requires_change: bool = Field(
        description="Cash: asks what was handed over and gives change."
    )
    allowed: bool = Field(description="Whether the till settings let it charge today.")


PaymentMethodPage = Page[PaymentMethodOut]


class PaymentMethodIn(Closed):
    name: _text(60, 1) = Field(description="The method's name, e.g. Bizum.")
    type: MethodType = Field(
        "cash", description="cash (default), card, transfer or other."
    )
    sort_order: int = Field(
        30, ge=0, le=100_000, description="Position in the charge sheet."
    )


# ── Departments and quick notes ───────────────────────────────────────────────────────────────────


class DepartmentListIn(PageIn):
    search: str | None = Field(None, max_length=60, description="Part of the name.")
    sort: Literal["sort_order", "name"] = Field(
        "sort_order", description="Column to sort by."
    )
    dir: SortDir = Field("asc", description="Sort direction.")


class DepartmentOut(Schema):
    id: UUID = Field(description="The department's id.")
    name: str = Field(description="Its name.")
    tax_category_key: str = Field(description="Key of the tax category it charges at.")
    tax_category_name: str = Field(
        description="That category's name in the reader's language."
    )
    tax_rate_pct: Decimal | None = Field(
        description="The rate it charges today in the business's country; empty without a rule."
    )
    sort_order: int = Field(description="Position in the open-price sheet.")


DepartmentPage = Page[DepartmentOut]


class DepartmentIn(Closed):
    name: _text(60, 1) = Field(
        description="The name the cashier reads, e.g. Fruit and veg."
    )
    tax_category_key: _text(80, 1) = Field(
        description="The tax category it charges at: its key, its name or an alias.", json_schema_extra=A_TAX_CATEGORY
    )
    sort_order: int = Field(
        0, ge=0, le=100_000, description="Position in the open-price sheet."
    )


class DepartmentRefIn(Closed):
    id: UUID | None = Field(
        None, title=gettext_noop("Section"), description="The department's id.", json_schema_extra=A_DEPARTMENT
    )
    department: _text(60, 1) | None = Field(
        None, description="Its name, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.department is None:
            raise ValueError(str(SAY_WHICH_DEPARTMENT_ROW))
        return self


class DepartmentUpdateIn(DepartmentRefIn):
    name: _text(60, 1) | None = Field(None, description="New name.")
    tax_category_key: _text(80, 1) | None = Field(
        None, description="New tax category: its key, its name or an alias.", json_schema_extra=A_TAX_CATEGORY
    )
    sort_order: int | None = Field(None, ge=0, le=100_000, description="New position.")


class QuickNoteListIn(PageIn):
    search: str | None = Field(None, max_length=80, description="Part of the text.")
    sort: Literal["sort_order", "text"] = Field(
        "sort_order", description="Column to sort by."
    )
    dir: SortDir = Field("asc", description="Sort direction.")


class QuickNoteOut(Schema):
    id: UUID = Field(description="The quick note's id.")
    text: str = Field(description="Its text.")
    sort_order: int = Field(description="Position among the chips.")


QuickNotePage = Page[QuickNoteOut]


class QuickNoteIn(Closed):
    text: _text(80, 1) = Field(description="The note, e.g. no salt.")
    sort_order: int = Field(
        0, ge=0, le=100_000, description="Position among the chips."
    )


class QuickNoteRefIn(Closed):
    id: UUID | None = Field(
        None, title=gettext_noop("Quick note"), description="The quick note's id.", json_schema_extra=A_QUICK_NOTE
    )
    quick_note: _text(80, 1) | None = Field(
        None, title=gettext_noop("Quick note"), description="Its text, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.quick_note is None:
            raise ValueError(str(SAY_WHICH_QUICK_NOTE))
        return self


class QuickNoteUpdateIn(QuickNoteRefIn):
    text: _text(80, 1) | None = Field(None, description="New text.")
    sort_order: int | None = Field(None, ge=0, le=100_000, description="New position.")
