"""Deleting an appointment and bringing it back (APPOINTMENT-F11)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.appointment import events
from apps.appointment.models import Appointment
from apps.appointment.queries import (
    APPOINTMENT_NOT_FOUND,
    MOVABLE,
    find_appointment,
    load_detail,
    resolve_services,
)
from apps.appointment.schemas import (
    AppointmentIdIn,
    AppointmentOut,
    AppointmentRefIn,
    BulkDeletedOut,
    BulkDeleteIn,
    DeletedOut,
    ServiceRefIn,
)
from apps.appointment.services.writes import (
    CANNOT,
    SYSTEM,
    A,
    S,
    _actor,
    _event,
    _history,
    _judge,
    _member_for_booking,
    _refuse_with_open_check,
    lock_appointments,
    lock_series,
)
from apps.customer.queries import find_customer

DELETE = "appointment.delete_appointment"
OCCURRENCE_BOOKED = _("Its repeating appointment has booked that date again since.")


def _delete(ctx: OperationContext, appointment: Appointment) -> None:
    if appointment.status in (S.IN_PROGRESS, S.COMPLETED) or appointment.sale_id:
        raise Conflict(str(CANNOT["delete"]), code="appointment.cannot_delete")
    _refuse_with_open_check(appointment)
    appointment.deleted_at = timezone.now()
    appointment.updated_by = _actor(ctx)
    appointment.save(update_fields=["deleted_at", "updated_by", "updated_at"])
    _history(ctx, appointment, A.DELETED)
    _event(ctx, events.APPOINTMENT_DELETED, appointment)


@operation(
    "appointment.appointment.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=DELETE,
    input=AppointmentRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete Lucía's appointment from the agenda",
                "erase that test appointment of Friday",
            ),
            "es": (
                "borra de la agenda la cita de Lucía",
                "quita del todo la cita de prueba del viernes",
            ),
        },
        "description": "Delete an appointment from the agenda (it is archived, not destroyed): pending, confirmed, "
        "cancelled or no-show and not charged. Cancelling keeps the record and is usually what is wanted.",
        "risk": "high",
    },
)
def delete_appointment(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    _delete(ctx, appointment)
    return {"id": appointment.id}


@operation(
    "appointment.appointment.bulk_delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=DELETE,
    input=BulkDeleteIn,
    output=BulkDeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete these three appointments at once",
                "remove all of Clara's appointments next week in one go",
            ),
            "es": (
                "borra de una vez las tres citas de Clara",
                "elimina juntas todas las citas de prueba del lunes",
            ),
        },
        "description": "Delete several appointments at once (all or none).",
        "risk": "high",
    },
)
def bulk_delete(ctx: OperationContext, data: BulkDeleteIn) -> dict:
    ids = list(dict.fromkeys(data.ids))
    lock_appointments(ids)
    deleted = []
    for appointment_id in ids:
        appointment = find_appointment(ctx, appointment_id, None, lock=True)
        _delete(ctx, appointment)
        deleted.append(appointment.id)
    return {"deleted": deleted}


@operation(
    "appointment.appointment.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=AppointmentIdIn,
    output=AppointmentOut,
    ai={
        "description": "Bring a deleted appointment back to the agenda, the same one with its number, its history and "
        "its series (run by the platform when ERPlora's staff recovers the business from a separate copy).",
        "risk": "normal",
    },
)
def restore_appointment(ctx: OperationContext, data: AppointmentIdIn) -> dict:
    """A deleted appointment back on the agenda as it was (deleting keeps it, APPOINTMENT-F11), with a line in its
    history. One already on the agenda is answered as it is."""
    # Its series first, as every write takes them: a run of the series cannot book its date meanwhile.
    lock_series(Appointment.objects.filter(pk=data.id).values("recurring_id"))
    appointment = Appointment.objects.select_for_update(of=("self",)).filter(pk=data.id).first()
    if appointment is None:
        raise NotFound(str(APPOINTMENT_NOT_FOUND), code="appointment.appointment_not_found")
    if appointment.deleted_at is not None:
        _refuse_unless_restorable(ctx, appointment)
        appointment.deleted_at = None
        appointment.updated_by = _actor(ctx)
        appointment.save(update_fields=["deleted_at", "updated_by", "updated_at"])
        _history(ctx, appointment, A.RESTORED)
        _event(ctx, events.APPOINTMENT_RESTORED, appointment)
    return load_detail(ctx, appointment.id)


def _refuse_unless_restorable(ctx: OperationContext, appointment: Appointment) -> None:
    """A deleted appointment comes back only as the agenda would book it now: for a live card, never on a date its
    series booked again and, while it is still booked, with its services and its professional bookable at a time
    that fits (judged by the customer's rules, as the platform always is)."""
    find_customer(ctx, appointment.customer_id, None)
    if (
        appointment.recurring_id
        and Appointment.objects.filter(
            recurring_id=appointment.recurring_id,
            occurrence_date=appointment.occurrence_date,
            deleted_at__isnull=True,
        ).exists()
    ):
        raise Conflict(str(OCCURRENCE_BOOKED), code="appointment.occurrence_booked")
    if appointment.status not in MOVABLE:
        return
    services = resolve_services([ServiceRefIn(service_id=line.service_id) for line in appointment.lines.all()])
    member = _member_for_booking(ctx, appointment.staff_id, None, services) if appointment.staff_id else None
    _judge(ctx, member, appointment.start, appointment.end, customer=True, confirm_overlap=False)
