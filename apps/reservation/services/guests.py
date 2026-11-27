"""The guest's card: the one the caller chose, the live card with the typed phone or a new one made by Customers, and
the phone as Customers keeps it (RESERVATION-F06).
"""

from live.context import OperationContext
from live.errors import InvalidPayload

from apps.customer.models import Customer
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries.reads import business_country, find_customer
from apps.customer.services.writes import PHONE_INVALID
from apps.reservation.queries.guests import card_with_phone, phone_guest, phone_names
from apps.reservation.services.other_apps import call_app, card_keeper


#: Where a card made from a reservation comes from, as Customers names it.
CARD_SOURCES = {"phone": "phone", "in_person": "walk_in", "whatsapp": "whatsapp", "online": "website"}


def chosen_card(ctx: OperationContext, customer_id, customer_said: str | None) -> Customer | None:
    """The card the caller chose (by id, or by name, phone or email), or ``None``.

    A card a write links is locked when it is found, as Customers' writes and the Hub admin's «Delete» of a card
    take it: a deletion under way is waited for and the card is gone (404), and one that comes after waits for
    the write and finds the row that protects the card."""
    if customer_id is None and not customer_said:
        return None
    return find_customer(ctx, customer_id, customer_said, lock=True)


def _guest_contact(ctx: OperationContext, data, typed: str) -> tuple[Customer | None, str, str, str]:
    """The card the caller chose (``chosen_card``) and the guest's name, phone and email: what was typed, else the
    card's."""
    card = chosen_card(ctx, data.customer_id, data.customer)
    return (
        card,
        data.guest_name or (card.name if card else ""),
        typed or (card.phone if card else ""),
        data.guest_email or (card.email if card else ""),
    )


def typed_phone(ctx: OperationContext, raw: str | None) -> str:
    """The phone the caller typed, as Customers keeps it: E.164, a number without prefix read in the business's
    country, one with a ``+`` kept in its own; empty stays empty. One that is not a valid number of its country is
    refused with Customers' reason on the phone field, before any other check (RESERVATION-F06)."""
    try:
        return to_e164(raw, business_country(ctx))
    except InvalidPhone:
        message = str(PHONE_INVALID)
        raise InvalidPayload(
            message, code="reservation.phone_invalid", fields={"guest_phone": message}
        ) from None


def booking_card(ctx: OperationContext, data, name: str, phone: str, email: str) -> Customer:
    """The card of a booking none was chosen for, by the phone typed: when the phone alone says whom a staff booking is
    for, the card it is on and never a new one (``phone_guest``); else ``card_for_phone``, under the guest's name or,
    for a guest who books herself without one, her phone."""
    if phone_names(data):
        return find_customer(ctx, phone_guest(ctx, phone).id, None, lock=True)
    return card_for_phone(ctx, name or phone, phone, email, CARD_SOURCES[data.source])


def card_for_phone(
    ctx: OperationContext, name: str, phone: str, email: str, source: str
) -> Customer:
    """The live card with ``phone`` (``card_with_phone``) or a new one with the guest's name, phone and email, made
    by Customers (``card_keeper``)."""
    match = card_with_phone(ctx, phone, name)
    if match is not None:
        return find_customer(ctx, match.id, None, lock=True)  # locked, as ``chosen_card``
    try:
        created = call_app(
            card_keeper(ctx),
            "customer.customer.create",
            {"name": name, "phone": phone, "email": email, "source": source},
        )
    except InvalidPayload as error:
        fields = {f"guest_{key}": text for key, text in (error.fields or {}).items()}
        raise InvalidPayload(error.message, fields=fields or None) from None
    return Customer.objects.get(pk=created.id)
