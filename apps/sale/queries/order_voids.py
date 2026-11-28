"""Who may void an open check (SALE-F18): an empty one, whoever builds checks; one with something ordered or charged
on it, only whoever holds the void permission. The void asks it, and the assistant before drawing the void's card, so
nobody confirms a card the void then refuses."""

from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation

from apps.sale.models.orders import Order
from apps.sale.queries.orders import find_order
from apps.sale.schemas.orders import OrderRefIn
from apps.sale.schemas.records import CheckFoundOut

VOID_PERMISSION = "sale.void_sale"


def refuse_unpermitted_void(ctx: OperationContext, order: Order) -> None:
    """Refuses voiding ``order`` for ``ctx``'s person when it has something on it and they lack ``VOID_PERMISSION``,
    with the code the till answers with a manager's approval."""
    if not ctx.has(VOID_PERMISSION) and (order.lines.live().exists() or order.sales.exists()):
        raise PermissionDenied(gettext("Permission “%(permission)s” is required.") % {"permission": VOID_PERMISSION})


@operation(
    "sale.order.check_void",
    kind="query",
    permission="sale.add_sale",
    input=OrderRefIn,
    output=CheckFoundOut,
    ai=INTERNAL,
)
def check_void(ctx: OperationContext, data: OrderRefIn) -> dict:
    """The open check ``sale.order.void`` voids, once its person may void it. One no longer open is the void's to
    answer, as it does before it looks at who asks."""
    order = find_order(data.order_id)
    if order.status == Order.Status.OPEN:
        refuse_unpermitted_void(ctx, order)
    return {"id": order.id}
