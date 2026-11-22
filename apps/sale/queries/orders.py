"""The open checks and their lines."""

from uuid import UUID

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, operation

from apps.sale.models import Order, OrderLine
from apps.sale.schemas.orders import OrderListIn, OrderOut, OrderPage, OrderRefIn
from base.allergens import found_in

ORDER_NOT_FOUND = _("That check does not exist.")
ORDER_CHANGED = _(
    "The check changed while it was being charged: a line was added, changed, removed, voided or charged, a "
    "discount was set or removed, or the check was split, merged or closed. Nothing was charged or changed: "
    "review the lines and try again."
)


def find_order(order_id: UUID, *, lock: bool = False) -> Order:
    orders = Order.objects.select_for_update() if lock else Order.objects.all()
    order = orders.filter(pk=order_id).first()
    if order is None:
        raise NotFound(str(ORDER_NOT_FOUND), code="sale.order_not_found")
    return order


def pending_lines(order: Order) -> list[OrderLine]:
    """The lines left to charge, in order."""
    return list(order.lines.live().unpaid().order_by("position", "id"))


def dish_allergens(dish: dict) -> list[str]:
    """What a dish of a menu froze; none on a menu ordered before its dishes kept them."""
    return dish.get("allergens", [])


def _combo_row(line: OrderLine) -> dict:
    components = [
        {
            **dish,
            "allergens": dish_allergens(dish),
            "allergy_in_dish": found_in(line.allergy, dish_allergens(dish)),
            "modifiers": [option["name"] for option in dish.get("options", [])],
        }
        for dish in line.combo["components"]
    ]
    return {"combo_id": line.combo_id, **line.combo, "components": components}


def order_line_row(line: OrderLine) -> dict:
    return {
        "id": line.id,
        "position": line.position,
        "product_id": line.product_id,
        "department_id": line.department_id,
        "name": line.name,
        "sku": line.sku,
        "is_service": line.is_service,
        "unit": line.unit,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "price_quantity": line.price_quantity,
        "pricing_unit": line.pricing_unit,
        "tax_category_key": line.tax_category_key,
        "discount_percent": line.discount_percent,
        "discount_approved": bool(line.discount_approved_by),
        "is_gift": line.is_gift,
        "gift_reason": line.gift_reason,
        "notes": line.notes,
        "staff_id": line.staff_id,
        "service_id": line.service_id,
        "paid_by_voucher": line.paid_by_voucher,
        "voucher_session_id": line.voucher_session_id,
        "voucher_grant_id": line.voucher_grant_id,
        "voucher_name": line.voucher_name,
        "voucher_remaining": line.voucher_remaining,
        "voucher_hold_until": line.voucher_hold_until,
        "line_total": line.line_total,
        "round_no": line.round_no,
        "fired_at": line.fired_at,
        "modifiers": line.modifiers,
        "modifier_lines": [
            {
                "option_id": own["option_id"],
                "name": own["name"],
                "tax_category_key": own["tax_category_key"],
                "unit_price": own["price_delta"],
                "quantity": own["quantity"],
            }
            for own in line.modifier_lines
        ],
        "kitchen_text": line.kitchen_text,
        "allergens": line.allergens,
        "allergy": line.allergy,
        "allergy_in_dish": found_in(line.allergy, line.allergens),
        "combo": _combo_row(line) if line.combo_id else None,
    }


def order_detail(order: Order) -> dict:
    lines = pending_lines(order)
    return {
        "id": order.id,
        "status": order.status,
        "label": order.label,
        "notes": order.notes,
        "appointment_id": order.appointment_id,
        "staff_id": order.staff_id,
        "staff_name": order.staff_name,
        "discount_percent": order.discount_percent,
        "discount_amount": order.discount_amount,
        "discount_approved": bool(order.discount_approved_by),
        "provisional_total": order.provisional_total,
        "version": order.version,
        "lines_count": len(lines),
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "lines": [order_line_row(line) for line in lines],
        "merged_into_id": order.merged_into_id,
    }


@operation(
    "sale.order.get",
    kind="query",
    permission="sale.view_sale",
    input=OrderRefIn,
    output=OrderOut,
    expose_api=True,
    ai=AI(
        description="Get an open check with the lines left to charge (each with its frozen price, quantity, discount, comp, "
        "note, professional and kitchen round), its ticket discount and its provisional total.",
        asks={
            "en": (
                "what's on table 4's check?",
                "how much is that open tab so far?",
                "what did the terrace order?",
            ),
            "es": (
                "¿qué lleva la cuenta de la mesa 4?",
                "¿cuánto va la cuenta de la terraza?",
                "¿qué han pedido en la 6?",
            ),
        },
    ),
)
def get_order(ctx: OperationContext, params: OrderRefIn) -> dict:
    return order_detail(find_order(params.order_id))


@operation(
    "sale.order.list",
    kind="query",
    permission="sale.view_sale",
    input=OrderListIn,
    output=OrderPage,
    expose_api=True,
    ai=AI(
        description="List the open checks of the business (a table's, a tab, a parked ticket: what is still to "
        "charge), or of another status, newest first, with their title and total.",
        asks={
            "en": (
                "which checks are still open?",
                "any tabs left unpaid?",
                "show me the parked tickets",
            ),
            "es": (
                "¿qué cuentas hay abiertas?",
                "¿queda alguna mesa sin cobrar?",
                "enséñame las cuentas aparcadas",
            ),
        },
    ),
)
def list_orders(ctx: OperationContext, params: OrderListIn) -> dict:
    orders = Order.objects.annotate(
        pending=Count(
            "lines", filter=Q(lines__removed_at__isnull=True, lines__sale__isnull=True)
        )
    )
    if params.status:
        orders = orders.filter(status=params.status)
    if params.search:
        orders = orders.filter(label__icontains=params.search.strip())
    page = orders.order_by("-created_at", "-id")[
        params.offset : params.offset + params.limit
    ]
    rows = [
        {
            "id": order.id,
            "status": order.status,
            "label": order.label,
            "provisional_total": order.provisional_total,
            "lines_count": order.pending,
            "appointment_id": order.appointment_id,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }
        for order in page
    ]
    return {
        "rows": rows,
        "total": orders.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
