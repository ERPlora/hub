"""Reactions to the Sales app (events.py; INVENTORY-F21, F22, F23, F24): a sale lowers the stock, a
void and a refund give it back, each sale and refund once."""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError
from live.context import OperationContext
from live.errors import AppInactive, NotFound, PermissionDenied
from live.operations import UnknownOperation, atomic, get, operation

from apps.inventory.models import RefundStock, SaleStock, StockMovement
from apps.inventory.queries.products import tracks_stock
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas import RefundStockOut, SaleCompletedIn, SaleRefundedIn, SaleStockOut, SaleVoidedIn
from apps.inventory.services.movements import _crossing, _locked, _move
from apps.inventory.services.writes import SYSTEM


@operation(
    "inventory.stock.apply_sale",
    kind="command",
    permission=SYSTEM,
    input=SaleCompletedIn,
    output=SaleStockOut,
    ai={
        "description": "Lower the stock of a paid sale's articles and of its menus' components (run by the "
        "platform when Sales reports a paid sale).",
        "risk": "high",
    },
)
def apply_sale(ctx: OperationContext, data: SaleCompletedIn) -> dict:
    """Each line (or each component of a menu) lowers its article once, with the sale as reference.

    Services, free-price lines, unknown or deleted products and articles without stock control move
    nothing; without «selling without stock» an article that does not reach is not lowered. A sale
    seen before, or voided before it arrived, changes nothing.
    """
    sale, created = _sale_stock(data.sale_id, SaleStock.State.UNMOVED)
    if not created:
        return _sale_result(sale, applied=False, movements=0)
    # INVENTORY-F16: the numbers the ledger shows and finds this sale by.
    sale.sale_number = data.sale_number[: SaleStock._meta.get_field("sale_number").max_length]
    sale.document_number = _document_number(ctx, data.sale_id)[: SaleStock._meta.get_field("document_number").max_length]
    units = [
        (unit.product_id, unit.quantity)
        for item in data.items
        for unit in (item.components or [item])
        if unit.product_id is not None and not unit.is_service and unit.quantity > 0
    ]
    products = _locked({product_id for product_id, _ in units})
    settings = current_settings()
    before = {product_id: product.stock for product_id, product in products.items()}
    moved = 0
    for product_id, quantity in units:
        product = products.get(product_id)
        if product is None or not tracks_stock(product, settings):
            continue
        if not settings.allow_sell_without_stock and product.stock < quantity:
            continue
        _move(ctx, product, StockMovement.Type.SALE, -quantity, reference=str(data.sale_id))
        moved += 1
    for product_id, product in products.items():
        if product.stock != before[product_id]:
            _crossing(ctx, product, settings, before[product_id], StockMovement.Type.SALE, str(data.sale_id))
    if moved:
        sale.state = SaleStock.State.MOVED
    sale.save(update_fields=["state", "sale_number", "document_number", "updated_at"])
    return _sale_result(sale, applied=True, movements=moved)


@operation(
    "inventory.stock.restore_sale",
    kind="command",
    permission=SYSTEM,
    input=SaleVoidedIn,
    output=SaleStockOut,
    ai={
        "description": "Give back to each article exactly what a voided sale took, read from the ledger (run by "
        "the platform when Sales reports a void).",
        "risk": "high",
    },
)
def restore_sale(ctx: OperationContext, data: SaleVoidedIn) -> dict:
    """Restores once what the ledger says the sale lowered, even if the article stopped tracking stock.

    A void that arrives before its sale is noted, so the late sale lowers nothing. A product deleted
    after the sale gets nothing back.
    """
    sale, created = _sale_stock(data.sale_id, SaleStock.State.VOIDED)
    if not created and sale.state == SaleStock.State.VOIDED:
        return _sale_result(sale, applied=False, movements=0)
    restored = 0
    if not created and sale.state == SaleStock.State.MOVED:
        taken = _still_out(data.sale_id)
        products = _locked(set(taken))
        settings = current_settings()
        for product_id, product in products.items():
            if taken[product_id] <= 0:
                continue
            previous = product.stock
            _move(ctx, product, StockMovement.Type.VOID, taken[product_id], reference=str(data.sale_id))
            _crossing(ctx, product, settings, previous, StockMovement.Type.VOID, str(data.sale_id))
            restored += 1
    if not created:
        sale.state = SaleStock.State.VOIDED
        sale.save(update_fields=["state", "updated_at"])
    return _sale_result(sale, applied=True, movements=restored)


