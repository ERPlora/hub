"""Adding, changing, splitting, removing and voiding the lines of an open check."""

from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Order, OrderLine
from apps.sale.queries.business import authoriser
from apps.sale.queries.departments import hold_departments
from apps.sale.queries.line_parts import check_grid, provisional_total
from apps.sale.queries.order_lines import freeze_combo_line, freeze_open_line, freeze_product_line
from apps.sale.queries.orders import find_order
from apps.sale.queries.service_lines import Booking, freeze_service_line
from apps.sale.schemas import (
    OrderAddLineIn,
    OrderAddOpenLineIn,
    OrderAddComboLineIn,
    OrderAddServiceLineIn,
    OrderLineRefIn,
    OrderOut,
    OrderSetLineStaffIn,
    OrderUpdateLineIn,
    OrderVoidLineIn,
    SplitLineOut,
)
from apps.sale.services.line_vouchers import _release_vouchers
from apps.sale.services.orders import (
    _guard_covered,
    _next_position,
    _open_order,
    _out,
    _pending_line,
    _save_lines,
    _touch,
)

#: Units one line may be split into (a voucher covers one line of one unit).
MAX_LINE_SPLIT = 50

LINE_NOT_REMOVABLE = _(
    "That line can no longer be removed: it was sent to the kitchen (void it with a reason), it is charged or it is "
    "no longer on an open check."
)
LINE_NOT_VOIDABLE = _(
    "That line cannot be voided: only a line already sent to the kitchen, not charged, of an open check, with a reason."
)
LINE_NOT_SPLITTABLE = _(
    "This line cannot be split: it must be pending, not a comp, and of 2 to 50 whole units."
)


