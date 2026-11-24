"""Taking and changing a reservation (RESERVATION-F06, F08), and the reservation an input names."""

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.reservation import engine, events
from apps.reservation.models import Reservation
from apps.reservation.queries import find_reservation, reservation_out
from apps.reservation.schemas import ReservationIn, ReservationOut, ReservationPatchIn, ReservationRefIn
from apps.reservation.services.gate import choose_table, judge, lock_book
from apps.reservation.services.guests import CARD_SOURCES, _guest_contact, card_for_phone, typed_phone
from apps.reservation.services.other_apps import drop_hold, status_changed, sync_hold
from apps.reservation.services.writes import S, _stamp
from base.assistant import card_order

#: What a reservation may still change once seated, completed, cancelled or not shown.
NOTES_ONLY = {"notes", "internal_notes"}
NOT_EDITABLE = _("This reservation can no longer change: only its notes.")
CUSTOMER_MISMATCH = _(
    "That reservation belongs to a different guest, so it cannot be managed on their behalf."
)
STAFF_ONLY = _(
    "The table and the restaurant's internal notes are set by the restaurant: they cannot be changed from the "
    "guest's own booking."
)
#: What only the restaurant sets on a booking, never a channel acting for the guest, booking a full slot anyway
#: included.
STAFF_ONLY_FIELDS = ("table_id", "table", "zone", "no_table", "internal_notes", "overbook")
#: The data that say for whom a booking is: the customer card, by its id or as said, else the guest's name.
FOR_WHOM = ("customer_id", "customer", "guest_name")


def _loaded(ctx: OperationContext, reservation: Reservation) -> dict:
    """The reservation's row, read again with its table and its waitlist entry, as ``ctx`` reads it."""
    return reservation_out(
        ctx, Reservation.objects.select_related("table__zone").get(pk=reservation.pk)
    )


def _booking_summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """For whom, the day and the time first, as the book lists a reservation: the card's line says only its first
    three data, so a guest's name said as well goes after them."""
    whom = next((field for field in fields if field["name"] in FOR_WHOM and field["kind"] == "text"), None)
    if whom is None:
        return fields
    return card_order.put_first(fields, (whom["name"], "date", "time"))


@operation(
    "reservation.reservation.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.add_reservation",
    input=ReservationIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "book a table for 4 tomorrow at 9 pm for Luis",
                "reservation for Marta on Saturday at 2 pm, six people",
            ),
            "es": (
                "reserva mesa para cuatro mañana a las 21:00 a nombre de Luis",
                "apunta una reserva para Marta el sábado a las 14:00, seis personas",
            ),
        },
        "description": "Takes a reservation («a table for 4 tomorrow at 21:00 for Ana, phone 600 111 222, table 5»): "
        "the guest's customer card (by id, name or phone; with only a name and phone, the card with that phone or a new "
        "one), the day, time and guests, optionally the table, duration, source and notes. It must pass the book's gate "
        "(guests, time, blocked days, opening hours, a slot with room, a free table); it is born pending, or confirmed "
        "when the book confirms by itself, which holds its table. Somebody already on the waitlist is booked with "
        "reservation.waitlist.convert, which marks their entry converted.",
        "risk": "normal",
        "summary": _booking_summary,
    },
)
def create_reservation(ctx: OperationContext, data: ReservationIn) -> dict:
    typed = typed_phone(ctx, data.guest_phone)
    settings = lock_book()
    card, name, phone, email = _guest_contact(ctx, data, typed)
    table = choose_table(data.table_id, data.table, data.zone)
    minutes = data.duration_minutes or settings.default_duration_minutes
    # The card before the gate: a phone Customers refuses is said first, never after «Book anyway?». A
    # refusal of the gate rolls the new card back with everything else.
    if card is None and phone:
        card = card_for_phone(ctx, name or phone, phone, email, CARD_SOURCES[data.source])
        phone = card.phone or phone
        # A guest who books herself without a name (WhatsApp) is booked under her card's name: her phone, on a
        # new card.
        name = name or card.name
    request = engine.Request(
        date=data.date,
        time=data.time,
        party_size=data.party_size,
        duration_minutes=minutes,
        source=data.source,
        check_contact=True,
        overbook=data.overbook,
        phone=phone,
        email=email,
    )
    judge(ctx, settings, request, table)
    confirmed = settings.auto_confirm
    reservation = Reservation(
        customer=card,
        guest_name=name,
        guest_phone=phone,
        guest_email=email,
        date=data.date,
        time=data.time,
        party_size=data.party_size,
        duration_minutes=minutes,
        table=table,
        source=data.source,
        notes=data.notes,
        internal_notes=data.internal_notes,
        status=S.CONFIRMED if confirmed else S.PENDING,
        confirmed_at=timezone.now() if confirmed else None,
    )
    _stamp(reservation, ctx, created=True)
    reservation.save()
    created_event(ctx, reservation)
    if confirmed:
        status_changed(ctx, reservation, None)
        sync_hold(ctx, reservation, S.CONFIRMED)
    return _loaded(ctx, reservation)


def created_event(ctx: OperationContext, reservation: Reservation) -> None:
    record_event(
        ctx,
        events.RESERVATION_CREATED,
        {
            "id": str(reservation.pk),
            "status": reservation.status,
            "table_id": str(reservation.table_id) if reservation.table_id else None,
            "date": reservation.date.isoformat(),
            "time": f"{reservation.time:%H:%M}",
            "party_size": reservation.party_size,
        },
    )


