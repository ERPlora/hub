"""Events of the appointment app (``appointment.<entity>.<fact>``) and its reactions to the events of
Customers, Staff and Sales.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids, the number and the time, never notes nor a reason (free text that may
hold health data).

Reactions (WORKBOOK «A qué reacciona»): two cards merged move the absorbed card's appointments and series
(``customer.customer.merged``), an erased card empties its copies (``customer.customer.erased``), a
professional who leaves unassigns her upcoming appointments and pauses her series
(``staff.member.terminated``), a sale from an appointment marks it charged (``sale.sale.created_from_appointment``),
a voided sale unmarks it (``sale.sale.voided``) and a voided open check frees it for a new one
(``sale.order.voided``); each through an operation of this app run as the
system, in its own transaction. Archiving a service changes nothing here (the market: Fresha, Phorest,
TimeTap — what is booked keeps its service; the next dates of a series are skipped with their reason).
The outbox relay (phase 2, in the worker) hands each delivered event to ``react``; every reaction is
idempotent, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

APPOINTMENT_CREATED = "appointment.appointment.created"
APPOINTMENT_CONFIRMED = "appointment.appointment.confirmed"
APPOINTMENT_STARTED = "appointment.appointment.started"
APPOINTMENT_COMPLETED = "appointment.appointment.completed"
APPOINTMENT_MARKED_NO_SHOW = "appointment.appointment.marked_no_show"
APPOINTMENT_CANCELLED = "appointment.appointment.cancelled"
APPOINTMENT_RESCHEDULED = "appointment.appointment.rescheduled"
APPOINTMENT_UPDATED = "appointment.appointment.updated"
APPOINTMENT_DELETED = "appointment.appointment.deleted"
APPOINTMENT_CHARGED = "appointment.appointment.charged"
APPOINTMENT_UNCHARGED = "appointment.appointment.uncharged"
APPOINTMENT_CHECK_OPENED = "appointment.appointment.check_opened"
APPOINTMENT_CHECK_CLOSED = "appointment.appointment.check_closed"
APPOINTMENT_UNASSIGNED = "appointment.appointment.unassigned"
APPOINTMENT_REASSIGNED = "appointment.appointment.reassigned"
BLOCKED_TIME_CREATED = "appointment.blocked_time.created"
BLOCKED_TIME_DELETED = "appointment.blocked_time.deleted"
RECURRING_CREATED = "appointment.recurring.created"
RECURRING_UPDATED = "appointment.recurring.updated"
RECURRING_DELETED = "appointment.recurring.deleted"
SETTINGS_UPDATED = "appointment.settings.updated"

#: Everything that changes what an appointment row says.
APPOINTMENT_EVENTS = [
    APPOINTMENT_CREATED,
    APPOINTMENT_CONFIRMED,
    APPOINTMENT_STARTED,
    APPOINTMENT_COMPLETED,
    APPOINTMENT_MARKED_NO_SHOW,
    APPOINTMENT_CANCELLED,
    APPOINTMENT_RESCHEDULED,
    APPOINTMENT_UPDATED,
    APPOINTMENT_DELETED,
    APPOINTMENT_CHARGED,
    APPOINTMENT_UNCHARGED,
    APPOINTMENT_CHECK_OPENED,
    APPOINTMENT_CHECK_CLOSED,
    APPOINTMENT_UNASSIGNED,
    APPOINTMENT_REASSIGNED,
]
BLOCKED_TIME_EVENTS = [BLOCKED_TIME_CREATED, BLOCKED_TIME_DELETED]
RECURRING_EVENTS = [RECURRING_CREATED, RECURRING_UPDATED, RECURRING_DELETED]
ALL = [*APPOINTMENT_EVENTS, *BLOCKED_TIME_EVENTS, *RECURRING_EVENTS, SETTINGS_UPDATED]

# Other apps' events (their WORKBOOKs fix the payloads).
CUSTOMER_MERGED = "customer.customer.merged"
CUSTOMER_ERASED = "customer.customer.erased"
STAFF_MEMBER_TERMINATED = "staff.member.terminated"
SALE_FROM_APPOINTMENT = "sale.sale.created_from_appointment"
SALE_VOIDED = "sale.sale.voided"
SALE_ORDER_VOIDED = "sale.order.voided"
#: What re-runs the agenda's lanes and the free times: who is on the team and when they work.
STAFF_EVENTS = [
    "staff.member.created",
    "staff.member.updated",
    "staff.member.deactivated",
    STAFF_MEMBER_TERMINATED,
    "staff.schedule.created",
    "staff.schedule.updated",
    "staff.schedule.deleted",
    "staff.time_off.approved",
    "staff.time_off.cancelled",
]
#: The business's hours (Schedules).
SCHEDULE_EVENTS = [
    "schedule.week.updated",
    "schedule.special_day.created",
    "schedule.special_day.updated",
    "schedule.special_day.deleted",
    "schedule.override.created",
    "schedule.override.updated",
    "schedule.override.deleted",
]
#: Who performs each service and what a service is (Services).
SERVICE_EVENTS = [
    "service.service.updated",
    "service.service.archived",
    "service.service.restored",
    "service.assignment.assigned",
    "service.assignment.updated",
    "service.assignment.removed",
]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    CUSTOMER_MERGED: "appointment.customer.reassign",
    CUSTOMER_ERASED: "appointment.customer.erase",
    STAFF_MEMBER_TERMINATED: "appointment.staff.release",
    SALE_FROM_APPOINTMENT: "appointment.appointment.mark_charged",
    SALE_VOIDED: "appointment.appointment.unmark_charged",
    SALE_ORDER_VOIDED: "appointment.appointment.release_check",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