@operation(
    "sale.order.add_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderAddLineIn,
    output=OrderOut,
    ai=AI(
        description="Add a product of the catalog (by id, SKU or name) to an open check, with its quantity in the product's "
        "unit. Find a check the person names with sale.order.list(search=...); never ask them for order_id. The price is "
        "the catalog's and stays frozen on the line.",
        risk="normal",
        asks={
            "en": (
                "add two coffees to table 4",
                "put another beer on that tab",
                "ring up a croissant",
            ),
            "es": (
                "añade dos cafés a la mesa 4",
                "ponle otra caña a la terraza",
                "mete un cruasán en la cuenta",
            ),
        },
    ),
)
def add_line(ctx: OperationContext, data: OrderAddLineIn) -> dict:
    find_order(data.order_id)
    line = freeze_product_line(ctx, data)
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.add_open_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.sell_open_price",
    input=OrderAddOpenLineIn,
    output=OrderOut,
    ai=AI(
        description="Add an open-price line to an open check: the amount typed, charged at a department's VAT (or a tax "
        "category's when there are no departments). Find a check the person names with sale.order.list(search=...); "
        "never ask them for order_id. Needs the open-price permission.",
        risk="normal",
        asks={
            "en": (
                "add 3.50 at an open price under bakery",
                "key in 12 euros by hand in the drinks section",
            ),
            "es": (
                "marca 3,50 € a precio libre en bollería",
                "mete 12 € a mano en la sección de varios",
            ),
        },
    ),
)
def add_open_line(ctx: OperationContext, data: OrderAddOpenLineIn) -> dict:
    find_order(data.order_id)
    line = freeze_open_line(ctx, data)
    hold_departments([(data, line)])
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.add_service_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderAddServiceLineIn,
    output=OrderOut,
    expose_api=True,
    ai=AI(
        description="Add a service of Services (by id or name) to an open check. Find a check the person names with "
        "sale.order.list(search=...); never ask them for order_id. A fixed-price service takes its price; one without a "
        "fixed price (from, hourly, variable, free) needs the amount charged, within its minimum and maximum. Its tax "
        "category is the service's.",
        risk="normal",
        asks={
            "en": (
                "add a haircut to Ana's ticket",
                "put the 45 euro colour on her check",
            ),
            "es": (
                "añade un corte de pelo a la cuenta de Ana",
                "cárgale también el lavado a su cuenta",
            ),
        },
    ),
)
def add_service_line(ctx: OperationContext, data: OrderAddServiceLineIn) -> dict:
    line = freeze_service_line(
        ctx, data, Booking(find_order(data.order_id).appointment_id)
    )
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.add_combo_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderAddComboLineIn,
    output=OrderOut,
    expose_api=True,
    ai=AI(
        description="Add a menu of Menus (by id or name) to an open check with the dishes picked in each course "
        "(«menu of the day with lentils, hake and flan»). Find a check the person names with "
        "sale.order.list(search=...); never ask them for order_id. Menus checks the courses and prices it: its closed "
        "price plus the supplements, frozen on the line; the kitchen receives its dishes.",
        risk="normal",
        asks={
            "en": (
                "add a menu of the day with lentils, hake and flan",
                "add two lunch menus to table 3",
            ),
            "es": (
                "pon un menú del día con lentejas, merluza y flan",
                "añade dos menús a la mesa 3",
            ),
        },
    ),
)
def add_combo_line(ctx: OperationContext, data: OrderAddComboLineIn) -> dict:
    find_order(data.order_id)
    line = freeze_combo_line(ctx, data)
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.update_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderUpdateLineIn,
    output=OrderOut,
    ai=AI(
        description="Change a pending line of an open check: its quantity, whether it is a comp (charged at 0, with a "
        "reason) and its note. Resolve the check with sale.order.list(search=...) and its line with sale.order.get; "
        "never ask the person for order_id or line_id. Priced from the line's frozen price.",
        risk="normal",
        asks={
            "en": (
                "make it three coffees instead of two",
                "the dessert is on the house, it took too long",
                "note on the burger: no onion",
            ),
            "es": (
                "que sean tres cafés en vez de dos",
                "el postre va invitado, que ha tardado mucho",
                "pon en la hamburguesa que sea sin cebolla",
            ),
        },
    ),
)
def update_line(ctx: OperationContext, data: OrderUpdateLineIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id)
    if (data.quantity is not None and data.quantity != line.quantity) or (
        data.is_gift is not None and data.is_gift != line.is_gift
    ):
        _guard_covered(line)
    if data.quantity is not None:
        check_grid(data.quantity, line.increment, line.unit)
        line.quantity = data.quantity
    if data.is_gift is not None:
        line.is_gift = data.is_gift
        line.gift_reason = (data.gift_reason or "") if data.is_gift else ""
    elif data.gift_reason is not None and line.is_gift:
        line.gift_reason = data.gift_reason
    if data.notes is not None:
        line.notes = data.notes
    line.line_total = provisional_total(line)
    line.save()
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_line_staff",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetLineStaffIn,
    output=OrderOut,
    ai=AI(
        description="Say who did a pending line of an open check (a member of Staff), or empty for the check's professional. "
        "Resolve the check with sale.order.list(search=...), its line with sale.order.get and the person with "
        "staff.member.list(search=...); never ask for order_id, line_id or staff_id. Money does not change.",
        risk="normal",
        asks={
            "en": (
                "the colour was done by Laura",
                "put Marta on the haircut line",
            ),
            "es": (
                "el tinte lo hizo Laura",
                "pon a Marta en la línea del corte",
            ),
        },
    ),
)
def set_line_staff(ctx: OperationContext, data: OrderSetLineStaffIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id)
    line.staff_id = data.staff_id
    line.save(update_fields=["staff_id", "updated_at"])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.split_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=SplitLineOut,
    ai=AI(
        description="Split a pending line of N whole units (2 to 50) of an open check into N lines of one unit, the check "
        "worth the same; the line keeps its id and the new ones come back.",
        risk="normal",
        asks={
            "en": (
                "split the three beers into separate lines",
                "break those 4 coffees into single ones",
            ),
            "es": (
                "separa las tres cañas en líneas sueltas",
                "desglosa los 4 cafés de uno en uno",
            ),
        },
    ),
)
def split_line(ctx: OperationContext, data: OrderLineRefIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id, unfired=False)
    units = line.quantity
    if (
        line.is_fired
        or line.is_gift
        or units != units.to_integral_value()
        or not 2 <= units <= MAX_LINE_SPLIT
    ):
        raise Conflict(str(LINE_NOT_SPLITTABLE), code="sale.line_not_splittable")
    line.quantity = Decimal(1)
    line.line_total = provisional_total(line)
    line.save()
    clones = []
    for _unit in range(int(units) - 1):
        clone = OrderLine.objects.get(pk=line.pk)
        clone.pk = None
        clone.id = OrderLine._meta.pk.default()
        clone._state.adding = True
        clones.append(clone)
    position = _next_position(order)
    for offset, clone in enumerate(clones):
        clone.position = position + offset
    OrderLine.objects.bulk_create(clones)
    _touch(ctx, order)
    return {"order": _out(order), "new_line_ids": [clone.id for clone in clones]}