#: What a change may send, and what of it the gate judges again.
SLOT_FIELDS = ("date", "time", "party_size", "duration_minutes")
CONTACT_FIELDS = ("guest_name", "guest_phone", "guest_email")


@operation(
    "reservation.reservation.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=ReservationPatchIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "move Luis's booking to 10 pm",
                "Marta's reservation is now for six",
            ),
            "es": (
                "pasa la reserva de Luis a las 22:00",
                "la reserva de Marta ahora es de seis personas",
            ),
        },
        "description": "Changes a reservation (by id, or by its guest and day): its day, time, guests, duration, table "
        "(or `no_table` to leave it without one), the guest's name, phone or email, or its notes. Only what is sent "
        "changes; the change passes the same gate as booking. A confirmed reservation moves its hold on the floor plan. "
        "Once seated, completed, cancelled or not shown, only its notes change.",
        "risk": "normal",
    },
)
def update_reservation(ctx: OperationContext, data: ReservationPatchIn) -> dict:  # noqa: C901
    settings = lock_book()
    reservation = _named(ctx, data)
    if data.on_behalf_of is not None and any(
        getattr(data, field) not in (None, False) for field in STAFF_ONLY_FIELDS
    ):
        raise Conflict(str(STAFF_ONLY), code="reservation.staff_only_field")
    sent = data.model_fields_set - {"id", "guest", "day", "zone", "on_behalf_of"}
    changes: dict[str, Any] = {
        field: getattr(data, field)
        for field in (*SLOT_FIELDS, *CONTACT_FIELDS, "notes", "internal_notes")
        if field in sent and getattr(data, field) is not None
    }
    if "guest_phone" in changes:
        # First, as in booking (RESERVATION-F06): a phone that is not a number is said before the table or the
        # gate; and before the comparison, so the same number typed another way is no change.
        changes["guest_phone"] = typed_phone(ctx, changes["guest_phone"])
    old_table = reservation.table
    new_table = old_table
    if data.no_table:
        new_table = None
    elif data.table_id is not None or data.table:
        new_table = choose_table(data.table_id, data.table, data.zone)
    changes = {
        field: value
        for field, value in changes.items()
        if getattr(reservation, field) != value
    }
    table_changed = (new_table.pk if new_table else None) != reservation.table_id
    if reservation.status not in (S.PENDING, S.CONFIRMED) and (
        set(changes) - NOTES_ONLY or table_changed
    ):
        raise Conflict(str(NOT_EDITABLE), code="reservation.not_editable")
    judged = set(changes) & set(SLOT_FIELDS) or table_changed
    for field, value in changes.items():
        setattr(reservation, field, value)
    reservation.table = new_table
    if judged:
        request = engine.Request(
            date=reservation.date,
            time=reservation.time,
            party_size=reservation.party_size,
            duration_minutes=reservation.duration_minutes,
            source=judged_as(reservation, data),
            check_when=bool({"date", "time"} & set(changes)),
            overbook=data.overbook,
        )
        judge(ctx, settings, request, new_table, exclude=(reservation.pk,))
    if not changes and not table_changed:
        return _loaded(ctx, reservation)
    _stamp(reservation, ctx)
    reservation.save()
    told = {
        field: (
            value.isoformat()
            if field == "date"
            else f"{value:%H:%M}"
            if field == "time"
            else value
        )
        for field, value in changes.items()
        if field in (*SLOT_FIELDS, "guest_name")
    }
    if table_changed:
        told["table_id"] = str(new_table.pk) if new_table else None
    record_event(ctx, events.RESERVATION_UPDATED, {"id": str(reservation.pk), **told})
    if reservation.status == S.CONFIRMED and (told or table_changed):
        if new_table is None and old_table is not None:
            drop_hold(ctx, reservation)
        else:
            sync_hold(ctx, reservation, S.CONFIRMED)
    return _loaded(ctx, reservation)


def _named(ctx: OperationContext, data: ReservationRefIn) -> Reservation:
    """The reservation the input names, locked. On the guest's behalf (``on_behalf_of``), only hers: any other —
    somebody else's, a walk-in without a card, a deleted or a missing one — is the same refusal, asked before its
    status, so a channel learns nothing about a booking that is not the guest's."""
    guest = getattr(data, "on_behalf_of", None)
    if guest is None:
        return find_reservation(ctx, data.id, data.guest, data.day, lock=True)
    try:
        reservation = find_reservation(ctx, data.id, data.guest, data.day, lock=True)
    except NotFound:
        reservation = None
    if reservation is None or reservation.customer_id != guest:
        raise Conflict(str(CUSTOMER_MISMATCH), code="reservation.customer_mismatch")
    return reservation


def judged_as(reservation: Reservation, data: ReservationPatchIn) -> str:
    """Whose rules judge a change (duda 8): the staff's, whatever the booking's origin; on the guest's behalf,
    those of a guest who books herself."""
    if data.on_behalf_of is None:
        return Reservation.Source.PHONE
    return reservation.source if reservation.source in engine.GUEST_SOURCES else Reservation.Source.WHATSAPP
