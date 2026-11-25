"""Schemas of the Excel of the issued invoices (INVOICE-F24)."""

from ninja import Field, Schema

from apps.invoice.schemas.invoices import InvoiceFiltersIn
from base.schemas.assistant import A_HANDED_FILE


class InvoiceExportIn(InvoiceFiltersIn):
    """The invoices to put in the file: the list's search and filters."""


class InvoiceExportOut(Schema):
    filename: str = Field(description="The file's name.")
    content_type: str = Field(description="The file's type, an Excel workbook.")
    invoices: int = Field(description="How many invoices it holds.")
    content_base64: str = Field(
        description="The workbook, in base64: a row per invoice and tax rate.", json_schema_extra=A_HANDED_FILE
    )
