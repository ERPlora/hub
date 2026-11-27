"""A customer's personal data in the carts and the orders: erasing it, on their right to erasure."""

from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.cart_checkout import events
from apps.cart_checkout.models import Cart, Order
from apps.cart_checkout.schemas import CustomerEraseIn, CustomerEraseOut
from apps.cart_checkout.services.carts import _actor

@operation(
    "cart_checkout.customer.erase",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=CustomerEraseIn,
    output=CustomerEraseOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "erase carmen@example.com's personal data from the carts",
                "wipe nuria@example.com from the web orders",
            ),
            "es": (
                "aplica el derecho al olvido a carmen@example.com en los carritos",
                "quita el email y las direcciones de nuria@example.com de los pedidos web",
            ),
        },
        "description": "Erase a customer's personal data (right to erasure), named by their exact email: every "
        "cart with that email, deleted ones too, loses the email, the name, the notes and the abandonment "
        "reason, and every order with that email or from one of those carts loses the email, the addresses, "
        "the notes and the failure reason. Numbers, totals and statuses stay. It cannot be undone.",
        "risk": "high",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEraseIn) -> dict:
    actor, now = _actor(ctx), timezone.now()
    carts = Cart.objects.filter(customer_email__iexact=data.email)
    cart_ids = list(carts.select_for_update().values_list("pk", flat=True))
    orders = Order.objects.filter(Q(customer_email__iexact=data.email) | Q(cart_id__in=cart_ids))
    order_ids = list(orders.select_for_update().values_list("pk", flat=True))
    Cart.objects.filter(pk__in=cart_ids).update(
        customer_email="", customer_name="", notes="", abandon_reason="", updated_by=actor, updated_at=now
    )
    Order.objects.filter(pk__in=order_ids).update(
        customer_email="",
        shipping_address={},
        billing_address={},
        notes="",
        failure_reason="",
        updated_by=actor,
        updated_at=now,
    )
    erased = {"carts": len(cart_ids), "orders": len(order_ids)}
    if cart_ids or order_ids:
        # How many, never whose: the event outlives the erasure.
        record_event(ctx, events.CUSTOMER_ERASED, erased)
    return erased
