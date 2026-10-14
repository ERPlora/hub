"""Write operations of the sale app: one operation = one transaction, with its events in the outbox.

Every write on an open check locks the check's row first (``select_for_update``) and raises its
``version``, so two devices are queued and a charge can tell the check moved under it. A charge locks
the check it charges, numbers the sale with its day's counter (``UPDATE … RETURNING``, in the same
transaction: a refusal never burns a number) and marks the lines it takes. A void and a refund lock the
sale's row: whichever comes first wins.
"""

import datetime as dt
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F, Max, Sum
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.customer.queries import find_customer
from apps.sale import events, pricing
from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Refund,
    RefundLine,
    RefundPayment,
    Sale,
    SaleCounter,
    SaleLine,
    SalePayment,
    Settings,
    sale_number,
)
from apps.sale.queries import (
    CASH_LIMIT,
    CURRENCY,
    METHOD_NOT_AVAILABLE,
    ORDER_CHANGED,
    ORDER_NOT_FOUND,
    TICKET_LIMIT,
    actor,
    allowed_types,
    breakdown_rows,
    business_country,
    check_grid,
    current_settings,
    department_rates,
    department_row,
    find_department,
    find_method,
    find_order,
    find_quick_note,
    find_sale,
    find_tax_category,
    freeze_open_line,
    freeze_product_line,
    inventory_units,
    lines_to_charge,
    loose_lines,
    method_display_name,
    order_detail,
    payment_method_row,
    provisional_total,
    quick_note_row,
    ratio_of,
    returned_by_line,
    sale_detail,
    settings_row,
    tender_options,
    valuate,
)
from apps.sale.schemas import (
    CompleteIn,
    CustomerMergedIn,
    CustomerReassignOut,
    DepartmentIn,
    DepartmentOut,
    DepartmentRefIn,
    DepartmentUpdateIn,
    OrderAddLineIn,
    OrderAddOpenLineIn,
    OrderFireIn,
    OrderFireOut,
    OrderLineRefIn,
    OrderMergeIn,
    OrderOpenIn,
    OrderOut,
    OrderRefIn,
    OrderSetAppointmentIn,
    OrderSetDiscountIn,
    OrderSetLabelIn,
    OrderSetLineDiscountIn,
    OrderSetLineStaffIn,
    OrderSplitIn,
    OrderSplitOut,
    OrderUpdateLineIn,
    OrderVoidLineIn,
    PaymentMethodIn,
    PaymentMethodOut,
    QuickNoteIn,
    QuickNoteOut,
    QuickNoteRefIn,
    QuickNoteUpdateIn,
    RefundIn,
    RefundOut,
    SaleOut,
    SettingsOut,
    SettingsPatchIn,
    SplitLineOut,
    VoidIn,
)

#: Units one line may be split into (a voucher covers one line of one unit).
MAX_LINE_SPLIT = 50

