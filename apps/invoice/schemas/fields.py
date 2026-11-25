"""What the invoice app's schemas share: the limits a document holds, the messages and descriptions several of them
use, a page of a list, and how a document, a sale or a recipient is named.
"""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import BeforeValidator, StringConstraints, field_validator, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

from apps.customer.tax_ids import IdTypeRequired, InvalidTaxId, normalize_tax_id
from apps.invoice.models import ForeignIdType, InvoiceType
from apps.tax.choices import COUNTRY_CODES
from base.schemas.assistant import names

T = TypeVar("T")

#: The business's own country while the platform has no setting for it (WORKBOOK «Antes de empezar»).
HOME_COUNTRY = "ES"
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
WHICH_INVOICE = _("Say which invoice: its id or its number.")
WHICH_SALE = _("Say which sale: its id or its number.")
FIELD_REQUIRED = _("This field is required.")
#: How the Facturas screens name the data the models do not (the assistant's card names each one by it).
SALE = gettext_noop("Sale")
NEXT_NUMBER = gettext_noop("Next number")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
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
InvoiceTypeCode = Literal[*InvoiceType.values]
IdType = Literal["", *ForeignIdType.values]


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
    "A customer card by its name (or a part of it), phone or email (for voice); same as customer_id."
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
