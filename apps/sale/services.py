"""Write operations of the sale app: one operation = one transaction, with its events in the outbox.

Every write on an open check locks the check's row first (``select_for_update``) and raises its
``version``, so two devices are queued and a charge can tell the check moved under it. A charge locks
the check it charges, numbers the sale with its day's counter (``UPDATE … RETURNING``, in the same
transaction: a refusal never burns a number) and marks the lines it takes. A void and a refund lock the
sale's row: whichever comes first wins.

A line of a service may be paid with a customer's voucher (SALE-F27): the voucher's session is reserved,
released, delivered and given back by Services' own operations (``call_services``), inside the very
transaction of the write here, and the line keeps the session that pays it. Services is no requirement:
with it off, what needs it is refused (``sale.services_unavailable``) and taking a voucher or a line off
still works (the session comes back on its own at its deadline).
"""

import datetime as dt
import logging
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F, Max, Sum
from django.utils import timezone, translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.customer.queries import find_customer
from apps.customer.services import lock_customers
from apps.customer.tax_ids import (
    IdTypeRequired,
    InvalidCountry,
    InvalidTaxId,
    normalize_country,
    normalize_tax_id,
)
from apps.sale import events, pricing
from apps.sale.models import (
    FiscalStatus,
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
    Booking,
    CURRENCY,
    METHOD_NOT_AVAILABLE,
    ORDER_CHANGED,
    ORDER_NOT_FOUND,
    TICKET_LIMIT,
    actor,
    allowed_types,
    breakdown_rows,
    business_country,
    call_app,
    call_services,
    charge_parts,
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
    combo_name,
    dishes_of,
    folded_names,
    freeze_combo_line,
    freeze_open_line,
    freeze_product_line,
    freeze_service_line,
    held_methods,
    hold_departments,
    inventory_units,
    is_child,
    lines_to_charge,
    loose_lines,
    method_display_name,
    operation_total,
    order_detail,
    payment_method_row,
    provisional_total,
    quick_note_row,
    ratio_of,
    refresh_combos,
    returned_by_line,
    sale_detail,
    sessions_to_return,
    settings_row,
    tender_options,
    valuate,
)
from apps.sale.schemas import (
    COUNTRY_CODE,
    CompleteIn,
    CustomerMergedIn,
    CustomerReassignOut,
    InvoiceIssuedIn,
    InvoiceRecordedOut,
    DepartmentIn,
    DepartmentOut,
    DepartmentRefIn,
    DepartmentUpdateIn,
    OrderAddLineIn,
    OrderAddOpenLineIn,
    OrderAddComboLineIn,
    OrderAddServiceLineIn,
    OrderApplyVoucherIn,
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
    SaleRefIn,
    SettingsOut,
    SettingsPatchIn,
    SplitLineOut,
    VoidIn,
)

#: Units one line may be split into (a voucher covers one line of one unit).
MAX_LINE_SPLIT = 50

logger = logging.getLogger(__name__)

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
LINE_NOT_COVERABLE = _(
    "Only a line of a service of Services that is not a comp can be paid with a voucher."
)
VOUCHER_NEEDS_ONE_UNIT = _("A voucher pays a line of one unit: split the line first.")
LINE_ALREADY_COVERED = _("That line is already paid with a voucher.")
LINE_NOT_COVERED = _("That line is not paid with any voucher.")
LINE_COVERED_BY_VOUCHER = _(
    "That line is paid with a voucher: undo the voucher before changing it."
)
REFUND_NOTHING = _("A refund has to give back money or the session of a voucher.")
REFUND_VOUCHER_LINE_WHOLE = _(
    "A line paid with a voucher goes back whole: its session is not split."
)
APPOINTMENT_CHECK_OPEN = _(
    "That appointment already has an open check: charge that one (Open checks)."
)
TAX_ID_INVALID = _("That tax ID is not valid.")
ID_TYPE_REQUIRED = _(
    "Say what kind of document a foreign tax ID is (EU VAT number, passport, tax ID of their country…)."
)
CASH_REGISTER_CLOSED = _(
    "The cash register is closed: open a cash session to charge in cash."
)
KEY_REUSED = _("That attempt key was already used for another charge. Open it again to charge this one.")


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


def lock_orders(ids) -> list[Order]:
    """Locks the checks ``ids`` in id order; those still there.

    Every write on a check locks it before what hangs from it (its lines, the sale that charges it), and so does
    the Hub admin's «Delete» (admin.py) before Django checks what protects it and gathers its lines: it waits for
    the write under way and takes what that write left, instead of failing on it at its COMMIT. A write that locks
    several (a merge) takes them here, in id order: two of them never wait in a circle.
    """
    return list(Order.objects.select_for_update().filter(pk__in=ids).order_by("id"))


def lock_rows(model, ids) -> list:
    """Locks the departments or payment methods ``ids`` in id order; those still there.

    A write that names one (an open-price line at a department, a tender of a payment method) holds it before it
    writes what points at it (``queries.held``), and the Hub admin's «Delete» (admin.py) locks it here before Django
    checks what protects it: whichever comes second waits. The deletion then finds what the write wrote and answers
    «Cannot delete», or the write finds the row gone, instead of either failing at its COMMIT. Several rows are taken
    in id order, as the writes hold them: the two never wait in a circle.
    """
    return list(model.objects.select_for_update().filter(pk__in=ids).order_by("id"))


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