ORDER_UNAVAILABLE = _("That check is no longer open.")
LINE_NOT_AVAILABLE = _(
    "That line can no longer be changed: it was sent to the kitchen, charged or removed."
)
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
NOTHING_TO_FIRE = _("There is nothing new to send to the kitchen.")
DISCOUNTS_NOT_ALLOWED = _("This business does not allow discounts.")
DISCOUNT_OVER_LIMIT = _(
    "That discount is above what this business allows without a manager's approval."
)
DISCOUNT_OUT_OF_RANGE = _("That discount is bigger than what it comes off.")
CUSTOMER_REQUIRED = _("This business requires a customer on every sale.")
INVOICE_RECIPIENT = _(
    "An invoice needs the customer's name, tax ID and address. Fill them in or charge it as a ticket."
)
TICKET_OVER_LIMIT = _(
    "Above %(limit)s this sale cannot be a ticket: charge it as an invoice with the customer's details."
)
PAYMENTS_MISMATCH = _("The payments do not add up to the total of the sale.")
INSUFFICIENT_TENDERED = _("What was handed over does not cover the amount.")
CASH_LIMIT_EXCEEDED = _(
    "By law, a sale of %(limit)s or more cannot be paid in cash, not even in part. Charge it by card, Bizum or bank transfer."
)
CHECKOUT_IN_PROGRESS = _(
    "This charge is already being recorded. Check it in Sales before charging again."
)
ALREADY_VOIDED = _("This sale is already voided.")
ALREADY_REFUNDED = _(
    "This sale already has refunds: refund what is left instead of voiding it."
)
REQUIRES_CREDIT_NOTE = _(
    "This sale carries a full invoice: issue a credit note instead of voiding it."
)
REFUND_REQUIRES_COMPLETED = _("There is no money left to refund on this sale.")
REFUND_TENDER_UNKNOWN = _("That payment is not one of this sale's.")
REFUND_TENDER_DUPLICATED = _("Each payment of the sale can be named only once.")
REFUND_EXCEEDS_TENDER = _(
    "%(method)s: %(amount)s is more than the %(remaining)s left to refund."
)
REFUND_NOT_ELIGIBLE = _("%(method)s: choose how this money goes back.")
REFUND_METHOD_UNAVAILABLE = _("That payment method is not available in this business.")
REFUND_LINE_UNKNOWN = _("That line is not one of this sale's.")
REFUND_LINE_DUPLICATED = _("Each line of the sale can be named only once.")
REFUND_LINE_ALREADY_RETURNED = _(
    "One of the lines marked already came back with another refund. Open the refund again to see what is left."
)
REFUND_LINE_QUANTITY_EXCEEDED = _(
    "One of the lines marked has fewer units left to return: another refund took part of them. Open the refund again "
    "to see what is left."
)
REFUND_IN_PROGRESS = _(
    "This refund is already being recorded. Check the sale before refunding again."
)
METHOD_EXISTS = _("There is already a payment method with that name.")


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f} €"


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with transaction.atomic():
            return Settings.objects.create(updated_by=actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


@operation(
    "sale.settings.update",
    kind="command",
    permission="sale.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    ai={
        "description": "Change the till settings field by field: which payment types charge, products and services shown, "
        "customer required, discounts and their cap (in %, per discount), parked checks, prices with VAT, the default "
        "document (ticket or invoice) and the receipt's texts. What is not sent is kept.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    changes = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)


# ── Payment methods ──────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.payment_method.create",
    kind="command",
    permission="sale.add_paymentmethod",
    input=PaymentMethodIn,
    output=PaymentMethodOut,
    ai={
        "description": "Add a payment method to the charge sheet (Bizum, bank transfer, vouchers…), saying its type: cash, "
        "card, transfer or other. Without a type it is cash (it counts in the till and is limited from 1,000 €).",
        "risk": "normal",
    },
)
def create_payment_method(ctx: OperationContext, data: PaymentMethodIn) -> dict:
    taken = {
        name.casefold() for name in PaymentMethod.objects.values_list("name", flat=True)
    }
    if data.name.casefold() in taken:
        raise Conflict(
            str(METHOD_EXISTS),
            code="sale.payment_method_exists",
            fields={"name": str(METHOD_EXISTS)},
        )
    method = PaymentMethod.objects.create(
        name=data.name,
        type=data.type,
        sort_order=data.sort_order,
        created_by=actor(ctx),
    )
    record_event(
        ctx, events.PAYMENT_METHOD_CREATED, {"id": str(method.id), "type": method.type}
    )
    methods = PaymentMethod.objects.filter(is_active=True)
    with translation.override(ctx.language):
        return payment_method_row(method, allowed_types(current_settings(), methods))


# ── Departments ──────────────────────────────────────────────────────────────────────────────────


def _department_out(ctx: OperationContext, department: Department) -> dict:
    with translation.override(ctx.language):
        return department_row(department, department_rates([department]))


@operation(
    "sale.department.create",
    kind="command",
    permission="sale.manage_settings",
    input=DepartmentIn,
    output=DepartmentOut,
    ai={
        "description": "Add a department to the till's open price: the name the cashier reads and the tax category (key, name "
        "or alias) it charges at, at a position.",
        "risk": "normal",
    },
)
def create_department(ctx: OperationContext, data: DepartmentIn) -> dict:
    category = find_tax_category(data.tax_category_key)
    department = Department.objects.create(
        name=data.name,
        tax_category=category,
        sort_order=data.sort_order,
        created_by=actor(ctx),
    )
    record_event(ctx, events.DEPARTMENT_CREATED, {"id": str(department.id)})
    return _department_out(ctx, department)


@operation(
    "sale.department.update",
    kind="command",
    permission="sale.manage_settings",
    input=DepartmentUpdateIn,
    output=DepartmentOut,
    ai={
        "description": "Change the name, the tax category or the position of a department of the open price (named by its id "
        "or its name). What was already sold keeps the name and the VAT it was charged with.",
        "risk": "normal",
    },
)
def update_department(ctx: OperationContext, data: DepartmentUpdateIn) -> dict:
    department = find_department(data.id, data.department, lock=True)
    if data.name is not None:
        department.name = data.name
    if data.tax_category_key is not None:
        department.tax_category = find_tax_category(data.tax_category_key)
    if data.sort_order is not None:
        department.sort_order = data.sort_order
    department.save()
    record_event(ctx, events.DEPARTMENT_UPDATED, {"id": str(department.id)})
    return _department_out(ctx, department)


@operation(
    "sale.department.delete",
    kind="command",
    permission="sale.manage_settings",
    input=DepartmentRefIn,
    output=DepartmentOut,
    ai={
        "description": "Retire a department of the open price (named by its id or its name). The lines already sold keep "
        "their name and VAT.",
        "risk": "normal",
    },
)
def delete_department(ctx: OperationContext, data: DepartmentRefIn) -> dict:
    department = find_department(data.id, data.department, lock=True)
    department.is_deleted = True
    department.deleted_at = timezone.now()
    department.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    record_event(ctx, events.DEPARTMENT_DELETED, {"id": str(department.id)})
    return _department_out(ctx, department)


# ── Quick notes ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.quick_note.create",
    kind="command",
    permission="sale.manage_settings",
    input=QuickNoteIn,
    output=QuickNoteOut,
    ai={
        "description": "Add a quick note to the till (e.g. «no salt»): it becomes a chip of the line-note sheet, at a position.",
        "risk": "normal",
    },
)
def create_quick_note(ctx: OperationContext, data: QuickNoteIn) -> dict:
    note = QuickNote.objects.create(
        text=data.text, sort_order=data.sort_order, created_by=actor(ctx)
    )
    record_event(ctx, events.QUICK_NOTE_CREATED, {"id": str(note.id)})
    return quick_note_row(note)


@operation(
    "sale.quick_note.update",
    kind="command",
    permission="sale.manage_settings",
    input=QuickNoteUpdateIn,
    output=QuickNoteOut,
    ai={
        "description": "Change the text or the position of a quick note of the till (named by its id or its text).",
        "risk": "normal",
    },
)
def update_quick_note(ctx: OperationContext, data: QuickNoteUpdateIn) -> dict:
    note = find_quick_note(data.id, data.quick_note, lock=True)
    if data.text is not None:
        note.text = data.text
    if data.sort_order is not None:
        note.sort_order = data.sort_order
    note.save()
    record_event(ctx, events.QUICK_NOTE_UPDATED, {"id": str(note.id)})
    return quick_note_row(note)


@operation(
    "sale.quick_note.delete",
    kind="command",
    permission="sale.manage_settings",
    input=QuickNoteRefIn,
    output=QuickNoteOut,
    ai={
        "description": "Retire a quick note of the till (named by its id or its text). The notes already written keep their text.",
        "risk": "normal",
    },
)
def delete_quick_note(ctx: OperationContext, data: QuickNoteRefIn) -> dict:
    note = find_quick_note(data.id, data.quick_note, lock=True)
    note.is_deleted = True
    note.deleted_at = timezone.now()
    note.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    record_event(ctx, events.QUICK_NOTE_DELETED, {"id": str(note.id)})
    return quick_note_row(note)


# ── Open checks: the shared steps ────────────────────────────────────────────────────────────────


def _open_order(order_id: UUID) -> Order:
    """The check, locked; refused when it is no longer open (it was charged or voided under the screen)."""
    order = find_order(order_id, lock=True)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    return order


