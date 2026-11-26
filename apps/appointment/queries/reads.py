"""What the reads share, and services too: the groups of statuses, how an appointment is found, how it is read and how a
list pages."""

import datetime as dt
from uuid import UUID

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound

from apps.appointment.models.appointments import Appointment
from apps.schedule.queries import day_label
from base.business import business_zone

from .access import for_caller
from .ownership import APPOINTMENTS

S = Appointment.Status
#: What occupies the professional's time.
BUSY = (S.PENDING, S.CONFIRMED, S.IN_PROGRESS)
#: What can still move.
MOVABLE = (S.PENDING, S.CONFIRMED)
CUSTOMER_SOURCES = (Appointment.Source.ONLINE, Appointment.Source.WHATSAPP)

APPOINTMENT_NOT_FOUND = _("That appointment does not exist in this business.")


def appointments(ctx: OperationContext) -> QuerySet[Appointment]:
    """The live appointments the caller may see (``APPOINTMENTS``), with their lines."""
    return APPOINTMENTS.visible(ctx).filter(deleted_at__isnull=True).prefetch_related("lines")


def find_appointment(
    ctx: OperationContext,
    appointment_id: UUID | None,
    number: str | None,
    *,
    lock: bool = False,
) -> Appointment:
    """The live appointment named by id or number that the caller may see (``NotFound`` otherwise)."""
    rows = APPOINTMENTS.visible(ctx).filter(deleted_at__isnull=True)
    rows = (
        rows.filter(pk=appointment_id)
        if appointment_id
        else rows.filter(number__iexact=number or "")
    )
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = rows.first()
    if found is None:
        raise NotFound(
            str(APPOINTMENT_NOT_FOUND), code="appointment.appointment_not_found"
        )
    return found


def _lines(appointment: Appointment) -> list[dict]:
    return [
        {
            "service_id": line.service_id,
            "name": line.name,
            "price": line.price,
            "duration_minutes": line.duration_minutes,
        }
        for line in appointment.lines.all()
    ]


def row(appointment: Appointment) -> dict:
    """An ``AppointmentRow``: what the agenda lists (no contact, no notes), on the business's clock."""
    zone = business_zone()
    lines = _lines(appointment)
    return {
        "id": appointment.id,
        "number": appointment.number,
        "customer_id": appointment.customer_id,
        "customer_name": appointment.customer_name,
        "staff_id": appointment.staff_id,
        "staff_name": appointment.staff_name,
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
        "source": appointment.source,
        "services": lines,
        "service_names": ", ".join(line["name"] for line in lines),
        "total": sum(line["price"] for line in lines),
        "booked_by_customer": appointment.source in CUSTOMER_SOURCES,
        "sale_id": appointment.sale_id,
        "order_id": appointment.order_id,
        "recurring_id": appointment.recurring_id,
        "occurrence_date": appointment.occurrence_date,
    }


def start_labels(ctx: OperationContext, start: dt.datetime) -> dict:
    """``start``'s day and hour ready to say (a flow's template has no clock nor formatter): the weekday and the date in
    the caller's language, and the hour in 24 hours."""
    wall = start.astimezone(business_zone())
    return {"start_date_label": day_label(wall.date(), ctx.language), "start_time_label": f"{wall:%H:%M}"}


def appointment_label(appointment: Appointment, said: dict) -> str:
    """How a card names an appointment: its customer (nothing once her data were erased), its day and hour (``said``,
    ``start_labels``) and its professional (nothing when it has none)."""
    parts = (appointment.customer_name, said["start_date_label"], said["start_time_label"], appointment.staff_name)
    return " · ".join(part for part in parts if part)


def detail(ctx: OperationContext, appointment: Appointment) -> dict:
    """An ``AppointmentOut``: everything, contact and notes included (for a person; ``for_caller``)."""
    said = start_labels(ctx, appointment.start)
    return for_caller(
        ctx,
        {
            **row(appointment),
            "customer_phone": appointment.customer_phone,
            "customer_email": appointment.customer_email,
            "notes": appointment.notes,
            "internal_notes": appointment.internal_notes,
            "cancelled_at": appointment.cancelled_at,
            "cancellation_reason": appointment.cancellation_reason,
            "cancelled_by_customer": appointment.cancelled_by_customer,
            "charged_at": appointment.charged_at,
            "created_at": appointment.created_at,
            "updated_at": appointment.updated_at,
            **said,
            "label": appointment_label(appointment, said),
        },
    )


def load_detail(ctx: OperationContext, appointment_id: UUID) -> dict:
    return detail(ctx, Appointment.objects.prefetch_related("lines").get(pk=appointment_id))


def _page(rows: QuerySet, limit: int, offset: int, out) -> dict:
    return {
        "rows": [out(item) for item in rows[offset : offset + limit]],
        "total": rows.count(),
        "limit": limit,
        "offset": offset,
    }