def _open_check_of(appointment_id) -> Order | None:
    """The open check of an appointment (one at a time: ``sale_order_one_open_per_appointment``)."""
    return Order.objects.filter(
        appointment_id=appointment_id, status=Order.Status.OPEN, source=Order.Source.POS
    ).first()


@operation(
    "sale.order.open",
    kind="command",
    permission="sale.add_sale",
    input=OrderOpenIn,
    output=OrderOut,
    ai={
        "description": "Open a check (an open ticket), empty or with lines: products of the catalog (by id, SKU or name, priced "
        "by the catalog and frozen), services of Services (by id or name) and, with the open-price permission, "
        "open-price lines by department. A title helps find it among the open checks. An appointment has one open "
        "check at a time: opening it again answers that check (already) and adds nothing.",
        "risk": "normal",
    },
)
def open_order(ctx: OperationContext, data: OrderOpenIn) -> dict:
    # An appointment has one open check at a time: a second «Charge» answers it as it is (``already``).
    if data.appointment_id is not None and (existing := _open_check_of(data.appointment_id)):
        return {**order_detail(existing), "already": True}
    lines = loose_lines(
        ctx,
        data.lines,
        data.open_lines,
        data.service_lines,
        Booking(data.appointment_id),
        hold=True,
        combo_lines=data.combo_lines,
    )
    try:
        with transaction.atomic():
            order = Order.objects.create(
                label=data.label,
                notes=data.notes,
                appointment_id=data.appointment_id,
                created_by=actor(ctx),
            )
    except IntegrityError:
        # The same appointment opened on another device at the same time: that check is the one.
        existing = _open_check_of(data.appointment_id)
        if existing is None:
            raise
        return {**order_detail(existing), "already": True}
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
    hold_departments([(data, line)])
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.add_service_line",
    kind="command",
    permission="sale.add_sale",
    input=OrderAddServiceLineIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Add a service of Services (by id or name) to an open check. A fixed-price service takes its price; one "
        "without a fixed price (from, hourly, variable, free) needs the amount charged, within its minimum and maximum. "
        "Its tax category is the service's.",
        "risk": "normal",
    },
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
    permission="sale.add_sale",
    input=OrderAddComboLineIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Add a menu of Menus (by id or name) to an open check with the dishes picked in each course "
        "(«menu of the day with lentils, hake and flan»). Menus checks the courses and prices it: its closed price plus "
        "the supplements, frozen on the line; the kitchen receives its dishes.",
        "risk": "normal",
    },
)
def add_combo_line(ctx: OperationContext, data: OrderAddComboLineIn) -> dict:
    find_order(data.order_id)
    line = freeze_combo_line(ctx, data)
    order = _open_order(data.order_id)
    _save_lines(order, [line])
    _touch(ctx, order)
    return _out(order)


# ── Open checks: a line paid with a voucher (SALE-F27) ──────────────────────────────────────────


def _guard_covered(line: OrderLine) -> None:
    """A line a voucher pays keeps its quantity, comp and discount: the voucher is undone first."""
    if line.voucher_session_id is not None:
        raise Conflict(
            str(LINE_COVERED_BY_VOUCHER), code="sale.line_covered_by_voucher"
        )


def _clear_voucher(line: OrderLine) -> None:
    line.voucher_session_id = None
    line.voucher_grant_id = None
    line.voucher_name = ""
    line.voucher_remaining = None
    line.voucher_hold_until = None


def _release_vouchers(ctx: OperationContext, lines) -> None:
    """Gives the sessions held for ``lines`` back to their vouchers (SERVICE-F23). With Services off, the
    write goes on: a held session stops counting on its own at its deadline (SERVICE-F25).

    One release per session, by voucher id and then session id: the order ``service.session.settle``
    locks the vouchers in, so two tills on the same vouchers queue instead of locking each other."""
    covered = sorted(
        (line for line in lines if line.voucher_session_id is not None),
        key=lambda line: (line.voucher_grant_id.int, line.voucher_session_id.int),
    )
    for line in covered:
        try:
            call_services(
                ctx, "service.session.release", {"id": line.voucher_session_id}
            )
        except Conflict as refusal:
            if refusal.code != "sale.services_unavailable":
                raise


