"""What the ticket's public page sends and gets (INVOICE-F04): the ticket's code, the customer's tax details checked as
at the counter, and back the ticket and the full invoice that replaces it."""

import datetime as dt

from ninja import Field, Schema

from apps.invoice.schemas.fields import RecipientFieldsIn
from apps.invoice.schemas.invoices import InvoiceOut

CODE = "The code printed on the ticket (the end of the address that opens its page)."


class PublicCodeIn(Schema):
    code: str = Field(max_length=64, description=CODE)


class PublicSubstituteIn(RecipientFieldsIn):
    """The ticket's code and the recipient of its full invoice (name, tax ID and address are required)."""

    code: str = Field(max_length=64, description=CODE)


class PublicTicketSummaryOut(Schema):
    number: str
    issue_date: dt.date
    total_amount: int = Field(json_schema_extra={"money": True})
    currency: str
    issuer_name: str


class PublicRecordOut(Schema):
    """VeriFactu's QR of the full invoice, for its A4 (INVOICE-F18)."""

    qr_svg: str
    qr_url: str


class PublicTicketOut(Schema):
    ticket: PublicTicketSummaryOut
    invoice: InvoiceOut | None = Field(description="The full invoice that replaces it; none until it is asked for.")
    record: PublicRecordOut | None = Field(description="Its VeriFactu QR; none without VeriFactu or a full invoice.")


class PublicIssueOut(Schema):
    issued: bool = Field(description="The full invoice was issued now.")
    already: bool = Field(description="The ticket already had it: the same one, nothing new.")
    invoice: InvoiceOut
    record: PublicRecordOut | None = Field(description="Its VeriFactu QR; none without VeriFactu.")
