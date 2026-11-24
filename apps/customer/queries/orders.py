"""Which card an open order is for (CUSTOMER-F19), the orders linked to a card, and the name of an open order on the
card of a write."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, INTERNAL, operation

from apps.customer.models import OrderLink
from apps.customer.queries.reads import find_customer, page
from apps.customer.schemas.orders import OrderCustomerOut, OrderIn, OrderListIn, OrderNamedOut, OrderPage
from base import operations as platform

SALES_UNAVAILABLE = _("Sales is not active in this business.")


def linked_customer_id(order_id: UUID) -> UUID | None:
    """The live card linked to the order, if any: a deleted, merged or erased one is nobody's customer any more."""
    link = OrderLink.objects.filter(order_id=order_id, customer__deleted_at__isnull=True).first()
    return link.customer_id if link else None


@operation(
    "customer.order.customer",
    kind="query",
    permission="customer.view",
    input=OrderIn,
    output=OrderCustomerOut,
    ai=AI(
        "Returns the customer linked to an open order, if any, so the till can put her back on a restored check.",
        asks={
            "en": ("who's on this order?", "whose tab is this?"),
            "es": ("¿de quién es este pedido?", "¿qué cliente tiene la cuenta abierta?"),
        },
    ),
)
def order_customer(ctx: OperationContext, data: OrderIn) -> dict:
    return {"order_id": data.order_id, "customer_id": linked_customer_id(data.order_id)}


@operation(
    "customer.order.list",
    kind="query",
    permission="customer.view",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai=AI(
        "Lists the order ids linked to a customer, newest first. The amounts live in the sale app.",
        asks={
            "en": ("what orders does Pedro have?", "list Ana's orders"),
            "es": ("¿qué pedidos tiene el cliente Pedro?", "los pedidos de la clienta Ana"),
        },
    ),
)
def list_orders(ctx: OperationContext, params: OrderListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    links = OrderLink.objects.filter(customer=customer)
    if params.search:
        links = links.filter(order_id__icontains=params.search.strip())
    return page(links.order_by("-linked_at", "-id"), params)


#: Sales's read that names one of its records by its id (an open check by ``order_id``).
SALES_NAMES = "sale.record.get"


# Not an assistant tool: what names the open order on the card of ``customer.order.link`` (``schemas.A_ORDER``). The
# order is Sales's, which Customers does not require: its name comes from Sales's own read, through the platform's one
# door (BASE-F84), with that read's permission. Sales off or absent → 409 ``customer.sales_unavailable``.
@operation(
    "customer.order.get",
    kind="query",
    permission="customer.view",
    input=OrderIn,
    output=OrderNamedOut,
    ai=INTERNAL,
)
def get_order(ctx: OperationContext, data: OrderIn) -> dict:
    unavailable = Conflict(str(SALES_UNAVAILABLE), code="customer.sales_unavailable")
    named = platform.call(ctx, SALES_NAMES, {"order_id": str(data.order_id)}, unavailable=unavailable)
    return {"order_id": data.order_id, "name": named.name}
