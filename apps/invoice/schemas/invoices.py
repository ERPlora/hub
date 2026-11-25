"""Schemas of the invoices: the list, one invoice and its A4 document, the invoice of a sale, a manual invoice, the
full invoice that replaces a ticket, and marking one paid.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import BeforeValidator, ConfigDict, PrivateAttr, ValidationInfo, field_validator, model_validator

from apps.invoice.models import SERIES_CODE_MAX_LENGTH, Invoice
from apps.invoice.schemas.document_issuer import DocumentIssuerOut
from apps.invoice.schemas.fields import (
    A_SERIES,
    DIRECTION,
    MAX_AMOUNT,
    SEARCH,
    Direction,
    InvoiceRefIn,
    InvoiceTypeCode,
    Page,
    PageIn,
    RecipientFieldsIn,
    RecipientIn,
    SaleRefIn,
    _blank_to_none,
    _text,
    check_tax_id,
)
from apps.invoice.withholding import RATES
from apps.tax.schemas.references import A_TAX_CATEGORY

RATE_OR_CATEGORY = _("Enter the VAT % of the line, or its tax category.")

VerifactuStatus = Literal["sealed", "unavailable", "pending"]
VERIFACTU_STATUS = (
    "What VeriFactu did with the document just issued, in the same transaction: sealed (its registration "
    "record is sealed), unavailable (VeriFactu is not in this business) or pending (it refused now; its "
    "reaction to invoice.invoice.issued seals it later)."
)
#: What the list's status filter takes: the statuses an invoice keeps, and those past their due date.
StatusFilter = Literal[*Invoice.Status.values, "overdue"]
SourceType = Literal[*Invoice.Source.values]
WithholdingRate = Literal[*RATES]


# ── Inputs: invoices ────────────────────────────────────────────────────────────────────────────


class InvoiceFiltersIn(Schema):
    """The invoice list's search and filters; the export takes the same."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Number, customer's name or tax ID."
    )
    status: StatusFilter | None = Field(
        None,
        description="Only those in this status: issued (not paid yet, overdue or not), paid or cancelled; or overdue: "
        "issued and not paid once their due date has passed.",
    )
    invoice_type: InvoiceTypeCode | None = Field(
        None, description="Only this type: F1, F2, F3 or R1–R5."
    )
    series_code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this series code."
    )
    source_type: SourceType | None = Field(
        None,
        description="Only those born so: sale, manual, substitution, rectification, refund or void.",
    )
    customer_id: UUID | None = Field(
        None, description="Only those of this customer card."
    )
    issue_date_from: dt.date | None = Field(
        None, description="Issued on this day or later (YYYY-MM-DD)."
    )
    issue_date_to: dt.date | None = Field(
        None, description="Issued on this day or earlier (YYYY-MM-DD)."
    )
    total_amount_from: int | None = Field(
        None, description="Total of at least this many cents.", json_schema_extra={"money": True}
    )
    total_amount_to: int | None = Field(
        None, description="Total of at most this many cents.", json_schema_extra={"money": True}
    )


class InvoiceListIn(InvoiceFiltersIn, PageIn):
    """The invoices, newest first unless sorted otherwise."""

    sort: Literal[
        "issued_at",
        "issue_date",
        "number",
        "customer_name",
        "total_amount",
        "status",
        "invoice_type",
        "series_code",
    ] = Field("issued_at", description="Column to sort by.")
    dir: Direction = Field("desc", description=DIRECTION)


class InvoiceGetIn(InvoiceRefIn):
    """One invoice with its lines, breakdown and links."""


class DocumentIn(InvoiceRefIn):
    """The printable document of an invoice."""

    duplicate: bool = Field(
        False, title=gettext_noop("Copy"), description="Mark the paper as a copy (a reprint)."
    )


class BySourceIn(SaleRefIn):
    """The invoice in force of a sale (its full invoice if its ticket was replaced)."""


class LineDefaultsIn(Schema):
    """What a line of a manual invoice starts with when its rate is typed."""


class LineDefaultsOut(Schema):
    """The tax a typed rate is declared with is the business territory's, which Taxes publishes
    (``tax.settings.get``'s ``tax_kind``): this operation does not repeat it."""

    tax_rate: Decimal | None = Field(
        description="The territory's general rate, %, from its own rule in Taxes; none when the territory has no "
        "rule of that tax."
    )


