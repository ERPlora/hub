"""Events of the reservation app (``reservation.<entity>.<fact>``) and its reactions to Customers' events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. ``status_changed`` and ``updated`` are the contract Tables listens to (TABLE-F25–F27): they
carry the table, the day and time, the guests and the guest's name and card, which Tables paints on the
hold. The rest carry ids and numbers, never a name or a free note (WORKBOOK «Lo que avisa»).

Reactions, each through an operation of this app run as the system, in its own transaction: two cards
merged move the absorbed card's reservations and waitlist entries (``customer.customer.merged``,
RESERVATION-F21); an erased card empties their personal data (``customer.customer.erased``, F22). The
outbox relay (phase 2, in the worker) hands each delivered event to ``react``; every reaction is
idempotent, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

RESERVATION_CREATED = "reservation.reservation.created"
RESERVATION_STATUS_CHANGED = "reservation.reservation.status_changed"
RESERVATION_UPDATED = "reservation.reservation.updated"
RESERVATION_DELETED = "reservation.reservation.deleted"
RESERVATION_UNCONFIRMED_RELEASED = "reservation.reservation.unconfirmed_released"
TIME_SLOT_CREATED = "reservation.time_slot.created"
TIME_SLOT_DELETED = "reservation.time_slot.deleted"
BLOCKED_DATE_CREATED = "reservation.blocked_date.created"
BLOCKED_DATE_DELETED = "reservation.blocked_date.deleted"
WAITLIST_CREATED = "reservation.waitlist.created"
WAITLIST_UPDATED = "reservation.waitlist.updated"
WAITLIST_CONVERTED = "reservation.waitlist.converted"
WAITLIST_DELETED = "reservation.waitlist.deleted"
SETTINGS_UPDATED = "reservation.settings.updated"
CUSTOMER_REASSIGNED = "reservation.customer.reassigned"
CUSTOMER_ERASED = "reservation.customer.erased"

#: Everything that changes what a reservation row says (or which rows there are).
RESERVATION_EVENTS = [
    RESERVATION_CREATED,
    RESERVATION_STATUS_CHANGED,
    RESERVATION_UPDATED,
    RESERVATION_DELETED,
    RESERVATION_UNCONFIRMED_RELEASED,
    CUSTOMER_REASSIGNED,
    CUSTOMER_ERASED,
]
SLOT_EVENTS = [TIME_SLOT_CREATED, TIME_SLOT_DELETED]
BLOCKED_EVENTS = [BLOCKED_DATE_CREATED, BLOCKED_DATE_DELETED]
WAITLIST_EVENTS = [
    WAITLIST_CREATED,
    WAITLIST_UPDATED,
    WAITLIST_CONVERTED,
    WAITLIST_DELETED,
    CUSTOMER_REASSIGNED,
    CUSTOMER_ERASED,
]
ALL = [
    RESERVATION_CREATED,
    RESERVATION_STATUS_CHANGED,
    RESERVATION_UPDATED,
    RESERVATION_DELETED,
    RESERVATION_UNCONFIRMED_RELEASED,
    TIME_SLOT_CREATED,
    TIME_SLOT_DELETED,
    BLOCKED_DATE_CREATED,
    BLOCKED_DATE_DELETED,
    WAITLIST_CREATED,
    WAITLIST_UPDATED,
    WAITLIST_CONVERTED,
    WAITLIST_DELETED,
    SETTINGS_UPDATED,
    CUSTOMER_REASSIGNED,
    CUSTOMER_ERASED,
]

# Other apps' events (their WORKBOOKs fix the payloads).
CUSTOMER_MERGED_IN = "customer.customer.merged"
CUSTOMER_ERASED_IN = "customer.customer.erased"
#: A table renamed, moved to another zone, taken out of service or deleted: its label and the free tables.
TABLE_EVENTS = [
    "table.table.created",
    "table.table.updated",
    "table.table.deleted",
    "table.zone.updated",
    "table.zone.deleted",
]
#: The business's hours (Schedules): a day's opening spans.
SCHEDULE_EVENTS = [
    "schedule.week.updated",
    "schedule.special_day.created",
    "schedule.special_day.updated",
    "schedule.special_day.deleted",
    "schedule.override.created",
    "schedule.override.updated",
    "schedule.override.deleted",
]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    CUSTOMER_MERGED_IN: "reservation.customer.reassign",
    CUSTOMER_ERASED_IN: "reservation.customer.erase",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
