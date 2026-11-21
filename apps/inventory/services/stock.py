"""The stock a person changes (INVENTORY-F13, F14, F15): a reception, a count and a write-off."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation

from apps.inventory.models import Product, StockMovement
from apps.inventory.queries.products import load_product, tracks_stock
from apps.inventory.queries.reads import find_product
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas import CountIn, ProductOut, ProductsOut, ReceiveIn, WriteOffIn
from apps.inventory.services.movements import _crossing, _locked, _move
from apps.inventory.services.writes import _check_grid, _service_has_no_stock

STOCK_NOT_TRACKED = _("This article does not track its stock: there is nothing to write off.")
INSUFFICIENT_STOCK = _("There is not enough stock to complete the operation.")
LINE_PRODUCT_UNKNOWN = _("This product does not exist in this hub.")


@operation(
    "inventory.stock.receive",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.adjust_stock",
    input=ReceiveIn,
    output=ProductsOut,
    expose_api=True,
    ai={
        "description": "Record goods received: raises the stock of one or more products (by id, SKU or name), "
        "with the unit cost and the delivery note's number.",
        "risk": "normal",
        "asks": {
            "en": (
                "I just received 20 coffees, delivery note A-123",
                "a delivery arrived: add 10 boxes of tea to the stock",
                "record the goods that came in today",
            ),
            "es": (
                "ha llegado un pedido: recibe 20 cafés con el albarán A-123",
                "entra mercancía: 10 cajas de té al stock",
                "registra la entrada de mercancía del proveedor de hoy",
            ),
        },
    },
)
def receive_stock(ctx: OperationContext, data: ReceiveIn) -> dict:
    """All lines or none: a line without a product, with a service or off its unit's step refuses the whole."""
    named = []
    for index, line in enumerate(data.items):
        field = f"items.{index}.product_id" if line.product_id is not None else f"items.{index}.product"
        try:
            named.append((index, field, find_product(line.product_id, line.product).id, line))
        except NotFound as exc:
            raise _line_product_unknown(field) from exc
    products = _locked({product_id for _, _, product_id, _ in named})
    lines = []
    for index, field, product_id, line in named:
        product = products.get(product_id)
        if product is None:  # deleted meanwhile
            raise _line_product_unknown(field)
        if product.product_type == Product.Type.SERVICE:
            raise _service_has_no_stock(field)
        _check_grid(line.qty, product.unit, f"items.{index}.qty")
        lines.append((product_id, line))
    settings = current_settings()
    before = {product_id: product.stock for product_id, product in products.items()}
    for product_id, line in lines:
        product = products[product_id]
        if line.unit_cost is not None:
            product.cost = line.unit_cost
        _move(ctx, product, StockMovement.Type.RECEPTION, line.qty, reference=data.reference, unit_cost=line.unit_cost)
    for product_id, product in products.items():
        _crossing(ctx, product, settings, before[product_id], StockMovement.Type.RECEPTION, data.reference)
    return {"rows": [load_product(product_id, ctx.scope) for product_id in dict.fromkeys(product_id for product_id, _ in lines)]}


@operation(
    "inventory.stock.count",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.adjust_stock",
    input=CountIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Apply a stock count: the product's balance becomes the ABSOLUTE value counted, with a "
        "mandatory reason; the ledger records the difference. Not for breakage, waste or own consumption: a write-off.",
        "risk": "normal",
        "asks": {
            "en": (
                "I counted 12 croissants, fix the stock",
                "do a stock count: the coffee is really 45",
                "inventory count of the tea: 8 left",
            ),
            "es": (
                "he contado 12 cruasanes, corrige el stock",
                "haz un recuento: del café hay 45 de verdad",
                "recuento del té: quedan 8",
            ),
        },
    },
)
def count_stock(ctx: OperationContext, data: CountIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    field = "product_id" if data.product_id is not None else "product"
    if product.product_type == Product.Type.SERVICE:
        raise _service_has_no_stock(field)
    _check_grid(data.stock, product.unit, "stock")
    previous = product.stock
    difference = data.stock - previous
    if difference:
        _move(ctx, product, StockMovement.Type.COUNT, difference, reason=data.reason)
        _crossing(ctx, product, current_settings(), previous, StockMovement.Type.COUNT, "")
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.stock.write_off",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.adjust_stock",
    input=WriteOffIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Write off stock without a sale (waste, breakage, own consumption) with its reason; a "
        "service or an article without stock control is refused (there is no stock to lower).",
        "risk": "normal",
        "asks": {
            "en": (
                "write off 2 coffees, they broke",
                "discard 3 croissants, they went stale",
                "take out of stock what we used ourselves",
            ),
            "es": (
                "da de baja 2 cafés que se han roto",
                "tira 3 cruasanes que se han puesto malos",
                "quita del stock lo que hemos consumido nosotros",
            ),
        },
    },
)
def write_off_stock(ctx: OperationContext, data: WriteOffIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    if product.product_type == Product.Type.SERVICE:
        raise _service_has_no_stock("product_id" if data.product_id is not None else "product")
    _check_grid(data.qty, product.unit, "qty")
    settings = current_settings()
    # Never a silent success: a write-off that would lower nothing says so.
    if not tracks_stock(product, settings):
        raise Conflict(str(STOCK_NOT_TRACKED), code="inventory.stock_not_tracked", fields={"qty": str(STOCK_NOT_TRACKED)})
    if not settings.allow_sell_without_stock and product.stock < data.qty:
        raise Conflict(str(INSUFFICIENT_STOCK), code="inventory.insufficient_stock", fields={"qty": str(INSUFFICIENT_STOCK)})
    previous = product.stock
    _move(ctx, product, StockMovement.Type.WRITE_OFF, -data.qty, reason=data.reason)
    _crossing(ctx, product, settings, previous, StockMovement.Type.WRITE_OFF, "")
    return load_product(product.id, ctx.scope)


def _line_product_unknown(field: str) -> InvalidPayload:
    message = str(LINE_PRODUCT_UNKNOWN)
    return InvalidPayload(message, code="invalid_field", fields={field: message})
