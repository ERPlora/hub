"""The platform's reaction (events.py, F12)."""

from live.context import OperationContext
from live.operations import operation

from apps.online_booking.models import Booking
from apps.online_booking.schemas.reactions import CustomerEventIn, ReactionOut

#: Run only by the platform (events.py): outside ``online_booking.*``, so no role and no API key holds it.
SYSTEM = "system.online_booking"


@operation(
    "online_booking.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's personal links stop working "
        "and the fingerprint of the device she booked with is forgotten.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    rows = Booking.objects.filter(appointment__customer_id=data.id).exclude(
        token_hash__isnull=True, requester=""
    )
    return {"changed": rows.update(token_hash=None, requester="")}
