"""Read operations of the cart_checkout app (``READ ONLY``): the carts, one cart with its lines, the lines
of a cart, one line, the orders and one order.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break, so pages never overlap. A deleted
cart is never read. An active cart past its expiry reads as expired everywhere (its ``status`` is
computed when read: nobody has to run the expiry first). The ``find_*`` helpers resolve how a person
names a record (assistant, voice): a cart by its id, its session code, or its customer (exact email,
else part of the name; among several carts of one customer, the only active one; carts of different
customers, or several active ones, 409 ``cart_checkout.cart_ambiguous`` naming their codes); an order by
its id or its number; a line by its id. services.py uses them too,
inside its own transaction.
"""

from collections.abc import Callable
from uuid import UUID

from django.db.models import Case, CharField, F, Q, QuerySet, Value, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.cart_checkout.models import Cart, CartItem, Order
from apps.cart_checkout.schemas import (
    CartDetailOut,
    CartListIn,
    CartPage,
    CartRefIn,
    ItemListIn,
    ItemOut,
    ItemPage,
    ItemRefIn,
    OrderListIn,
    OrderOut,
    OrderPage,
    OrderRefIn,
)

#: The business's currency until the Hub keeps its own (the same euro the till charges in).
CURRENCY = "EUR"

CART_NOT_FOUND = _("That cart does not exist in this business.")
CART_AMBIGUOUS = _("“%(said)s” matches several carts: %(codes)s. Say which one.")
ITEM_NOT_FOUND = _("That cart line does not exist in this business.")
ORDER_NOT_FOUND = _("That order does not exist in this business.")

#: How many session codes an ambiguous reference lists.
MAX_CANDIDATES = 5

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
ITEM_ORDER = {
    "product_ref": ("product_ref",),
    "product_name": ("product_name",),
    "sku": ("sku",),
    "quantity": ("quantity",),
    "unit_price": ("unit_price",),
    "line_total": ("line_total",),
    "created_at": ("created_at",),
}
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


def business_currency() -> str:
    """The currency a cart is in when its creator does not say one (the old ``hub_settings.currency``)."""
    return CURRENCY


# --- Shared with services.py, inside the command's own transaction --------------------------------


def is_overdue(cart: Cart) -> bool:
    """An active cart whose expiry has come: it reads, and behaves, as expired."""
    return cart.expires_at is not None and cart.expires_at <= timezone.now()


def state_of(cart: Cart) -> str:
    """The status a cart has now: an active one past its expiry is expired."""
    if cart.status == Cart.Status.ACTIVE and is_overdue(cart):
        return Cart.Status.EXPIRED
    return cart.status


def live_carts() -> QuerySet:
    """The carts not deleted, each with ``state``, its status now."""
    overdue = Q(status=Cart.Status.ACTIVE, expires_at__isnull=False, expires_at__lte=timezone.now())
    return Cart.objects.filter(deleted_at__isnull=True).annotate(
        state=Case(
            When(overdue, then=Value(Cart.Status.EXPIRED)),
            default=F("status"),
            output_field=CharField(),
        )
    )


def _person(cart: Cart) -> tuple[str, str]:
    """Who a cart is of, as two carts are compared: the email in lowercase, the name without case or
    extra spaces."""
    return cart.customer_email.strip().lower(), " ".join(cart.customer_name.split()).casefold()


def _one_customer(carts: list[Cart]) -> bool:
    """Every cart is of the same customer: one non-empty email, or one non-empty full name."""
    emails = {_person(cart)[0] for cart in carts}
    names = {_person(cart)[1] for cart in carts}
    return (len(emails) == 1 and "" not in emails) or (len(names) == 1 and "" not in names)


def _by_customer(said: str) -> UUID | None:
    """The cart of the customer ``said`` names: the exact email, else part of the name. Among several
    carts of ONE customer, the only active one (an old converted cart does not make «Ana's cart»
    ambiguous); carts of different customers («ana» is a piece of «Mariana») are always asked about."""
    candidates: list[Cart] = []
    for lookup in (Q(customer_email__iexact=said), Q(customer_name__icontains=said)):
        candidates = list(live_carts().filter(lookup).order_by("session_token", "id"))
        if candidates:
            break
    if len(candidates) > 1:
        active = [cart for cart in candidates if cart.state == Cart.Status.ACTIVE]
        if len(active) == 1 and _one_customer(candidates):
            return active[0].pk
        listed = active if len(active) > 1 else candidates
        codes = ", ".join(cart.session_token for cart in listed[:MAX_CANDIDATES])
        raise Conflict(
            str(CART_AMBIGUOUS) % {"said": said, "codes": codes},
            code="cart_checkout.cart_ambiguous",
        )
    return candidates[0].pk if candidates else None