class ManualLineIn(Schema):
    description: _text(255, min_length=1) = Field(description="What is invoiced.")
    quantity: Decimal = Field(
        gt=0,
        max_digits=15,
        decimal_places=3,
        description="Quantity, up to three decimals.",
    )
    unit_price: int = Field(
        ge=0, le=MAX_AMOUNT, description="Unit price WITHOUT VAT, in cents.", json_schema_extra={"money": True}
    )
    tax_category_key: Annotated[_text(255) | None, BeforeValidator(_blank_to_none)] = Field(
        None,
        description="Tax category of the Taxes app (key, name or alias): its rule today gives the rate and the "
        "qualification. Without it, tax_rate is charged as domestic VAT, subject.",
        json_schema_extra=A_TAX_CATEGORY,
    )
    tax_rate: Decimal | None = Field(
        None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        validate_default=True,
        description="VAT % of the line when it has no tax category, such as 21, 10 or 4.",
    )
    product_id: UUID | None = Field(
        None, description="Product of the Inventory app it refers to, if any."
    )

    @field_validator("tax_rate")
    @classmethod
    def _rate_or_category(
        cls, value: Decimal | None, info: ValidationInfo
    ) -> Decimal | None:
        if value is None and not info.data.get("tax_category_key"):
            raise ValueError(str(RATE_OR_CATEGORY))
        return value


class InvoiceCreateIn(RecipientIn):
    """A manual invoice: VAT on top of each price, closed once per rate."""

    series_id: UUID | None = Field(
        None, description="Id of the series to number it in (F1 or F2, active).", json_schema_extra=A_SERIES
    )
    series_code: Annotated[
        _text(SERIES_CODE_MAX_LENGTH) | None, BeforeValidator(_blank_to_none)
    ] = Field(
        None,
        description="Code of the series of its year instead of its id (FACT for invoices, TICKET for tickets). "
        "Without series, the default series of the year, else FACT.",
    )
    issue_date: dt.date | None = Field(
        None,
        # The first year a series may number.
        ge=dt.date(2000, 1, 1),
        description="The invoice's date (YYYY-MM-DD): leave it out for today. Never a future day, nor one before the "
        "last invoice of its series.",
    )
    due_date: dt.date | None = Field(
        None, description="The day it has to be paid by (YYYY-MM-DD), if it says one: never before its date."
    )
    withholding_rate: WithholdingRate | None = Field(
        None,
        description="IRPF the customer withholds, % of the taxable base, if any: 15, 7, 1 or 19. It only takes from what is "
        "collected. Never on a ticket.",
    )
    notes: _text(2000) = Field("", description="Free notes printed on the invoice.")
    lines: list[ManualLineIn] = Field(
        min_length=1,
        max_length=100,
        title=gettext_noop("Lines"),
        description="The lines, 1 to 100.",
    )


class FromSaleIn(SaleRefIn, RecipientFieldsIn):
    """The sale charged (also the payload of ``sale.sale.completed``, whose other keys are ignored), with
    the recipient the sale took, read as any other (name: the sale's by default). A tax ID that does not
    check is kept with its refusal (``tax_id_refusal``): only the operation knows whether the sale is a
    ticket, which goes without it, or an invoice, which is refused under that field."""

    model_config = ConfigDict(extra="ignore")
    _tax_id_refusal: tuple[str, str] | None = PrivateAttr(default=None)

    @property
    def tax_id_refusal(self) -> tuple[str, str] | None:
        """``(field, message)`` of the recipient's tax ID that does not check; ``None`` when it does."""
        return self._tax_id_refusal

    @model_validator(mode="after")
    def _valid_tax_id(self):
        try:
            self.customer_tax_id = check_tax_id(
                self.customer_tax_id,
                country=self.customer_country,
                id_type=self.customer_id_type,
            )
        except ValueError as refusal:
            self._tax_id_refusal = (refusal.field, str(refusal))
        return self


class SubstituteIn(InvoiceRefIn, RecipientIn):
    """The ticket (F2) to replace and the recipient of its full invoice (F3)."""


class MarkPaidIn(InvoiceRefIn):
    """An issued invoice to mark as paid now."""


# ── Outputs ─────────────────────────────────────────────────────────────────────────────────────


class BreakdownOut(Schema):
    tax: str = Field(description="Tax family: vat, igic, ipsi…")
    regime: str = Field(description="AEAT regime key (01 general).")
    qualification: str = Field(
        description="subject, subject_reverse, exempt, not_subject, not_subject_location."
    )
    exempt_reason: str = Field(
        description="AEAT exemption cause (E1…E6) of an exempt key."
    )
    rate: Decimal = Field(description="Main rate, %.")
    surcharge_rate: Decimal = Field(
        description="Equivalence surcharge rate, % (0 = none)."
    )
    base: int = Field(description="Taxable base, cents.", json_schema_extra={"money": True})
    quota: int = Field(description="Quota of the main rate, cents.", json_schema_extra={"money": True})
    surcharge_quota: int = Field(description="Quota of the surcharge, cents.", json_schema_extra={"money": True})


