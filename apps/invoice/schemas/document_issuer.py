"""The issuer of an ``InvoiceOut``, as ``apps.invoice.document_issuer`` reads it from the copy the invoice keeps."""

from ninja import Field, Schema


class DocumentIssuerOut(Schema):
    issuer_name: str
    issuer_tax_id: str = Field(
        description="The issuer's tax ID as kept: the one VeriFactu declares and the QR carries."
    )
    issuer_vat_number: str = Field(
        description="The issuer's tax ID as the document prints it: its EU VAT number (ESB27593136) while it is "
        "registered for intra-EU operations (ROI), its tax ID as kept otherwise."
    )
    issuer_address: str
    issuer_country: str
