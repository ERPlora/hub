"""The waitlist (RESERVATION-F14 to F16): writing somebody on it, marking them contacted, turning their entry into a
reservation and taking them off.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.reservation import engine, events
from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.queries import entry_out, find_entry
from apps.reservation.schemas import (
    ConvertedOut,
    DeletedOut,
    WaitlistIn,
    WaitlistOut,
    WaitlistPatchIn,
    WaitlistConvertIn,
    WaitlistRefIn,
)
from apps.reservation.services.gate import judge, lock_book
from apps.reservation.services.guests import _guest_contact, card_for_phone, typed_phone
from apps.reservation.services.other_apps import status_changed
from apps.reservation.services.reservations import _loaded, created_event
from apps.reservation.services.writes import S, _stamp

ENTRY_CONVERTED = _("This entry was already converted into a reservation.")


@operation(
    "reservation.waitlist.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_waitlistentry",
    input=WaitlistIn,
    output=WaitlistOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "put Luis on the waitlist for Saturday, four people",
                "add Marta to tonight's waitlist",
            ),
            "es": (
                "añade a Luis a la lista de espera del sábado",
                "mete a Marta en la lista de espera de esta noche",
            ),
        },
        "description": "Writes somebody on the waitlist for a day, around a time, for a number of guests: the guest's "
        "card (by id, name or phone; with a name and phone, the card with that phone or a new one).",
        "risk": "normal",
    },
)
def create_entry(ctx: OperationContext, data: WaitlistIn) -> dict:
    # No contact is required (market, duda 7): the phone is only for calling back.
    typed = typed_phone(ctx, data.guest_phone)
    card, name, phone, email = _guest_contact(ctx, data, typed)
    if card is None and phone:
        card = card_for_phone(ctx, name, phone, email, "walk_in")
        phone = card.phone or phone
    entry = WaitlistEntry(
        customer=card,
        guest_name=name,
        guest_phone=phone,
        guest_email=email,
        date=data.date,
        preferred_time=data.preferred_time,
        party_size=data.party_size,
        notes=data.notes,
    )
    _stamp(entry, ctx, created=True)
    entry.save()
    record_event(ctx, events.WAITLIST_CREATED, {"id": str(entry.pk)})
    return entry_out(entry)


@operation(
    "reservation.waitlist.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_waitlistentry",
    input=WaitlistPatchIn,
    output=WaitlistOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "I already called Luis from the waitlist",
                "note on Marta's waitlist entry that she comes with a baby",
            ),
            "es": (
                "cambia a Luis de la lista de espera a contactado",
                "anota en la espera de Marta que viene con un bebé",
            ),
        },
        "description": "Marks a waitlist entry as contacted (or not) and changes its notes (by id, or by its guest).",
        "risk": "normal",
    },
)
def update_entry(ctx: OperationContext, data: WaitlistPatchIn) -> dict:
    entry = find_entry(ctx, data.id, data.guest, data.day, lock=True)
    if data.is_contacted is not None and data.is_contacted != entry.is_contacted:
        entry.is_contacted = data.is_contacted
        entry.contacted_at = timezone.now() if data.is_contacted else None
    if data.notes is not None:
        entry.notes = data.notes
    _stamp(entry, ctx)
    entry.save()
    record_event(ctx, events.WAITLIST_UPDATED, {"id": str(entry.pk)})
    return entry_out(entry)


@operation(
    "reservation.waitlist.convert",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_waitlistentry",
    input=WaitlistConvertIn,
    output=ConvertedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "turn Luis's waitlist entry into a booking",
                "a spot opened up: convert Marta's waitlist entry",
            ),
            "es": (
                "pasa a Luis de la lista de espera a reserva",
                "se ha liberado sitio: dale la reserva a Marta de la lista de espera",
            ),
        },
        "description": "Turns a waitlist entry (by id, or by its guest's name or phone) into a reservation with its own "
        "data (guest, day, preferred time, guests, notes) and the default duration. It only checks the blocked days, "
        "the opening hours and a slot with room; the entry is marked converted.",
        "risk": "normal",
    },
)
def convert_entry(ctx: OperationContext, data: WaitlistConvertIn) -> dict:
    settings = lock_book()
    entry = find_entry(ctx, data.id, data.guest, data.day, lock=True)
    if entry.reservation_id is not None:
        raise Conflict(str(ENTRY_CONVERTED), code="reservation.waitlist_converted")
    request = engine.Request(
        date=entry.date,
        time=entry.preferred_time,
        party_size=entry.party_size,
        duration_minutes=settings.default_duration_minutes,
        kind="waitlist",
        overbook=data.overbook,
    )
    judge(ctx, settings, request, None)
    confirmed = settings.auto_confirm
    reservation = Reservation(
        customer_id=entry.customer_id,
        guest_name=entry.guest_name,
        guest_phone=entry.guest_phone,
        guest_email=entry.guest_email,
        date=entry.date,
        time=entry.preferred_time,
        party_size=entry.party_size,
        duration_minutes=settings.default_duration_minutes,
        source=Reservation.Source.WAITLIST,
        notes=entry.notes,
        status=S.CONFIRMED if confirmed else S.PENDING,
        confirmed_at=timezone.now() if confirmed else None,
    )
    _stamp(reservation, ctx, created=True)
    reservation.save()
    entry.reservation = reservation
    _stamp(entry, ctx)
    entry.save()
    created_event(ctx, reservation)
    if confirmed:
        status_changed(ctx, reservation, None)
    record_event(
        ctx,
        events.WAITLIST_CONVERTED,
        {"id": str(entry.pk), "reservation_id": str(reservation.pk)},
    )
    return {"entry": entry_out(entry), "reservation": _loaded(ctx, reservation)}


@operation(
    "reservation.waitlist.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_waitlistentry",
    input=WaitlistRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "take Luis off the waitlist",
                "remove Marta from the waiting list",
            ),
            "es": (
                "elimina a Luis de la lista de espera",
                "borra a Marta de la lista de espera",
            ),
        },
        "description": "Takes somebody off the waitlist (by id, or by their name or phone).",
        "risk": "high",
    },
)
def delete_entry(ctx: OperationContext, data: WaitlistRefIn) -> dict:
    entry = find_entry(ctx, data.id, data.guest, data.day, lock=True)
    entry.is_deleted, entry.deleted_at = True, timezone.now()
    _stamp(entry, ctx)
    entry.save()
    record_event(ctx, events.WAITLIST_DELETED, {"id": str(entry.pk)})
    return {"id": entry.pk}