class InvoiceLineOut(Schema):
    id: UUID
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal = Field(
        description="Unit price WITHOUT VAT and before any discount, in cents with two decimals."
    )
    discount_amount: int = Field(
        description="Discount of the line WITHOUT VAT, in cents, with the line's sign (0 = none).", json_schema_extra={"money": True}
    )
    tax_rate: Decimal
    surcharge_rate: Decimal
    tax_category_key: str
    base_amount: int = Field(json_schema_extra={"money": True})
    tax_amount: int = Field(json_schema_extra={"money": True})
    total_amount: int = Field(json_schema_extra={"money": True})
    product_id: UUID | None


class InvoiceLinkOut(Schema):
    id: UUID
    number: str
    invoice_type: str
    status: str
    issue_date: dt.date
    total_amount: int = Field(json_schema_extra={"money": True})


class InvoiceRowOut(Schema):
    id: UUID
    number: str
    invoice_type: str
    series_code: str
    year: int
    issue_date: dt.date
    due_date: dt.date | None = Field(description="The day it has to be paid by; none if it does not say one.")
    issued_at: dt.datetime
    customer_name: str
    customer_tax_id: str
    base_amount: int = Field(json_schema_extra={"money": True})
    tax_amount: int = Field(json_schema_extra={"money": True})
    total_amount: int = Field(json_schema_extra={"money": True})
    currency: str
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR, 0 in JPY): its amounts' minor unit.")
    status: str
    source_type: str
    rectifies_id: UUID | None
    rectifies_number: str
    substituted: bool = Field(description="A ticket replaced by a full invoice (F3).")
    overdue: bool = Field(description="Issued and not paid, and its due date has passed.")
    can_mark_paid: bool
    can_rectify: bool
    can_substitute: bool


class WithholdingOut(Schema):
    """What the customer withholds of a document, and what is left to collect."""

    withholding_rate: Decimal | None = Field(description="IRPF withheld, % of the base; none if nothing is withheld.")
    withholding_amount: int = Field(
        description="IRPF withheld, cents, with the document's sign: it takes from what is collected, never from the total.",
        json_schema_extra={"money": True},
    )
    payable_amount: int = Field(
        description="What is collected: the total without what is withheld, cents.", json_schema_extra={"money": True}
    )


class InvoiceOut(InvoiceRowOut, DocumentIssuerOut, WithholdingOut):
    series_id: UUID
    sequence: int
    operation_date: dt.date
    customer_id: UUID | None
    customer_address: str
    customer_country: str
    customer_id_type: str
    description: str
    notes: str
    tax_breakdown: list[BreakdownOut]
    rectification_kind: str
    sale_id: UUID | None
    sale_number: str
    refund_id: UUID | None
    rectifies: InvoiceLinkOut | None
    substitutes: InvoiceLinkOut | None
    substituted_by: InvoiceLinkOut | None
    rectifications: list[InvoiceLinkOut]
    remaining: int = Field(
        description="What is left of it after its rectifications, cents.", json_schema_extra={"money": True}
    )
    paid_at: dt.datetime | None
    created_by: str
    lines: list[InvoiceLineOut]
    verifactu_status: VerifactuStatus | None = Field(
        None, description=VERIFACTU_STATUS + " Only in the answer of the operation that issued it."
    )


class IssueOut(Schema):
    issued: bool = Field(description="A document was issued now.")
    already: bool = Field(
        description="The same request had issued it before: nothing new."
    )
    verifactu_status: VerifactuStatus | None = Field(
        None, description=VERIFACTU_STATUS + " None when nothing was issued now."
    )
    invoice: InvoiceOut | None = Field(
        description="The document; none when there is nothing to issue."
    )


class BySourceOut(Schema):
    found: bool
    invoice: InvoiceOut | None


class DocumentOut(Schema):
    invoice_id: UUID
    number: str
    html: str = Field(
        description="The A4 document, a whole HTML page in the reader's language."
    )


class PaperOut(Schema):
    """The page Printing queued for the system printer; one no printer takes is not printed (``invoice.no_printer``)."""

    job_id: UUID = Field(description="Its job in the printing queue.")
    printer: str = Field(description="The printer it went to.")


InvoicePage = Page[InvoiceRowOut]