def _still_open(order_id: UUID) -> Order:
    """The check, locked, for a change of the check itself: a closed one is unavailable."""
    order = find_order(order_id, lock=True)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_UNAVAILABLE), code="sale.order_unavailable")
    return order


def _pending_line(
    order: Order,
    line_id: UUID,
    *,
    unfired: bool = True,
    message=LINE_NOT_AVAILABLE,
    code="sale.order_line_not_available",
) -> OrderLine:
    lines = order.lines.live().unpaid().select_for_update().filter(pk=line_id)
    if unfired:
        lines = lines.filter(fired_at__isnull=True)
    line = lines.first()
    if line is None:
        raise Conflict(str(message), code=code)
    return line


def _next_position(order: Order) -> int:
    return (order.lines.aggregate(last=Max("position"))["last"] or 0) + 1


def _recount(order: Order) -> None:
    order.provisional_total = (
        order.lines.live().unpaid().aggregate(total=Sum("line_total"))["total"] or 0
    )


def _touch(ctx: OperationContext, order: Order, *, event: bool = True) -> None:
    """Recompute the provisional total, raise the version and say the check changed."""
    _recount(order)
    order.version = F("version") + 1
    order.save(update_fields=["provisional_total", "version", "updated_at"])
    if event:
        record_event(ctx, events.ORDER_CHANGED, {"order_id": str(order.id)})


def _save_lines(order: Order, lines: list[OrderLine]) -> None:
    position = _next_position(order)
    for offset, line in enumerate(lines):
        line.order = order
        line.position = position + offset
    OrderLine.objects.bulk_create(lines)


def _out(order: Order) -> dict:
    order.refresh_from_db()
    return order_detail(order)


# ── Open checks: building them ───────────────────────────────────────────────────────────────────


@operation(
    "sale.order.open",
    kind="command",
    permission="sale.add_sale",
    input=OrderOpenIn,
    output=OrderOut,
    ai={
        "description": "Open a check (an open ticket), empty or with lines: products of the catalog (by id, SKU or name, priced "
        "by the catalog and frozen) and, with the open-price permission, open-price lines by department. A title helps "
        "find it among the open checks.",
        "risk": "normal",
    },
)
def open_order(ctx: OperationContext, data: OrderOpenIn) -> dict:
    lines = loose_lines(ctx, data.lines, data.open_lines)
    order = Order.objects.create(
        label=data.label,
        notes=data.notes,
        appointment_id=data.appointment_id,
        created_by=actor(ctx),
    )
    _save_lines(order, lines)
    _recount(order)
    order.save(update_fields=["provisional_total"])
    record_event(
        ctx, events.ORDER_OPENED, {"order_id": str(order.id), "lines_count": len(lines)}
    )
    return order_detail(order)


@operation(
    "sale.order.add_line",
    kind="command",
    permission="sale.add_sale",
    input=OrderAddLineIn,
    output=OrderOut,
    ai={
        "description": "Add a product of the catalog (by id, SKU or name) to an open check, with its quantity in the product's "
        "unit. The price is the catalog's and stays frozen on the line.",
        "risk": "normal",
    },
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
    permission="sale.sell_open_price",
    input=OrderAddOpenLineIn,
    output=OrderOut,
    ai={
        "description": "Add an open-price line to an open check: the amount typed, charged at a department's VAT (or a tax "
        "category's when there are no departments). Needs the open-price permission.",
        "risk": "normal",
    },
)
def add_open_line(ctx: OperationContext, data: OrderAddOpenLineIn) -> dict:
    find_order(data.order_id)
    line = freeze_open_line(ctx, data)
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.update_line",
    kind="command",
    permission="sale.add_sale",
    input=OrderUpdateLineIn,
    output=OrderOut,
    ai={
        "description": "Change a pending line of an open check: its quantity, whether it is a comp (charged at 0, with a "
        "reason) and its note. Priced from the line's frozen price.",
        "risk": "normal",
    },
)
def update_line(ctx: OperationContext, data: OrderUpdateLineIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id)
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
    permission="sale.add_sale",
    input=OrderSetLineStaffIn,
    output=OrderOut,
    ai={
        "description": "Say who did a pending line of an open check (a member of Staff), or empty for the check's professional. "
        "Money does not change.",
        "risk": "normal",
    },
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
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=SplitLineOut,
    ai={
        "description": "Split a pending line of N whole units (2 to 50) of an open check into N lines of one unit, the check "
        "worth the same; the line keeps its id and the new ones come back.",
        "risk": "normal",
    },
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
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=OrderOut,
    ai={
        "description": "Remove a line of an open check that was NOT sent to the kitchen yet. A line already sent is voided "
        "with a reason instead (sale.order.void_line).",
        "risk": "normal",
    },
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
    permission="sale.void_sale",
    input=OrderVoidLineIn,
    output=OrderOut,
    ai={
        "description": "Void a line of an open check that was ALREADY sent to the kitchen, with a mandatory reason: it leaves "
        "the check, keeps the reason, who and when, and the kitchen is told.",
        "risk": "high",
    },
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
    line.removed_at = timezone.now()
    line.void_reason = data.reason
    line.voided_by = actor(ctx)
    line.save(update_fields=["removed_at", "void_reason", "voided_by", "updated_at"])
    reference = {"order_id": str(order.id), "line_id": str(line.id)}
    record_event(ctx, events.ORDER_LINE_REMOVED, reference)
    record_event(ctx, events.ORDER_LINE_VOIDED, {**reference, "reason": data.reason})
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.fire",
    kind="command",
    permission="sale.add_sale",
    input=OrderFireIn,
    output=OrderFireOut,
    ai={
        "description": "Send the pending lines of an open check to the kitchen as a new round (a double send sends nothing "
        "twice). The label is what the kitchen reads as the check's name (e.g. Table 4).",
        "risk": "normal",
    },
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
            "waiter": actor(ctx),
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
                }
                for line in pending
            ],
        },
    )
    _touch(ctx, order)
    return {"order": _out(order), "round_no": round_no, "lines_count": len(pending)}


# ── Open checks: splitting, merging and voiding ──────────────────────────────────────────────────