@operation(
    "sale.order.remove_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=OrderOut,
    ai=AI(
        description="Remove a line of an open check that was NOT sent to the kitchen yet. A line already sent is voided "
        "with a reason instead (sale.order.void_line).",
        risk="normal",
        asks={
            "en": (
                "take the croissant off, they changed their mind",
                "remove the last coffee from the check",
            ),
            "es": (
                "quita el cruasán, que ya no lo quieren",
                "elimina el último café de la cuenta",
            ),
        },
    ),
)
def remove_line(ctx: OperationContext, data: OrderLineRefIn) -> dict:
    order = find_order(data.order_id, lock=True)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(LINE_NOT_REMOVABLE), code="sale.order_line_not_removable")
    line = _pending_line(
        order,
        data.line_id,
        message=LINE_NOT_REMOVABLE,
        code="sale.order_line_not_removable",
    )
    _release_vouchers(ctx, [line])
    line.removed_at = timezone.now()
    line.save(update_fields=["removed_at", "updated_at"])
    record_event(
        ctx,
        events.ORDER_LINE_REMOVED,
        {"order_id": str(order.id), "line_id": str(line.id)},
    )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.void_line",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.void_sale",
    input=OrderVoidLineIn,
    output=OrderOut,
    ai=AI(
        description="Void a line of an open check that was ALREADY sent to the kitchen, with a mandatory reason: it leaves "
        "the check, keeps the reason, who and when, and the kitchen is told. Resolve the check with "
        "sale.order.list(search=...) and its line with sale.order.get; never ask the person for order_id or line_id.",
        risk="high",
        asks={
            "en": (
                "void the burger that already went to the kitchen",
                "cancel the fries we sent, they don't want them",
            ),
            "es": (
                "anula la hamburguesa que ya salió a cocina",
                "cancela las bravas de la comanda, que no las quieren",
            ),
        },
    ),
)
def void_line(ctx: OperationContext, data: OrderVoidLineIn) -> dict:
    order = find_order(data.order_id, lock=True)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(LINE_NOT_VOIDABLE), code="sale.order_line_not_voidable")
    line = (
        order.lines.live()
        .unpaid()
        .select_for_update()
        .filter(pk=data.line_id, fired_at__isnull=False)
        .first()
    )
    if line is None:
        raise Conflict(str(LINE_NOT_VOIDABLE), code="sale.order_line_not_voidable")
    _release_vouchers(ctx, [line])
    line.removed_at = timezone.now()
    line.void_reason = data.reason
    # Who authorised it: the manager who approved it with their PIN on the cashier's device, or who voided it.
    line.voided_by = authoriser(ctx)
    line.save(update_fields=["removed_at", "void_reason", "voided_by", "updated_at"])
    reference = {"order_id": str(order.id), "line_id": str(line.id)}
    record_event(ctx, events.ORDER_LINE_REMOVED, reference)
    record_event(ctx, events.ORDER_LINE_VOIDED, {**reference, "reason": data.reason})
    _touch(ctx, order)
    return _out(order)