@operation(
    "sale.order.apply_voucher",
    kind="command",
    permission="sale.add_sale",
    input=OrderApplyVoucherIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Pay a line of a service of an open check with one session of a customer's voucher (Services): the "
        "session is held for the line and the line is charged at 0. One unit per line (split it first). Read the "
        "customer's vouchers for that service with service.grant.tender_options. The sale must then be charged to the "
        "voucher's owner.",
        "risk": "normal",
    },
)
def apply_voucher(ctx: OperationContext, data: OrderApplyVoucherIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id, unfired=False)
    if line.service_id is None or line.is_gift:
        raise Conflict(str(LINE_NOT_COVERABLE), code="sale.line_not_coverable")
    if line.voucher_session_id is not None:
        raise Conflict(str(LINE_ALREADY_COVERED), code="sale.line_already_covered")
    if line.quantity != 1:
        raise Conflict(
            str(VOUCHER_NEEDS_ONE_UNIT), code="sale.voucher_needs_one_unit"
        )
    session = call_services(
        ctx,
        "service.session.hold",
        {
            "grant_id": data.grant_id,
            "service_id": line.service_id,
            "order_line_id": line.id,
        },
    )
    line.voucher_session_id = session.id
    line.voucher_grant_id = session.grant_id
    line.voucher_name = session.package_name
    line.voucher_remaining = session.remaining
    line.voucher_hold_until = session.hold_until
    line.line_total = provisional_total(line)
    line.save()
    # A fixed ticket discount never comes off more than is left to pay (the hold rolls back with it).
    if order.discount_amount:
        left = sum(
            pricing.half_up(
                Fraction(other.line_total) * (1 - Fraction(order.discount_percent) / 100)
            )
            for other in order.lines.live().unpaid()
            if not other.is_gift
        )
        if order.discount_amount > left:
            raise Conflict(
                str(DISCOUNT_OUT_OF_RANGE), code="sale.discount_out_of_range"
            )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.remove_voucher",
    kind="command",
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=OrderOut,
    expose_api=True,
    ai={
        "description": "Undo the voucher of a line of an open check: its session goes back to the voucher and the line is "
        "charged at its price again. Only before the sale is charged.",
        "risk": "normal",
    },
)
def remove_voucher(ctx: OperationContext, data: OrderLineRefIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id, unfired=False)
    if line.voucher_session_id is None:
        raise Conflict(str(LINE_NOT_COVERED), code="sale.line_not_covered")
    _release_vouchers(ctx, [line])
    _clear_voucher(line)
    line.line_total = provisional_total(line)
    line.save()
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
    _release_vouchers(ctx, [line])
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
                    "modifiers": line.kitchen_text,
                    "kitchen_name": line.combo.get("kitchen_name", "") if line.combo_id else "",
                    "components": [
                        {
                            "product_id": dish["product_id"],
                            "product_name": dish["product_name"],
                            "category_id": dish["category_id"],
                            "quantity": f"{dish['quantity'] * line.quantity:.3f}",
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
    source.save(update_fields=["status", "voided_by", "closed_at", "updated_at"])
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
    # An empty check (no live line, no charge) is voided by whoever builds checks: a party that leaves
    # without ordering needs no manager (TABLE-F21). One with something on it asks ``VOID_PERMISSION``.
    permission="sale.add_sale",
    input=OrderRefIn,
    output=OrderOut,
    ai={
        "description": "Void (delete) an open check before it is charged: it is kept as voided, never erased. What was already "
        "charged from it stays in its sales. An empty check (nothing ordered, nothing charged) can be voided by whoever "
        "builds checks; one with lines or charges needs the void permission.",
        "risk": "high",
    },
)
def void_order(ctx: OperationContext, data: OrderRefIn) -> dict:
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
    if data.discount_percent != line.discount_percent:
        _guard_covered(line)
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
    try:
        with transaction.atomic():
            order.save(update_fields=["appointment_id", "updated_at"])
    except IntegrityError:
        raise Conflict(
            str(APPOINTMENT_CHECK_OPEN), code="sale.appointment_check_open"
        ) from None
    _touch(ctx, order)
    return _out(order)


# ── Charging ─────────────────────────────────────────────────────────────────────────────────────


def _customer_details(data: CompleteIn) -> tuple:
    """``(card, name, tax id, address, country)`` of the sale's customer: what was sent, else the card's.
    The name is the fiscal one, as Invoicing reads a card: its company when it has one (the NombreRazon
    that goes with the company's tax ID), else the person. The card is locked before the check, as Customers'
    writes and the Hub admin's «Delete» of a card take it: a deletion under way is waited for and the card is
    gone (404), and one that comes after waits for the charge and finds the sale that protects the card."""
    card = None
    if data.customer_id is not None or data.customer:
        card = find_customer(data.customer_id, data.customer, lock=True)
    name = data.customer_name or ((card.company_name or card.name) if card else "")
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


def _checked_country(country: str) -> str:
    """The recipient's country of an invoice as Invoicing reads it (ISO 3166-1 alpha-2); one an old card
    keeps that it would refuse («UK») is a 422 on its field, to fix before charging."""
    try:
        return normalize_country(country)
    except InvalidCountry:
        message = str(COUNTRY_CODE)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_country": message}
        ) from None


def _checked_tax_id(tax_id: str, country: str, id_type: str) -> str:
    """The recipient's tax ID of an invoice as the document keeps it (``apps.customer.tax_ids``, the one
    reading of Customers and Invoicing): a Spanish NIF, NIE or CIF and an EU VAT number (02) must check;
    abroad, its kind of document (02–07) is required. A refusal is a 422 on its field."""
    try:
        return normalize_tax_id(tax_id, country=country, id_type=id_type)
    except IdTypeRequired:
        message = str(ID_TYPE_REQUIRED)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_id_type": message}
        ) from None
    except InvalidTaxId:
        message = str(TAX_ID_INVALID)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_tax_id": message}
        ) from None


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
    # What is left to pay: a line a voucher pays is worth nothing (SALE-F27).
    payable = sum(
        pricing.line_amount(
            line.unit_price,
            ratio_of(line),
            line_percent=line.discount_percent,
            ticket_percent=percent,
            is_gift=line.is_gift,
        )
        for line in lines
        if line.voucher_session_id is None
    )
    if percent > cap or amount > payable * cap // 100:
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")


