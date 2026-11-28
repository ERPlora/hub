"""Cancelling by the link (F11): the customer cancels her booking as herself, under the business's policy."""

from live.context import OperationContext
from live.operations import get, operation

from apps.appointment.models.appointments import Appointment
from apps.appointment.schemas import changes as diary_changes
from apps.online_booking.queries.links import find_by_token, public_booking_out
from apps.online_booking.queries.visitors import PUBLIC, delegated
from apps.online_booking.schemas.public import PublicBookingOut, PublicCancelIn


@operation(
    "online_booking.public.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=PUBLIC,
    input=PublicCancelIn,
    output=PublicBookingOut,
    ai={
        "asks": {
            "en": (
                "cancel through Leire's own link on her behalf",
                "with the customer's link, call off her booking for her",
            ),
            "es": (
                "anula lo que Leire reservó en la web, con su enlace y por ella",
                "con el enlace de Leire, anúlale lo del jueves por ella",
            ),
        },
        "description": "Cancel the booking behind a customer's personal link, as the customer: the business's "
        "cancellation policy applies.",
        "risk": "high",
    },
)
def public_cancel(ctx: OperationContext, data: PublicCancelIn) -> dict:
    appointment = find_by_token(data.token).appointment
    cancel = get("appointment.appointment.cancel")
    cancel(
        delegated(ctx),
        diary_changes.CancelIn(
            id=appointment.id,
            on_behalf_of_customer=True,
            customer_id=appointment.customer_id,
            reason=data.reason,
        ),
    )
    return public_booking_out(
        ctx, Appointment.objects.prefetch_related("lines").get(pk=appointment.pk)
    )
