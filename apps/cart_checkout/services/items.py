"""A cart's lines: adding, changing and removing them, within what a cart can hold."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.cart_checkout import events, item_card
from apps.cart_checkout.models import QUANTITY, Cart, CartItem
from apps.cart_checkout.queries import cart_row, find_cart, find_item, item_row
from apps.cart_checkout.schemas import MAX_AMOUNT, ItemAddIn, ItemChangeOut, ItemRefIn, ItemUpdateIn
from apps.cart_checkout.services.carts import _active, _actor, _locked, _recount

LINE_TOO_LARGE = _("The total of this line (quantity × price) is above what a cart can hold.")
CART_TOO_LARGE = _("The cart's total would be above what a cart can hold.")

CENT = Decimal("1")
THOUSANDTH = Decimal("0.001")


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=ItemAddIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("add two shampoos to Carmen's cart", "put a bottle of wine at 12 euros each in the web basket"),
            "es": ("añade dos champús al carrito de Carmen", "mete un vino a 12 € cada uno en la cesta web"),
        },
        "description": "Add a product line to an active shopping cart (named by its session code, its customer or "
        "its id): the product's reference and name as free text, the quantity (up to three decimals) and the "
        "unit price in minor units of the cart's currency (its currency_decimals: 12.50 is 1250 with two, ¥1,250 is "
        "1250). The cart's totals are recomputed.",
        "risk": "normal",
        "summary": item_card.summary,
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
        ctx, events.ITEM_ADDED,
        {
            "item_id": str(item.id),
            "cart_id": str(cart.id),
            "session_token": cart.session_token,
            "product_ref": item.product_ref,
            "quantity": _quantity(item.quantity),
            "line_total": item.line_total,
            "currency": cart.currency,
        },
    )
    return _change(item, cart)


@operation(
    "cart_checkout.item.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=ItemUpdateIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the shampoo in Carmen's cart to two units",
                "set the wine in the web basket to five units, same price",
            ),
            "es": (
                "cambia el champú del carrito de Carmen a dos unidades",
                "pon cinco unidades del vino de la cesta web, al mismo precio",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cart_checkout.manage_cart",
    input=ItemRefIn,
    output=ItemChangeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "take the shampoo out of Carmen's cart",
                "remove the wine line from Nuria's web basket",
            ),
            "es": (
                "quita el champú del carrito de Carmen",
                "elimina el vino de la cesta web de Nuria",
            ),
        },
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