def _legs(data: CompleteIn, total: int, settings: Settings, operation: int) -> list[dict]:
    """The tenders, resolved and checked: methods allowed, amounts adding up, cash tendered, change, and
    no cash at all when the whole ``operation`` reaches the cash limit."""
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
    # Held until the charge ends: one deleted since it was read is not available, as one never added.
    named = {leg["method"].id for leg in legs}
    if held_methods(named) != named:
        raise Conflict(
            str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
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
        and operation >= limit
        and any(leg["method"].type == PaymentMethod.Type.CASH for leg in legs)
    ):
        raise Conflict(
            str(CASH_LIMIT_EXCEEDED) % {"limit": _money(limit)},
            code="sale.cash_limit_exceeded",
        )
    return legs


# ── The fiscal document of a write: Invoicing, by name, in the same transaction ──────────────────

#: VeriFactu's refusals (through Invoicing, unchanged) of a business that files for real and cannot reach the AEAT
#: now (verifactu WORKBOOK, «Contrato con Facturación»): not a document that waits but the write's own refusal.
#: Working-rules §15, as the old Hub's ``enforce_fiscal_road`` (HUB-1935): nothing is charged that could never be
#: filed. The route's lacks and the server's (its own certificate it cannot open, no gateway, real filing closed).
NO_WAY_TO_THE_AEAT = frozenset(
    {
        "verifactu.live_option_unpaid",
        "verifactu.representation_not_approved",
        "verifactu.own_certificate_missing",
        "verifactu.own_certificate_unreadable",
        "verifactu.gateway_unavailable",
        "verifactu.production_closed",
    }
)

#: The keys of ``sale.sale.completed`` that carry the recipient of an invoice (empty, never null).
RECIPIENT_KEYS = (
    "customer_name",
    "customer_tax_id",
    "customer_address",
    "customer_country",
    "customer_id_type",
)


def _fiscal_document(
    ctx: OperationContext,
    name: str,
    data: dict,
    *,
    typed_recipient: bool = False,
    strict: bool = False,
) -> dict:
    """Invoicing's operation ``name`` (its ticket or invoice of a charge, its rectifying invoice of a refund
    or a void), run by name with the seller's session INSIDE this write's transaction (CLAUDE.md
    «Fiscal»): the document and its number commit with the sale, or neither does.

    ``{status, id, number, type}``: «issued» with the document; «none» when there is nothing to declare
    (a refund of no money); «unavailable» when Invoicing is not in this business (the sale stays a ticket
    without fiscal document); «pending» when Invoicing refused now (no issuer yet, the seller may not
    issue…): its savepoint leaves nothing behind, the write goes on, and Invoicing's own reaction to the
    notice issues it later (INVOICE-F06). A programming error (``LiveMisuse``) is never swallowed. With
    ``typed_recipient`` (a full invoice, whose recipient is the cashier's input), Invoicing refusing that
    input (``InvalidPayload``) is the caller's 422, to fix now: such a document would never be issued. A
    business that files for real and cannot reach the AEAT (``NO_WAY_TO_THE_AEAT``) refuses the write itself:
    nothing is charged. ``strict`` («Issue now»): every refusal reaches the caller as it is, worded by
    Invoicing."""
    try:
        answer = call_app(ctx, name, data, "sale.invoice_unavailable")
    except InvalidPayload:
        if typed_recipient or strict:
            raise
        failure = "invalid_payload"
    except Conflict as refusal:
        if strict or refusal.code in NO_WAY_TO_THE_AEAT:
            raise
        if refusal.code == "sale.invoice_unavailable":
            return {"status": FiscalStatus.UNAVAILABLE, "id": None, "number": "", "type": ""}
        failure = refusal.code
    except OperationError as refusal:
        if strict:
            raise
        failure = refusal.code
    except DatabaseError as error:
        if strict:
            raise
        failure = type(error).__name__
    else:
        document = answer.invoice
        if document is None:
            return {"status": FiscalStatus.NONE, "id": None, "number": "", "type": ""}
        return {
            "status": FiscalStatus.ISSUED,
            "id": document.id,
            "number": document.number,
            "type": document.invoice_type,
        }
    logger.warning("sale: %s refused (%s); Invoicing issues it later from the outbox", name, failure)
    return {"status": FiscalStatus.PENDING, "id": None, "number": "", "type": ""}


def _recipient_of(sale: Sale) -> dict:
    """What a document issued later declares as the recipient: an invoice's, as checked at the till; a
    ticket's is its card, which Invoicing reads itself."""
    if sale.document_type != Settings.DocumentType.INVOICE:
        return {}
    return {
        "customer_name": sale.customer_name,
        "customer_tax_id": sale.customer_tax_id,
        "customer_address": sale.customer_address,
        "customer_country": sale.customer_country,
        "customer_id_type": sale.customer_id_type,
    }


