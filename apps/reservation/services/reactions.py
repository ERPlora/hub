"""The platform's reactions to Customers (RESERVATION-F21, F22): a card merged into another and a customer erased."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation
from live.models import OutboxEvent
from live.outbox import record_event

from apps.customer.services.writes import lock_customers
from apps.reservation import events
from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.schemas import ChangedOut, CustomerEventIn, MergedIn

#: The platform's own writes (reactions): the system has «*»; no role is given this one.
SYSTEM = "reservation.system"


@operation(
    "reservation.customer.reassign",
    kind="command",
    permission=SYSTEM,
    input=MergedIn,
    output=ChangedOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's reservations and waitlist "
        "entries move to the card that stays (the names they were booked with do not change).",
        "risk": "normal",
    },
)
def reassign_customer(ctx: OperationContext, data: MergedIn) -> dict:
    if data.id is None or data.absorbed_id is None or data.id == data.absorbed_id:
        return {"changed": 0}
    # The card that stays before the rows that move to it; one the Hub admin deleted takes nothing.
    if not lock_customers([data.id]):
        return {"changed": 0}
    moved = Reservation.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    moved += WaitlistEntry.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    if moved:
        record_event(
            ctx,
            events.CUSTOMER_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"changed": moved}


#: The events of the contract with Tables that carry the guest's name (the hold's label).
NAMED_EVENTS = (events.RESERVATION_STATUS_CHANGED, events.RESERVATION_UPDATED)


def forget_names_announced(customer_id) -> int:
    """Empties the guest's name in the events her reservations announced (`status_changed`, `updated`, the
    payload Tables reads): the outbox keeps them, and her erasure must reach them too. How many changed."""
    ids = [str(pk) for pk in Reservation.objects.filter(customer_id=customer_id).values_list("pk", flat=True)]
    if not ids:
        return 0
    named = OutboxEvent.objects.filter(name__in=NAMED_EVENTS, payload__id__in=ids, payload__has_key="guest_name")
    redacted = []
    for event in named:
        if event.payload.get("guest_name"):
            event.payload = {**event.payload, "guest_name": ""}
            redacted.append(event)
    OutboxEvent.objects.bulk_update(redacted, ["payload"])
    return len(redacted)


@operation(
    "reservation.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ChangedOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's name, phone, email, notes and "
        "cancellation reasons are emptied in her reservations and waitlist entries (deleted ones too); the bookings "
        "themselves stay.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    if data.id is None:
        return {"changed": 0}
    changed = forget_names_announced(data.id)
    changed += (
        Reservation.objects.filter(customer_id=data.id)
        .exclude(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            internal_notes="",
            cancellation_reason="",
        )
        .update(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            internal_notes="",
            cancellation_reason="",
            updated_at=timezone.now(),
        )
    )
    changed += (
        WaitlistEntry.objects.filter(customer_id=data.id)
        .exclude(guest_name="", guest_phone="", guest_email="", notes="")
        .update(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            updated_at=timezone.now(),
        )
    )
    if changed:
        record_event(ctx, events.CUSTOMER_ERASED, {"id": str(data.id)})
    return {"changed": changed}
