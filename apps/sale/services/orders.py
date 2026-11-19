"""Opening a check, and the steps every write on an open check shares: locking it, its pending lines, its total and
its version."""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import F, Max, Sum
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, atomic, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Order, OrderLine
from apps.sale.queries.business import actor
from apps.sale.queries.checkout import loose_lines
from apps.sale.queries.orders import ORDER_CHANGED, find_order, order_detail
from apps.sale.queries.service_lines import Booking
from apps.sale.schemas import OrderOpenIn, OrderOut

ORDER_UNAVAILABLE = _("That check is no longer open.")
LINE_NOT_AVAILABLE = _(
    "That line can no longer be changed: it was sent to the kitchen, charged or removed."
)
LINE_COVERED_BY_VOUCHER = _(
    "That line is paid with a voucher: undo the voucher before changing it."
)


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
    writes what points at it (``queries.rows.held``), and the Hub admin's «Delete» (admin.py) locks it here before Django
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


def _guard_covered(line: OrderLine) -> None:
    """A line a voucher pays keeps its quantity, comp and discount: the voucher is undone first."""
    if line.voucher_session_id is not None:
        raise Conflict(
            str(LINE_COVERED_BY_VOUCHER), code="sale.line_covered_by_voucher"
        )


def _open_check_of(appointment_id) -> Order | None:
    """The open check of an appointment (one at a time: ``sale_order_one_open_per_appointment``)."""
    return Order.objects.filter(
        appointment_id=appointment_id, status=Order.Status.OPEN, source=Order.Source.POS
    ).first()


@operation(
    "sale.order.open",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderOpenIn,
    output=OrderOut,
    ai=AI(
        description="Open a check (an open ticket), empty or with lines: products of the catalog (by id, SKU or name, priced "
        "by the catalog and frozen), services of Services (by id or name) and, with the open-price permission, "
        "open-price lines by department. A title helps find it among the open checks. An appointment has one open "
        "check at a time: opening it again answers that check (already) and adds nothing.",
        risk="normal",
        asks={
            "en": (
                "start a check for table 4",
                "open a tab for Ana with two beers",
                "open a ticket with a coffee",
            ),
            "es": (
                "ábreme una cuenta para la mesa 4",
                "abre la cuenta de la terraza con dos cañas",
                "abre un ticket con un café",
            ),
        },
    ),
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
        with atomic():
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
