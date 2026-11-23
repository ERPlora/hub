"""A customer put on an open order, or taken off it (CUSTOMER-F19)."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import OrderLink
from apps.customer.queries import find_customer
from apps.customer.schemas.orders import OrderCustomerOut, OrderLinkIn


@operation(
    "customer.order.link",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=OrderLinkIn,
    output=OrderCustomerOut,
    ai=AI(
        "Puts a customer on an open order (at most one per order; a new one replaces the old), or takes the customer "
        "off when none is given.",
        asks={
            "en": ("put this order on Ana", "this tab is Luis's", "take the customer off this order"),
            "es": ("Ana es la clienta de este pedido", "quita el cliente de este pedido"),
        },
    ),
)
def link_order(ctx: OperationContext, data: OrderLinkIn) -> dict:
    unlinking = data.customer_id is None and not (data.customer or "").strip()
    # The card before the link, the order a merge takes them in (cards, then what hangs from them).
    customer = (
        None if unlinking else find_customer(ctx, data.customer_id, data.customer, lock=True)
    )
    link = OrderLink.objects.select_for_update().filter(order_id=data.order_id).first()
    if customer is None:
        if link is not None:
            link.delete()
            record_event(
                ctx,
                events.ORDER_UNLINKED,
                {"order_id": str(data.order_id), "customer_id": str(link.customer_id)},
            )
        return {"order_id": data.order_id, "customer_id": None}
    if link is None or link.customer_id != customer.id:
        OrderLink.objects.update_or_create(
            order_id=data.order_id,
            defaults={"customer": customer, "linked_at": timezone.now()},
        )
        record_event(
            ctx,
            events.ORDER_LINKED,
            {"order_id": str(data.order_id), "customer_id": str(customer.id)},
        )
    return {"order_id": data.order_id, "customer_id": customer.id}
