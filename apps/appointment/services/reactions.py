"""The platform's reactions to other apps (events.py): a sale charged or voided, a check released, a customer merged or
erased and a professional who leaves.
"""

from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.appointment import events
from apps.appointment.models import Appointment, History, Recurring
from apps.appointment.queries import BUSY, MOVABLE, now
from apps.appointment.schemas import (
    CustomerEventIn,
    MemberEventIn,
    MergedIn,
    OrderVoidedIn,
    ReactionOut,
    SaleFromAppointmentIn,
    SaleVoidedIn,
)
from apps.appointment.services.writes import (
    ALREADY_CHARGED,
    CANNOT,
    SYSTEM,
    A,
    S,
    _event,
    _history,
    lock_appointments,
    lock_series,
)
from apps.customer.services import lock_customers


@operation(
    "appointment.appointment.mark_charged",
    kind="command",
    permission=SYSTEM,
    input=SaleFromAppointmentIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.created_from_appointment: the appointment is charged with that "
        "sale and completed.",
        "risk": "normal",
    },
)
def mark_charged(ctx: OperationContext, data: SaleFromAppointmentIn) -> dict:
    appointment = (
        Appointment.objects.select_for_update().filter(pk=data.appointment_id).first()
    )
    if (
        appointment is None
        or appointment.deleted_at is not None
        or appointment.status in (S.CANCELLED, S.NO_SHOW)
    ):
        raise Conflict(str(CANNOT["charge"]), code="appointment.cannot_charge")
    if appointment.sale_id == data.sale_id:
        return {"changed": 0}
    if appointment.sale_id:
        raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
    appointment.sale_id = data.sale_id
    appointment.charged_at = timezone.now()
    completes = appointment.status in BUSY
    if completes:
        appointment.status = S.COMPLETED
    appointment.save()
    _history(ctx, appointment, A.CHARGED, new={"sale_id": str(data.sale_id)})
    _event(ctx, events.APPOINTMENT_CHARGED, appointment, sale_id=str(data.sale_id))
    if completes:
        _history(ctx, appointment, A.COMPLETED)
        _event(ctx, events.APPOINTMENT_COMPLETED, appointment)
    return {"changed": 1}


@operation(
    "appointment.appointment.unmark_charged",
    kind="command",
    permission=SYSTEM,
    input=SaleVoidedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.voided: its appointment is no longer charged.",
        "risk": "normal",
    },
)
def unmark_charged(ctx: OperationContext, data: SaleVoidedIn) -> dict:
    changed = 0
    for appointment in (
        Appointment.objects.select_for_update()
        .filter(sale_id=data.sale_id)
        .order_by("id")
    ):
        appointment.sale_id = None
        appointment.charged_at = None
        appointment.order_id = None
        appointment.save(
            update_fields=["sale_id", "charged_at", "order_id", "updated_at"]
        )
        _history(ctx, appointment, A.UNCHARGED, old={"sale_id": str(data.sale_id)})
        _event(
            ctx, events.APPOINTMENT_UNCHARGED, appointment, sale_id=str(data.sale_id)
        )
        changed += 1
    return {"changed": changed}


@operation(
    "appointment.appointment.release_check",
    kind="command",
    permission=SYSTEM,
    input=OrderVoidedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.order.voided: the appointment whose open check was voided can open a "
        "new one.",
        "risk": "normal",
    },
)
def release_check(ctx: OperationContext, data: OrderVoidedIn) -> dict:
    changed = 0
    for appointment in (
        Appointment.objects.select_for_update()
        .filter(order_id=data.order_id, sale_id__isnull=True)
        .order_by("id")
    ):
        appointment.order_id = None
        appointment.save(update_fields=["order_id", "updated_at"])
        _event(
            ctx,
            events.APPOINTMENT_CHECK_CLOSED,
            appointment,
            order_id=str(data.order_id),
        )
        changed += 1
    return {"changed": changed}


@operation(
    "appointment.customer.reassign",
    kind="command",
    permission=SYSTEM,
    input=MergedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's appointments and series move "
        "to the card that stays (the names they were booked with do not change).",
        "risk": "normal",
    },
)
def reassign_customer(ctx: OperationContext, data: MergedIn) -> dict:
    # The card that stays before the rows that move to it; one the Hub admin deleted takes nothing.
    if not lock_customers([data.id]):
        return {"changed": 0}
    series = Recurring.objects.filter(customer_id=data.absorbed_id)
    lock_series(series.values_list("id", flat=True))
    appointments = Appointment.objects.filter(customer_id=data.absorbed_id)
    lock_appointments(appointments.values_list("id", flat=True))
    moved = appointments.update(customer_id=data.id)
    moved += series.update(customer_id=data.id)
    if moved:
        record_event(
            ctx,
            events.APPOINTMENT_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"changed": moved}


@operation(
    "appointment.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's name, contact, notes and "
        "cancellation reasons are emptied in her appointments, series and their history; her series are paused.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    series = Recurring.objects.filter(customer_id=data.id)
    lock_series(series.values_list("id", flat=True))
    rows = Appointment.objects.filter(customer_id=data.id)
    lock_appointments(rows.values_list("id", flat=True))
    changed = rows.exclude(
        customer_name="",
        customer_phone="",
        customer_email="",
        notes="",
        internal_notes="",
        cancellation_reason="",
    ).update(
        customer_name="",
        customer_phone="",
        customer_email="",
        notes="",
        internal_notes="",
        cancellation_reason="",
    )
    for line in History.objects.filter(appointment__customer_id=data.id):
        new_value = {
            key: value
            for key, value in line.new_value.items()
            if key != "customer_name"
        }
        if line.reason or new_value != line.new_value:
            line.reason = ""
            line.new_value = new_value
            line.save(update_fields=["reason", "new_value"])
    changed += series.exclude(customer_name="", is_active=False).update(
        customer_name="", is_active=False
    )
    if changed:
        record_event(ctx, events.APPOINTMENT_UPDATED, {"customer_id": str(data.id)})
    return {"changed": changed}


@operation(
    "appointment.staff.release",
    kind="command",
    permission=SYSTEM,
    input=MemberEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to staff.member.terminated: the professional's upcoming pending or confirmed "
        "appointments become unassigned (to hand to somebody else) and their series are paused.",
        "risk": "normal",
    },
)
def release_staff(ctx: OperationContext, data: MemberEventIn) -> dict:
    changed = 0
    own_series = Recurring.objects.filter(staff_id=data.id, deleted_at__isnull=True)
    own_series = own_series.filter(
        pk__in=lock_series(own_series.values_list("id", flat=True))
    )
    upcoming = Appointment.objects.filter(
        staff_id=data.id, status__in=MOVABLE, start__gte=now(), deleted_at__isnull=True
    )
    locked = lock_appointments(upcoming.values_list("id", flat=True))
    for appointment in upcoming.filter(pk__in=locked).order_by("start", "id"):
        name = appointment.staff_name
        appointment.staff = None
        appointment.save(update_fields=["staff", "updated_at"])
        _history(ctx, appointment, A.UNASSIGNED, old={"staff": name})
        _event(
            ctx,
            events.APPOINTMENT_UNASSIGNED,
            appointment,
            previous_staff_id=str(data.id),
        )
        changed += 1
    for series in own_series:
        series.staff = None
        series.is_active = False
        series.save(update_fields=["staff", "is_active", "updated_at"])
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
        changed += 1
    return {"changed": changed}
