"""Schemas of what inventory reads of Sales' events (``events.py``) and of what each reaction answers."""

from decimal import Decimal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.inventory.schemas.fields import Quantity, _text


class SaleComponentIn(Schema):
    product_id: UUID | None = Field(None, description="The component's product.")
    quantity: Quantity = Field(
        Decimal("0"),
        description="Quantity of it sold in the line, the line's multiplier applied.",
    )
    is_service: bool = Field(False, description="A service never moves stock.")


class SaleItemIn(Schema):
    product_id: UUID | None = Field(
        None, description="The line's product; none for a free-price line."
    )
    quantity: Quantity = Field(Decimal("0"), description="Quantity sold.")
    is_service: bool = Field(False, description="A service never moves stock.")
    components: list[SaleComponentIn] = Field(
        default_factory=list,
        description="A menu or a pack: it has no stock, its components move instead.",
    )


class SaleCompletedIn(Schema):
    sale_id: UUID = Field(description="The sale that was paid.")
    sale_number: str = Field("", description="Its number (AAAAMMDD-NNNN), for the ledger's reference.")
    items: list[SaleItemIn] = Field(default_factory=list, title=gettext_noop("Sale lines"), description="Its lines.")


class SaleVoidedIn(Schema):
    sale_id: UUID = Field(description="The sale that was voided.")


class SaleRefundLineIn(Schema):
    product_id: UUID | None = Field(None, description="The returned line's product; none for a free-price line.")
    quantity: Quantity = Field(Decimal("0"), description="How many units of it come back.")


class SaleRefundedIn(Schema):
    """What inventory reads of Sales' ``sale.sale.refunded``; the rest of the payload is ignored."""

    sale_id: UUID = Field(description="The sale refunded.")
    refund_id: UUID = Field(description="The refund: each one gives its units back once.")
    reason: _text(500) = Field("", description="Why it was refunded; it goes on the movement.")
    lines: list[SaleRefundLineIn] = Field(
        default_factory=list,
        title=gettext_noop("Returned lines"),
        description="The lines that come back; none = only money."
    )


class SaleStockOut(Schema):
    sale_id: UUID = Field(description="The sale.")
    state: str = Field(description="moved, unmoved (nothing to move) or voided.")
    applied: bool = Field(
        description="False: it had been applied already, nothing was done this time."
    )
    movements: int = Field(description="Movements written this time.")


class RefundStockOut(Schema):
    refund_id: UUID = Field(description="The refund.")
    sale_id: UUID = Field(description="Its sale.")
    applied: bool = Field(
        description="False: it had been applied already, nothing was done this time."
    )
    movements: int = Field(description="Movements written this time.")
