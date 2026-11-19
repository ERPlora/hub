"""Schemas of what Sales does when another app tells it: a customer merged, a document of Invoicing issued."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict



class CustomerMergedIn(Schema):
    id: UUID = Field(description="The customer card that stays.")
    absorbed_id: UUID = Field(description="The card merged into it.")


class CustomerReassignOut(Schema):
    customer_id: UUID = Field(description="The card that stays.")
    moved: int = Field(description="Sales moved to it.")


class InvoiceSourceIn(Schema):
    """Where a document of Invoicing comes from (its WORKBOOK «Contrato del origen con Ventas»)."""

    model_config = ConfigDict(extra="ignore")

    type: str = Field(max_length=20, description="sale, manual, substitution, rectification, refund or void.")
    sale_id: UUID | None = Field(None, description="The sale it comes from (also its F3 and its rectifications).")
    refund_id: UUID | None = Field(None, description="The refund a rectifying invoice of a refund corrects.")
    void: bool = Field(False, description="True on the rectifying invoice of a void.")


class InvoiceIssuedIn(Schema):
    """Invoicing's notice of a document issued (``invoice.invoice.issued``; its other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    invoice_id: UUID = Field(description="The document in Invoicing.")
    number: str = Field(max_length=60, description="Its number in its series.")
    invoice_type: str = Field(max_length=2, description="F1, F2, F3 or R1–R5.")
    source: InvoiceSourceIn | None = Field(
        None, description="Which charge, refund or void of Sales it comes from; none = not from Sales."
    )


class InvoiceRecordedOut(Schema):
    sale_id: UUID | None = Field(description="The sale that now knows its document.")
    recorded: bool = Field(description="Something was written now; false on a repeat or another document.")
