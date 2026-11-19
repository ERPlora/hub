"""Freezing a line of a service of Services, at the price an appointment booked, the professional's own or the
service's."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied

from apps.sale.models import OrderLine
from apps.sale.queries.business import actor, business_currency, missing_tax, money_text
from apps.sale.queries.line_parts import GRID_FALLBACK, check_grid, provisional_total
from apps.sale.queries.order_lines import OPEN_PRICE_PERMISSION
from apps.sale.queries.other_apps import call_app, call_services
from apps.sale.schemas import ServiceLineFields

BOOKED_PRICE_MISMATCH = _(
    "That is not the price the appointment booked for this service: it is cancelled, it is another "
    "customer's, it did not book this service or it booked it cheaper."
)
APPOINTMENT_NOT_VISIBLE = _(
    "You cannot see that appointment: it is another professional's or it no longer exists. Charge it "
    "from the appointment's own professional or at the catalog price."
)
SERVICE_NOT_AVAILABLE = _(
    "That service is no longer offered: it is archived or it does not exist."
)
SERVICE_PRICE_REQUIRED = _(
    "This service has no fixed price: type the amount that is charged."
)
SERVICE_PRICE_FIXED = _("This service has a fixed price: no amount is typed.")
SERVICE_PRICE_OUT_OF_RANGE = _(
    "That amount is outside what the service allows (%(min)s – %(max)s)."
)


def _line_price(
    ctx: OperationContext, service, data: ServiceLineFields, booking: "Booking | None"
) -> int:
    if data.booked_price is not None:
        return booked_price(ctx, booking, service.id, data.booked_price)
    price = _service_price(service, data.unit_price, business_currency(ctx))
    if service.pricing_type == "fixed":
        return own_price(ctx, service.id, data.staff_id) or price
    return price


def _service_price(service, unit_price: int | None, currency: str) -> int:
    """The price a line of ``service`` is charged at: its own when fixed, the amount typed otherwise (out of its range,
    said in the business's ``currency``)."""
    if service.pricing_type == "fixed":
        if unit_price is not None:
            message = str(SERVICE_PRICE_FIXED)
            raise Conflict(message, code="sale.service_price_fixed", fields={"unit_price": message})
        return service.price
    if unit_price is None:
        message = str(SERVICE_PRICE_REQUIRED)
        raise Conflict(message, code="sale.service_price_required", fields={"unit_price": message})
    low, high = service.min_price, service.max_price
    if (low is not None and unit_price < low) or (high is not None and unit_price > high):
        message = str(SERVICE_PRICE_OUT_OF_RANGE) % {"min": money_text(low, currency), "max": money_text(high, currency)}
        raise Conflict(
            message, code="sale.service_price_out_of_range", fields={"unit_price": message}
        )
    return unit_price


class Booking:
    """The appointment a check charges (SALE-F26), asked once and by name to Appointments
    (``appointment.appointment.get``, with the seller's session) when a line brings its ``booked_price``.
    ``customer_id``, when the charge knows it, must be the appointment's."""

    UNAVAILABLE = object()

    def __init__(self, appointment_id: UUID | None, customer_id: UUID | None = None):
        self.appointment_id = appointment_id
        self.customer_id = customer_id
        self._read = None

    def read(self, ctx: OperationContext):
        """The appointment; ``None`` when the seller cannot see it (it does not exist, was deleted, is
        another's); ``UNAVAILABLE`` when Appointments cannot be asked (off, absent, not allowed)."""
        if self._read is None:
            try:
                self._read = call_app(
                    ctx,
                    "appointment.appointment.get",
                    {"id": self.appointment_id},
                    "sale.appointment_unavailable",
                )
            except NotFound:
                self._read = False
            except (Conflict, PermissionDenied) as failure:
                if isinstance(failure, Conflict) and failure.code != "sale.appointment_unavailable":
                    raise
                self._read = self.UNAVAILABLE
        return self._read or None


#: An appointment that no longer charges: its booked price is gone with it.
_UNCHARGEABLE = {"cancelled", "no_show"}


def booked_price(
    ctx: OperationContext, booking: "Booking | None", service_id: UUID, price: int
) -> int:
    """``price`` as the line's frozen price when the check's appointment booked that service at it (lower
    only with ``sale.sell_open_price``); without an appointment, or without Appointments to ask, an open
    price (403 without the right). 409 ``sale.booked_price_mismatch`` otherwise."""
    may_open = ctx.has("sale.sell_open_price")
    appointment = (
        booking.read(ctx) if booking and booking.appointment_id else Booking.UNAVAILABLE
    )
    if appointment is Booking.UNAVAILABLE:
        if not may_open:
            raise PermissionDenied(str(OPEN_PRICE_PERMISSION))
        return price
    booked = (
        []
        if appointment is None
        or appointment.status in _UNCHARGEABLE
        or appointment.sale_id is not None
        or (booking.customer_id and appointment.customer_id != booking.customer_id)
        else [line.price for line in appointment.services if line.service_id == service_id]
    )
    if price in booked or (booked and price < max(booked) and may_open):
        return price
    # One the seller cannot see (another professional's, deleted) is said as such: she cannot know why.
    message = str(APPOINTMENT_NOT_VISIBLE if appointment is None else BOOKED_PRICE_MISMATCH)
    raise Conflict(message, code="sale.booked_price_mismatch", fields={"booked_price": message})


def own_price(ctx: OperationContext, service_id: UUID, staff_id: UUID | None) -> int | None:
    """The professional's own price for the service (Services' assignment, SERVICE-F31), as Fresha,
    Phorest and Timely charge it; ``None`` when she has none (or is no professional of Staff)."""
    if staff_id is None:
        return None
    try:
        page = call_services(
            ctx,
            "service.assignment.list",
            {"service_id": service_id, "member_id": staff_id, "limit": 100},
        )
    except NotFound:
        return None
    return next(
        (row.custom_price for row in page.rows if row.is_active and row.custom_price is not None),
        None,
    )


def freeze_service_line(
    ctx: OperationContext, data: ServiceLineFields, booking: Booking | None = None
) -> OrderLine:
    """An unsaved row for a service of Services: its name, price and tax category frozen from it. The
    price: the one the appointment booked (``booked_price``, checked); else, of a fixed-price service,
    the professional's own or the service's; else the amount typed, within the service's range."""
    try:
        service = call_services(
            ctx, "service.service.get", {"id": data.service_id, "service": data.service}
        )
    except NotFound:
        raise Conflict(
            str(SERVICE_NOT_AVAILABLE), code="sale.service_not_available"
        ) from None
    if not service.is_active:
        raise Conflict(str(SERVICE_NOT_AVAILABLE), code="sale.service_not_available")
    if service.needs_tax_setup or not service.tax_category_key:
        raise Conflict(
            missing_tax(service.name),
            code="sale.tax_category_missing",
        )
    check_grid(data.quantity, GRID_FALLBACK, "ud")
    line = OrderLine(
        service_id=service.id,
        name=service.name,
        sku=service.sku,
        is_service=True,
        unit="ud",
        increment=GRID_FALLBACK,
        quantity=data.quantity,
        unit_price=_line_price(ctx, service, data, booking),
        cost=service.cost,
        tax_category_key=service.tax_category_key,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line
