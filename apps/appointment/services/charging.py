"""Charging an appointment at the till (APPOINTMENT-F17)."""

import logging
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, NotFound, OperationError, PermissionDenied
from live.operations import UnknownOperation, get, operation

from apps.appointment import events
from apps.appointment.models.appointments import Appointment
from apps.appointment.queries.access import CHANGE_OWN, may_change
from apps.appointment.queries.reads import find_appointment
from apps.appointment.schemas.appointments import AppointmentRefIn
from apps.appointment.schemas.changes import ChargeOut
from apps.appointment.services.writes import (
    ALREADY_CHARGED,
    CANNOT,
    CHANGE_OWN_ONLY,
    S,
    _event,
)
from apps.service.queries.catalog import needs_tax_setup

NEEDS_TAX_SETUP = _(
    "“%(name)s” has no tax category: set it in Services before charging."
)
logger = logging.getLogger("apps.appointment.services")

SALE_UNAVAILABLE = _(
    "The till (Sales) is not active in this business: the appointment cannot be charged there."
)


@operation(
    "appointment.appointment.charge",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=ChargeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "charge Julia's appointment",
                "send Paula's appointment to the checkout",
            ),
            "es": (
                "cobra la cita de Julia",
                "hazle la cuenta a la cita de Paula",
            ),
        },
        "description": "Charge an appointment at the till: opens a check in Sales linked to it, in the customer's name, "
        "titled with her and the appointment's number, with a line per service at the price booked and the professional who did it, "
        "so a voucher of the customer can pay one. While that check is open, charging again goes back to it. "
        "Charging the check then marks the appointment charged and completed.",
        "risk": "high",
    },
)
def charge(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if appointment.status in (S.CANCELLED, S.NO_SHOW):
        raise Conflict(str(CANNOT["charge"]), code="appointment.cannot_charge")
    if appointment.sale_id:
        raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
    try:
        if appointment.order_id:
            # One check per appointment: while the one it opened is open, charging goes back to it; once
            # charged (the sale's notice may not have arrived yet) it is charged; voided, a new one opens.
            current = _check_of(ctx, appointment.order_id)
            if current is not None and current.status == "open":
                return _charge_out(appointment, current)
            if current is not None and current.status == "completed":
                raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
        order = _open_check(ctx, appointment)
    except UnknownOperation, AppInactive:
        raise Conflict(
            str(SALE_UNAVAILABLE), code="appointment.sale_unavailable"
        ) from None
    if appointment.order_id != order.id:
        appointment.order_id = order.id
        appointment.save(update_fields=["order_id", "updated_at"])
        _put_customer_on(ctx, appointment, order.id)
        _event(
            ctx, events.APPOINTMENT_CHECK_OPENED, appointment, order_id=str(order.id)
        )
    return _charge_out(appointment, order)


def _check_of(ctx: OperationContext, order_id: UUID):
    """The check of the till (Sales) ``order_id``, or ``None`` when it no longer exists."""
    read = get("sale.order.get")
    try:
        return read(ctx, read.input.model_validate({"order_id": str(order_id)}))
    except NotFound:
        return None


def _open_check(ctx: OperationContext, appointment: Appointment):
    """Opens the appointment's check in the till: titled «customer · number», a service line per service
    (SALE-F38: a voucher of the customer can pay it, SALE-F27) at its booked price, by the professional
    who did it. Sales answers the check already open for it, if any (``already``)."""
    staff_id = str(appointment.staff_id) if appointment.staff_id else None
    lines = []
    for line in appointment.lines.select_related("service__tax_category").order_by(
        "position", "id"
    ):
        if needs_tax_setup(line.service):
            raise Conflict(
                str(NEEDS_TAX_SETUP) % {"name": line.name},
                code="appointment.service_needs_tax_setup",
            )
        # Charged what was booked (the professional's own price included, whatever the catalog says
        # today): Sales checks it against this appointment.
        lines.append(
            {
                "service_id": str(line.service_id),
                "staff_id": staff_id,
                "booked_price": line.price,
            }
        )
    label = f"{appointment.customer_name or appointment.number} · {appointment.number}"[
        :60
    ]
    open_check = get("sale.order.open")
    return open_check(
        ctx,
        open_check.input.model_validate(
            {
                "label": label,
                "appointment_id": str(appointment.id),
                "service_lines": lines,
            }
        ),
    )


def _put_customer_on(ctx: OperationContext, appointment: Appointment, order_id: UUID) -> None:
    """Puts the appointment's customer on its check, as the till's «Assign customer» does: the sale is then hers
    and counts on her card. A card that can no longer go on a check (deleted, merged, erased) or a caller without
    the right leaves the check without one, as it was: the till still shows «Assign customer»."""
    link = get("customer.order.link")
    data = {"order_id": str(order_id), "customer_id": str(appointment.customer_id)}
    try:
        link(ctx, link.input.model_validate(data))
    except OperationError as refusal:
        logger.info("appointment: check opened without the customer (%s)", refusal.code)


def _charge_out(appointment: Appointment, order) -> dict:
    return {
        "appointment_id": appointment.id,
        "order_id": order.id,
        "label": order.label,
    }
