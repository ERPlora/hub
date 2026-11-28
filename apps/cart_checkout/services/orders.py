"""Orders: starting one from a cart, with its number of the day, and its steps (paid, failed, completed)."""

from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.cart_checkout import events
from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter
from apps.cart_checkout.queries.reads import find_order
from apps.cart_checkout.queries.rows import order_row
from apps.cart_checkout.schemas import CheckoutIn, FailIn, OrderOut, OrderRefIn
from apps.cart_checkout.services.carts import _active, _actor, _locked
from base.business import business_zone

CART_EMPTY = _("This cart has no lines: add a product before starting the order.")
EMAIL_MISSING = _("Say the customer's email: the cart has none.")
PAY_REFUSED = _("Only an initiated order can be marked as paid; this one is %(status)s.")
FAIL_REFUSED = _("Only an initiated or paid order can fail; this one is %(status)s.")
COMPLETE_REFUSED = _("Only a paid order can be completed; this one is %(status)s.")

#: Where an order may still fail from: a payment that failed before or after it was marked.
FAILABLE = (Order.Status.INITIATED, Order.Status.PAID)


def _number(day) -> int:
    """The next order number of ``day``: the counter's row raised with ``UPDATE … RETURNING``."""
    OrderCounter.objects.bulk_create([OrderCounter(day=day)], ignore_conflicts=True)
    counter = OrderCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


@operation(
    "cart_checkout.checkout.initiate",
    kind="command",
    permission="cart_checkout.checkout",
    input=CheckoutIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "turn Carmen's cart into an order",
                "place the order of Nuria's web basket with home delivery",
            ),
            "es": (
                "convierte el carrito de Carmen en un pedido",
                "tramita el pedido de la cesta web de Nuria con envío a casa",
            ),
        },
        "description": "Start an order from an active shopping cart with lines (named by its session code, its "
        "customer or its id): it gets its number of the day and copies the cart's total. Optionally the "
        "customer's email (else the cart's), addresses, shipping and payment methods and notes. It is not the "
        "till: it charges nothing and creates no sale or invoice.",
        "risk": "normal",
    },
)
def initiate_checkout(ctx: OperationContext, data: CheckoutIn) -> dict:
    cart = _locked(data)
    _active(cart)
    if not CartItem.objects.filter(cart=cart).exists():
        raise Conflict(str(CART_EMPTY), code="cart_checkout.cart_empty")
    email = data.customer_email or cart.customer_email
    if not email:
        raise InvalidPayload(
            str(EMAIL_MISSING), code="invalid_field", fields={"customer_email": str(EMAIL_MISSING)}
        )
    day = timezone.localdate(timezone=business_zone())
    actor = _actor(ctx)
    order = Order.objects.create(
        cart=cart,
        order_number=f"OS-{day:%Y%m%d}-{_number(day):04d}",
        customer_email=email,
        shipping_address=data.shipping_address,
        billing_address=data.billing_address or data.shipping_address,
        shipping_method=data.shipping_method,
        payment_method=data.payment_method,
        total_amount=cart.total_amount,
        currency=cart.currency,
        notes=data.notes,
        placed_at=timezone.now(),
        created_by=actor,
        updated_by=actor,
    )
    record_event(
        ctx,
        events.CHECKOUT_INITIATED,
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "cart_id": str(cart.id),
            "total_amount": order.total_amount,
            "currency": order.currency,
        },
    )
    return order_row(order)


def _step(ctx: OperationContext, order: Order, status: str, event: str, **fields) -> dict:
    """Moves the locked ``order`` to ``status`` with ``fields`` and records ``event``."""
    order.status = status
    order.updated_by = _actor(ctx)
    for field, value in fields.items():
        setattr(order, field, value)
    order.save(update_fields=["status", "updated_by", "updated_at", *fields])
    record_event(
        ctx,
        event,
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": order.total_amount,
            "currency": order.currency,
        },
    )
    return order_row(order)


def _refuse(refusal, order: Order) -> Conflict:
    return Conflict(
        str(refusal) % {"status": Order.Status(order.status).label},
        code="cart_checkout.invalid_transition",
    )


@operation(
    "cart_checkout.order.mark_paid",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.checkout",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "mark order OS-20261014-0003 as paid",
                "the customer already paid the web order by bank transfer",
            ),
            "es": (
                "marca como pagado el pedido OS-20261014-0003",
                "el cliente ya ha pagado el pedido web por transferencia",
            ),
        },
        "description": "Mark an initiated order as paid (named by its number or its id), after the customer paid "
        "some other way. It records a mark: it is not the till, charges nothing and creates no sale, invoice or "
        "cash movement. Never use it to charge a customer at the counter.",
        "risk": "high",
    },
)
def mark_paid(ctx: OperationContext, data: OrderRefIn) -> dict:
    order = find_order(data.order_id, data.order_number, lock=True)
    if order.status != Order.Status.INITIATED:
        raise _refuse(PAY_REFUSED, order)
    return _step(ctx, order, Order.Status.PAID, events.ORDER_PAID, paid_at=timezone.now())


@operation(
    "cart_checkout.order.fail",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.checkout",
    input=FailIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "the payment of OS-20261014-0003 failed",
                "the bank declined the payment of Carmen's online purchase",
            ),
            "es": (
                "el pago del pedido OS-20261014-0003 ha fallado",
                "el banco rechazó el pago del pedido web de Carmen",
            ),
        },
        "description": "Record that the payment of an initiated or paid order failed (named by its number or its "
        "id), with the mandatory reason, which stays on the order. A paid order that fails leaves no refund.",
        "risk": "high",
    },
)
def fail_order(ctx: OperationContext, data: FailIn) -> dict:
    order = find_order(data.order_id, data.order_number, lock=True)
    if order.status not in FAILABLE:
        raise _refuse(FAIL_REFUSED, order)
    return _step(
        ctx,
        order,
        Order.Status.FAILED,
        events.ORDER_FAILED,
        failure_reason=data.reason,
        failed_at=timezone.now(),
    )


@operation(
    "cart_checkout.order.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.checkout",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "complete the paid order OS-20261014-0003",
                "finish Carmen's web order, it's already paid",
            ),
            "es": (
                "completa el pedido pagado OS-20261014-0003",
                "da por terminado el pedido web de Carmen, que ya está pagado",
            ),
        },
        "description": "Complete a paid order (named by its number or its id): it becomes completed and its cart "
        "converted, in one step. Nothing fiscal or of stock happens.",
        "risk": "normal",
    },
)
def complete_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    order = find_order(data.order_id, data.order_number, lock=True)
    if order.status != Order.Status.PAID:
        raise _refuse(COMPLETE_REFUSED, order)
    cart = Cart.objects.select_for_update().get(pk=order.cart_id)
    if cart.deleted_at is None:
        cart.status = Cart.Status.CONVERTED
        cart.updated_by = _actor(ctx)
        cart.save(update_fields=["status", "updated_by", "updated_at"])
    order.cart = cart
    return _step(ctx, order, Order.Status.COMPLETED, events.ORDER_COMPLETED, completed_at=timezone.now())