@operation(
    "sale.order.split",
    kind="command",
    permission="sale.add_sale",
    input=OrderSplitIn,
    output=OrderSplitOut,
    ai={
        "description": "Split an open check in two: the lines named move whole (amount, VAT and kitchen round) to a new check; "
        "with no lines the new check is blank. Both add up to the original to the cent.",
        "risk": "normal",
    },
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
    new_order = Order.objects.create(label=data.label, created_by=actor(ctx))
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
    permission="sale.add_sale",
    input=OrderMergeIn,
    output=OrderOut,
    ai={
        "description": "Join two open checks: every unpaid line of the first moves to the second (what was sent to the kitchen "
        "keeps its round) and the first ends voided. Repeating it changes nothing.",
        "risk": "normal",
    },
)
def merge(ctx: OperationContext, data: OrderMergeIn) -> dict:
    if data.from_order_id == data.to_order_id:
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    # Both rows locked, always in the same order: two merges at once never deadlock.
    locked = {
        order.id: order
        for order in Order.objects.select_for_update()
        .filter(pk__in=[data.from_order_id, data.to_order_id])
        .order_by("id")
    }
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
    source.save(update_fields=["status", "voided_by", "closed_at", "updated_at"])
    _touch(ctx, source, event=False)
    record_event(
        ctx,
        events.ORDER_MERGED,
        {"from_order_id": str(source.id), "to_order_id": str(target.id)},
    )
    _touch(ctx, target)
    return _out(target)


@operation(
    "sale.order.void",
    kind="command",
    permission="sale.void_sale",
    input=OrderRefIn,
    output=OrderOut,
    ai={
        "description": "Void (delete) an open check before it is charged: it is kept as voided, never erased. What was already "
        "charged from it stays in its sales.",
        "risk": "high",
    },
)
def void_order(ctx: OperationContext, data: OrderRefIn) -> dict:
    order = find_order(data.order_id, lock=True)
    if order.status == Order.Status.VOIDED:
        return order_detail(order)
    if order.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_UNAVAILABLE), code="sale.order_unavailable")
    order.status = Order.Status.VOIDED
    order.voided_by = actor(ctx)
    order.closed_at = timezone.now()
    order.version = F("version") + 1
    order.save(
        update_fields=["status", "voided_by", "closed_at", "version", "updated_at"]
    )
    record_event(ctx, events.ORDER_VOIDED, {"order_id": str(order.id)})
    return _out(order)


# ── Open checks: discounts, title and appointment ────────────────────────────────────────────────


def _cap(over_limit: bool, settings: Settings) -> int:
    return 100 if over_limit else settings.max_discount_percent


def _set_discount(
    ctx: OperationContext, data: OrderSetDiscountIn, *, over_limit: bool
) -> dict:
    order = _still_open(data.order_id)
    settings = current_settings()
    percent = data.discount_percent
    amount = (
        order.discount_amount if data.discount_amount is None else data.discount_amount
    )
    if (percent > 0 or amount > 0) and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    lines = list(order.lines.live().unpaid())
    gross = sum(
        pricing.half_up(
            Fraction(line.line_total) * (1 - Fraction(percent) / 100)
        )
        for line in lines
        if not line.is_gift
    )
    if amount > gross:
        raise Conflict(
            str(DISCOUNT_OUT_OF_RANGE),
            code="sale.discount_out_of_range",
            fields={"discount_amount": str(DISCOUNT_OUT_OF_RANGE)},
        )
    cap = _cap(over_limit, settings)
    if cap < 100 and (percent > cap or amount > gross * cap // 100):
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    order.discount_percent = percent
    order.discount_amount = amount
    order.discount_approved_by = (
        actor(ctx) if over_limit and (percent > 0 or amount > 0) else ""
    )
    order.save(
        update_fields=[
            "discount_percent",
            "discount_amount",
            "discount_approved_by",
            "updated_at",
        ]
    )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_discount",
    kind="command",
    permission="sale.add_sale",
    input=OrderSetDiscountIn,
    output=OrderOut,
    ai={
        "description": "Set the ticket discount of an open check: a percentage (0 removes it) and/or a fixed amount in cents. "
        "Above the business's cap it is refused: only a manager can (sale.order.set_discount_over_limit).",
        "risk": "high",
    },
)
def set_discount(ctx: OperationContext, data: OrderSetDiscountIn) -> dict:
    return _set_discount(ctx, data, over_limit=False)


@operation(
    "sale.order.set_discount_over_limit",
    kind="command",
    permission="sale.discount_over_limit",
    input=OrderSetDiscountIn,
    output=OrderOut,
    ai={
        "description": "The manager's door to the very same ticket discount, for one bigger than the business's cap; the check "
        "remembers who approved it. Never use it for a discount that fits under the cap.",
        "risk": "high",
    },
)
def set_discount_over_limit(ctx: OperationContext, data: OrderSetDiscountIn) -> dict:
    return _set_discount(ctx, data, over_limit=True)


def _set_line_discount(
    ctx: OperationContext, data: OrderSetLineDiscountIn, *, over_limit: bool
) -> dict:
    order = _still_open(data.order_id)
    line = _pending_line(order, data.line_id)
    settings = current_settings()
    percent = data.discount_percent
    if percent > 0 and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    if percent > _cap(over_limit, settings):
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    line.discount_percent = percent
    line.discount_approved_by = actor(ctx) if over_limit and percent > 0 else ""
    line.line_total = provisional_total(line)
    line.save(
        update_fields=[
            "discount_percent",
            "discount_approved_by",
            "line_total",
            "updated_at",
        ]
    )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_line_discount",
    kind="command",
    permission="sale.add_sale",
    input=OrderSetLineDiscountIn,
    output=OrderOut,
    ai={
        "description": "Set the discount (in %, 0 removes it) of a pending line of an open check. Above the business's cap it "
        "is refused: only a manager can (sale.order.set_line_discount_over_limit).",
        "risk": "high",
    },
)
def set_line_discount(ctx: OperationContext, data: OrderSetLineDiscountIn) -> dict:
    return _set_line_discount(ctx, data, over_limit=False)


@operation(
    "sale.order.set_line_discount_over_limit",
    kind="command",
    permission="sale.discount_over_limit",
    input=OrderSetLineDiscountIn,
    output=OrderOut,
    ai={
        "description": "The manager's door to the very same line discount, for one bigger than the business's cap; the line "
        "remembers who approved it.",
        "risk": "high",
    },
)
def set_line_discount_over_limit(
    ctx: OperationContext, data: OrderSetLineDiscountIn
) -> dict:
    return _set_line_discount(ctx, data, over_limit=True)


