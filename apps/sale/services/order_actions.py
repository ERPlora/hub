"""What is done to an open check as a whole: sending it to the kitchen, splitting, merging and voiding it, and its
title and appointment."""


from django.db import IntegrityError
from django.db.models import F, Max
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import AI, atomic, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Order, OrderLine
from apps.sale.queries.business import actor
from apps.sale.queries.orders import ORDER_CHANGED, ORDER_NOT_FOUND, dish_allergens, find_order, order_detail
from apps.sale.queries.people import member_name, person_label
from apps.sale.schemas.orders import (
    OrderFireIn,
    OrderFireOut,
    OrderMergeIn,
    OrderOut,
    OrderRefIn,
    OrderSetAppointmentIn,
    OrderSetLabelIn,
    OrderSetStaffIn,
    OrderSplitIn,
    OrderSplitOut,
)
from apps.sale.services.line_vouchers import _release_vouchers
from apps.sale.services.orders import (
    ORDER_UNAVAILABLE,
    _next_position,
    _open_order,
    _out,
    _still_open,
    _touch,
    lock_orders,
)

NOTHING_TO_FIRE = _("There is nothing new to send to the kitchen.")
APPOINTMENT_CHECK_OPEN = _(
    "That appointment already has an open check: charge that one (Open checks)."
)


@operation(
    "sale.order.fire",
    kind="command",
    permission="sale.add_sale",
    input=OrderFireIn,
    output=OrderFireOut,
    ai=AI(
        description="Send the pending lines of an open check to the kitchen as a new round (a double send sends nothing "
        "twice). The label is what the kitchen reads as the check's name (e.g. Table 4).",
        risk="normal",
        asks={
            "en": (
                "send table 4 to the kitchen",
                "fire the mains",
                "send the order through",
            ),
            "es": (
                "manda la comanda de la mesa 4 a cocina",
                "marcha los segundos",
                "pasa lo de la terraza a cocina",
            ),
        },
    ),
)
def fire(ctx: OperationContext, data: OrderFireIn) -> dict:
    order = _still_open(data.order_id)
    pending = list(
        order.lines.live()
        .unpaid()
        .select_for_update()
        .filter(fired_at__isnull=True)
        .order_by("position", "id")
    )
    if not pending:
        raise Conflict(str(NOTHING_TO_FIRE), code="sale.nothing_to_fire")
    round_no = (order.lines.aggregate(last=Max("round_no"))["last"] or 0) + 1
    now = timezone.now()
    OrderLine.objects.filter(pk__in=[line.pk for line in pending]).update(
        round_no=round_no, fired_at=now
    )
    record_event(
        ctx,
        events.ORDER_FIRED,
        {
            "order_id": str(order.id),
            "label": data.label or order.label,
            "channel": data.channel,
            "priority": data.priority,
            "round_no": round_no,
            # Whoever the till names, else who serves the check, else who sends the round.
            "waiter": (data.waiter or order.staff_name or person_label(ctx.actor))[:128],
            "items": [
                {
                    "order_item_id": str(line.id),
                    "product_id": str(line.product_id) if line.product_id else None,
                    "product_name": line.name,
                    "quantity": f"{line.quantity:.3f}",
                    "unit": line.unit,
                    "notes": " · ".join(
                        text
                        for text in (
                            line.notes,
                            line.gift_reason if line.is_gift else "",
                        )
                        if text
                    ),
                    "is_service": line.is_service,
                    "category_id": str(line.category_id) if line.category_id else None,
                    "staff_id": str(line.staff_id) if line.staff_id else None,
                    "modifiers": line.kitchen_text,
                    "allergens": line.allergens,
                    "allergy": line.allergy,
                    "kitchen_name": line.combo.get("kitchen_name", "") if line.combo_id else "",
                    "components": [
                        {
                            "product_id": dish["product_id"],
                            "product_name": dish["product_name"],
                            "category_id": dish["category_id"],
                            "quantity": f"{dish['quantity'] * line.quantity:.3f}",
                            "allergens": dish_allergens(dish),
                        }
                        for dish in (line.combo.get("components", []) if line.combo_id else [])
                    ],
                }
                for line in pending
            ],
        },
    )
    _touch(ctx, order)
    return {"order": _out(order), "round_no": round_no, "lines_count": len(pending)}


