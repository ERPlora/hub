"""What the card of a write of Services says of a record of Sales or Appointments, by those apps' own reads."""

from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation

from apps.service.schemas import RecordRefIn
from base.operations import call
from base.schemas.assistant import RecordNameOut

#: Sales' reads of a sale and of the records it names by their id; Appointments' of an appointment.
SALE_GET = "sale.sale.get"
SALE_NAMES = "sale.record.get"
APPOINTMENT_GET = "appointment.appointment.get"
SALES_UNAVAILABLE = _("Sales is not active in this business.")
APPOINTMENTS_UNAVAILABLE = _("Appointments is not active in this business.")
#: How the card says the sale a void gives sessions back with: the sale itself is the document (SERVICE-F27).
VOID_OF_SALE = pgettext_lazy("service", "Void of sale %(number)s")


def _of_sales(ctx: OperationContext, name: str, data: dict):
    """Sales' read ``name`` for the caller (BASE-F84): its permission applies, its refusals reach the caller as they
    are; off or absent → 409 ``service.sales_unavailable``."""
    return call(ctx, name, data, unavailable=Conflict(str(SALES_UNAVAILABLE), code="service.sales_unavailable"))


def _of_appointments(ctx: OperationContext, name: str, data: dict):
    """Appointments' read ``name``, as ``_of_sales``; off or absent → 409 ``service.appointments_unavailable``."""
    unavailable = Conflict(str(APPOINTMENTS_UNAVAILABLE), code="service.appointments_unavailable")
    return call(ctx, name, data, unavailable=unavailable)


def _returned_by(ctx: OperationContext, reference: UUID) -> str:
    """The document that gives sessions back: a refund, as Sales names it by its sale; else the sale voided."""
    try:
        return _of_sales(ctx, SALE_NAMES, {"refund_id": str(reference)}).name
    except NotFound as missing:
        if missing.code != "sale.refund_not_found":
            raise
    number = _of_sales(ctx, SALE_GET, {"sale_id": str(reference)}).number
    with translation.override(ctx.language):
        return str(VOID_OF_SALE) % {"number": number}


#: How each record of ``RecordRefIn`` gets its name: by the read of its app, as whoever asks.
RECORD_NAMES = {
    "sale_id": lambda ctx, record_id: _of_sales(ctx, SALE_GET, {"sale_id": str(record_id)}).number,
    "sale_line_id": lambda ctx, record_id: _of_sales(ctx, SALE_NAMES, {"sale_line_id": str(record_id)}).name,
    "order_line_id": lambda ctx, record_id: _of_sales(ctx, SALE_NAMES, {"line_id": str(record_id)}).name,
    "appointment_id": lambda ctx, record_id: _of_appointments(ctx, APPOINTMENT_GET, {"id": str(record_id)}).label,
    "reference": _returned_by,
}


# Not an assistant tool: what names, on the card of a write of Services, a record of Sales or Appointments, which
# Services does not require (``schemas.A_SALE``, ``A_SALE_LINE``, ``AN_APPOINTMENT``, ``A_CHECK_LINE``, ``A_RETURN``).
@operation(
    "service.record.get",
    kind="query",
    permission="service.view_package_balance",
    input=RecordRefIn,
    output=RecordNameOut,
    ai=INTERNAL,
)
def get_record(ctx: OperationContext, data: RecordRefIn) -> dict:
    field = next(name for name in RECORD_NAMES if getattr(data, name) is not None)
    return {"name": RECORD_NAMES[field](ctx, getattr(data, field))}
