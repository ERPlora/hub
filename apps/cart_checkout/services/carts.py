"""Carts: creating, abandoning, deleting, clearing and expiring them, and the lock and the check every action on a
cart starts with."""

from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.cart_checkout import events
from apps.cart_checkout.models import ACTOR_MAX_LENGTH, Cart, CartItem
from apps.cart_checkout.queries import business_currency, cart_row, find_cart, state_of
from apps.cart_checkout.schemas import AbandonIn, CartIn, CartOut, CartRefIn, CleanupIn, CleanupOut
from base.queries.people import actor_name

SESSION_TAKEN = _("There is already a cart with that session.")
CART_NOT_ACTIVE = _("This cart no longer takes changes: it is %(status)s.")


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a colleague reads them (never by their address); the platform or an API key as they name
    themselves."""
    return actor_name(ctx.actor)[:ACTOR_MAX_LENGTH]


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=CartIn,
    output=CartOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "start a shopping cart for Carmen, carmen@example.com",
                "create a new web basket for an anonymous visit",
            ),
            "es": (
                "crea un carrito para Carmen, carmen@example.com",
                "crea una cesta web nueva para una visita anónima",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=AbandonIn,
    output=CartOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "mark Carmen's cart as abandoned",
                "the customer left the web basket unfinished, set it as abandoned",
            ),
            "es": (
                "marca como abandonado el carrito de Carmen",
                "la clienta dejó la cesta web sin terminar: dala por abandonada",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=CartRefIn,
    output=CartOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete Carmen's shopping cart",
                "remove the web basket of session sess_a1b2c3 but keep its orders",
            ),
            "es": (
                "borra el carrito de Carmen",
                "elimina la cesta web de la sesión sess_a1b2c3 sin tocar sus pedidos",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=CartRefIn,
    output=CartOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "empty Carmen's shopping cart",
                "clear every line of the web basket but keep it active",
                "leave cart sess_a1b2c3 with no products",
            ),
            "es": (
                "vacía la cesta web de Carmen",
                "vacía el carrito sess_a1b2c3 sin borrarlo",
                "deja el carrito de Nuria sin ningún producto, que siga abierto",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=CleanupIn,
    output=CleanupOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "expire the shopping carts that are past their date",
                "mark the overdue web baskets as expired",
            ),
            "es": (
                "caduca los carritos que ya vencieron",
                "da por caducadas las cestas web que pasaron su fecha",
            ),
        },
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
