"""Pausing, resuming, deleting and bringing back a repeating appointment (APPOINTMENT-F15)."""

from uuid import UUID

from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.appointment import events
from apps.appointment.models import Recurring
from apps.appointment.queries.access import CHANGE_OWN, may_change
from apps.appointment.queries.booking import resolve_services
from apps.appointment.queries.series import RECURRING_NOT_FOUND, find_series, load_series
from apps.appointment.schemas import (
    RecurringDeletedOut,
    RecurringOut,
    RecurringRefIn,
    ServiceRefIn,
)
from apps.appointment.services.series import RECURRING_NO_STAFF
from apps.appointment.services.writes import (
    CHANGE_OWN_ONLY,
    SYSTEM,
    _member_for_booking,
)
from apps.customer.queries import find_customer


def _set_active(ctx: OperationContext, series_id: UUID, active: bool) -> dict:
    series = find_series(ctx, series_id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if active and series.staff is None:
        raise Conflict(str(RECURRING_NO_STAFF), code="appointment.recurring_no_staff")
    if series.is_active != active:
        series.is_active = active
        series.save(update_fields=["is_active", "updated_at"])
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
    return load_series(series.id)


@operation(
    "appointment.recurring.deactivate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "pause Teresa's repeating appointment",
                "stop Carmen's weekly appointment for the summer",
            ),
            "es": (
                "deja en pausa la cita fija de Teresa",
                "desactiva la cita semanal de Carmen en verano",
            ),
        },
        "description": "Pause a repeating appointment: it stops booking dates; the ones booked are kept.",
        "risk": "normal",
    },
)
def deactivate_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    return _set_active(ctx, data.id, False)


@operation(
    "appointment.recurring.activate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "resume Teresa's paused repeating appointment",
                "reactivate Carmen's weekly appointment",
            ),
            "es": (
                "reanuda la cita fija de Teresa",
                "retoma la cita semanal de Carmen que estaba parada",
            ),
        },
        "description": "Reactivate a paused repeating appointment (it books nothing by itself: materialize does).",
        "risk": "normal",
    },
)
def activate_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    return _set_active(ctx, data.id, True)


@operation(
    "appointment.recurring.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringDeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete Teresa's repeating appointment but keep the ones booked",
                "remove Carmen's weekly appointment for good",
            ),
            "es": (
                "borra la cita fija de Teresa y deja las que ya tiene",
                "quita la serie de Carmen sin tocar sus citas",
            ),
        },
        "description": "Delete a repeating appointment; the appointments already booked are kept.",
        "risk": "high",
    },
)
def delete_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    series = find_series(ctx, data.id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    series.deleted_at = timezone.now()
    series.is_active = False
    series.save(update_fields=["deleted_at", "is_active", "updated_at"])
    record_event(ctx, events.RECURRING_DELETED, {"id": str(series.id)})
    return {"id": series.id}


@operation(
    "appointment.recurring.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=RecurringRefIn,
    output=RecurringOut,
    ai={
        "description": "Bring a deleted repeating appointment back to Repeating, the same one with the appointments it "
        "had booked, active and booking nothing by itself (run by the platform when ERPlora's staff recovers the "
        "business from a separate copy).",
        "risk": "normal",
    },
)
def restore_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    """A deleted series back in Repeating (deleting keeps it and its appointments, APPOINTMENT-F15), active, only as
    Repeating would create it now: for a live card, with its services and its professional bookable. It books nothing:
    its next dates wait for «Book» (APPOINTMENT-F13), which skips those it has booked. One already in Repeating is
    answered as it is."""
    series = Recurring.objects.select_for_update(of=("self",)).filter(pk=data.id).first()
    if series is None:
        raise NotFound(str(RECURRING_NOT_FOUND), code="appointment.recurring_not_found")
    if series.deleted_at is not None:
        find_customer(ctx, series.customer_id, None)
        if series.staff_id is None:
            raise Conflict(str(RECURRING_NO_STAFF), code="appointment.recurring_no_staff")
        services = resolve_services([ServiceRefIn(service_id=line.service_id) for line in series.lines.all()])
        _member_for_booking(ctx, series.staff_id, None, services)
        series.deleted_at = None
        series.is_active = True
        series.save(update_fields=["deleted_at", "is_active", "updated_at"])
        record_event(ctx, events.RECURRING_RESTORED, {"id": str(series.id), "customer_id": str(series.customer_id)})
    return load_series(series.id)