@operation(
    "sale.order.split",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSplitIn,
    output=OrderSplitOut,
    ai=AI(
        description="Split an open check in two: the lines named move whole (amount, VAT and kitchen round) to a new check; "
        "with no lines the new check is blank. Resolve the check with sale.order.list(search=...) and the lines to move "
        "with sale.order.get; never ask the person for order_id or line_ids. Both add up to the original to the cent.",
        risk="normal",
        asks={
            "en": (
                "split table 4's bill in two",
                "move the drinks to another check, they pay separately",
            ),
            "es": (
                "divide la cuenta de la mesa 4",
                "pasa las bebidas a otra cuenta, que pagan aparte",
            ),
        },
    ),
)
def split(ctx: OperationContext, data: OrderSplitIn) -> dict:
    order = _open_order(data.order_id)
    moving = []
    if data.line_ids:
        moving = list(
            order.lines.live()
            .unpaid()
            .select_for_update()
            .filter(pk__in=data.line_ids)
            .order_by("position", "id")
        )
        if not moving:
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    new_order = Order.objects.create(
        label=data.label, staff_id=order.staff_id, staff_name=order.staff_name, created_by=actor(ctx)
    )
    for position, line in enumerate(moving, start=1):
        line.order = new_order
        line.position = position
    OrderLine.objects.bulk_update(moving, ["order", "position"])
    record_event(
        ctx,
        events.ORDER_OPENED,
        {"order_id": str(new_order.id), "lines_count": len(moving)},
    )
    _touch(ctx, order)
    _touch(ctx, new_order)
    return {"order": _out(order), "new_order": _out(new_order)}


@operation(
    "sale.order.merge",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderMergeIn,
    output=OrderOut,
    ai=AI(
        description="Join two open checks: every unpaid line of the first moves to the second (what was sent to the kitchen "
        "keeps its round) and the first ends voided. Repeating it changes nothing.",
        risk="normal",
        asks={
            "en": (
                "merge the checks of tables 3 and 4",
                "put the bar tab together with table 2's",
            ),
            "es": (
                "junta las cuentas de la 3 y la 4",
                "une la cuenta de la barra con la de la mesa 2",
            ),
        },
    ),
)
def merge(ctx: OperationContext, data: OrderMergeIn) -> dict:
    if data.from_order_id == data.to_order_id:
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    # Both rows locked in id order, as the Hub admin's «Delete selected» locks them: never in a circle.
    locked = {order.id: order for order in lock_orders([data.from_order_id, data.to_order_id])}
    source, target = locked.get(data.from_order_id), locked.get(data.to_order_id)
    if source is None or target is None:
        raise NotFound(
            str(ORDER_NOT_FOUND),
            code="sale.order_not_found",
        )
    if target.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    if (
        source.status == Order.Status.VOIDED
        and not source.lines.live().unpaid().exists()
    ):
        return order_detail(target)  # a replay: it was merged already
    if source.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    moving = list(source.lines.live().unpaid().order_by("position", "id"))
    position = _next_position(target)
    for offset, line in enumerate(moving):
        line.order = target
        line.position = position + offset
    OrderLine.objects.bulk_update(moving, ["order", "position"])
    source.status = Order.Status.VOIDED
    source.voided_by = actor(ctx)
    source.closed_at = timezone.now()
    source.merged_into_id = target.id
    source.save(
        update_fields=["status", "voided_by", "closed_at", "merged_into_id", "updated_at"]
    )
    _touch(ctx, source, event=False)
    record_event(
        ctx,
        events.ORDER_MERGED,
        {"from_order_id": str(source.id), "to_order_id": str(target.id)},
    )
    _touch(ctx, target)
    return _out(target)


#: Voiding a check with something ordered or charged on it is a manager's (SALE-F18).
VOID_PERMISSION = "sale.void_sale"


@operation(
    "sale.order.void",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    # An empty check (no live line, no charge) is voided by whoever builds checks: a party that leaves
    # without ordering needs no manager (TABLE-F21). One with something on it asks ``VOID_PERMISSION``.
    permission="sale.add_sale",
    input=OrderRefIn,
    output=OrderOut,
    ai=AI(
        description="Void (delete) an open check before it is charged: it is kept as voided, never erased. What was already "
        "charged from it stays in its sales. An empty check (nothing ordered, nothing charged) can be voided by whoever "
        "builds checks; one with lines or charges needs the void permission.",
        risk="high",
        asks={
            "en": (
                "delete that empty check",
                "cancel table 5's check, they left without ordering",
            ),
            "es": (
                "anula la cuenta vacía de la barra",
                "cancela la cuenta de la mesa 5, que se fueron sin pedir",
            ),
        },
    ),
)
def void_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    return _void_order(ctx, data)