@operation(
    "sale.order.set_label",
    kind="command",
    permission="sale.add_sale",
    input=OrderSetLabelIn,
    output=OrderOut,
    ai={
        "description": "Set the title of an open check (e.g. «Table 4», «Ana — terrace»): how it is recognised among the open "
        "checks when it is parked.",
        "risk": "normal",
    },
)
def set_label(ctx: OperationContext, data: OrderSetLabelIn) -> dict:
    order = _still_open(data.order_id)
    order.label = data.label
    order.save(update_fields=["label", "updated_at"])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_appointment",
    kind="command",
    permission="sale.add_sale",
    input=OrderSetAppointmentIn,
    output=OrderOut,
    ai={
        "description": "Link an open check to the appointment it charges (or unlink it): charging it then tells the diary.",
        "risk": "normal",
    },
)
def set_appointment(ctx: OperationContext, data: OrderSetAppointmentIn) -> dict:
    order = _still_open(data.order_id)
    order.appointment_id = data.appointment_id
    order.save(update_fields=["appointment_id", "updated_at"])
    _touch(ctx, order)
    return _out(order)


# ── Charging ─────────────────────────────────────────────────────────────────────────────────────


def _customer_details(data: CompleteIn) -> tuple:
    """``(card, name, tax id, address, country)`` of the sale's customer: what was sent, else the card's."""
    card = None
    if data.customer_id is not None or data.customer:
        card = find_customer(data.customer_id, data.customer)
    name = data.customer_name or (card.name if card else "")
    tax_id = data.customer_tax_id or (card.tax_id if card else "")
    if data.customer_address:
        address = data.customer_address
    elif card:
        town = " ".join(part for part in (card.postal_code, card.city) if part)
        address = ", ".join(part for part in (card.address, town) if part)
    else:
        address = ""
    country = data.customer_country or (card.country if card else "")
    return card, name, tax_id, address, country


def _check_discounts(
    lines: list[OrderLine],
    percent: Decimal,
    amount: int,
    *,
    approved: bool,
    over_limit: bool,
    settings: Settings,
) -> None:
    discounted = (
        percent > 0 or amount > 0 or any(line.discount_percent > 0 for line in lines)
    )
    if discounted and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    cap = _cap(over_limit, settings)
    if cap >= 100:
        return
    for line in lines:
        if not line.discount_approved_by and line.discount_percent > cap:
            raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    if approved:
        return
    payable = sum(
        pricing.line_amount(
            line.unit_price,
            ratio_of(line),
            line_percent=line.discount_percent,
            ticket_percent=percent,
            is_gift=line.is_gift,
        )
        for line in lines
    )
    if percent > cap or amount > payable * cap // 100:
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")


def _legs(data: CompleteIn, total: int, settings: Settings) -> list[dict]:
    """The tenders, resolved and checked: methods allowed, amounts adding up, cash tendered, change."""
    if total == 0:
        if any(leg.amount for leg in data.payments):
            raise Conflict(
                str(PAYMENTS_MISMATCH), code="sale.payments_do_not_match_total"
            )
        return []
    sent = data.payments or [None]
    active = PaymentMethod.objects.filter(is_active=True)
    allowed = allowed_types(settings, active)
    legs = []
    for leg in sent:
        method = (
            find_method(None, "cash")
            if leg is None
            else find_method(leg.method_id, leg.method)
        )
        if method.type not in allowed:
            raise Conflict(
                str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
            )
        legs.append(
            {
                "method": method,
                "amount": leg.amount if leg else None,
                "tendered": leg.tendered if leg else None,
                "reference": leg.reference if leg else "",
            }
        )
    open_legs = [leg for leg in legs if leg["amount"] is None]
    given = sum(leg["amount"] for leg in legs if leg["amount"] is not None)
    if len(open_legs) > 1 or (open_legs and given >= total):
        raise Conflict(str(PAYMENTS_MISMATCH), code="sale.payments_do_not_match_total")
    if open_legs:
        open_legs[0]["amount"] = total - given
    if sum(leg["amount"] for leg in legs) != total:
        raise Conflict(str(PAYMENTS_MISMATCH), code="sale.payments_do_not_match_total")
    for leg in legs:
        if leg["method"].type == PaymentMethod.Type.CASH:
            tendered = leg["amount"] if leg["tendered"] is None else leg["tendered"]
            if tendered < leg["amount"]:
                raise Conflict(
                    str(INSUFFICIENT_TENDERED), code="sale.insufficient_tendered"
                )
            leg["tendered"], leg["change"] = tendered, tendered - leg["amount"]
        else:
            leg["tendered"], leg["change"] = leg["amount"], 0
    limit = CASH_LIMIT.get(business_country())
    if (
        limit is not None
        and total >= limit
        and any(leg["method"].type == PaymentMethod.Type.CASH for leg in legs)
    ):
        raise Conflict(
            str(CASH_LIMIT_EXCEEDED) % {"limit": _money(limit)},
            code="sale.cash_limit_exceeded",
        )
    return legs



def _number(day: dt.date) -> int:
    """The next number of ``day``: the counter's row raised with ``UPDATE … RETURNING`` (never a sequence)."""
    SaleCounter.objects.bulk_create([SaleCounter(day=day)], ignore_conflicts=True)
    counter = SaleCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


