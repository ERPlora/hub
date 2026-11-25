"""The lookups the reads share with the writes (services/), inside the command's own transaction: a reservation, a
waitlist entry, a slot or a blocked date by its id or as a person says it.
"""

import datetime as dt
import re
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound

from apps.customer.queries.contact import sees_contact
from apps.reservation.models import BlockedDate, Reservation, TimeSlot, WaitlistEntry
from apps.reservation.queries.clock import business_now
from apps.reservation.queries.gate import HOLDING
from apps.reservation.queries.rows import reservations

#: What a guest's name alone names, when she has any of them.
OPEN = HOLDING
MAX_CANDIDATES = 5
DIGITS = re.compile(r"\D")

RESERVATION_NOT_FOUND = _("That reservation does not exist in this business.")
RESERVATION_AMBIGUOUS = _(
    "“%(said)s” has several reservations: %(matches)s. Say which day."
)
ENTRY_NOT_FOUND = _("That waitlist entry does not exist in this business.")
ENTRY_AMBIGUOUS = _(
    "“%(said)s” is on the waitlist several times: %(matches)s. Say which day."
)
SLOT_NOT_FOUND = _("That time slot does not exist in this business.")
BLOCK_NOT_FOUND = _("That blocked date does not exist in this business.")
BLOCK_AMBIGUOUS = _("That date is blocked at several times: say which one by its id.")


def _phone_matches(said: str) -> Q:
    """Part of the guest's phone, as typed or by its digits alone (spaces, dashes, a prefix)."""
    text = said.strip()
    match = Q(guest_phone__icontains=text)
    digits = DIGITS.sub("", text)
    if len(digits) >= 3:
        match |= Q(guest_phone__icontains=digits)
    return match


def _guest_matches(ctx: OperationContext, said: str) -> Q:
    """The guest by part of the name and, for whoever sees the customers' contact details, of the email or the phone
    (however typed: spaces, prefix): a search by them would tell whose they are."""
    text = said.strip()
    named = Q(guest_name__icontains=text)
    return (named | Q(guest_email__icontains=text) | _phone_matches(text)) if sees_contact(ctx) else named


def _when(day: dt.date, at: dt.time) -> str:
    return f"{day:%Y-%m-%d} {at:%H:%M}"


def find_reservation(
    ctx: OperationContext,
    reservation_id: UUID | None,
    guest: str | None,
    day: dt.date | None,
    *,
    lock: bool = False,
) -> Reservation:
    """A live reservation by id or, as a person says it, by its guest's name or phone (``_guest_matches``) and its
    day (the coming ones when no day is said; among several, the open ones)."""
    rows = reservations()
    if reservation_id is None:
        named = rows.filter(_guest_matches(ctx, guest or ""))
        named = (
            named.filter(date=day)
            if day
            else named.filter(date__gte=business_now().date())
        )
        candidates = list(named.order_by("date", "time", "id")[: MAX_CANDIDATES * 4])
        open_ones = [item for item in candidates if item.status in OPEN]
        candidates = open_ones or candidates
        if len(candidates) > 1:
            matches = ", ".join(
                f"{item.guest_name} · {_when(item.date, item.time)}"
                for item in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(RESERVATION_AMBIGUOUS) % {"said": guest, "matches": matches},
                code="reservation.reservation_ambiguous",
            )
        reservation_id = candidates[0].pk if candidates else None
    if reservation_id is not None and lock:
        rows = rows.select_for_update(of=("self",))
    found = (
        rows.filter(pk=reservation_id).first() if reservation_id is not None else None
    )
    if found is None:
        raise NotFound(
            str(RESERVATION_NOT_FOUND), code="reservation.reservation_not_found"
        )
    return found


def waiting_entries() -> QuerySet[WaitlistEntry]:
    return WaitlistEntry.objects.filter(is_deleted=False)


def find_entry(
    ctx: OperationContext, entry_id: UUID | None, guest: str | None, day: dt.date | None, *, lock: bool = False
) -> WaitlistEntry:
    """A live waitlist entry by id or by its guest (``_guest_matches``) and day; among several, the ones waiting."""
    rows = waiting_entries()
    if entry_id is None:
        named = rows.filter(_guest_matches(ctx, guest or ""))
        if day:
            named = named.filter(date=day)
        candidates = list(
            named.order_by("date", "preferred_time", "created_at", "id")[
                : MAX_CANDIDATES * 4
            ]
        )
        waiting = [item for item in candidates if item.reservation_id is None]
        candidates = waiting or candidates
        if len(candidates) > 1:
            matches = ", ".join(
                f"{item.guest_name} · {_when(item.date, item.preferred_time)}"
                for item in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(ENTRY_AMBIGUOUS) % {"said": guest, "matches": matches},
                code="reservation.entry_ambiguous",
            )
        entry_id = candidates[0].pk if candidates else None
    if entry_id is not None and lock:
        rows = rows.select_for_update()
    found = rows.filter(pk=entry_id).first() if entry_id is not None else None
    if found is None:
        raise NotFound(str(ENTRY_NOT_FOUND), code="reservation.entry_not_found")
    return found


def find_slot(
    slot_id: UUID | None,
    day_of_week: int | None,
    start_time: dt.time | None,
    *,
    lock: bool = False,
) -> TimeSlot:
    """A live slot by id or by its weekday and its start."""
    rows = TimeSlot.objects.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    if slot_id is not None:
        rows = rows.filter(pk=slot_id)
    else:
        rows = rows.filter(day_of_week=day_of_week, start_time=start_time)
    slot = rows.first()
    if slot is None:
        raise NotFound(str(SLOT_NOT_FOUND), code="reservation.slot_not_found")
    return slot


def find_block(
    block_id: UUID | None, day: dt.date | None, *, lock: bool = False
) -> BlockedDate:
    """A live blocked date by id or by its day, when that day is blocked once."""
    rows = BlockedDate.objects.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    rows = rows.filter(pk=block_id) if block_id is not None else rows.filter(date=day)
    found = list(rows[:2])
    if not found:
        raise NotFound(str(BLOCK_NOT_FOUND), code="reservation.blocked_date_not_found")
    if len(found) > 1:
        raise Conflict(str(BLOCK_AMBIGUOUS), code="reservation.blocked_date_ambiguous")
    return found[0]
