"""Input and output schemas of the invoice app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).

Made for voice: a document is named by its id or its number (``FACT-2026-000012``), a sale by its id or
its number of the day (``20261014-0003``), a customer by its id or by its exact name, phone or email (the
Customers app's reference), a series by its id or its code. A Spanish tax ID is checked with python-stdnum (NIF, NIE or CIF; the EU VAT number
with document type 02); a foreign one is taken as written. Money is whole cents; rates are percentages
with two decimals; quantities have three decimals, as the sale's.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    BeforeValidator,
    PrivateAttr,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

from apps.customer.tax_ids import IdTypeRequired, InvalidTaxId, normalize_tax_id
from apps.invoice import fiscal
from apps.invoice.models import (
    SERIES_CODE_MAX_LENGTH,
    SERIES_CODE_RE,
    ForeignIdType,
    Invoice,
    InvoiceType,
)
from base.schemas import names

T = TypeVar("T")

#: The business's own country while the platform has no setting for it (WORKBOOK «Antes de empezar»).
HOME_COUNTRY = "ES"
COUNTRY_CODES: tuple[str, ...] = tuple(
    sorted(country.alpha_2 for country in pycountry.countries)
)
#: What VeriFactu's record holds (SuministroInformacion.xsd): NombreRazon is TextMax120Type and the ID of a
#: foreign recipient (IDOtro) TextMax20Type; a Spanish NIF is 9.
NAME_MAX = 120
TAX_ID_MAX = 20
#: Bounds of an amount in cents (± 10 000 million euros).
MAX_AMOUNT = 10**12

TAX_ID_INVALID = _("That tax ID is not valid.")
ID_TYPE_REQUIRED = _(
    "Say what kind of document a foreign tax ID is (EU VAT number, passport, tax ID of their country…)."
)
COUNTRY_UNKNOWN = _("Enter an ISO 3166-1 country code, such as ES or FR.")
FORMAT_INVALID = _(
    "The format needs the year ({year}) and a sequence placeholder ({seq} or {seq:01d}…{seq:09d}), and fits in "
    "one line of 60 characters without accents or symbols such as º or ª."
)
PREFIX_INVALID = _(
    "The prefix is written without accents or symbols such as º or ª (letters, digits, spaces and - / . _)."
)
RATE_OR_CATEGORY = _("Enter the VAT % of the line, or its tax category.")
WHICH_INVOICE = _("Say which invoice: its id or its number.")
WHICH_SALE = _("Say which sale: its id or its number.")
WHICH_SERIES = _("Say which series: its id, or its code.")
FIELD_REQUIRED = _("This field is required.")
#: How the Facturas screens name the data the models do not (the assistant's card names each one by it).
SALE = gettext_noop("Sale")
NEXT_NUMBER = gettext_noop("Next number")

# The assistant's card names the record a write acts on by these reads (base/assistant.py ``REFERS``), run as whoever
# asks, never by its id: an invoice and a sale by their numbers, as their screens do; a refund by its sale and what it
# gave back; a series by its code, its year and its name, as the Series screen's card titles it; the customer by the name
# on their card. The product of a manual line is Inventory's, which Invoicing does not require: the card leaves it out,
# and the line's description says what is invoiced.
AN_INVOICE = names("invoice.invoice.get", by="invoice_id", name=("number",))
A_SERIES = names("invoice.series.get", by="series_id", name=("label",))
A_SALE = names("sale.sale.get", by="sale_id", name=("number",))
A_REFUND = names("invoice.refund.get", by="refund_id", name=("label",))
A_CUSTOMER = names("customer.customer.detail")

Direction = Literal["asc", "desc"]
VerifactuStatus = Literal["sealed", "unavailable", "pending"]
VERIFACTU_STATUS = (
    "What VeriFactu did with the document just issued, in the same transaction: sealed (its registration "
    "record is sealed), unavailable (VeriFactu is not in this business) or pending (it refused now; its "
    "reaction to invoice.invoice.issued seals it later)."
)
InvoiceTypeCode = Literal[*InvoiceType.values]
RectificationType = Literal["R1", "R2", "R3", "R4"]
IdType = Literal["", *ForeignIdType.values]
Status = Literal[*Invoice.Status.values]
SourceType = Literal[*Invoice.Source.values]


def _text(max_length: int, *, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _country(value: Any, *, home_is_empty: bool) -> str:
    code = (value or "").strip().upper() if isinstance(value, str) else ""
    if not code:
        return "" if home_is_empty else HOME_COUNTRY
    if code not in COUNTRY_CODES:
        raise ValueError(str(COUNTRY_UNKNOWN))
    return "" if home_is_empty and code == HOME_COUNTRY else code


def check_tax_id(value: str, *, country: str, id_type: str) -> str:
    """The tax ID as kept (``apps.customer.tax_ids``: a Spanish NIF/NIE/CIF or an EU VAT number checked and
    compact, a foreign document of a known kind as written); a refusal is a ``ValueError`` in the reader's
    words, naming the field it belongs to in ``field``."""
    try:
        return normalize_tax_id(value, country=country, id_type=id_type)
    except IdTypeRequired:
        error = ValueError(str(ID_TYPE_REQUIRED))
        error.field = "customer_id_type"
        raise error from None
    except InvalidTaxId:
        error = ValueError(str(TAX_ID_INVALID))
        error.field = "customer_tax_id"
        raise error from None


def _refused(model: str, field: str, message: str, value: Any) -> ValidationError:
    """A 422 of one field raised from a model validator (the field it belongs to, not the model)."""
    return ValidationError.from_exception_data(
        model,
        [
            InitErrorDetails(
                type=PydanticCustomError("value_error", message),
                loc=(field,),
                input=value,
            )
        ],
    )


# Descriptions shared by several schemas.
INVOICE_ID = "Id of the invoice (from a list or a lookup)."
INVOICE_NUMBER = "Number of the invoice as printed, such as FACT-2026-000012. Either this or invoice_id."
SEARCH = "Free text to search."
DIRECTION = "Sort direction: asc or desc."
CUSTOMER_ID = "Id of a customer card of the Customers app: fills the recipient's data that is not sent."
CUSTOMER_REF = (
    "A customer card by its exact name, phone or email (for voice); same as customer_id."
)
CUSTOMER_NAME = "Recipient's name or company name."
CUSTOMER_TAX_ID = "Recipient's tax ID: a Spanish NIF, NIE or CIF (checked), or the foreign document's number."
CUSTOMER_ADDRESS = "Recipient's address, in one line."
CUSTOMER_COUNTRY = "Recipient's country, ISO 3166-1 alpha-2; empty or ES = Spain."
CUSTOMER_ID_TYPE = (
    "Kind of document of a foreign recipient (AEAT IDType): 02 EU VAT number, 03 passport, 04 tax ID of their "
    "country, 05 residence certificate, 06 other document, 07 not registered; empty = a Spanish NIF."
)


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


# ── Naming things ───────────────────────────────────────────────────────────────────────────────


class InvoiceRefIn(Schema):
    """An invoice, by its id or its number."""

    invoice_id: UUID | None = Field(None, description=INVOICE_ID, json_schema_extra=AN_INVOICE)
    number: Annotated[_text(60) | None, BeforeValidator(_blank_to_none)] = Field(
        None, description=INVOICE_NUMBER
    )

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.invoice_id is None and not self.number:
            raise ValueError(str(WHICH_INVOICE))
        return self


class SaleRefIn(Schema):
    """A sale of the Sales app, by its id or its number of the day."""

    sale_id: UUID | None = Field(None, title=SALE, description="Id of the sale.", json_schema_extra=A_SALE)
    sale: Annotated[_text(24) | None, BeforeValidator(_blank_to_none)] = Field(
        None,
        description="Number of the sale as printed on its ticket, such as 20261014-0003. Either this or sale_id.",
    )

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.sale_id is None and not self.sale:
            raise ValueError(str(WHICH_SALE))
        return self


def _none_to_blank(value: Any) -> Any:
    return "" if value is None else value


class RecipientFieldsIn(Schema):
    """A recipient as typed, checked one way for every document (``apps.customer.tax_ids``): a Spanish tax ID
    must be valid, an EU VAT number too, and a foreign tax ID says its kind of document (422 per field)."""

    customer_name: Annotated[_text(NAME_MAX), BeforeValidator(_none_to_blank)] = Field(
        "", description=CUSTOMER_NAME
    )
    customer_country: str = Field("", description=CUSTOMER_COUNTRY)
    customer_id_type: Annotated[IdType, BeforeValidator(_none_to_blank)] = Field(
        "", description=CUSTOMER_ID_TYPE
    )
    customer_tax_id: Annotated[_text(TAX_ID_MAX), BeforeValidator(_none_to_blank)] = Field(
        "", description=CUSTOMER_TAX_ID
    )
    customer_address: Annotated[_text(500), BeforeValidator(_none_to_blank)] = Field(
        "", description=CUSTOMER_ADDRESS
    )

    @field_validator("customer_country", mode="before")
    @classmethod
    def _iso_country(cls, value: Any) -> str:
        return _country(value, home_is_empty=True)

    @model_validator(mode="after")
    def _valid_tax_id(self):
        try:
            self.customer_tax_id = check_tax_id(
                self.customer_tax_id,
                country=self.customer_country,
                id_type=self.customer_id_type,
            )
        except ValueError as refusal:
            field = getattr(refusal, "field", "customer_tax_id")
            raise _refused(
                type(self).__name__, field, str(refusal), getattr(self, field)
            ) from None
        return self


class RecipientIn(RecipientFieldsIn):
    """The recipient of a document: a customer card (by id or reference) and what is typed over it."""

    customer_id: UUID | None = Field(None, description=CUSTOMER_ID, json_schema_extra=A_CUSTOMER)
    customer: Annotated[_text(200) | None, BeforeValidator(_blank_to_none)] = Field(
        None, description=CUSTOMER_REF
    )


# ── Inputs: invoices ────────────────────────────────────────────────────────────────────────────


class InvoiceListIn(PageIn):
    """The invoices, newest first unless sorted otherwise."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Number, customer's name or tax ID."
    )
    status: Status | None = Field(
        None, description="Only those in this status: issued, paid or cancelled."
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
    tax_category_key: Annotated[_text(255) | None, BeforeValidator(_blank_to_none)] = (
        Field(
            None,
            description="Tax category of the Taxes app (key, name or alias): its rule today gives the rate and the "
            "qualification. Without it, tax_rate is charged as domestic VAT, subject.",
        )
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
        description="Code of this year's series instead of its id (FACT for invoices, TICKET for tickets). "
        "Without series, the default series of the year, else FACT.",
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


class RectificationPreviewIn(InvoiceRefIn):
    """The invoice to rectify, with the reason and the type the rectification will be sent with."""

    reason: _text(500, min_length=1) = Field(
        description="Why it is rectified; printed on the rectifying invoice."
    )
    rectification_type: RectificationType | None = Field(
        None,
        title=gettext_noop("Type of rectifying invoice"),
        description="R1 error founded in law and art. 80 One, Two and Six LIVA (default), R2 insolvency, R3 bad "
        "debts, R4 other causes. A simplified invoice (ticket) is always rectified as R5.",
    )


class RectifyIn(RectificationPreviewIn):
    """A rectification of what is left of an invoice, dated today."""

    issue_date: dt.date | None = Field(
        None,
        description="Leave it out: a rectifying invoice is dated the day it is issued, and any other day is refused.",
    )


class FromRefundIn(Schema):
    """A refund of the Sales app (also the payload of ``sale.sale.refunded``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    refund_id: UUID = Field(
        title=gettext_noop("Sale refund"),
        description="Id of the refund document of the Sales app.",
        json_schema_extra=A_REFUND,
    )


class FromVoidIn(Schema):
    """A voided sale (also the payload of ``sale.sale.voided``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    sale_id: UUID = Field(title=SALE, description="Id of the voided sale.", json_schema_extra=A_SALE)


class MarkPaidIn(InvoiceRefIn):
    """An issued invoice to mark as paid now."""


# ── Inputs: series ──────────────────────────────────────────────────────────────────────────────

def _upper_code(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


SeriesCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=SERIES_CODE_MAX_LENGTH, pattern=SERIES_CODE_RE),
    BeforeValidator(_upper_code),
]


def _format(value: str) -> str:
    text = value.strip()
    if text and not fiscal.format_is_valid(text):
        raise ValueError(str(FORMAT_INVALID))
    return text


def _prefix(value: str | None) -> str | None:
    # NumSerieFactura admits printable ASCII only (and no tab: one line).
    if value is not None and not fiscal.is_printable_ascii(value):
        raise ValueError(str(PREFIX_INVALID))
    return value


class SeriesListIn(PageIn):
    """The numbering series."""

    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Code or name."
    )
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this code."
    )
    invoice_type: InvoiceTypeCode | None = Field(None, description="Only this type.")
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")
    is_active: bool | None = Field(
        None, description="True: active ones only; false: inactive ones only."
    )
    is_default: bool | None = Field(None, description="True: the default ones only.")
    sort: Literal[
        "code",
        "name",
        "invoice_type",
        "year",
        "current_number",
        "prefix",
        "is_active",
        "is_default",
    ] = Field("year", description="Column to sort by.")
    dir: Direction = Field("desc", description=DIRECTION)