def find_cart(
    cart_id: UUID | None,
    session_token: str | None = None,
    customer: str | None = None,
    *,
    lock: bool = False,
) -> Cart:
    """A cart not deleted, by its id, its session code or its customer (in that order of precedence)."""
    found = Cart.objects.filter(deleted_at__isnull=True)
    if cart_id is not None:
        found = found.filter(pk=cart_id)
    elif session_token is not None:
        found = found.filter(session_token=session_token)
    else:
        found = found.filter(pk=_by_customer(customer or ""))
    cart = (found.select_for_update() if lock else found).first()
    if cart is None:
        raise NotFound(str(CART_NOT_FOUND), code="cart_checkout.cart_not_found")
    return cart


def find_item(item_id: UUID, *, lock: bool = False) -> CartItem:
    """A line of a cart that is not deleted."""
    found = CartItem.objects.filter(pk=item_id, cart__deleted_at__isnull=True)
    item = (found.select_for_update(of=("self",)) if lock else found).first()
    if item is None:
        raise NotFound(str(ITEM_NOT_FOUND), code="cart_checkout.item_not_found")
    return item


def find_order(order_id: UUID | None, order_number: str | None, *, lock: bool = False) -> Order:
    """An order by its id or its number (uppercase, as the schema keeps it)."""
    found = Order.objects.select_related("cart")
    found = found.filter(pk=order_id) if order_id is not None else found.filter(order_number=order_number)
    order = (found.select_for_update(of=("self",)) if lock else found).first()
    if order is None:
        raise NotFound(str(ORDER_NOT_FOUND), code="cart_checkout.order_not_found")
    return order


def cart_row(cart: Cart) -> dict:
    """A cart as the operations give it, with its status now."""
    return {
        "id": cart.id,
        "session_token": cart.session_token,
        "customer_email": cart.customer_email,
        "customer_name": cart.customer_name,
        "status": getattr(cart, "state", None) or state_of(cart),
        "total_items": cart.total_items,
        "total_amount": cart.total_amount,
        "currency": cart.currency,
        "expires_at": cart.expires_at,
        "last_activity_at": cart.last_activity_at,
        "notes": cart.notes,
        "abandon_reason": cart.abandon_reason,
        "created_by": cart.created_by,
        "updated_by": cart.updated_by,
        "created_at": cart.created_at,
        "updated_at": cart.updated_at,
    }