def _complete(ctx: OperationContext, data: CompleteIn, *, over_limit: bool) -> dict:
    existing = Sale.objects.filter(idempotency_key=data.idempotency_key).first()
    if existing is not None:
        with translation.override(ctx.language):
            return sale_detail(existing, already=True)
    settings = current_settings()
    card, customer_name, customer_tax_id, customer_address, customer_country = (
        _customer_details(data)
    )

    if data.order_id is not None:
        order = find_order(data.order_id, lock=True)
        if order.status != Order.Status.OPEN or (
            data.order_version is not None and data.order_version != order.version
        ):
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
        lines, closes = lines_to_charge(order, data.line_ids)
        percent = order.discount_percent
        amount = order.discount_amount if closes else 0
        approved = bool(order.discount_approved_by)
        appointment_id = order.appointment_id
    else:
        order = None
        lines, closes = loose_lines(ctx, data.lines, data.open_lines), True
        percent, amount, approved, appointment_id = (
            data.discount_percent,
            data.discount_amount,
            False,
            data.appointment_id,
        )

    _check_discounts(
        lines,
        percent,
        amount,
        approved=approved,
        over_limit=over_limit,
        settings=settings,
    )
    if settings.require_customer and card is None:
        raise Conflict(str(CUSTOMER_REQUIRED), code="sale.customer_required")
    document_type = data.document_type or settings.default_document_type
    if document_type == Settings.DocumentType.INVOICE and not (
        customer_name and customer_tax_id and customer_address
    ):
        raise Conflict(str(INVOICE_RECIPIENT), code="sale.invoice_recipient_incomplete")

    now = timezone.now()
    day = timezone.localdate(now)
    valuation = valuate(
        lines,
        discount_percent=percent,
        discount_amount=amount,
        tax_included=settings.default_tax_included,
        on=day,
    )
    country = business_country()
    ticket_limit = TICKET_LIMIT.get(country)
    if (
        document_type == Settings.DocumentType.TICKET
        and ticket_limit is not None
        and valuation.total > ticket_limit
    ):
        raise Conflict(
            str(TICKET_OVER_LIMIT) % {"limit": _money(ticket_limit)},
            code="sale.ticket_over_limit",
        )
    legs = _legs(data, valuation.total, settings)

    if order is None:
        order = Order.objects.create(
            source=Order.Source.COUNTER,
            created_by=actor(ctx),
            appointment_id=appointment_id,
        )
        _save_lines(order, lines)
        record_event(
            ctx,
            events.ORDER_OPENED,
            {"order_id": str(order.id), "lines_count": len(lines)},
        )

    sequence = _number(day)
    principal = max(legs, key=lambda leg: leg["amount"]) if legs else None
    try:
        with transaction.atomic():
            sale = Sale.objects.create(
                number=sale_number(day, sequence),
                business_day=day,
                sequence=sequence,
                document_type=document_type,
                order=order,
                customer=card,
                customer_name=customer_name,
                staff_id=data.staff_id,
                appointment_id=appointment_id,
                tax_included=settings.default_tax_included,
                currency=CURRENCY,
                subtotal=valuation.subtotal,
                tax_total=valuation.tax_total,
                discount_percent=percent,
                discount_amount=valuation.discount_amount,
                gift_total=valuation.gift_total,
                total=valuation.total,
                tendered_total=sum(leg["tendered"] for leg in legs),
                change_total=sum(leg["change"] for leg in legs),
                tax_breakdown=breakdown_rows(valuation.breakdown),
                payment_method_name=principal["method"].name if principal else "",
                idempotency_key=data.idempotency_key,
                notes=data.notes,
                created_at=now,
                created_by=actor(ctx),
            )
    except IntegrityError:
        raise Conflict(
            str(CHECKOUT_IN_PROGRESS), code="sale.checkout_in_progress"
        ) from None
    sale_lines = SaleLine.objects.bulk_create(
        [
            SaleLine(
                sale=sale,
                position=position,
                order_line_id=line.id,
                product_id=line.product_id,
                department_id=line.department_id,
                name=line.name,
                sku=line.sku,
                is_service=line.is_service,
                category_id=line.category_id,
                unit=line.unit,
                quantity=line.quantity,
                unit_price=line.unit_price,
                price_quantity=line.price_quantity,
                pricing_unit=line.pricing_unit,
                cost=line.cost,
                discount_percent=line.discount_percent,
                is_gift=line.is_gift,
                gift_reason=line.gift_reason,
                notes=line.notes,
                staff_id=line.staff_id,
                tax_category_key=out.tax_category_key,
                tax_rate=out.tax_rate,
                tax_country_code=out.tax_country_code,
                tax_region_code=out.tax_region_code or "",
                tax_rule_id=out.tax_rule_id,
                net_amount=out.net_amount,
                tax_amount=out.tax_amount,
                line_total=out.line_total,
                tax_components=[
                    {
                        **c,
                        "rule_id": str(c["rule_id"]) if c["rule_id"] else None,
                        "rate_pct": str(c["rate_pct"]),
                    }
                    for c in out.tax_components
                ],
            )
            for position, (line, out) in enumerate(
                zip(lines, valuation.lines, strict=True), start=1
            )
        ]
    )
    payments = SalePayment.objects.bulk_create(
        [
            SalePayment(
                sale=sale,
                position=position,
                method=leg["method"],
                method_name=leg["method"].name,
                method_type=leg["method"].type,
                amount=leg["amount"],
                tendered=leg["tendered"],
                change=leg["change"],
                reference=leg["reference"],
            )
            for position, leg in enumerate(legs, start=1)
        ]
    )
    OrderLine.objects.filter(pk__in=[line.id for line in lines]).update(sale=sale)
    if closes:
        order.status = Order.Status.COMPLETED
        order.closed_at = now
    _recount(order)
    order.version = F("version") + 1
    order.save(
        update_fields=[
            "status",
            "closed_at",
            "provisional_total",
            "version",
            "updated_at",
        ]
    )

    record_event(
        ctx,
        events.SALE_COMPLETED,
        _completed_payload(
            sale,
            sale_lines,
            payments,
            customer_tax_id,
            customer_address,
            customer_country,
            data.customer_id_type,
        ),
    )
    if appointment_id is not None:
        record_event(
            ctx,
            events.SALE_CREATED_FROM_APPOINTMENT,
            {
                "sale_id": str(sale.id),
                "appointment_id": str(appointment_id),
                "staff_id": str(sale.staff_id) if sale.staff_id else None,
                "total": sale.total,
            },
        )
    if closes:
        record_event(ctx, events.ORDER_COMPLETED, {"order_id": str(order.id)})
    with translation.override(ctx.language):
        return sale_detail(sale)


