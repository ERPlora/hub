"""Other apps, by their operations: Tables holds, moves and releases a reservation's table, reading it as
``status_changed`` carries it, and Customers finds or makes the guest's card.
"""

from dataclasses import replace
from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, get
from live.outbox import record_event

from apps.reservation import events
from apps.reservation.models import Reservation
from base.sensitive import VIEW_CUSTOMER_CONTACT

#: Tables' platform operations (the holds of reservations).
TABLE_SYSTEM = "table.system"
#: What finding the guest's card by the phone she gives, or making it, asks of Customers (``card_keeper``): that phone
#: is looked up among the customers' contact details.
CARD_RIGHTS = frozenset({"customer.view", "customer.manage", VIEW_CUSTOMER_CONTACT})
TABLES_UNAVAILABLE = _(
    "Tables is not available in this business: the reservation's table cannot be held or seated."
)


def call_app(ctx: OperationContext, name: str, data: dict) -> Any:
    """Runs another app's operation ``name`` with ``ctx``, in this transaction."""
    try:
        op = get(name)
    except UnknownOperation:
        raise Conflict(
            str(TABLES_UNAVAILABLE), code="reservation.tables_unavailable"
        ) from None
    try:
        return op(ctx, op.input.model_validate(data))
    except AppInactive:
        raise Conflict(
            str(TABLES_UNAVAILABLE), code="reservation.tables_unavailable"
        ) from None


def table_system(ctx: OperationContext) -> OperationContext:
    """``ctx`` with Tables' platform permission added, for the holds of reservations only."""
    return replace(ctx, permissions=ctx.permissions | {TABLE_SYSTEM})


def card_keeper(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to find the guest's card by her phone or make it, for that only: booking needs no right in
    Customers, as it needs none in Schedules (``queries.reader``), so an automation granted only to book books by
    phone (FLOW-F12) and keeps none of Customers' rights after it."""
    return replace(ctx, permissions=ctx.permissions | CARD_RIGHTS)


def contract(reservation: Reservation, status: str) -> dict:
    """The reservation as Tables reads it (TABLE-F25–F27): the payload of ``status_changed``."""
    return {
        "id": str(reservation.pk),
        "status": status,
        "table_id": str(reservation.table_id) if reservation.table_id else None,
        "date": reservation.date.isoformat(),
        "time": f"{reservation.time:%H:%M}",
        "duration_minutes": reservation.duration_minutes,
        "party_size": reservation.party_size,
        "guest_name": reservation.guest_name,
        "customer_id": str(reservation.customer_id)
        if reservation.customer_id
        else None,
    }


def sync_hold(ctx: OperationContext, reservation: Reservation, status: str) -> None:
    """Tables holds, moves or releases the reservation's table (only when it has one)."""
    if reservation.table_id is not None:
        call_app(
            table_system(ctx),
            "table.hold.sync_reservation",
            contract(reservation, status),
        )


def drop_hold(ctx: OperationContext, reservation: Reservation) -> None:
    """A confirmed reservation left without a table: Tables releases its hold."""
    call_app(
        table_system(ctx),
        "table.hold.move_reservation",
        {"id": str(reservation.pk), "table_id": None},
    )


def status_changed(
    ctx: OperationContext,
    reservation: Reservation,
    previous: str | None,
    status: str | None = None,
) -> None:
    record_event(
        ctx,
        events.RESERVATION_STATUS_CHANGED,
        {
            **contract(reservation, status or reservation.status),
            "previous_status": previous,
        },
    )
