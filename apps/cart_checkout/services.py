"""Write operations of the cart_checkout app: one operation = one transaction, with its events in the
outbox.

Every check runs before the first write, so a refusal leaves no trace: no row, no order number spent, no
event (the old module answered «ok» to an action on a cart that was not active or to a step from the
wrong state, spent an order number on an order it did not save and emitted the event anyway). An action
locks the cart's row first (and then its line or its order), so two people at once go one after the
other and the second hears why. The order number of the day comes from the counter's row raised with
``UPDATE … RETURNING`` in the order's transaction (never a sequence). A session code two saves take at
once ends in the database's unique constraint, translated to the same 409 as the check.

Nothing here is fiscal and nothing charges: «paid» is a mark a person sets after charging some other
way; no sale, invoice, VeriFactu record, cash or stock movement is created.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.cart_checkout import events
from apps.cart_checkout.models import ACTOR_MAX_LENGTH, QUANTITY, Cart, CartItem, Order, OrderCounter
from apps.cart_checkout.queries import (
    business_currency,
    cart_row,
    find_cart,
    find_item,
    find_order,
    item_row,
    order_row,
    state_of,
)
from apps.cart_checkout.schemas import (
    AbandonIn,
    CartIn,
    CartOut,
    CartRefIn,
    CheckoutIn,
    CleanupIn,
    CleanupOut,
    CustomerEraseIn,
    CustomerEraseOut,
    FailIn,
    ItemAddIn,
    ItemChangeOut,
    ItemRefIn,
    ItemUpdateIn,
    MAX_AMOUNT,
    OrderOut,
    OrderRefIn,
)

SESSION_TAKEN = _("There is already a cart with that session.")
CART_NOT_ACTIVE = _("This cart no longer takes changes: it is %(status)s.")
CART_EMPTY = _("This cart has no lines: add a product before starting the order.")
EMAIL_MISSING = _("Say the customer's email: the cart has none.")
PAY_REFUSED = _("Only an initiated order can be marked as paid; this one is %(status)s.")
FAIL_REFUSED = _("Only an initiated or paid order can fail; this one is %(status)s.")
COMPLETE_REFUSED = _("Only a paid order can be completed; this one is %(status)s.")
LINE_TOO_LARGE = _("The total of this line (quantity × price) is above what a cart can hold.")
CART_TOO_LARGE = _("The cart's total would be above what a cart can hold.")

#: Where an order may still fail from: a payment that failed before or after it was marked.
FAILABLE = (Order.Status.INITIATED, Order.Status.PAID)
CENT = Decimal("1")
THOUSANDTH = Decimal("0.001")


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it: an account's full name, else its email, else its username; the
    platform or an API key as they name themselves."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        name = actor.get_full_name() or actor.email or actor.get_username()
    else:
        name = str(actor)
    return name[:ACTOR_MAX_LENGTH]


def _quantity(value: Decimal) -> str:
    """A quantity as an event carries it: three decimals, as the database keeps it."""
    return str(value.quantize(THOUSANDTH))


#: The most a cart's items column holds (``Decimal(15, 3)``).
MAX_TOTAL_ITEMS = Decimal(10 ** (QUANTITY["max_digits"] - QUANTITY["decimal_places"])) - THOUSANDTH


def _line_total(quantity: Decimal, unit_price: int) -> int:
    """Quantity × price in minor units, rounded to the minor unit half up (the old money SDK's rule)."""
    return int((quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP))


def _too_large(message) -> InvalidPayload:
    return InvalidPayload(str(message), code="invalid_field", fields={"quantity": str(message)})


def _fits(cart: Cart, line_total: int, quantity: Decimal, *, replacing: CartItem | None = None) -> None:
    """Refuses a line whose total, or the cart's totals with it, leave what a cart holds (the database's
    bigint would overflow: a 500), under ``quantity``, before anything is written."""
    if line_total > MAX_AMOUNT:
        raise _too_large(LINE_TOO_LARGE)
    amount = cart.total_amount + line_total - (replacing.line_total if replacing else 0)
    items = cart.total_items + quantity - (replacing.quantity if replacing else 0)
    if amount > MAX_AMOUNT or items > MAX_TOTAL_ITEMS:
        raise _too_large(CART_TOO_LARGE)


# ── Carts ─────────────────────────────────────────────────────────────────────────────────────


def _locked(data: CartRefIn) -> Cart:
    return find_cart(data.cart_id, data.session_token, data.customer, lock=True)


def _active(cart: Cart) -> None:
    """Refuses a cart that is not active now (an active one past its expiry is expired)."""
    state = state_of(cart)
    if state != Cart.Status.ACTIVE:
        raise Conflict(
            str(CART_NOT_ACTIVE) % {"status": Cart.Status(state).label},
            code="cart_checkout.cart_not_active",
        )


def _session_taken() -> Conflict:
    return Conflict(
        str(SESSION_TAKEN),
        code="cart_checkout.session_taken",
        fields={"session_token": str(SESSION_TAKEN)},
    )


def _recount(cart: Cart, actor: str) -> None:
    """The cart's totals from its lines, summed in the database, and its last activity now."""
    sums = CartItem.objects.filter(cart=cart).aggregate(items=Sum("quantity"), amount=Sum("line_total"))
    cart.total_items = sums["items"] or Decimal("0")
    cart.total_amount = sums["amount"] or 0
    cart.last_activity_at = timezone.now()
    cart.updated_by = actor
    cart.save(update_fields=["total_items", "total_amount", "last_activity_at", "updated_by", "updated_at"])


def _cart_event(ctx: OperationContext, name: str, cart: Cart) -> None:
    record_event(ctx, name, {"id": str(cart.id), "session_token": cart.session_token})


@operation(
    "cart_checkout.cart.create",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=CartIn,
    output=CartOut,
    expose_api=True,
    ai={
        "description": "Create a shopping cart in the internal cart notebook, for a customer (email and name) or "
        "for an anonymous session code, which must be unique. Leave the currency out unless the customer asked "
        "for another one: the cart then takes the business's currency. Not the till.",
        "risk": "normal",
    },
)
def create_cart(ctx: OperationContext, data: CartIn) -> dict:
    if Cart.objects.filter(session_token=data.session_token, deleted_at__isnull=True).exists():
        raise _session_taken()
    actor = _actor(ctx)
    cart = Cart(
        session_token=data.session_token,
        customer_email=data.customer_email,
        customer_name=data.customer_name,
        currency=data.currency or business_currency(ctx),
        expires_at=data.expires_at,
        last_activity_at=timezone.now(),
        created_by=actor,
        updated_by=actor,
    )
    try:
        with atomic():
            cart.save()
    except IntegrityError:
        raise _session_taken() from None
    record_event(
        ctx,
        events.CART_CREATED,
        {"id": str(cart.id), "session_token": cart.session_token, "currency": cart.currency},
    )
    return cart_row(cart)


@operation(
    "cart_checkout.cart.mark_abandoned",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=AbandonIn,
    output=CartOut,
    expose_api=True,
    ai={
        "description": "Mark an active shopping cart as abandoned, when the customer did not finish (named by its "
        "session code, its customer or its id), with an optional reason. It keeps its lines.",
        "risk": "normal",
    },
)
def mark_abandoned(ctx: OperationContext, data: AbandonIn) -> dict:
    cart = _locked(data)
    _active(cart)
    cart.status = Cart.Status.ABANDONED
    cart.abandon_reason = data.reason
    cart.updated_by = _actor(ctx)
    cart.save(update_fields=["status", "abandon_reason", "updated_by", "updated_at"])
    _cart_event(ctx, events.CART_ABANDONED, cart)
    return cart_row(cart)


@operation(
    "cart_checkout.cart.delete",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=CartRefIn,
    output=CartOut,
    expose_api=True,
    ai={
        "description": "Delete a shopping cart in any status (named by its session code, its customer or its id). "
        "Its orders stay; its session code becomes free for another cart. It cannot be undone.",
        "risk": "high",
    },
)
def delete_cart(ctx: OperationContext, data: CartRefIn) -> dict:
    cart = _locked(data)
    cart.deleted_at = timezone.now()
    cart.updated_by = _actor(ctx)
    cart.save(update_fields=["deleted_at", "updated_by", "updated_at"])
    _cart_event(ctx, events.CART_DELETED, cart)
    return cart_row(cart)


@operation(
    "cart_checkout.cart.clear",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=CartRefIn,
    output=CartOut,
    expose_api=True,
    ai={
        "description": "Empty an active shopping cart (named by its session code, its customer or its id): every "
        "line goes and its totals go back to zero; the cart stays active.",
        "risk": "normal",
    },
)
def clear_cart(ctx: OperationContext, data: CartRefIn) -> dict:
    cart = _locked(data)
    _active(cart)
    removed, _ = CartItem.objects.filter(cart=cart).delete()
    if removed:
        _recount(cart, _actor(ctx))
        _cart_event(ctx, events.CART_CLEARED, cart)
    return cart_row(cart)


@operation(
    "cart_checkout.cart.cleanup_expired",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=CleanupIn,
    output=CleanupOut,
    expose_api=True,
    ai={
        "description": "Mark as expired every active shopping cart whose expiry has passed, and say how many. A "
        "scheduled task runs it every quarter of an hour.",
        "risk": "normal",
    },
)
def cleanup_expired(ctx: OperationContext, data: CleanupIn) -> dict:
    now = timezone.now()
    expired = Cart.objects.filter(
        deleted_at__isnull=True,
        status=Cart.Status.ACTIVE,
        expires_at__isnull=False,
        expires_at__lte=now,
    ).update(status=Cart.Status.EXPIRED, updated_by=_actor(ctx), updated_at=now)
    if expired:
        record_event(ctx, events.CART_EXPIRED, {"count": expired})
    return {"expired": expired}


# ── Lines ─────────────────────────────────────────────────────────────────────────────────────


def _change(item: CartItem | None, cart: Cart) -> dict:
    return {"item": item_row(item) if item else None, "removed": item is None, "cart": cart_row(cart)}


def _line_and_cart(item_id) -> tuple[CartItem, Cart]:
    """The line and its active cart, both locked: the cart first, as every action on a cart does."""
    cart_id = find_item(item_id).cart_id
    cart = find_cart(cart_id, lock=True)
    _active(cart)
    return find_item(item_id, lock=True), cart


@operation(
    "cart_checkout.item.add",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=ItemAddIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "description": "Add a product line to an active shopping cart (named by its session code, its customer or "
        "its id): the product's reference and name as free text, the quantity (up to three decimals) and the "
        "unit price in minor units of the cart's currency (its currency_decimals: 12.50 is 1250 with two, ¥1,250 is "
        "1250). The cart's totals are recomputed.",
        "risk": "normal",
    },
)
def add_item(ctx: OperationContext, data: ItemAddIn) -> dict:
    cart = _locked(data)
    _active(cart)
    line_total = _line_total(data.quantity, data.unit_price)
    _fits(cart, line_total, data.quantity)
    actor = _actor(ctx)
    item = CartItem.objects.create(
        cart=cart,
        product_ref=data.product_ref,
        product_name=data.product_name,
        sku=data.sku,
        quantity=data.quantity,
        unit_price=data.unit_price,
        line_total=line_total,
        variant_attributes=data.variant_attributes,
        created_by=actor,
        updated_by=actor,
    )
    _recount(cart, actor)
    record_event(
        ctx,
        events.ITEM_ADDED,
        {
            "item_id": str(item.id),
            "cart_id": str(cart.id),
            "session_token": cart.session_token,
            "product_ref": item.product_ref,
            "quantity": _quantity(item.quantity),
            "line_total": item.line_total,
        },
    )
    return _change(item, cart)