def _completed_payload(
    sale, lines, payments, tax_id, address, country, id_type
) -> dict:
    """What ``sale.sale.completed`` carries: Inventory reads ``items``, Customers the customer and total."""
    return {
        "sale_id": str(sale.id),
        "sale_number": sale.number,
        "order_id": str(sale.order_id) if sale.order_id else None,
        "document_type": sale.document_type,
        "tax_included": sale.tax_included,
        "currency": sale.currency,
        "purchased_at": sale.created_at.isoformat(),
        "business_day": sale.business_day.isoformat(),
        "total": sale.total,
        "subtotal": sale.subtotal,
        "tax_amount": sale.tax_total,
        "discount_amount": sale.discount_amount,
        "gift_total": sale.gift_total,
        "customer_id": str(sale.customer_id) if sale.customer_id else None,
        "customer_name": sale.customer_name,
        "customer_tax_id": tax_id,
        "customer_address": address,
        "customer_country": country,
        "customer_id_type": id_type,
        "staff_id": str(sale.staff_id) if sale.staff_id else None,
        "appointment_id": str(sale.appointment_id) if sale.appointment_id else None,
        "payment_method_name": sale.payment_method_name,
        "payments": [
            {
                "method_id": str(payment.method_id),
                "method_name": payment.method_name,
                "method_type": payment.method_type,
                "amount": payment.amount,
                "tendered": payment.tendered,
                "change": payment.change,
                "reference": payment.reference,
            }
            for payment in payments
        ],
        "items_count": len(lines),
        "items": [
            {
                "line_id": str(line.id),
                "order_item_id": str(line.order_line_id)
                if line.order_line_id
                else None,
                "product_id": str(line.product_id) if line.product_id else None,
                "product_name": line.name,
                "quantity": f"{line.quantity:.3f}",
                "unit": line.unit,
                "unit_price": line.unit_price,
                "tax_rate": str(line.tax_rate),
                "tax_category_key": line.tax_category_key,
                "net_amount": line.net_amount,
                "tax_amount": line.tax_amount,
                "line_total": line.line_total,
                "is_gift": line.is_gift,
                "is_service": line.is_service,
                "category_id": str(line.category_id) if line.category_id else None,
                "components": [],
            }
            for line in lines
        ],
    }


@operation(
    "sale.sale.complete",
    kind="command",
    permission="sale.take_payment",
    input=CompleteIn,
    output=SaleOut,
    expose_api=True,
    ai={
        "description": "Charge a sale: an open check (all its lines, or some for a partial charge) or loose lines (products by "
        "SKU or name, open prices by department). Payments: cash with what was handed over (change), card or other "
        "methods for the exact amount, or split. The server prices, taxes and numbers it; a ticket up to 3,000 €, above "
        "or on request an invoice with the customer's name, tax ID and address (ask for them). Send the same "
        "idempotency_key on a retry: it never charges twice.",
        "risk": "high",
    },
)
def complete(ctx: OperationContext, data: CompleteIn) -> dict:
    return _complete(ctx, data, over_limit=False)


@operation(
    "sale.sale.complete_over_limit",
    kind="command",
    permission="sale.discount_over_limit",
    input=CompleteIn,
    output=SaleOut,
    ai={
        "description": "The manager's door to the very same charge as sale.sale.complete, for a discount bigger than the "
        "business's cap. Never use it to dodge the cap when the discount fits under it.",
        "risk": "high",
    },
)
def complete_over_limit(ctx: OperationContext, data: CompleteIn) -> dict:
    return _complete(ctx, data, over_limit=True)


# ── Voids and refunds ────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.sale.void",
    kind="command",
    permission="sale.void_sale",
    input=VoidIn,
    output=SaleOut,
    ai={
        "description": "Void a charged sale (by its id or number) with a mandatory reason, before any money went back: it is "
        "kept, marked voided with who, when and why, and stock and the customer's history are corrected. A sale with "
        "refunds is refunded instead; one charged as a full invoice is corrected with a credit note.",
        "risk": "high",
    },
)
def void_sale(ctx: OperationContext, data: VoidIn) -> dict:
    sale = find_sale(data.sale_id, data.sale, lock=True)
    if sale.status == Sale.Status.REFUNDED:
        raise Conflict(str(ALREADY_REFUNDED), code="sale.sale_already_refunded")
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(str(ALREADY_VOIDED), code="sale.already_voided")
    if sale.document_type == Settings.DocumentType.INVOICE:
        raise Conflict(str(REQUIRES_CREDIT_NOTE), code="sale.void_requires_credit_note")
    if sale.refunded_total > 0 or sale.refunds.exists():
        raise Conflict(str(ALREADY_REFUNDED), code="sale.sale_already_refunded")
    sale.status = Sale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.voided_by = actor(ctx)
    sale.void_reason = data.reason
    sale.notes = f"{sale.notes}\n[VOIDED] {data.reason}".strip()
    sale.save(
        update_fields=["status", "voided_at", "voided_by", "void_reason", "notes"]
    )
    record_event(
        ctx,
        events.SALE_VOIDED,
        {
            "sale_id": str(sale.id),
            "sale_number": sale.number,
            "reason": sale.void_reason,
            "voided_by": sale.voided_by,
            "voided_at": sale.voided_at.isoformat(),
            "total": sale.total,
            "order_id": str(sale.order_id) if sale.order_id else None,
            "document_type": sale.document_type,
            "customer_id": str(sale.customer_id) if sale.customer_id else None,
        },
    )
    with translation.override(ctx.language):
        return sale_detail(sale)


def _refund_lines(sale: Sale, data: RefundIn) -> list[tuple[SaleLine, Decimal]]:
    lines = {line.id: line for line in sale.lines.all()}
    returned = returned_by_line(sale)
    chosen, seen = [], set()
    for item in data.lines:
        line = lines.get(item.line_id)
        if line is None:
            raise Conflict(str(REFUND_LINE_UNKNOWN), code="sale.refund_line_unknown")
        if item.line_id in seen:
            raise Conflict(
                str(REFUND_LINE_DUPLICATED), code="sale.refund_line_duplicated"
            )
        seen.add(item.line_id)
        left = line.quantity - returned.get(line.id, Decimal(0))
        if left <= 0:
            raise Conflict(
                str(REFUND_LINE_ALREADY_RETURNED),
                code="sale.refund_line_already_returned",
            )
        quantity = item.quantity if item.quantity is not None else left
        if quantity > left:
            raise Conflict(
                str(REFUND_LINE_QUANTITY_EXCEEDED),
                code="sale.refund_line_quantity_exceeded",
            )
        chosen.append((line, quantity))
    return chosen


