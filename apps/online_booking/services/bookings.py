"""The inbox (F02–F06): confirming, completing, a no-show, cancelling and deleting a booking, done by the diary."""

from live.context import OperationContext
from live.operations import get, operation

from apps.appointment.models.appointments import Appointment
from apps.online_booking.queries.bookings import find_booking, load_detail
from apps.online_booking.schemas.bookings import BookingOut, BookingRefIn, CancelIn, DeletedOut

CHANGE = "online_booking.change_booking"
CONFIRM = "online_booking.confirm_booking"
DELETE = "online_booking.delete_booking"


def _diary(ctx: OperationContext, name: str, appointment: Appointment, **extra):
    """Runs the diary's operation ``name`` on ``appointment`` with ``ctx`` (its rules and its permission)."""
    op = get(name)
    return op(ctx, op.input.model_validate({"id": str(appointment.id), **extra}))


@operation(
    "online_booking.booking.confirm",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CONFIRM,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "accept Nerea's self-booking for Wednesday",
                "approve the booking that came in from my link",
            ),
            "es": (
                "acepta la reserva de internet de Nerea del miércoles",
                "da el visto bueno a la reserva de Nerea que tengo en la bandeja",
            ),
        },
        "description": "Confirm a booking a customer made online that is waiting (pending), named by its number or "
        "as a person says it: the customer and the day (e.g. confirm Ana's booking of tomorrow).",
        "risk": "normal",
    },
)
def confirm_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.confirm", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Nerea's self-booking from earlier today is done",
                "close off the booking APT-20261120-0004 from my link as finished",
            ),
            "es": (
                "lo que reservó Nerea por internet, dalo por hecho",
                "da por acabada la reserva de la bandeja APT-20261120-0004",
            ),
        },
        "description": "Mark an online booking (confirmed or in progress) as completed, named by its number or by the "
        "customer and the day. It does not charge it: that is the till.",
        "risk": "normal",
    },
)
def complete_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.complete", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.no_show",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Olga never turned up for her self-booking yesterday",
                "Olga missed her booking made through my link",
            ),
            "es": (
                "Olga no se ha presentado a lo que reservó por internet ayer",
                "Olga faltó a su reserva de la web: déjalo anotado",
            ),
        },
        "description": "Record that the customer of an online booking did not show up (only once its time has "
        "passed), named by its number or by the customer and the day.",
        "risk": "high",
    },
)
def no_show_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.mark_no_show", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=CHANGE,
    input=CancelIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel Olga's self-booking on Saturday, something came up",
                "decline the booking that came in through my link for Thursday",
            ),
            "es": (
                "anula la reserva de internet de Olga del sábado, no puede venir",
                "rechaza la reserva de la bandeja que tengo para el jueves",
            ),
        },
        "description": "Cancel (or decline) an online booking, named by its number or by the customer and the day, "
        "with an optional reason; its time becomes free.",
        "risk": "high",
    },
)
def cancel_booking(ctx: OperationContext, data: CancelIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.cancel", booking, reason=data.reason)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=DELETE,
    input=BookingRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "remove Olga's duplicate self-booking completely",
                "get rid of the fake booking that came in through my link for good",
            ),
            "es": (
                "borra la reserva de internet repetida de Olga",
                "quita para siempre de la bandeja la reserva falsa",
            ),
        },
        "description": "Delete an online booking from the inbox and the diary (archived, not destroyed), named by "
        "its number or by the customer and the day. Cancelling keeps its history and is usually what is wanted.",
        "risk": "high",
    },
)
def delete_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.delete", booking)
    return {"id": booking.id, "deleted": True}