class SeriesCreateIn(Schema):
    code: SeriesCode = Field(
        description="Code of the series: capitals, digits, hyphen, underscore (TICKET, FACT, RECT…)."
    )
    name: _text(120) = Field("", description="Name of the series.")
    invoice_type: InvoiceTypeCode = Field(
        description="Type of the documents it numbers: F1, F2, F3 or R1–R5."
    )
    year: int = Field(ge=2000, le=2999, description="Year it numbers.")
    prefix: _text(20) = Field(
        "", description="Text before the number; empty = the code."
    )
    format: str = Field(
        "",
        max_length=fiscal.FORMAT_MAX_LENGTH,
        description="Number template with {prefix}, {code}, {year}, {seq} or {seq:01d}…{seq:09d}; empty = "
        "PREFIX-YYYY-NNNNNN.",
    )
    next_number: int = Field(
        1,
        ge=1,
        title=NEXT_NUMBER,
        description="The number its first document takes (to continue another system).",
    )
    is_active: bool = Field(True, description="Offered when issuing by hand.")
    is_default: bool = Field(
        False, description="The series a manual invoice proposes; one per year."
    )

    @field_validator("format")
    @classmethod
    def _valid_format(cls, value: str) -> str:
        return _format(value)

    @field_validator("prefix")
    @classmethod
    def _valid_prefix(cls, value: str) -> str:
        return _prefix(value)