@operation(
    "cart_checkout.item.update",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=ItemUpdateIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "description": "Change the quantity of a line of an active shopping cart (by the line's id); 0 removes the "
        "line. Its total uses the price kept on the line, and the cart's totals are recomputed.",
        "risk": "normal",
    },
)
def update_item(ctx: OperationContext, data: ItemUpdateIn) -> dict:
    item, cart = _line_and_cart(data.item_id)
    actor = _actor(ctx)
    removed = data.quantity == 0
    item_id = item.id
    if removed:
        item.delete()
    else:
        line_total = _line_total(data.quantity, item.unit_price)
        _fits(cart, line_total, data.quantity, replacing=item)
        item.quantity = data.quantity
        item.line_total = line_total
        item.updated_by = actor
        item.save(update_fields=["quantity", "line_total", "updated_by", "updated_at"])
    _recount(cart, actor)
    record_event(
        ctx,
        events.ITEM_UPDATED,
        {"item_id": str(item_id), "cart_id": str(cart.id), "quantity": _quantity(data.quantity), "removed": removed},
    )
    return _change(None if removed else item, cart)


@operation(
    "cart_checkout.item.remove",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=ItemRefIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "description": "Remove a line from an active shopping cart (by the line's id); the cart's totals are "
        "recomputed.",
        "risk": "normal",
    },
)
def remove_item(ctx: OperationContext, data: ItemRefIn) -> dict:
    item, cart = _line_and_cart(data.item_id)
    item_id = item.id
    item.delete()
    _recount(cart, _actor(ctx))
    record_event(ctx, events.ITEM_REMOVED, {"item_id": str(item_id), "cart_id": str(cart.id)})
    return _change(None, cart)


# ── Orders ────────────────────────────────────────────────────────────────────────────────────


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
    day = timezone.localdate()
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
    permission="cart_checkout.checkout",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
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
    permission="cart_checkout.checkout",
    input=FailIn,
    output=OrderOut,
    expose_api=True,
    ai={
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
    permission="cart_checkout.checkout",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
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


# ── Personal data ─────────────────────────────────────────────────────────────────────────────


@operation(
    "cart_checkout.customer.erase",
    kind="command",
    permission="cart_checkout.manage_cart",
    input=CustomerEraseIn,
    output=CustomerEraseOut,
    expose_api=True,
    ai={
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
