"""The book's gate without a database: services.py reads what it needs and asks ``verdict``.

**Can this reservation be taken?** The first reason that refuses wins, in this order (the old module's
pre-check and gate, plus the opening hours and the table):

1. ``phone_required``, ``email_required`` — only when booking (``check_contact``): a change does not ask
   again, as the old update gate did not.
2. ``party_size_exceeded`` — outside the rules' minimum and maximum guests.
3. ``in_past`` (a time already gone, to the minute) or ``too_soon`` (less than the minimum notice) — only
   when the day or the time is new (``check_when``): a reservation under way may get one more guest.
4. ``too_far`` — beyond the maximum days ahead (same condition).
5. ``date_blocked`` — a blocked day, or a blocked window that covers the time (both ends included).
6. ``outside_schedule`` — Schedules governs the day and no opening span holds the start (the eve's span
   past midnight counts). A day no rule reaches (``restricted`` false) refuses nothing.
7. ``no_service_day`` — no slot of the weekday covers the time (start included, end excluded).
8. ``no_capacity`` — the slot that covers it is full: its reservations, or its covers when it limits them.
9. ``table_unavailable`` and ``table_taken`` — the table is out of service, or another live reservation
   holds it for part of the window.

**Whose rules** (market, WORKBOOK «Investigación de mercado», duda 8): the guest who books herself
(online, WhatsApp) is bound by the party limits, the minimum notice, the days ahead and a full slot. The
staff (phone, in person, a conversion from the waitlist) only by a time already gone, and may book a full
slot knowingly (``overbook``, after a warning: the refusal says ``{"overbook": True}``). Blocked days,
opening hours, slots and tables bind everybody, and nobody books a time gone. A conversion
(``kind="waitlist"``) is the staff acting, often for right now: like any staff booking it skips the party
limits, the notice and the days ahead (the old module's promotion), never the clock.

Times are the business's wall clock, naive: the day and time a reservation keeps.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

#: The sources where the guest books herself: the book's online rules bind them.
GUEST_SOURCES = frozenset({"online", "whatsapp"})


@dataclass(frozen=True)
class Rules:
    """The book's settings that judge a reservation."""

    min_party_size: int = 1
    max_party_size: int = 20
    min_advance_hours: int = 1
    max_advance_days: int = 30
    require_phone: bool = True
    require_email: bool = False


@dataclass(frozen=True)
class Window:
    """From ``start`` to ``end`` (excluded) on the wall clock."""

    start: dt.datetime
    end: dt.datetime

    @classmethod
    def of(cls, day: dt.date, at: dt.time, minutes: int) -> "Window":
        start = dt.datetime.combine(day, at)
        return cls(start, start + dt.timedelta(minutes=minutes))

    def overlaps(self, other: "Window") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Slot:
    """A slot of the day with what it already holds (live reservations and their guests)."""

    id: object
    start: dt.time
    end: dt.time
    max_reservations: int
    max_covers: int | None = None
    reserved: int = 0
    covers: int = 0

    def covers_time(self, at: dt.time) -> bool:
        return self.start <= at < self.end

    @property
    def available(self) -> int:
        return max(self.max_reservations - self.reserved, 0)

    @property
    def full(self) -> bool:
        return self.reserved >= self.max_reservations or (
            self.max_covers is not None and self.covers >= self.max_covers
        )

    def fits(self, party_size: int) -> bool:
        return self.reserved < self.max_reservations and (
            self.max_covers is None or self.covers + party_size <= self.max_covers
        )


@dataclass(frozen=True)
class Block:
    """A blocked day (``is_full_day``) or a blocked window of it."""

    is_full_day: bool
    start: dt.time | None = None
    end: dt.time | None = None

    def blocks(self, at: dt.time) -> bool:
        if self.is_full_day:
            return True
        return (
            self.start is not None
            and self.end is not None
            and self.start <= at <= self.end
        )


@dataclass(frozen=True)
class Hours:
    """The business's opening spans of the day and of the eve (Schedules), naive wall clock."""

    restricted: bool
    spans: tuple[tuple[dt.datetime, dt.datetime], ...] = ()

    def open_at(self, moment: dt.datetime) -> bool:
        if not self.restricted:
            return True
        return any(start <= moment < end for start, end in self.spans)


@dataclass(frozen=True)
class TableFacts:
    """The table asked for: whether it is in service, and the windows other live reservations hold."""

    label: str
    in_service: bool
    booked: tuple[Window, ...] = ()


@dataclass(frozen=True)
class Request:
    date: dt.date
    time: dt.time
    party_size: int
    duration_minutes: int
    source: str = "phone"
    kind: Literal["booking", "waitlist"] = "booking"
    check_contact: bool = False
    # False when a change keeps the day and the time: the clock is not judged again.
    check_when: bool = True
    # The staff book a full slot knowingly (never the guest who books herself).
    overbook: bool = False
    phone: str = ""
    email: str = ""

    @property
    def window(self) -> Window:
        return Window.of(self.date, self.time, self.duration_minutes)


@dataclass(frozen=True)
class Refusal:
    code: str
    params: dict = field(default_factory=dict)


def slot_for(slots, at: dt.time) -> Slot | None:
    """The slot that covers ``at`` (slots of a day do not overlap)."""
    return next((slot for slot in slots if slot.covers_time(at)), None)


def _hhmm(moment: dt.datetime) -> str:
    return f"{moment:%H:%M}"


def verdict(
    request: Request,
    *,
    rules: Rules,
    now: dt.datetime,
    blocks,
    hours: Hours,
    slots,
    table: TableFacts | None,
) -> Refusal | None:
    """The first reason that refuses ``request``, or ``None`` when it can be taken."""
    guest = request.source in GUEST_SOURCES and request.kind != "waitlist"
    if request.check_contact:
        if rules.require_phone and not request.phone.strip():
            return Refusal("phone_required")
        if rules.require_email and not request.email.strip():
            return Refusal("email_required")
    start = dt.datetime.combine(request.date, request.time)
    if guest and not rules.min_party_size <= request.party_size <= rules.max_party_size:
        return Refusal(
            "party_size_exceeded",
            {"min": rules.min_party_size, "max": rules.max_party_size},
        )
    if request.check_when:
        if guest:
            if start < now + dt.timedelta(hours=rules.min_advance_hours):
                return Refusal("too_soon", {"hours": rules.min_advance_hours})
            if (request.date - now.date()).days > rules.max_advance_days:
                return Refusal("too_far", {"days": rules.max_advance_days})
        elif start < now.replace(second=0, microsecond=0):
            return Refusal("in_past")
    if any(block.blocks(request.time) for block in blocks):
        return Refusal("date_blocked")
    if not hours.open_at(start):
        return Refusal("outside_schedule")
    slot = slot_for(slots, request.time)
    if slot is None:
        return Refusal("no_service_day")
    if not slot.fits(request.party_size) and (guest or not request.overbook):
        return Refusal("no_capacity", {} if guest else {"overbook": True})
    if table is not None:
        if not table.in_service:
            return Refusal("table_unavailable", {"table": table.label})
        window = request.window
        clash = next((other for other in table.booked if other.overlaps(window)), None)
        if clash is not None:
            return Refusal(
                "table_taken",
                {
                    "table": table.label,
                    "start": _hhmm(clash.start),
                    "end": _hhmm(clash.end),
                },
            )
    return None