def _invoiced(ctx: OperationContext, sale: Sale, document: dict, **more) -> None:
    """Says a document of ``sale`` was issued after its write (the lists and the paper follow it)."""
    record_event(
        ctx,
        events.SALE_INVOICED,
        {
            "sale_id": str(sale.id),
            "invoice_id": str(document["id"]) if document["id"] else None,
            "number": document["number"],
            "refund_id": None,
            "void": False,
            **more,
        },
    )


def _issue_waiting_document(ctx: OperationContext, sale: Sale, *, strict: bool = False) -> bool:
    """The ticket or invoice of ``sale`` while it waits (``pending``), asked again by name with the
    recipient the sale keeps: idempotent in Invoicing (one per sale). True when it is issued now."""
    if sale.invoice_status != FiscalStatus.PENDING:
        return False
    document = _fiscal_document(
        ctx,
        "invoice.invoice.create_from_sale",
        {"sale_id": str(sale.id), **_recipient_of(sale)},
        strict=strict,
    )
    if document["status"] != FiscalStatus.ISSUED:
        return False
    sale.invoice_status, sale.invoice_id = document["status"], document["id"]
    sale.invoice_number, sale.invoice_type = document["number"], document["type"]
    sale.save(update_fields=["invoice_status", "invoice_id", "invoice_number", "invoice_type"])
    _invoiced(ctx, sale, document)
    return True


#: Cash register's answer to «may the till charge cash now?» (CASH_REGISTER-F04).
DRAWER_CHECK = "cash_register.session.current"


def _check_drawer(ctx: OperationContext, legs: list[dict]) -> None:
    """SALE-F08 (CASH_REGISTER-F04): cash only with the drawer open. With a cash leg, Cash register is asked
    by name with the seller's session; «required» and no session open → 409 ``sale.cash_register_closed``.
    Cash register off, absent or failing (a refusal, a timeout) → the till charges: the lock gives way
    before the sales stop, and Cash register shows the charge among those of no shift (CASH_REGISTER-F17)."""
    if not any(leg["method"].type == PaymentMethod.Type.CASH for leg in legs):
        return
    try:
        drawer = call_app(ctx, DRAWER_CHECK, {}, "sale.cash_register_unavailable")
    except (OperationError, DatabaseError) as failure:
        logger.info(
            "sale: cash charged without asking Cash register (%s)",
            getattr(failure, "code", type(failure).__name__),
        )
        return
    if drawer.required and drawer.session is None:
        raise Conflict(str(CASH_REGISTER_CLOSED), code="sale.cash_register_closed")


def _number(day: dt.date) -> int:
    """The next number of ``day``: the counter's row raised with ``UPDATE … RETURNING`` (never a sequence)."""
    SaleCounter.objects.bulk_create([SaleCounter(day=day)], ignore_conflicts=True)
    counter = SaleCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


def _replay(ctx: OperationContext, data: CompleteIn) -> dict | None:
    """The sale this attempt already charged, if any (``already``); 409 when the key was charged for
    something else: another check, other lines of it, or a counter sale instead of a check."""
    sale = Sale.objects.select_related("order").filter(idempotency_key=data.idempotency_key).first()
    if sale is None:
        return None
    if data.order_id is None:
        same = sale.order is not None and sale.order.source == Order.Source.COUNTER
    else:
        same = sale.order_id == data.order_id and (
            not data.line_ids or set(sale.order_lines.values_list("id", flat=True)) == set(data.line_ids)
        )
    if not same:
        raise Conflict(str(KEY_REUSED), code="sale.idempotency_key_reused")
    # The same attempt again is the till's retry: a document that waited is asked for once more (phase 1
    # has no relay to issue it on its own); still refused, it keeps waiting, in sight.
    _issue_waiting_document(ctx, sale)
    with translation.override(ctx.language):
        return sale_detail(sale, already=True)


def _claim_counter(ctx: OperationContext, data: CompleteIn) -> Order | dict:
    """A counter sale's check, created FIRST and holding the attempt's key (unique): the same attempt
    sent twice at once waits here, then answers the sale the first one charged."""
    try:
        with transaction.atomic():
            return Order.objects.create(
                source=Order.Source.COUNTER,
                attempt_key=data.idempotency_key,
                created_by=actor(ctx),
                appointment_id=data.appointment_id,
            )
    except IntegrityError:
        answer = _replay(ctx, data)
        if answer is None:
            raise Conflict(str(CHECKOUT_IN_PROGRESS), code="sale.checkout_in_progress") from None
        return answer


