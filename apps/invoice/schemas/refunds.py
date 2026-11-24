"""Schemas of a refund of the Sales app as Invoicing names it.
"""

from uuid import UUID

from ninja import Field, Schema


class RefundGetIn(Schema):
    """A refund of the Sales app, by its id."""

    refund_id: UUID = Field(description="Id of the refund document of the Sales app.")


class RefundOut(Schema):
    """A refund of the Sales app as Invoicing names it: the sale it gives back and what it gave back."""

    id: UUID
    sale_id: UUID
    sale_number: str = Field(description="Number of the sale it gives back, as printed on its ticket.")
    total: int = Field(
        description="What it gave back, in the minor unit of its currency.",
        json_schema_extra={"money": True},
    )
    currency: str = Field(description="The sale's currency (ISO 4217).")
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR, 0 in JPY): its amounts' minor unit.")
    invoice_number: str = Field(description="Number of its rectifying invoice; empty while none is issued.")
    label: str = Field(
        description="How it is named outside its sale, in the reader's language: the sale's number and what it gave "
        "back (e.g. «20261014-0003 · €5.00»)."
    )