def item_row(item: CartItem) -> dict:
    return {
        "id": item.id,
        "cart_id": item.cart_id,
        "product_ref": item.product_ref,
        "product_name": item.product_name,
        "sku": item.sku,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
        "variant_attributes": item.variant_attributes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def order_row(order: Order) -> dict:
    return {
        "id": order.id,
        "cart_id": order.cart_id,
        "session_token": order.cart.session_token,
        "order_number": order.order_number,
        "customer_email": order.customer_email,
        "shipping_address": order.shipping_address,
        "billing_address": order.billing_address,
        "shipping_method": order.shipping_method,
        "payment_method": order.payment_method,
        "status": order.status,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "notes": order.notes,
        "failure_reason": order.failure_reason,
        "placed_at": order.placed_at,
        "paid_at": order.paid_at,
        "failed_at": order.failed_at,
        "completed_at": order.completed_at,
        "created_by": order.created_by,
        "updated_by": order.updated_by,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


# --- Lists ----------------------------------------------------------------------------------------


def _sorted(rows: QuerySet, sort: str, columns: dict, tie: tuple[str, ...]) -> QuerySet:
    """``rows`` by ``sort`` (a column, ``-`` first for descending), then ``tie`` and ``id``, all in the
    same direction; empty values last."""
    descending = sort.startswith("-")
    fields = columns[sort.removeprefix("-")]
    rest = [field for field in tie if field not in fields]
    return rows.order_by(
        *(
            F(field).desc(nulls_last=True) if descending else F(field).asc(nulls_last=True)
            for field in (*fields, *rest, "id")
        )
    )


def _page(rows: QuerySet, params, row: Callable) -> dict:
    total = rows.count()
    window = rows[params.offset : params.offset + params.limit]
    return {
        "rows": [row(item) for item in window],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def _bounds(**bounds) -> dict:
    return {lookup: value for lookup, value in bounds.items() if value is not None}


def _containing(**fragments) -> dict:
    """``field__icontains`` for every fragment given (stripped; an empty one narrows nothing)."""
    return {
        f"{field}__icontains": text.strip()
        for field, text in fragments.items()
        if text is not None and text.strip()
    }


# --- Carts ----------------------------------------------------------------------------------------


@operation(
    "cart_checkout.cart.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=CartListIn,
    output=CartPage,
    expose_api=True,
    ai={
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
        carts = carts.filter(
            Q(session_token__icontains=text) | Q(customer_email__icontains=text) | Q(customer_name__icontains=text)
        )
    carts = carts.filter(
        **_containing(
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
    return _page(_sorted(carts, params.sort, CART_ORDER, ("created_at",)), params, cart_row)


@operation(
    "cart_checkout.cart.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=CartRefIn,
    output=CartDetailOut,
    expose_api=True,
    ai={
        "description": "Get one shopping cart with all its lines (product, quantity, unit price, line total), "
        "named by its session code, by its customer's email or name, or by its id.",
        "risk": "normal",
    },
)
def get_cart(ctx: OperationContext, data: CartRefIn) -> dict:
    cart = find_cart(data.cart_id, data.session_token, data.customer)
    return {**cart_row(cart), "items": [item_row(item) for item in cart.items.order_by("created_at", "id")]}


# --- Lines ----------------------------------------------------------------------------------------


@operation(
    "cart_checkout.item.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=ItemListIn,
    output=ItemPage,
    expose_api=True,
    ai={
        "description": "List the lines of one shopping cart (named by its session code or id): product reference "
        "and name, SKU, quantity, unit price and line total in minor units.",
        "risk": "normal",
    },
)
def list_items(ctx: OperationContext, params: ItemListIn) -> dict:
    cart = find_cart(params.cart_id, params.session_token)
    items = CartItem.objects.filter(cart=cart)
    if params.search and params.search.strip():
        text = params.search.strip()
        items = items.filter(
            Q(product_ref__icontains=text) | Q(product_name__icontains=text) | Q(sku__icontains=text)
        )
    if params.product_ref:
        items = items.filter(product_ref=params.product_ref.strip())
    items = items.filter(
        **_containing(product_name=params.product_name, sku=params.sku),
        **_bounds(
            quantity__gte=params.quantity_min,
            quantity__lte=params.quantity_max,
            unit_price__gte=params.unit_price_min,
            unit_price__lte=params.unit_price_max,
            line_total__gte=params.line_total_min,
            line_total__lte=params.line_total_max,
        ),
    )
    return _page(_sorted(items, params.sort, ITEM_ORDER, ("created_at",)), params, item_row)


@operation(
    "cart_checkout.item.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=ItemRefIn,
    output=ItemOut,
    expose_api=True,
    ai={
        "description": "Get one line of a shopping cart by its id, with its quantity and the unit price kept on it.",
        "risk": "normal",
    },
)
def get_item(ctx: OperationContext, data: ItemRefIn) -> dict:
    return item_row(find_item(data.item_id))


# --- Orders ---------------------------------------------------------------------------------------


@operation(
    "cart_checkout.order.list",
    kind="query",
    permission="cart_checkout.view_cart",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai={
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
        orders = orders.filter(Q(order_number__icontains=text) | Q(customer_email__icontains=text))
    if params.cart_id:
        orders = orders.filter(cart_id=params.cart_id)
    if params.status:
        orders = orders.filter(status=params.status)
    if params.shipping_method and params.shipping_method.strip():
        orders = orders.filter(shipping_method__iexact=params.shipping_method.strip())
    if params.currency and params.currency.strip():
        orders = orders.filter(currency=params.currency.strip().upper())
    orders = orders.filter(
        **_containing(
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
    return _page(_sorted(orders, params.sort, ORDER_ORDER, ("created_at",)), params, order_row)


@operation(
    "cart_checkout.order.get",
    kind="query",
    permission="cart_checkout.view_cart",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Get one order with everything it has (addresses, shipping and payment methods, dates, "
        "notes, why it failed), named by its number (OS-20261014-0003) or its id.",
        "risk": "normal",
    },
)
def get_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    return order_row(find_order(data.order_id, data.order_number))
