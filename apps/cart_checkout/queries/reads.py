"""What the reads of the cart_checkout app share, and services/ too, inside the command's own transaction: the
currency a new cart takes, a cart's status now, how a person names a cart, a line or an order, and how a list pages.
"""

from collections.abc import Callable
from uuid import UUID

from django.db.models import Case, CharField, F, Q, QuerySet, Value, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound

from apps.cart_checkout.models import Cart, CartItem, Order
from base import operations as platform
from base.text_search import contains_text

CART_NOT_FOUND = _("That cart does not exist in this business.")
CART_AMBIGUOUS = _("“%(said)s” matches several carts: %(codes)s. Say which one.")
ITEM_NOT_FOUND = _("That cart line does not exist in this business.")
ORDER_NOT_FOUND = _("That order does not exist in this business.")

#: How many session codes an ambiguous reference lists.
MAX_CANDIDATES = 5


def business_currency(ctx: OperationContext) -> str:
    """The currency a cart is in when its creator does not say one (the old ``hub_settings.currency``): the business's,
    its country's (``base.operations.business_currency``, BASE-F50), on ERPlora's own hub its issuer's country's."""
    return platform.business_currency(ctx.scope)


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
    for lookup in (Q(customer_email__iexact=said), contains_text(said, "customer_name")):
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
    found = CartItem.objects.select_related("cart").filter(pk=item_id, cart__deleted_at__isnull=True)
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


def _containing(**fragments) -> Q:
    """The rows whose field contains every fragment given (stripped; an empty one narrows nothing)."""
    found = Q()
    for field, text in fragments.items():
        if text is not None and text.strip():
            found &= contains_text(text.strip(), field)
    return found