@operation(
    "sale.order.void_ordered",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    # The manager's door to the very same void for a check with something ordered or charged on it (SALE-F18):
    # its own permission is the void's, so a cashier's request is one a manager approves with their PIN (BASE-F84).
    permission=VOID_PERMISSION,
    input=OrderRefIn,
    output=OrderOut,
    ai=AI(
        description="The manager's door to the very same void as sale.order.void, for an open check with something "
        "ordered or charged on it: kept as voided, never erased. An empty check is voided with sale.order.void.",
        risk="high",
        asks={
            "en": (
                "throw away table 5's check even though it has drinks on it",
                "void that check with food on it, I'm the manager",
            ),
            "es": (
                "anula la cuenta de la 5 aunque tenga cosas",
                "cancela la cuenta de la mesa 2 con lo que ya han tomado, lo autorizo yo",
            ),
        },
    ),
)
def void_ordered(ctx: OperationContext, data: OrderRefIn) -> dict:
    return _void_order(ctx, data)


def _void_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    order = find_order(data.order_id, lock=True)
    if order.status == Order.Status.VOIDED:
        return order_detail(order)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_UNAVAILABLE), code="sale.order_unavailable")
    if not ctx.has(VOID_PERMISSION) and (
        order.lines.live().exists() or order.sales.exists()
    ):
        raise PermissionDenied(
            gettext("Permission “%(permission)s” is required.")
            % {"permission": VOID_PERMISSION}
        )
    _release_vouchers(ctx, order.lines.live().unpaid().exclude(voucher_session_id=None))
    order.status = Order.Status.VOIDED
    order.voided_by = actor(ctx)
    order.closed_at = timezone.now()
    order.version = F("version") + 1
    order.save(
        update_fields=["status", "voided_by", "closed_at", "version", "updated_at"]
    )
    record_event(ctx, events.ORDER_VOIDED, {"order_id": str(order.id)})
    return _out(order)


@operation(
    "sale.order.set_label",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetLabelIn,
    output=OrderOut,
    ai=AI(
        description="Set the title of an open check (e.g. «Table 4», «Ana — terrace»): how it is recognised among the open "
        "checks when it is parked. Find a check the person names with sale.order.list(search=...); never ask them for "
        "order_id.",
        risk="normal",
        asks={
            "en": (
                "call this check 'Ana, terrace'",
                "name the tab Table 4",
            ),
            "es": (
                "ponle de nombre «Ana — terraza» a la cuenta",
                "llama a esta cuenta «Mesa 4»",
            ),
        },
    ),
)
def set_label(ctx: OperationContext, data: OrderSetLabelIn) -> dict:
    order = _still_open(data.order_id)
    order.label = data.label
    order.save(update_fields=["label", "updated_at"])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_staff",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetStaffIn,
    output=OrderOut,
    ai=AI(
        description="Say who serves an open check (a member of Staff), or empty for whoever holds the session: the lines "
        "added from then on are theirs, the kitchen ticket names them and the sale is theirs; the lines already on it "
        "keep whoever they had. Resolve the check with sale.order.list(search=...) and the person with "
        "staff.member.list(search=...); never ask for order_id or staff_id.",
        risk="normal",
        asks={
            "en": (
                "Lucia is serving table 6",
                "put Marco in charge of the terrace check",
            ),
            "es": (
                "la cuenta de la mesa 6 la atiende Lucía",
                "que la cuenta de la terraza la lleve Marco",
            ),
        },
    ),
)
def set_staff(ctx: OperationContext, data: OrderSetStaffIn) -> dict:
    order = _still_open(data.order_id)
    order.staff_name = member_name(ctx, data.staff_id)
    order.staff_id = data.staff_id
    order.save(update_fields=["staff_id", "staff_name", "updated_at"])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_appointment",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetAppointmentIn,
    output=OrderOut,
    ai=AI(
        description="Link an open check to the appointment it charges (or unlink it): charging it then tells the diary. "
        "Find the check with sale.order.list(search=...) and the appointment by customer, service or date with "
        "appointment.appointment.list; never ask the person for order_id or appointment_id.",
        risk="normal",
        asks={
            "en": (
                "this ticket is for Ana's 5 o'clock appointment",
                "link the check to Marta's appointment",
            ),
            "es": (
                "esta cuenta es de la cita de Ana de las 5",
                "asocia la cuenta a la cita de Marta",
            ),
        },
    ),
)
def set_appointment(ctx: OperationContext, data: OrderSetAppointmentIn) -> dict:
    order = _still_open(data.order_id)
    order.appointment_id = data.appointment_id
    try:
        with atomic():
            order.save(update_fields=["appointment_id", "updated_at"])
    except IntegrityError:
        raise Conflict(
            str(APPOINTMENT_CHECK_OPEN), code="sale.appointment_check_open"
        ) from None
    _touch(ctx, order)
    return _out(order)
