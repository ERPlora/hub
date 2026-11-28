"""Read operations of the lines of a cart: the list and one line."""

from live.context import OperationContext
from live.operations import operation

from apps.cart_checkout.queries.reads import _bounds, _containing, _page, find_cart, find_item
from apps.cart_checkout.queries.rows import item_row
from apps.cart_checkout.schemas import ItemListIn, ItemOut, ItemPage, ItemRefIn
from base.ordering import list_order_for
from base.text_search import contains_text

ITEM_ORDER = {
    "product_ref": ("product_ref",),
    "product_name": ("product_name",),
    "sku": ("sku",),
    "quantity": ("quantity",),
    "unit_price": ("unit_price",),
    "line_total": ("line_total",),
    "created_at": ("created_at",),
}


@operation(
    "cart_checkout.item.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=ItemListIn,
    output=ItemPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which products are in Carmen's web basket?",
                "list the lines of cart sess_a1b2c3 with their prices",
                "which products did Nuria leave in her cart?",
            ),
            "es": (
                "¿qué productos hay en la cesta web de Carmen?",
                "lista las líneas del carrito sess_a1b2c3 con sus precios",
                "¿cuántas unidades de cada producto lleva el carrito de Nuria?",
            ),
        },
        "description": "List the lines of one shopping cart (named by its session code or id): product reference "
        "and name, SKU, quantity, unit price and line total in minor units.",
        "risk": "normal",
    },
)
def list_items(ctx: OperationContext, params: ItemListIn) -> dict:
    cart = find_cart(params.cart_id, params.session_token)
    items = cart.items.all()  # Its lines know their cart (its currency): no read of it per line.
    if params.search and params.search.strip():
        text = params.search.strip()
        items = items.filter(contains_text(text, "product_ref", "product_name", "sku"))
    if params.product_ref:
        items = items.filter(product_ref=params.product_ref.strip())
    items = items.filter(
        _containing(product_name=params.product_name, sku=params.sku),
        **_bounds(
            quantity__gte=params.quantity_min,
            quantity__lte=params.quantity_max,
            unit_price__gte=params.unit_price_min,
            unit_price__lte=params.unit_price_max,
            line_total__gte=params.line_total_min,
            line_total__lte=params.line_total_max,
        ),
    )
    ordered = items.order_by(*list_order_for(params.sort, "created_at", columns=ITEM_ORDER, nulls_last=True))
    return _page(ordered, params, item_row)


@operation(
    "cart_checkout.item.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=ItemRefIn,
    output=ItemOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "at what price was the shampoo kept in Carmen's cart?",
                "show me one line of the web basket with its quantity",
            ),
            "es": (
                "¿a qué precio quedó guardado el champú en el carrito de Carmen?",
                "enséñame una línea de la cesta web con su cantidad",
            ),
        },
        "description": "Get one line of a shopping cart by its id, with its quantity and the unit price kept on it.",
        "risk": "normal",
    },
)
def get_item(ctx: OperationContext, data: ItemRefIn) -> dict:
    return item_row(find_item(data.item_id))