class SeriesUpdateIn(Schema):
    series_id: UUID = Field(description="Id of the series.", json_schema_extra=A_SERIES)
    name: _text(120) | None = Field(None, description="New name.")
    prefix: _text(20) | None = Field(
        None, description="New prefix (only while the series has numbered nothing)."
    )
    format: str | None = Field(
        None,
        max_length=fiscal.FORMAT_MAX_LENGTH,
        description="New number template (only while the series has numbered nothing); empty = PREFIX-YYYY-NNNNNN.",
    )
    next_number: int | None = Field(
        None,
        ge=1,
        title=NEXT_NUMBER,
        description="New first number (only while the series has numbered nothing).",
    )
    is_active: bool | None = Field(None, description="Offered when issuing by hand.")
    is_default: bool | None = Field(None, description="The default series of its year.")

    @field_validator("format")
    @classmethod
    def _valid_format(cls, value: str | None) -> str | None:
        return None if value is None else _format(value)

    @field_validator("prefix")
    @classmethod
    def _valid_prefix(cls, value: str | None) -> str | None:
        return _prefix(value)


class SeriesPeekIn(Schema):
    series_id: UUID | None = Field(None, description="Id of the series.")
    code: Annotated[
        _text(SERIES_CODE_MAX_LENGTH) | None, BeforeValidator(_blank_to_none)
    ] = Field(None, description="Code of the series instead of its id.")
    year: int | None = Field(
        None,
        ge=2000,
        le=2999,
        description="Year of the series named by code; default this year.",
    )

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.series_id is None and not self.code:
            raise ValueError(str(WHICH_SERIES))
        return self


