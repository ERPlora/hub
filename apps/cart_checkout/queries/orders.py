"""Read operations of the orders made from the carts: the list and one order, and whether this database keeps any."""

from live.context import OperationContext
from live.operations import operation

from apps.cart_checkout.models import Order
from apps.cart_checkout.queries.reads import _bounds, _containing, _page, find_order
from apps.cart_checkout.queries.rows import order_row
from apps.cart_checkout.schemas import OrderListIn, OrderOut, OrderPage, OrderRefIn
from base.ordering import list_order_for
from base.text_search import contains_text

ORDER_ORDER = {
    "order_number": ("order_number",),
    "customer_email": ("customer_email",),
    "shipping_method": ("shipping_method",),
    "payment_method": ("payment_method",),
    "status": ("status",),
    "placed_at": ("placed_at",),
    "paid_at": ("paid_at",),
    "completed_at": ("completed_at",),
    "total_amount": ("total_amount",),
    "created_at": ("created_at",),
}


@operation(
    "cart_checkout.order.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which online purchases are waiting to be paid?",
                "list what the online shop sold this week",
            ),
            "es": (
                "¿qué pedidos web siguen pendientes?",
                "lista los pedidos de la tienda online de esta semana",
            ),
        },
        "description": "List the orders made from shopping carts with their number (OS-YYYYMMDD-NNNN), email, "
        "status (initiated, paid, failed, completed), payment method and total in minor units. They are not "
        "the till's sales and nothing in them is fiscal.",
        "risk": "normal",
    },
)
def list_orders(ctx: OperationContext, params: OrderListIn) -> dict:
    orders = Order.objects.select_related("cart")
    if params.search and params.search.strip():
        text = params.search.strip()
        orders = orders.filter(contains_text(text, "order_number", "customer_email"))
    if params.cart_id:
        orders = orders.filter(cart_id=params.cart_id)
    if params.status:
        orders = orders.filter(status=params.status)
    if params.shipping_method and params.shipping_method.strip():
        orders = orders.filter(shipping_method__iexact=params.shipping_method.strip())
    if params.currency and params.currency.strip():
        orders = orders.filter(currency=params.currency.strip().upper())
    orders = orders.filter(
        _containing(
            order_number=params.order_number,
            customer_email=params.customer_email,
            payment_method=params.payment_method,
            notes=params.notes,
        ),
        **_bounds(
            total_amount__gte=params.total_amount_min,
            total_amount__lte=params.total_amount_max,
            placed_at__gte=params.placed_from,
            placed_at__lte=params.placed_to,
            paid_at__gte=params.paid_from,
            paid_at__lte=params.paid_to,
            completed_at__gte=params.completed_from,
            completed_at__lte=params.completed_to,
            created_at__gte=params.created_from,
            created_at__lte=params.created_to,
        ),
    )
    ordered = orders.order_by(*list_order_for(params.sort, "created_at", columns=ORDER_ORDER, nulls_last=True))
    return _page(ordered, params, order_row)


@operation(
    "cart_checkout.order.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what status is OS-20261014-0003 in?",
                "give me the shipping address of what Carmen bought online",
            ),
            "es": (
                "¿en qué estado está OS-20261014-0003?",
                "dame la dirección de envío de la compra online de Carmen",
            ),
        },
        "description": "Get one order with everything it has (addresses, shipping and payment methods, dates, "
        "notes, why it failed), named by its number (OS-20261014-0003) or its id.",
        "risk": "normal",
    },
)
def get_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    return order_row(find_order(data.order_id, data.order_number))


def keeps_fiscal_documents() -> bool:
    """Whether this database holds its shop orders (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Order.objects.exists()
