"""Every change of stock: the products' rows locked in the order of their ids, the balance and its ledger
movement written together with ``inventory.stock.changed``, and the crossing of the low-stock threshold
(INVENTORY-F18)."""

from decimal import Decimal
from uuid import UUID

from live.context import OperationContext
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import Product, Settings, StockMovement
from apps.inventory.queries.products import tracks_stock
from apps.inventory.services.writes import _actor

THOUSANDTHS = Decimal("0.001")


def _q(value: Decimal) -> str:
    """A quantity in an event: always three decimals, so its consumers read it the same way."""
    return str(value.quantize(THOUSANDTHS))


def _locked(product_ids: set[UUID]) -> dict[UUID, Product]:
    """The live products, their rows locked in the order of their ids (no two writes wait in a circle)."""
    products = Product.objects.select_for_update().filter(pk__in=product_ids, is_deleted=False).order_by("id")
    return {product.id: product for product in products}


def _move(  # noqa: PLR0913
    ctx: OperationContext,
    product: Product,
    movement_type: str,
    qty: Decimal,
    *,
    reason: str = "",
    reference: str = "",
    unit_cost: int | None = None,
) -> StockMovement:
    """The balance and its movement, written together; ``product``'s row is already locked."""
    product.stock += qty
    product.updated_by = _actor(ctx)
    product.save(update_fields=["stock", "cost", "updated_by", "updated_at"])
    movement = StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        qty=qty,
        stock_after=product.stock,
        reason=reason,
        reference=reference,
        unit_cost=unit_cost,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.STOCK_CHANGED,
        {"product_id": str(product.id), "movement_type": movement_type, "qty": _q(qty), "stock_after": _q(product.stock)},
    )
    return movement


def _crossing(  # noqa: PLR0913, PLR0917
    ctx: OperationContext, product: Product, settings: Settings, previous: Decimal, movement_type: str, reference: str
) -> None:
    """INVENTORY-F18: an article with stock control crossing its threshold, down («below») or up («recovered»).

    Decided once per operation on the total it moved, so staying on either side never repeats it.
    """
    if not tracks_stock(product, settings):
        return
    threshold, current = product.low_stock_threshold, product.stock
    if previous > threshold >= current:
        crossing = "below"
    elif previous <= threshold < current:
        crossing = "recovered"
    else:
        return
    record_event(
        ctx,
        events.STOCK_THRESHOLD_CROSSED,
        {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "previous_quantity": _q(previous),
            "current_quantity": _q(current),
            "low_stock_threshold": _q(threshold),
            "crossing": crossing,
            "movement_type": movement_type,
            "reference": reference,
        },
    )
