"""Schemas of the PDF of an invoice (INVOICE-F25)."""

from ninja import Field, Schema

from base.schemas.assistant import A_HANDED_FILE


class InvoicePdfOut(Schema):
    filename: str = Field(description="The file's name: the invoice's number.")
    content_type: str = Field(description="The file's type, a PDF.")
    content_base64: str = Field(description="The PDF, in base64.", json_schema_extra=A_HANDED_FILE)
