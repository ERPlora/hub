"""A booking by its personal link, as the customer sees it, and until when she may cancel it."""

import datetime as dt

from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.appointment.models.appointments import Appointment
from apps.appointment.queries.business import current_settings as current_rules, now
from apps.online_booking.models import Booking
from apps.online_booking.schemas.public import PublicBookingOut, TokenIn
from base.business import business_zone, zone_name

from .bookings import BOOKING_NOT_FOUND, S
from .settings import current_settings
from .visitors import PUBLIC, hash_token


def find_by_token(token: str) -> Booking:
    """The live booking whose link is ``token`` (404 ``online_booking.booking_not_found`` otherwise)."""
    found = (
        Booking.objects.select_related("appointment")
        .filter(token_hash=hash_token(token), appointment__deleted_at__isnull=True)
        .first()
    )
    if found is None:
        raise NotFound(str(BOOKING_NOT_FOUND), code="online_booking.booking_not_found")
    return found


def cancel_until(appointment: Appointment) -> dt.datetime | None:
    """Until when the customer may cancel it herself (the diary's policy); ``None`` when she may not."""
    rules = current_rules()
    if (
        not rules.allow_customer_cancellation
        or appointment.status not in (S.PENDING, S.CONFIRMED)
        or appointment.sale_id
        or appointment.order_id
    ):
        return None
    return (
        appointment.start - dt.timedelta(hours=rules.cancellation_notice_hours)
    ).astimezone(business_zone())


def public_booking_out(ctx: OperationContext, appointment: Appointment) -> dict:
    zone, own = business_zone(), current_settings()
    until = cancel_until(appointment)
    return PublicBookingOut.owner(ctx, own.logo) | {
        "number": appointment.number,
        "status": appointment.status,
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "timezone": zone_name(),
        "service_names": ", ".join(line.name for line in appointment.lines.all()),
        "staff_name": appointment.staff_name,
        "can_cancel": until is not None and now() <= until,
        "cancel_until": until,
        "cancellation_policy": own.cancellation_policy,
    }


@operation(
    "online_booking.public.booking",
    kind="query",
    permission=PUBLIC,
    input=TokenIn,
    output=PublicBookingOut,
    ai={
        "asks": {
            "en": (
                "what does Leire see on the link of her booking?",
                "can Leire cancel it from her own link?",
            ),
            "es": (
                "¿qué ve Leire con el enlace de su reserva?",
                "¿Leire todavía puede anular desde su enlace?",
            ),
        },
        "description": "The booking behind a customer's personal link, and whether she may still cancel it."
    },
)
def public_booking(ctx: OperationContext, data: TokenIn) -> dict:
    return public_booking_out(ctx, find_by_token(data.token).appointment)
