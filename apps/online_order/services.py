"""Write operations of Online orders: one operation = one transaction, with its event in the outbox.

The order a table's customer sends (``online_order.public.send``) runs through base's public door holding
``online_order.public`` alone, and asks the other apps with ``order_caller(ctx)``: the visitor's context able to read
the table and the menu with its prices (``ORDER_READS``), and nothing that changes anything. Every price is the server's.
"""

import secrets
from dataclasses import replace

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.online_order import events
from apps.online_order.models import Order, OrderLine, TableCode
from apps.online_order.queries import COMBO_PAGE, PUBLIC, code_row, table_of
from apps.online_order.schemas import PublicSendIn, PublicSentOut, SendLineIn, TableCodeOut
from apps.table.schemas import TableRefIn
from base.apps_on import active_apps
from base.catalog_groups import every_row
from base.operations import call
from base.throttle import RateLimited, allow

#: Bytes of randomness in a table's code: 128 bits, 22 characters in the URL.
CODE_BYTES = 16


@operation(
    "online_order.qr_code.regenerate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="online_order.change_qr_code",
    input=TableRefIn,
    output=TableCodeOut,
    expose_api=True,
    ai={
        "description": "Gives a table, by its id or its number (with its zone if the number repeats), a new code for "
        "its ordering QR: the QR printed before stops working at once and the new one has to be printed. A table "
        "without a code gets its first one. It cannot be undone.",
        "risk": "high",
        "asks": {
            "en": (
                "regenerate the QR code of table 4 on the terrace",
                "someone took a photo of table 7's QR code, give it a new one",
            ),
            "es": (
                "regenera el código QR de la mesa 4 de la terraza",
                "alguien se ha llevado una foto del código QR de la mesa 7, genera otro",
            ),
        },
    },
)
def regenerate_qr_code(ctx: OperationContext, data: TableRefIn) -> dict:
    """One upsert on the table's row: two regenerations at once of a table without a code never collide."""
    table = call(ctx, "table.table.get", data.model_dump(exclude_none=True))
    code = TableCode(table_id=table.id, code=secrets.token_urlsafe(CODE_BYTES), issued_at=timezone.now())
    TableCode.objects.bulk_create(
        [code], update_conflicts=True, unique_fields=["table_id"], update_fields=["code", "issued_at"]
    )
    record_event(ctx, events.QR_CODE_REGENERATED, {"table_id": str(table.id)})
    return code_row(ctx, table, code)


#: What the send adds to the visitor's in the other apps: its table and the menu with its prices, each a read.
ORDER_READS = frozenset({"table.view_table", "inventory.view_product", "modifier.view", "combo.view"})
#: Who sends when nobody is signed in, as the outbox names them.
ONLINE_ACTOR = "online order"
#: Orders one table, and the whole business, may send within ``LIMIT_WINDOW`` seconds. By table, not by phone: the
#: phones on the restaurant's Wi-Fi share one address.
TABLE_LIMIT = 10
BUSINESS_LIMIT = 120
LIMIT_WINDOW = 600
TOO_MANY_ORDERS = _("Too many orders in a row. Try again in a few minutes or ask the staff for help.")
NOT_ON_MENU = _("This is no longer on the menu: take it out of your order and send it again.")