class RefundGetIn(Schema):
    """A refund of the Sales app, by its id."""

    refund_id: UUID = Field(description="Id of the refund document of the Sales app.")


class NumberingStatusIn(Schema):
    """Whether this year's numbering is set up."""


class GapsIn(PageIn):
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this series code."
    )
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")


class AllocationsIn(PageIn):
    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Number or series code."
    )
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this series code."
    )
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")


# ── Inputs: the issuer ──────────────────────────────────────────────────────────────────────────


class IssuerGetIn(Schema):
    """The business's tax identity."""


class IssuerIn(Schema):
    legal_name: _text(NAME_MAX, min_length=1) = Field(
        description="Legal name of the business."
    )
    country: str = Field(
        HOME_COUNTRY,
        description="Country of the business, ISO 3166-1 alpha-2; default ES.",
    )
    tax_id: _text(TAX_ID_MAX, min_length=1) = Field(
        description="Tax ID of the business (a Spanish NIF or CIF, checked)."
    )
    address: _text(255, min_length=1) = Field(description="Street and number.")
    postal_code: _text(20) = Field("", description="Postal code.")
    city: _text(100) = Field("", description="City.")
    province: _text(100) = Field("", description="Province.")

    @field_validator("country", mode="before")
    @classmethod
    def _iso_country(cls, value: Any) -> str:
        return _country(value, home_is_empty=False)

    @field_validator("tax_id")
    @classmethod
    def _valid_tax_id(cls, value: str, info: ValidationInfo) -> str:
        # The issuer's own NIF or CIF is checked; a business abroad keeps its tax ID as written.
        country = info.data.get("country", HOME_COUNTRY)
        if country != HOME_COUNTRY:
            return value.strip()
        return check_tax_id(value, country=country, id_type="")


