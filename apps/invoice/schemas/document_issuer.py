"""The issuer as ``apps.invoice.document_issuer`` reads it: the one of an ``InvoiceOut``, from the copy the invoice
keeps, and what ``IssuerIn`` and ``IssuerOut`` say of the ROI."""

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


class IntraEuOperatorIn(Schema):
    intra_eu_operator: bool = Field(
        False,
        description="The business is registered for intra-EU operations (ROI): every document issued from now on "
        "prints its EU VAT number (ESB12345674); VeriFactu keeps the tax ID without the prefix.",
    )


class IntraEuOperatorOut(Schema):
    intra_eu_operator: bool = Field(description="The business is registered for intra-EU operations (ROI).")
    vat_number: str = Field(
        description="The tax ID as the documents print it: the EU VAT number (ESB12345674) while registered for "
        "intra-EU operations, the tax ID as kept otherwise."
    )