def order_caller(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the table and the menu with its prices in the other apps (and only that)."""
    actor = ctx.actor if ctx.actor is not None else ONLINE_ACTOR
    return replace(ctx, actor=actor, permissions=ctx.permissions | ORDER_READS)


def _count(ctx: OperationContext, table_id) -> None:
    """One more order of this table and of the business; 429 past either limit."""
    slug = ctx.scope.key
    within = allow(f"online_order:send:{slug}:{table_id}", limit=TABLE_LIMIT, window=LIMIT_WINDOW) and allow(
        f"online_order:send:{slug}", limit=BUSINESS_LIMIT, window=LIMIT_WINDOW
    )
    if not within:
        raise RateLimited(str(TOO_MANY_ORDERS))


def _not_on_menu(index: int) -> Conflict:
    message = str(NOT_ON_MENU)
    return Conflict(message, code="online_order.not_on_menu", fields={f"lines.{index}": message})


def _dish(caller: OperationContext, index: int, line: SendLineIn, dishes: dict) -> OrderLine:
    """A dish of the menu at its price, its options valued by Modifiers (which checks each group's rules)."""
    dish = dishes.get(line.product_id)
    if dish is None:
        raise _not_on_menu(index)
    picks = []
    if line.option_ids or "modifier" in active_apps(caller.scope):
        resolved = call(
            caller,
            "modifier.selection.resolve",
            {"product_id": str(dish.id), "option_ids": [str(option) for option in line.option_ids]},
            unavailable=_not_on_menu(index),
        )
        picks = [
            {"option_id": str(pick.option_id), "name": pick.name, "price_delta": pick.price_delta}
            for pick in resolved.picks
        ]
    unit_price = dish.price + sum(pick["price_delta"] for pick in picks)
    return OrderLine(product_id=dish.id, name=dish.name, unit_price=unit_price, picks=picks)


def _set_menu(caller: OperationContext, index: int, line: SendLineIn, set_menus: dict) -> OrderLine:
    """A set menu on sale, priced by Menus and combos with its supplements (which checks each course's rules)."""
    combo = set_menus.get(line.combo_id)
    if combo is None:
        raise _not_on_menu(index)
    choices = [{"option_id": str(choice.option_id), "quantity": choice.quantity} for choice in line.choices]
    resolved = call(caller, "combo.combo.resolve", {"id": str(combo.id), "choices": choices, "channel": "dine_in"})
    picks = [
        {
            "option_id": str(dish.option_id),
            "name": dish.product_name,
            "course": dish.group_name,
            "quantity": dish.quantity,
            "price_delta": dish.price_delta,
        }
        for dish in resolved.components
    ]
    return OrderLine(combo_id=combo.id, name=combo.name, unit_price=resolved.amount, picks=picks)


def _priced(caller: OperationContext, lines: list[SendLineIn]) -> list[OrderLine]:
    """Each line as the menu prices it today; the first one the menu does not offer refuses the order."""
    dishes, set_menus = {}, {}
    if any(line.product_id for line in lines):
        shown = every_row(caller, "inventory.product.list_for_sale", show_on_website=True)
        dishes = {row.id: row for row in shown}
    if any(line.combo_id for line in lines) and "combo" in active_apps(caller.scope):
        set_menus = {row.id: row for row in every_row(caller, "combo.combo.for_sale", page_size=COMBO_PAGE)}
    priced = []
    for index, line in enumerate(lines):
        own = _dish(caller, index, line, dishes) if line.product_id else _set_menu(caller, index, line, set_menus)
        own.position, own.quantity, own.notes = index, line.quantity, line.notes
        priced.append(own)
    return priced


@operation(
    "online_order.public.send",
    kind="command",
    permission=PUBLIC,
    input=PublicSendIn,
    output=PublicSentOut,
    ai=INTERNAL,
)
def public_send(ctx: OperationContext, data: PublicSendIn) -> dict:
    caller = order_caller(ctx)
    # The code's row stays locked until the COMMIT: a regeneration of the table's code waits for this order, and one
    # that came first leaves the old code opening nothing.
    table = table_of(caller, data.code, codes=TableCode.objects.select_for_update())
    _count(ctx, table.id)
    lines = _priced(caller, data.lines)
    order = Order.objects.create(table_id=table.id, total=sum(line.unit_price * line.quantity for line in lines))
    for line in lines:
        line.order = order
    OrderLine.objects.bulk_create(lines)
    record_event(caller, events.ORDER_SENT, {"order_id": str(order.id), "table_id": str(table.id), "total": order.total})
    return {"id": order.id, "status": order.status, "total": order.total}