def _refund_legs(sale: Sale, data: RefundIn) -> list[dict]:
    options = {row["payment_id"]: row for row in tender_options(sale)}
    payments = {
        payment.id: payment for payment in sale.payments.select_related("method")
    }
    legs, seen = [], set()
    for allocation in data.allocations:
        option = options.get(allocation.payment_id)
        if option is None:
            raise Conflict(
                str(REFUND_TENDER_UNKNOWN), code="sale.refund_tender_unknown"
            )
        if allocation.payment_id in seen:
            raise Conflict(
                str(REFUND_TENDER_DUPLICATED), code="sale.refund_tender_duplicated"
            )
        seen.add(allocation.payment_id)
        name = method_display_name(option["method_name"])
        if allocation.amount > option["remaining"]:
            message = str(REFUND_EXCEEDS_TENDER) % {
                "method": name,
                "amount": _money(allocation.amount),
                "remaining": _money(option["remaining"]),
            }
            raise Conflict(message, code="sale.refund_exceeds_tender")
        if allocation.to_method_id is None:
            if not option["refundable"]:
                raise Conflict(
                    str(REFUND_NOT_ELIGIBLE) % {"method": name},
                    code="sale.refund_tender_not_eligible",
                )
            method = payments[allocation.payment_id].method
        else:
            method = PaymentMethod.objects.filter(
                pk=allocation.to_method_id, is_active=True
            ).first()
            if method is None:
                raise Conflict(
                    str(REFUND_METHOD_UNAVAILABLE),
                    code="sale.refund_method_unavailable",
                )
        legs.append(
            {
                "payment": payments[allocation.payment_id],
                "method": method,
                "amount": allocation.amount,
            }
        )
    return legs


@operation(
    "sale.sale.refund",
    kind="command",
    permission="sale.refund_sale",
    input=RefundIn,
    output=RefundOut,
    ai={
        "description": "Refund a charged sale (by its id or number), whole or in part, with a mandatory reason: how much goes "
        "back on each of its tenders (never more than each charged minus what it already returned; another method if the "
        "original is gone) and, if the customer returns them, which lines and how many units. Read sale.refund.options "
        "first. Send an idempotency_key on a retry.",
        "risk": "high",
    },
)
def refund(ctx: OperationContext, data: RefundIn) -> dict:
    if data.idempotency_key:
        existing = Refund.objects.filter(idempotency_key=data.idempotency_key).first()
        if existing is not None:
            return {
                "already": True,
                "refund_id": existing.id,
                "sale_id": existing.sale_id,
                "total": existing.total,
                "fully_refunded": existing.sale.status == Sale.Status.REFUNDED,
            }
    sale = find_sale(data.sale_id, data.sale, lock=True)
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(
            str(REFUND_REQUIRES_COMPLETED), code="sale.refund_requires_completed"
        )
    returning = _refund_lines(sale, data)
    legs = _refund_legs(sale, data)
    total = sum(leg["amount"] for leg in legs)
    try:
        with transaction.atomic():
            record = Refund.objects.create(
                sale=sale,
                total=total,
                reason=data.reason,
                note=data.note,
                idempotency_key=data.idempotency_key,
                created_by=actor(ctx),
            )
    except IntegrityError:
        raise Conflict(
            str(REFUND_IN_PROGRESS), code="sale.refund_in_progress"
        ) from None
    RefundPayment.objects.bulk_create(
        [
            RefundPayment(
                refund=record,
                position=position,
                sale_payment=leg["payment"],
                method=leg["method"],
                method_name=leg["method"].name,
                method_type=leg["method"].type,
                amount=leg["amount"],
            )
            for position, leg in enumerate(legs, start=1)
        ]
    )
    RefundLine.objects.bulk_create(
        [
            RefundLine(refund=record, sale_line=line, quantity=quantity)
            for line, quantity in returning
        ]
    )
    sale.refunded_total += total
    fully = sale.total > 0 and sale.refunded_total >= sale.total
    if fully:
        sale.status = Sale.Status.REFUNDED
    sale.save(update_fields=["refunded_total", "status"])
    record_event(
        ctx,
        events.SALE_REFUNDED,
        {
            "sale_id": str(sale.id),
            "sale_number": sale.number,
            "refund_id": str(record.id),
            "total": total,
            "reason": record.reason,
            "refunded_by": record.created_by,
            "refunded_at": record.created_at.isoformat(),
            "fully_refunded": fully,
            "document_type": sale.document_type,
            "order_id": str(sale.order_id) if sale.order_id else None,
            "customer_id": str(sale.customer_id) if sale.customer_id else None,
            "payments": [
                {
                    "payment_id": str(leg["payment"].id),
                    "method_id": str(leg["method"].id),
                    "method_name": leg["method"].name,
                    "method_type": leg["method"].type,
                    "amount": leg["amount"],
                }
                for leg in legs
            ],
            "lines": [
                {
                    "line_id": str(line.id),
                    "product_id": str(line.product_id) if line.product_id else None,
                    "quantity": f"{quantity:.3f}",
                }
                for line, quantity in returning
            ],
        },
    )
    return {
        "already": False,
        "refund_id": record.id,
        "sale_id": sale.id,
        "total": total,
        "fully_refunded": fully,
    }


# ── Reactions ────────────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.customer.reassign",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it, as the reactions run.
    permission="sale.reassign_customer",
    input=CustomerMergedIn,
    output=CustomerReassignOut,
    ai={
        "description": "System only: when Customers merges two cards, the absorbed card's sales move to the one that stays "
        "(the printed name and the amounts never change). Repeating it changes nothing.",
        "risk": "high",
    },
)
def reassign_customer(ctx: OperationContext, data: CustomerMergedIn) -> dict:
    moved = 0
    if data.id != data.absorbed_id:
        moved = Sale.objects.filter(customer_id=data.absorbed_id).update(
            customer_id=data.id
        )
    if moved:
        record_event(
            ctx,
            events.SALE_REASSIGNED,
            {"customer_id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"customer_id": data.id, "moved": moved}
