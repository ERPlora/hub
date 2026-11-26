"""Whom a booking is for (RESERVATION-F06): the live card with the phone typed, found by Customers' search by phone,
and the check of a booking's card before the assistant shows it."""

import unicodedata
from dataclasses import replace

from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import INTERNAL, operation

from apps.customer.queries.cards import customers_by_phone
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.cards import ByPhoneIn, PhoneMatch
from apps.reservation.schemas.fields import SAY_FOR_WHOM
from apps.reservation.schemas.reservations import GUEST_BOOKS, BookingGuestOut, ReservationIn
from base.sensitive import VIEW_CUSTOMER_CONTACT

NO_GUEST = "reservation.no_guest"
#: Booking needs no right in Customers (FLOW-F12): the card with the guest's phone is looked up for the booking.
SEEKING = frozenset({"customer.view", VIEW_CUSTOMER_CONTACT})


def _folded(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in plain if not unicodedata.combining(char)).strip()


def card_with_phone(ctx: OperationContext, phone: str, name: str) -> PhoneMatch | None:
    """The live card with ``phone`` (among several, the one with ``name``, case and accents ignored; else the first
    by name), or ``None``."""
    seeker = replace(ctx, permissions=ctx.permissions | SEEKING)
    matches = customers_by_phone(seeker, ByPhoneIn(phone=phone)).rows
    wanted = _folded(name)
    return next((row for row in matches if _folded(row.name) == wanted), matches[0] if matches else None)


def phone_names(data) -> bool:
    """Whether only the guest's phone says whom a staff booking is for: no card chosen nor name given."""
    named = data.guest_name or data.customer_id is not None or data.customer
    return not named and bool(data.guest_phone) and data.source not in GUEST_BOOKS


def card_of_phone(ctx: OperationContext, phone: str) -> PhoneMatch | None:
    """The card a staff booking that gives only the guest's phone is for, or ``None``: whoever does not see the
    customers' contact searches a customer only by her name (BASE-F119)."""
    return card_with_phone(ctx, phone, "") if ctx.has(VIEW_CUSTOMER_CONTACT) else None


def phone_guest(ctx: OperationContext, phone: str) -> PhoneMatch:
    """``card_of_phone``, refused when there is none: the staff are asked the guest's name, and no card is made."""
    card = card_of_phone(ctx, phone)
    if card is None:
        message = str(SAY_FOR_WHOM)
        raise InvalidPayload(message, code=NO_GUEST, fields={"guest_name": message})
    return card


@operation(
    "reservation.reservation.check",
    kind="query",
    permission="reservation.add_reservation",
    input=ReservationIn,
    output=BookingGuestOut,
    ai=INTERNAL,
)
def check_booking(ctx: OperationContext, data: ReservationIn) -> dict:
    """Whom a booking is for, before the assistant shows its card: the card chosen, or the one with the phone a staff
    booking gives alone; refused when there is none, so the person is asked before any card."""
    if data.customer_id is not None or data.customer:
        return {"id": find_customer(ctx, data.customer_id, data.customer).id}
    return {"id": phone_guest(ctx, data.guest_phone).id if phone_names(data) else None}