class IssuerSyncIn(IssuerIn):
    version: int = Field(
        ge=0,
        description="Version of the SaaS's photo it comes with; an older one is ignored.",
    )


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
    base: int = Field(description="Taxable base, cents.")
    quota: int = Field(description="Quota of the main rate, cents.")
    surcharge_quota: int = Field(description="Quota of the surcharge, cents.")


class InvoiceLineOut(Schema):
    id: UUID
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal = Field(
        description="Unit price WITHOUT VAT and before any discount, in cents with two decimals."
    )
    discount_amount: int = Field(
        description="Discount of the line WITHOUT VAT, in cents, with the line's sign (0 = none)."
    )
    tax_rate: Decimal
    surcharge_rate: Decimal
    tax_category_key: str
    base_amount: int
    tax_amount: int
    total_amount: int
    product_id: UUID | None


class InvoiceLinkOut(Schema):
    id: UUID
    number: str
    invoice_type: str
    status: str
    issue_date: dt.date
    total_amount: int


class InvoiceRowOut(Schema):
    id: UUID
    number: str
    invoice_type: str
    series_code: str
    year: int
    issue_date: dt.date
    issued_at: dt.datetime
    customer_name: str
    customer_tax_id: str
    base_amount: int
    tax_amount: int
    total_amount: int
    currency: str
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR, 0 in JPY): its amounts' minor unit.")
    status: str
    source_type: str
    rectifies_id: UUID | None
    rectifies_number: str
    substituted: bool = Field(description="A ticket replaced by a full invoice (F3).")
    can_mark_paid: bool
    can_rectify: bool
    can_substitute: bool


class InvoiceOut(InvoiceRowOut):
    series_id: UUID
    sequence: int
    operation_date: dt.date
    issuer_name: str
    issuer_tax_id: str
    issuer_address: str
    issuer_country: str
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
        description="What is left of it after its rectifications, cents."
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


class RectifiedOut(Schema):
    invoice_id: UUID = Field(description="The invoice that would be rectified.")
    number: str = Field(description="Its number: name it to rectify exactly this one.")
    invoice_type: str = Field(description="Its type: F1, F2 ticket or F3.")
    issue_date: dt.date = Field(description="Its issue date.")
    customer_name: str = Field(description="Its recipient; empty on a ticket without one.")
    total_amount: int = Field(description="Its total, in cents.")
    remaining: int = Field(
        description="What is left of it before this rectification, in cents (less than its total after a partial "
        "rectification by differences)."
    )


class PreviewLineOut(Schema):
    description: str
    quantity: Decimal = Field(description="Negative: the quantity carries the sign, the price does not.")
    tax_rate: Decimal = Field(description="Its rate, %.")
    base_amount: int = Field(description="Its base, in cents (negative).")
    total_amount: int = Field(description="Its total with tax, in cents (negative).")


