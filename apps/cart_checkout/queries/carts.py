"""Read operations of the carts: the list and one cart with its lines."""

from live.context import OperationContext
from live.operations import operation

from apps.cart_checkout.queries.reads import _bounds, _containing, _page, find_cart, live_carts
from apps.cart_checkout.queries.rows import cart_row, item_row
from apps.cart_checkout.schemas import CartDetailOut, CartListIn, CartPage, CartRefIn
from base.ordering import list_order_for
from base.text_search import contains_text

CART_ORDER = {
    "session_token": ("session_token",),
    "customer_email": ("customer_email",),
    "customer_name": ("customer_name",),
    "status": ("state",),
    "total_items": ("total_items",),
    "total_amount": ("total_amount",),
    "currency": ("currency",),
    "expires_at": ("expires_at",),
    "last_activity_at": ("last_activity_at",),
    "created_at": ("created_at",),
}


@operation(
    "cart_checkout.cart.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=CartListIn,
    output=CartPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the open shopping carts",
                "which online baskets were abandoned this week?",
                "list the customers' carts that became orders",
            ),
            "es": (
                "¿qué carritos de la tienda online siguen abiertos?",
                "enséñame las cestas abandonadas de esta semana",
                "lista los carritos de compra que acabaron en pedido",
            ),
        },
        "description": "List the shopping carts of the internal cart notebook (not the till's tickets) with their "
        "session code, customer's email and name, status (active, abandoned, converted, expired), items and "
        "total in minor units. Search by code, email or name.",
        "risk": "normal",
    },
)
def list_carts(ctx: OperationContext, params: CartListIn) -> dict:
    carts = live_carts()
    if params.search and params.search.strip():
        text = params.search.strip()
        carts = carts.filter(contains_text(text, "session_token", "customer_email", "customer_name"))
    carts = carts.filter(
        _containing(
            session_token=params.session_token,
            customer_email=params.customer_email,
            customer_name=params.customer_name,
            notes=params.notes,
        )
    )
    if params.status:
        carts = carts.filter(state=params.status)
    if params.currency and params.currency.strip():
        carts = carts.filter(currency=params.currency.strip().upper())
    carts = carts.filter(
        **_bounds(
            total_items__gte=params.total_items_min,
            total_items__lte=params.total_items_max,
            total_amount__gte=params.total_amount_min,
            total_amount__lte=params.total_amount_max,
            expires_at__gte=params.expires_from,
            expires_at__lte=params.expires_to,
            last_activity_at__gte=params.last_activity_from,
            last_activity_at__lte=params.last_activity_to,
            created_at__gte=params.created_from,
            created_at__lte=params.created_to,
        )
    )
    ordered = carts.order_by(*list_order_for(params.sort, "created_at", columns=CART_ORDER, nulls_last=True))
    return _page(ordered, params, cart_row)


@operation(
    "cart_checkout.cart.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=CartRefIn,
    output=CartDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what's in Carmen's shopping cart and how much is it?",
                "show me the whole basket of session sess_a1b2c3",
                "open the cart of nuria@example.com, every line of it",
            ),
            "es": (
                "¿qué lleva el carrito de Carmen y cuánto suma?",
                "enséñame entera la cesta de la sesión sess_a1b2c3",
                "dame el carrito de nuria@example.com con todo lo que lleva",
            ),
        },
        "description": "Get one shopping cart with all its lines (product, quantity, unit price, line total), "
        "named by its session code, by its customer's email or name, or by its id.",
        "risk": "normal",
    },
)
def get_cart(ctx: OperationContext, data: CartRefIn) -> dict:
    cart = find_cart(data.cart_id, data.session_token, data.customer)
    return {**cart_row(cart), "items": [item_row(item) for item in cart.items.order_by("created_at", "id")]}