def _complete(ctx: OperationContext, data: CompleteIn, *, over_limit: bool) -> dict:
    answer = _replay(ctx, data)
    if answer is not None:
        return answer
    settings = current_settings()
    card, customer_name, customer_tax_id, customer_address, customer_country = (
        _customer_details(data)
    )

    if data.order_id is not None:
        order = find_order(data.order_id, lock=True)
        # The same attempt may have charged this check while this one waited for its lock.
        answer = _replay(ctx, data)
        if answer is not None:
            return answer
        if order.status != Order.Status.OPEN or (
            data.order_version is not None and data.order_version != order.version
        ):
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
        lines, closes = lines_to_charge(order, data.line_ids)
        refresh_combos(ctx, lines)
        percent = order.discount_percent
        amount = order.discount_amount if closes else 0
        approved = bool(order.discount_approved_by)
        appointment_id = order.appointment_id
    else:
        claimed = _claim_counter(ctx, data)
        if isinstance(claimed, dict):
            return claimed
        order = claimed
        booking = Booking(data.appointment_id, card.id if card else None)
        lines, closes = (
            loose_lines(
                ctx,
                data.lines,
                data.open_lines,
                data.service_lines,
                booking,
                hold=True,
                combo_lines=data.combo_lines,
            ),
            True,
        )
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
    invoice = document_type == Settings.DocumentType.INVOICE
    if invoice and not (customer_name and customer_tax_id and customer_address):
        raise Conflict(str(INVOICE_RECIPIENT), code="sale.invoice_recipient_incomplete")
    if invoice:
        customer_country = _checked_country(customer_country)
        customer_tax_id = _checked_tax_id(
            customer_tax_id, customer_country, data.customer_id_type
        )

    now = timezone.now()
    day = timezone.localdate(now)
    parts = charge_parts(lines)
    valuation = valuate(
        parts,
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
    counter_sale = order.source == Order.Source.COUNTER and not order.lines.exists()
    operation = operation_total(None if counter_sale else order, closes, valuation, on=day)
    legs = _legs(data, valuation.total, settings, operation)
    _check_drawer(ctx, legs)

    if counter_sale:
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
                **(
                    {
                        "customer_tax_id": customer_tax_id,
                        "customer_address": customer_address,
                        "customer_country": customer_country,
                        "customer_id_type": data.customer_id_type,
                    }
                    if invoice
                    else {}
                ),
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
    # The sessions held for the lines a voucher pays are delivered with the sale, or nothing is charged.
    covered = [line.voucher_session_id for line in lines if line.voucher_session_id]
    if covered:
        call_services(
            ctx,
            "service.session.settle",
            {
                "ids": covered,
                "sale_id": sale.id,
                "customer_id": card.id if card else None,
            },
        )
    sale_lines = SaleLine.objects.bulk_create(
        _sale_lines(sale, parts, valuation)
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

    completed = _completed_payload(
        sale,
        sale_lines,
        payments,
        customer_tax_id,
        customer_address,
        customer_country,
        data.customer_id_type,
    )
    record_event(ctx, events.SALE_COMPLETED, completed)
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
    # Its ticket (F2) or its invoice (F1), numbered by Invoicing in this very transaction (INVOICE-F01, F02).
    # A ticket's recipient is its card (Invoicing reads it); an invoice's, the one checked above.
    recipient = {key: completed[key] or "" for key in RECIPIENT_KEYS} if invoice else {}
    document = _fiscal_document(
        ctx,
        "invoice.invoice.create_from_sale",
        {"sale_id": str(sale.id), **recipient},
        typed_recipient=invoice,
    )
    sale.invoice_status, sale.invoice_id = document["status"], document["id"]
    sale.invoice_number, sale.invoice_type = document["number"], document["type"]
    sale.save(update_fields=["invoice_status", "invoice_id", "invoice_number", "invoice_type"])
    with translation.override(ctx.language):
        return sale_detail(sale)


def _sale_lines(sale: Sale, parts: list[OrderLine], valuation) -> list[SaleLine]:
    """The fiscal copy of each part charged (``charge_parts``): a line of the check with the names of the
    options charged inside it, and a child line of an option under the line of its dish."""
    rows: list[SaleLine] = []
    of_line: dict = {}
    for position, (line, out) in enumerate(zip(parts, valuation.lines, strict=True), start=1):
        child = is_child(line)
        row = SaleLine(
            sale=sale,
            position=position,
            order_line_id=line.origin.id,
            parent_line_id=of_line[line.origin.id] if child else None,
            modifiers=[] if child else folded_names(line),
            combo_id=line.combo_id,
            combo_name=combo_name(line),
            components=dishes_of(line),
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
            service_id=line.service_id,
            voucher_session_id=line.voucher_session_id,
            voucher_grant_id=line.voucher_grant_id,
            voucher_name=line.voucher_name,
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
        if not child:
            of_line[line.id] = row.id
        rows.append(row)
    return rows


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
                "service_id": str(line.service_id) if line.service_id else None,
                "paid_by_voucher": line.paid_by_voucher,
                "category_id": str(line.category_id) if line.category_id else None,
                "modifiers": line.modifiers,
                "parent_line_id": str(line.parent_line_id) if line.parent_line_id else None,
                "components": [
                    {
                        "product_id": str(dish["product_id"]),
                        "product_name": dish["product_name"],
                        "quantity": f"{dish['quantity'] * line.quantity:.3f}",
                        "is_service": dish["is_service"],
                    }
                    for dish in line.components
                ],
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
        "SKU or name, services by name, open prices by department). The sessions of the lines paid with a voucher are "
        "spent with it (the sale must be charged to the voucher's owner). Payments: cash with what was handed over (change), card or other "
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
        "kept, marked voided with who, when and why, the sessions of the vouchers it spent go back, and stock and the "
        "customer's history are corrected. A sale with "
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
    # A ticket that waited is issued first: its rectifying invoice needs it (INVOICE-F07). Still refused,
    # both wait in sight and the void goes on.
    _issue_waiting_document(ctx, sale)
    # Every session spent in it goes back to its voucher (SERVICE-F27), or nothing is voided.
    sessions = list(
        sale.lines.exclude(voucher_session_id=None).values_list(
            "voucher_session_id", flat=True
        )
    )
    if sessions:
        call_services(
            ctx,
            "service.session.return",
            {"ids": sessions, "reference": sale.id, "reason": data.reason},
        )
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
    # The rectifying invoice of the whole ticket (R5), in this very transaction (INVOICE-F07).
    document = _fiscal_document(
        ctx, "invoice.invoice.rectify_from_void", {"sale_id": str(sale.id)}
    )
    sale.void_invoice_status, sale.void_invoice_number = document["status"], document["number"]
    sale.save(update_fields=["void_invoice_status", "void_invoice_number"])
    with translation.override(ctx.language):
        return sale_detail(sale)


@operation(
    "sale.sale.issue_documents",
    kind="command",
    permission="sale.take_payment",
    input=SaleRefIn,
    output=SaleOut,
    ai={
        "description": "Issue now the fiscal documents of a sale (by its id or number) that wait because Invoicing could "
        "not issue them in the charge, the void or a refund (no issuer yet, no permission…): its ticket or invoice, "
        "the rectifying invoice of its void and those of its refunds. A refusal says why and changes nothing; with "
        "nothing waiting, nothing happens.",
        "risk": "high",
    },
)
def issue_documents(ctx: OperationContext, data: SaleRefIn) -> dict:
    """«Issue now» (phase 1 has no relay to issue them on its own): every document of the sale that waits,
    in order — its own, then its void's or its refunds' rectifying invoices, which need it —, each by its
    operation of Invoicing with the caller's session. Any refusal reaches the caller and nothing is kept."""
    sale = find_sale(data.sale_id, data.sale, lock=True)
    _issue_waiting_document(ctx, sale, strict=True)
    if sale.void_invoice_status == FiscalStatus.PENDING:
        document = _fiscal_document(
            ctx, "invoice.invoice.rectify_from_void", {"sale_id": str(sale.id)}, strict=True
        )
        sale.void_invoice_status, sale.void_invoice_number = document["status"], document["number"]
        sale.save(update_fields=["void_invoice_status", "void_invoice_number"])
        _invoiced(ctx, sale, document, void=True)
    for record in sale.refunds.filter(invoice_status=FiscalStatus.PENDING).order_by(
        "created_at", "id"
    ):
        document = _fiscal_document(
            ctx, "invoice.invoice.rectify_from_refund", {"refund_id": str(record.id)}, strict=True
        )
        record.invoice_status, record.invoice_number = document["status"], document["number"]
        record.invoice_type = document["type"]
        record.save(update_fields=["invoice_status", "invoice_number", "invoice_type"])
        _invoiced(ctx, sale, document, refund_id=str(record.id))
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
        if line.voucher_session_id is not None and quantity != left:
            raise Conflict(
                str(REFUND_VOUCHER_LINE_WHOLE), code="sale.refund_voucher_line_whole"
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
    # Held until the refund ends: one deleted since it was read is not available, as one never added.
    named = {leg["method"].id for leg in legs}
    if held_methods(named) != named:
        raise Conflict(
            str(REFUND_METHOD_UNAVAILABLE), code="sale.refund_method_unavailable"
        )
    return legs


def _refund_replay(data: RefundIn) -> dict | None:
    """The refund this attempt already recorded, if any (``already``); 409 when the key was used for
    another sale or other lines."""
    if not data.idempotency_key:
        return None
    existing = Refund.objects.select_related("sale").filter(idempotency_key=data.idempotency_key).first()
    if existing is None:
        return None
    same_sale = existing.sale_id == data.sale_id if data.sale_id is not None else existing.sale.number == (data.sale or "").strip()
    same_lines = set(existing.lines.values_list("sale_line_id", flat=True)) == {line.line_id for line in data.lines}
    if not (same_sale and same_lines):
        raise Conflict(str(KEY_REUSED), code="sale.idempotency_key_reused")
    return {
        "already": True,
        "refund_id": existing.id,
        "sale_id": existing.sale_id,
        "total": existing.total,
        "fully_refunded": existing.sale.status == Sale.Status.REFUNDED,
        "invoice_status": existing.invoice_status,
        "invoice_number": existing.invoice_number,
        "invoice_type": existing.invoice_type,
    }


@operation(
    "sale.sale.refund",
    kind="command",
    permission="sale.refund_sale",
    input=RefundIn,
    output=RefundOut,
    ai={
        "description": "Refund a charged sale (by its id or number), whole or in part, with a mandatory reason: how much goes "
        "back on each of its tenders (never more than each charged minus what it already returned; another method if the "
        "original is gone) and, if the customer returns them, which lines and how many units. A line paid with a voucher "
        "gives its session back, also with no money at all. Read sale.refund.options "
        "first. Send an idempotency_key on a retry.",
        "risk": "high",
    },
)
def refund(ctx: OperationContext, data: RefundIn) -> dict:
    answer = _refund_replay(data)
    if answer is not None:
        return answer
    sale = find_sale(data.sale_id, data.sale, lock=True)
    # The same attempt may have refunded this sale while this one waited for its lock.
    answer = _refund_replay(data)
    if answer is not None:
        return answer
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(
            str(REFUND_REQUIRES_COMPLETED), code="sale.refund_requires_completed"
        )
    returning = _refund_lines(sale, data)
    legs = _refund_legs(sale, data)
    total = sum(leg["amount"] for leg in legs)
    sessions = [line.voucher_session_id for line, _quantity in returning if line.voucher_session_id]
    if not legs and not sessions:
        raise Conflict(str(REFUND_NOTHING), code="sale.refund_nothing")
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
    if sessions:
        call_services(
            ctx,
            "service.session.return",
            {"ids": sessions, "reference": record.id, "reason": data.reason},
        )
    sale.refunded_total += total
    # Refunded whole: all the money back and every voucher session back.
    fully = sale.refunded_total >= sale.total and sessions_to_return(sale) == 0
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
            # A menu gives back each of its dishes, times the menus that come back (COMBO-F10).
            "lines": [
                {
                    "line_id": str(line.id),
                    "product_id": str(unit["product_id"]) if unit["product_id"] else None,
                    "quantity": f"{unit['quantity'] * quantity:.3f}",
                }
                for line, quantity in returning
                for unit in (
                    line.components or [{"product_id": line.product_id, "quantity": 1}]
                )
            ],
        },
    )
    # Its rectifying invoice, by differences or whole, in this very transaction (INVOICE-F09, F10), once
    # the document it rectifies exists: a ticket that waited is asked for first.
    _issue_waiting_document(ctx, sale)
    document = _fiscal_document(
        ctx, "invoice.invoice.rectify_from_refund", {"refund_id": str(record.id)}
    )
    record.invoice_status, record.invoice_number = document["status"], document["number"]
    record.invoice_type = document["type"]
    record.save(update_fields=["invoice_status", "invoice_number", "invoice_type"])
    return {
        "already": False,
        "refund_id": record.id,
        "sale_id": sale.id,
        "total": total,
        "fully_refunded": fully,
        "invoice_status": record.invoice_status,
        "invoice_number": record.invoice_number,
        "invoice_type": record.invoice_type,
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
    # The card that stays before the sales that move to it; one the Hub admin deleted takes nothing.
    if data.id != data.absorbed_id and lock_customers([data.id]):
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


#: The documents of a charge its paper prints: the ticket or the invoice issued from the sale.
_SALE_DOCUMENTS = {"F1", "F2"}


@operation(
    "sale.sale.record_invoice",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it, as the reactions run.
    permission="sale.record_invoice",
    input=InvoiceIssuedIn,
    output=InvoiceRecordedOut,
    ai={
        "description": "System only: when Invoicing issues later a document it could not issue in the write itself (no "
        "issuer yet…) — the ticket or invoice of a charge, the rectifying invoice of a void or of a refund —, the "
        "sale or the refund keeps its number for its paper. Repeating it changes nothing.",
        "risk": "normal",
    },
)
def record_invoice(ctx: OperationContext, data: InvoiceIssuedIn) -> dict:
    """Links a document issued later to the write it belongs to, by its ``source``: a refund's rectifying
    invoice to that refund, a void's to the sale it voids, the ticket or invoice of a charge to its sale.
    Anything else (a manual invoice, a substitution F3, a rectification of an invoice) is Invoicing's."""
    source, recorded = data.source, 0
    if source is None or source.sale_id is None:
        return {"sale_id": None, "recorded": False}
    issued = {"invoice_status": FiscalStatus.ISSUED, "invoice_number": data.number}
    if source.refund_id is not None:
        recorded = (
            Refund.objects.filter(pk=source.refund_id, sale_id=source.sale_id)
            .exclude(invoice_status=FiscalStatus.ISSUED)
            .update(**issued, invoice_type=data.invoice_type)
        )
    elif source.void:
        recorded = (
            Sale.objects.filter(pk=source.sale_id)
            .exclude(void_invoice_status=FiscalStatus.ISSUED)
            .update(void_invoice_status=FiscalStatus.ISSUED, void_invoice_number=data.number)
        )
    elif source.type == "sale" and data.invoice_type in _SALE_DOCUMENTS:
        recorded = (
            Sale.objects.filter(pk=source.sale_id)
            .exclude(invoice_status=FiscalStatus.ISSUED)
            .update(**issued, invoice_id=data.invoice_id, invoice_type=data.invoice_type)
        )
    if recorded:
        record_event(
            ctx,
            events.SALE_INVOICED,
            {
                "sale_id": str(source.sale_id),
                "invoice_id": str(data.invoice_id),
                "number": data.number,
                "refund_id": str(source.refund_id) if source.refund_id else None,
                "void": source.void,
            },
        )
    return {"sale_id": source.sale_id, "recorded": bool(recorded)}