class RectificationPreviewOut(Schema):
    """The rectifying invoice that rectifying would issue now, before it is issued (INVOICE-F08): nothing is written.
    ``invoice.invoice.rectify`` shows its type, next number and amounts on its card (BASE-F98): their titles are the
    names the Facturas screens give them, and an amount says «in cents» to be shown as money."""

    original: RectifiedOut = Field(description="The invoice it rectifies.")
    invoice_type: str = Field(
        title=gettext_noop("Type of rectifying invoice"),
        description="The rectification's type: R1–R4 for an invoice, R5 for a ticket.",
    )
    reason: str = Field(description="Its reason, printed on it.")
    series_code: str = Field(description="Its series: this year's rectifying one (RECT).")
    next_number: str = Field(
        title=NEXT_NUMBER,
        description="The number it would carry if issued now: the series' next one, NOT reserved — it is taken only "
        "when the rectification is issued, so another one issued before takes it. Say it as the next number, never as "
        "its own."
    )
    issue_date: dt.date = Field(description="Its date: today, the day it is issued.")
    whole: bool = Field(
        description="True: the whole original negated, line by line. False: what is left of it, one line per tax rate."
    )
    base_amount: int = Field(title=gettext_noop("Tax base"), description="Its base, in cents (negative).", json_schema_extra={"money": True})
    tax_amount: int = Field(title=gettext_noop("Tax"), description="Its tax, in cents (negative).", json_schema_extra={"money": True})
    total_amount: int = Field(description="Its total, in cents (negative).", json_schema_extra={"money": True})
    currency: str
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR): its amounts' minor unit.")
    lines: list[PreviewLineOut] = Field(description="Its lines.")


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
    queued: bool = Field(
        description="True: Printing queued the page for the system printer. False: Printing is not on, no system "
        "printer takes it, its VeriFactu record is not there to be read or Printing refused it — the device prints "
        "the screen's paper."
    )
    job_id: UUID | None = Field(description="Its job in the printing queue.")
    printer: str | None = Field(description="The printer it went to.")


class SeriesOut(Schema):
    id: UUID
    code: str
    name: str
    display_name: str
    invoice_type: str
    year: int
    prefix: str
    format: str
    current_number: int
    next_number: str = Field(description="The number its next document will carry.")
    format_locked: bool
    is_active: bool
    is_default: bool


class SeriesDetailOut(SeriesOut):
    """One series as the Series screen shows it, and how it is named outside its screen."""

    label: str = Field(
        description="How it is named outside its screen, in the reader's language: its code, its year and its name "
        "(e.g. «FACT · 2026 · Invoices»)."
    )


class RefundOut(Schema):
    """A refund of the Sales app as Invoicing names it: the sale it gives back and what it gave back."""

    id: UUID
    sale_id: UUID
    sale_number: str = Field(description="Number of the sale it gives back, as printed on its ticket.")
    total: int = Field(description="What it gave back, in the minor unit of its currency.")
    currency: str = Field(description="The sale's currency (ISO 4217).")
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR, 0 in JPY): its amounts' minor unit.")
    invoice_number: str = Field(description="Number of its rectifying invoice; empty while none is issued.")
    label: str = Field(
        description="How it is named outside its sale, in the reader's language: the sale's number and what it gave "
        "back (e.g. «20261014-0003 · €5.00»)."
    )


class SeriesPeekOut(Schema):
    series_id: UUID
    code: str
    year: int
    next_sequence: int
    next_number: str
    format_locked: bool


class NumberingStatusOut(Schema):
    fiscal_year: int
    ordinary_series: int
    rectifying_series: int
    default_series: int
    total_series: int
    configured: bool = Field(
        description="This year has an ordinary series and a rectifying one."
    )


class GapOut(Schema):
    series_code: str
    year: int
    after_sequence: int
    missing_from: int
    next_recorded: int
    missing_count: int


class AllocationOut(Schema):
    series_code: str
    year: int
    sequence: int
    number: str
    invoice_id: UUID
    invoice_type: str
    issued_at: dt.datetime


class IssuerOut(Schema):
    configured: bool
    legal_name: str
    tax_id: str
    address: str
    postal_code: str
    city: str
    province: str
    country: str
    address_line: str
    source: str
    synced_version: int | None
    synced_at: dt.datetime | None
    updated_at: dt.datetime | None


class IssuerSyncOut(Schema):
    applied: bool = Field(description="False when an older photo was ignored.")
    issuer: IssuerOut


InvoicePage = Page[InvoiceRowOut]
SeriesPage = Page[SeriesOut]
GapPage = Page[GapOut]
AllocationPage = Page[AllocationOut]


# ── ERPlora's own invoices, posted by the SaaS to its platform hub (PLAN-SAAS §4) ───────────────────────────
# The body of ``POST /internal/platform/invoices``: ``platform_payload()`` of saas-next/billing/services.py, field by
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