@operation(
    "inventory.stock.restore_refund",
    kind="command",
    permission=SYSTEM,
    input=SaleRefundedIn,
    output=RefundStockOut,
    ai={
        "description": "Put back in the stock the units a refund of Sales returns, never more than its sale took "
        "(run by the platform when Sales reports a refund).",
        "risk": "high",
    },
)
def restore_refund(ctx: OperationContext, data: SaleRefundedIn) -> dict:
    """Each returned line gives its article back once per refund (INVENTORY-F24).

    Never more than the sale still has out according to the ledger (what it lowered minus what earlier
    refunds gave back), so nothing it did not lower comes back: a service, a free-price line, an article
    without stock control or one that did not reach. An article that no longer tracks its stock is left
    as it is. A refund of a sale voided (or not seen) gives nothing back. The movement «refund» carries
    the sale as reference, so a later void restores only what is still out.
    """
    note, created = _refund_stock(data.refund_id, data.sale_id)
    if not created:
        return _refund_result(note, applied=False, movements=0)
    sale = SaleStock.objects.select_for_update().filter(sale_id=data.sale_id).first()
    returned: dict[UUID, Decimal] = defaultdict(Decimal)
    for line in data.lines:
        if line.product_id is not None and line.quantity > 0:
            returned[line.product_id] += line.quantity
    moved = 0
    if sale is not None and sale.state == SaleStock.State.MOVED and returned:
        out = _still_out(data.sale_id)
        settings = current_settings()
        for product_id, product in _locked(set(returned)).items():
            quantity = min(returned[product_id], out[product_id])
            if quantity <= 0 or not tracks_stock(product, settings):
                continue
            previous = product.stock
            _move(ctx, product, StockMovement.Type.REFUND, quantity, reason=data.reason, reference=str(data.sale_id))
            _crossing(ctx, product, settings, previous, StockMovement.Type.REFUND, str(data.sale_id))
            moved += 1
    if moved:
        note.movements = moved
        note.save(update_fields=["movements"])
    return _refund_result(note, applied=True, movements=moved)


def _sale_stock(sale_id: UUID, state: str) -> tuple[SaleStock, bool]:
    """The sale's note, created with ``state`` if it is new, or the existing one with its row locked.

    Two deliveries of the same sale at once: the second waits on the unique key until the first commits.
    """
    try:
        with atomic():
            return SaleStock.objects.create(sale_id=sale_id, state=state), True
    except IntegrityError:
        return SaleStock.objects.select_for_update().get(sale_id=sale_id), False


def _document_number(ctx: OperationContext, sale_id: UUID) -> str:
    """The number of the sale's ticket or invoice, read from Sales by its operation; empty when Sales is not
    reachable, does not know the sale or it has no fiscal document yet."""
    try:
        get_sale = get("sale.sale.get")
        found = get_sale(ctx, get_sale.input.model_validate({"sale_id": str(sale_id)}))
    except (UnknownOperation, AppInactive, PermissionDenied, NotFound):
        return ""
    return found.invoice_number


def _sale_result(sale: SaleStock, *, applied: bool, movements: int) -> dict:
    return {"sale_id": sale.sale_id, "state": sale.state, "applied": applied, "movements": movements}


def _still_out(sale_id: UUID) -> dict[UUID, Decimal]:
    """Per article, what the sale lowered and no refund has given back yet, read from the ledger."""
    out: dict[UUID, Decimal] = defaultdict(Decimal)
    for product_id, qty in StockMovement.objects.filter(
        movement_type__in=[StockMovement.Type.SALE, StockMovement.Type.REFUND], reference=str(sale_id)
    ).values_list("product_id", "qty"):
        out[product_id] -= qty
    return out


def _refund_stock(refund_id: UUID, sale_id: UUID) -> tuple[RefundStock, bool]:
    """The refund's note, created if it is new; two deliveries at once: the second waits on the unique key."""
    try:
        with atomic():
            return RefundStock.objects.create(refund_id=refund_id, sale_id=sale_id), True
    except IntegrityError:
        return RefundStock.objects.select_for_update().get(refund_id=refund_id), False


def _refund_result(note: RefundStock, *, applied: bool, movements: int) -> dict:
    return {"refund_id": note.refund_id, "sale_id": note.sale_id, "applied": applied, "movements": movements}
