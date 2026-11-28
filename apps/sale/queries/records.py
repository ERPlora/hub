"""The name of a record a write of Sales names, for the assistant's card."""

from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.sale.models.orders import OrderLine
from apps.sale.models.payments import SalePayment
from apps.sale.models.refunds import Refund
from apps.sale.models.sales import SaleLine
from apps.sale.queries.business import business_currency, money_text
from apps.sale.queries.departments import find_department, find_quick_note
from apps.sale.queries.orders import find_order
from apps.sale.queries.other_apps import answer_if_on, call_app
from apps.sale.queries.payment_methods import find_method, method_display_name
from apps.sale.schemas.records import RecordRefIn
from base.schemas.assistant import RecordNameOut

LINE_NOT_FOUND = _("That line does not exist.")
TENDER_NOT_FOUND = _("That tender does not exist.")
REFUND_NOT_FOUND = _("That refund does not exist.")
#: How a refund is said where something names it (the card of Services' write that gives back the sessions a refund
#: returns): it has no number of its own, «Sales» lists it under its sale.
REFUND_OF_SALE = _("Refund of sale %(number)s")
#: Tables' read of the table a check sits at (Sales does not require Tables), and the state of a check at a table.
CHECK_TABLE = "table.session.by_order"
SEATED = "open"


def _check_name(ctx: OperationContext, order_id: UUID) -> str:
    """A check at a table as Tables says where it is («4 (Dining room)»), in the reader's language: its title is
    written once, in the language of whoever seated it. Any other check as «Open checks» lists it: by its title or,
    with none, by its amount."""
    order = find_order(order_id)
    return _table_of(ctx, order_id) or order.label or money_text(order.provisional_total, business_currency(ctx))


def _table_of(ctx: OperationContext, order_id: UUID) -> str | None:
    """Where Tables says the check sits, read as whoever asks; ``None`` when no table holds it, or when Tables is
    absent, off or not theirs to read."""
    seats = answer_if_on(ctx, CHECK_TABLE, {"order_id": str(order_id)})
    return next((row.label for row in seats.rows if row.status == SEATED), None) if seats else None


def _check_line_name(ctx: OperationContext, line_id: UUID) -> str:
    line = OrderLine.objects.live().filter(pk=line_id).first()
    if line is None:
        raise NotFound(str(LINE_NOT_FOUND), code="sale.line_not_found")
    return line.name


def _sale_line_name(ctx: OperationContext, line_id: UUID) -> str:
    line = SaleLine.objects.filter(pk=line_id).first()
    if line is None:
        raise NotFound(str(LINE_NOT_FOUND), code="sale.line_not_found")
    return line.name


def _tender_name(ctx: OperationContext, payment_id: UUID) -> str:
    tender = SalePayment.objects.filter(pk=payment_id).first()
    if tender is None:
        raise NotFound(str(TENDER_NOT_FOUND), code="sale.tender_not_found")
    return method_display_name(tender.method_name)


def _refund_name(ctx: OperationContext, refund_id: UUID) -> str:
    refund = Refund.objects.select_related("sale").filter(pk=refund_id).first()
    if refund is None:
        raise NotFound(str(REFUND_NOT_FOUND), code="sale.refund_not_found")
    with translation.override(ctx.language):
        return str(REFUND_OF_SALE) % {"number": refund.sale.number}


def _named_by(read: str, unavailable_code: str, name: str = "name", by: str = "id"):
    """The name an app Sales does not require gives its record, by its own read and as whoever asks."""
    return lambda ctx, record: getattr(call_app(ctx, read, {by: record}, unavailable_code), name)


#: How each record of ``RecordRefIn`` gets its name: Sales' own by their rows, the other apps' by their reads.
RECORD_NAMES = {
    "department_id": lambda ctx, record_id: find_department(record_id, None).name,
    "quick_note_id": lambda ctx, record_id: find_quick_note(record_id, None).text,
    "method_id": lambda ctx, record_id: find_method(record_id, None).display_name,
    "order_id": _check_name,
    "line_id": _check_line_name,
    "sale_line_id": _sale_line_name,
    "payment_id": _tender_name,
    "refund_id": _refund_name,
    "product_id": _named_by("inventory.product.get", "sale.catalog_unavailable"),
    # The same read the write finds it with: the card says the product it will add.
    "product": _named_by("inventory.product.get", "sale.catalog_unavailable", by="product"),
    "service_id": _named_by("service.service.get", "sale.services_unavailable"),
    "combo_id": _named_by("combo.combo.get", "sale.combo_unavailable"),
    "dish_id": _named_by("combo.option.get", "sale.combo_unavailable", "product_name"),
    "modifier_id": _named_by("modifier.option.get", "sale.modifier_unavailable"),
    "staff_id": _named_by("staff.member.detail", "sale.staff_unavailable", "full_name"),
    "appointment_id": _named_by("appointment.appointment.get", "sale.appointment_unavailable", "number"),
    "grant_id": _named_by("service.grant.get", "sale.services_unavailable", "package_name"),
}


@operation(
    "sale.record.get",
    kind="query",
    permission="sale.view_sale",
    input=RecordRefIn,
    output=RecordNameOut,
    ai=INTERNAL,
)
def get_record(ctx: OperationContext, data: RecordRefIn) -> dict:
    """The name of one record a write of Sales names, by its id, for the assistant's card (``schemas.fields.A_*``): the
    screen says it by that name, and the model never needs this read, it names them from its own reads."""
    field = next(name for name in RECORD_NAMES if getattr(data, name) is not None)
    return {"name": RECORD_NAMES[field](ctx, getattr(data, field))}
