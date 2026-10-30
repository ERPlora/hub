"""Read operations of the reservation app (``READ ONLY``): the reservations, one reservation, a day's
figures and slots, the free tables, the slots, the blocked dates, the waitlist and the rules. A read by id
(a reservation, a waitlist entry, a slot, a blocked date) also answers its ``label``: the words the book's
screens name it by, which the assistant's card says instead of the id (schemas.py, ``names``).

Shared with services.py, inside the command's own transaction: the business's clock, the rules, the
lookups of a reservation, a waitlist entry, a slot or a blocked date as a person says it, and everything the gate (engine.py)
reads — the slots of a day with what they hold, its blocks, its opening hours (Schedules) and a table's
facts (Tables). The business's zone is the Hub's; in phase 1, ``settings.TIME_ZONE`` (Europe/Madrid).
"""

import datetime as dt
import re
from dataclasses import replace
from uuid import UUID

from babel.dates import format_date, format_time, get_day_names
from django.db.models import CharField, Count, F, Func, Q, QuerySet, Sum, Value
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.reservation import engine
from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)
from apps.reservation.schemas import (
    BlockedDateDetailOut,
    BlockedDateListIn,
    BlockedDatePage,
    BlockedDateRefIn,
    DayIn,
    DayOut,
    FreeTablesOut,
    NoIn,
    ReservationDetailOut,
    ReservationListIn,
    ReservationPage,
    ReservationRefIn,
    SettingsOut,
    TablesIn,
    TimeSlotDetailOut,
    TimeSlotListIn,
    TimeSlotPage,
    TimeSlotRefIn,
    WaitlistDetailOut,
    WaitlistListIn,
    WaitlistPage,
    WaitlistRefIn,
)
from apps.schedule.queries import day_label, get_week, hours_for_range
from apps.schedule.schemas import HoursRangeIn, NoParamsIn
from apps.table.models import Table
from apps.table.queries import natural_key, table_label
from base.business import babel_locale

S = Reservation.Status
#: What a slot counts (the old gate's rule): every reservation not cancelled nor a no-show.
UNCOUNTED = (S.CANCELLED, S.NO_SHOW)
#: What holds a table for its window: the ones still coming or sitting there.
HOLDING = (S.PENDING, S.CONFIRMED, S.SEATED)
#: What a guest's name alone names, when she has any of them.
OPEN = HOLDING
MAX_CANDIDATES = 5
#: The rules of Schedules a business sets on purpose (its usual week counts once confirmed).
EXCEPTIONS = frozenset({"special_day", "override"})
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


# ── The business's clock and rules ───────────────────────────────────────────────────────────────


def business_zone():
    """The business's time zone (phase 1: ``settings.TIME_ZONE``; the Hub keeps no zone yet)."""
    return timezone.get_current_timezone()


def zone_name() -> str:
    zone = business_zone()
    return getattr(zone, "key", str(zone))


def business_now() -> dt.datetime:
    """Now on the business's wall clock (naive), what a reservation's day and time compare with (its
    ``fold`` says which pass of a repeated hour it is)."""
    return timezone.localtime(timezone.now(), business_zone()).replace(tzinfo=None)


def starts_at(day: dt.date, at: dt.time) -> dt.datetime:
    """The instant (UTC) ``day`` at ``at`` on the business's wall clock is."""
    return engine.instant(dt.datetime.combine(day, at), business_zone())


def window_of(day: dt.date, at: dt.time, minutes: int) -> engine.Window:
    """A stay from ``day`` at ``at`` on the business's wall clock, ``minutes`` of real time long."""
    return engine.Window.of(day, at, minutes, business_zone())


def wall_clock(moment: dt.datetime) -> dt.datetime:
    """An instant on the business's wall clock (naive)."""
    return engine.wall(moment, business_zone())


def current_settings() -> Settings:
    """The book's rules; the factory ones (unsaved) while nobody saved them."""
    return Settings.objects.first() or Settings()


def rules_of(settings: Settings) -> engine.Rules:
    return engine.Rules(
        min_party_size=settings.min_party_size,
        max_party_size=settings.max_party_size,
        min_advance_hours=settings.min_advance_hours,
        max_advance_days=settings.max_advance_days,
        require_phone=settings.require_phone,
        require_email=settings.require_email,
    )


def settings_row(settings: Settings) -> dict:
    return {
        "min_party_size": settings.min_party_size,
        "max_party_size": settings.max_party_size,
        "min_advance_hours": settings.min_advance_hours,
        "max_advance_days": settings.max_advance_days,
        "default_duration_minutes": settings.default_duration_minutes,
        "auto_confirm": settings.auto_confirm,
        "require_phone": settings.require_phone,
        "require_email": settings.require_email,
        "no_show_window_minutes": settings.no_show_window_minutes,
        "timezone": zone_name(),
    }


# ── Rows ─────────────────────────────────────────────────────────────────────────────────────────


def reservations() -> QuerySet[Reservation]:
    """The live reservations (never the deleted ones), with their table and its zone."""
    return Reservation.objects.filter(is_deleted=False).select_related(
        "table__zone", "waitlist_entry"
    )


def _end(reservation: Reservation) -> dt.time:
    """When the stay ends on the wall clock: the night the clocks change, 90 minutes from 01:37 end at
    02:07 (the second one) in October and 90 from 01:30 at 04:00 in March."""
    window = window_of(reservation.date, reservation.time, reservation.duration_minutes)
    return wall_clock(window.end).time()


def reservation_out(ctx: OperationContext, reservation: Reservation) -> dict:
    """A ``ReservationOut``, its day and hour also ready to say in ``ctx``'s language (a reservation keeps the
    business's wall clock: no zone moves them)."""
    table = reservation.table
    try:
        entry_id = reservation.waitlist_entry.pk
    except WaitlistEntry.DoesNotExist:
        entry_id = None
    return {
        "id": reservation.pk,
        "customer_id": reservation.customer_id,
        "guest_name": reservation.guest_name,
        "guest_phone": reservation.guest_phone,
        "guest_email": reservation.guest_email,
        "date": reservation.date,
        "time": reservation.time,
        "end_time": _end(reservation),
        "date_label": day_label(reservation.date, ctx.language),
        "time_label": f"{reservation.time:%H:%M}",
        "duration_minutes": reservation.duration_minutes,
        "party_size": reservation.party_size,
        "table_id": reservation.table_id,
        "table_label": table_label(table) if table is not None else "",
        "table_capacity": table.capacity if table is not None else None,
        "status": reservation.status,
        "source": reservation.source,
        "notes": reservation.notes,
        "internal_notes": reservation.internal_notes,
        "cancellation_reason": reservation.cancellation_reason,
        "confirmed_at": reservation.confirmed_at,
        "seated_at": reservation.seated_at,
        "completed_at": reservation.completed_at,
        "cancelled_at": reservation.cancelled_at,
        "no_show_at": reservation.no_show_at,
        "table_session_id": reservation.table_session_id,
        "waitlist_entry_id": entry_id,
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    }


def entry_out(entry: WaitlistEntry) -> dict:
    return {
        "id": entry.pk,
        "customer_id": entry.customer_id,
        "guest_name": entry.guest_name,
        "guest_phone": entry.guest_phone,
        "guest_email": entry.guest_email,
        "date": entry.date,
        "preferred_time": entry.preferred_time,
        "party_size": entry.party_size,
        "notes": entry.notes,
        "is_contacted": entry.is_contacted,
        "contacted_at": entry.contacted_at,
        "is_converted": entry.reservation_id is not None,
        "reservation_id": entry.reservation_id,
        "created_at": entry.created_at,
    }


def slot_out(slot: TimeSlot) -> dict:
    return {
        "id": slot.pk,
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "max_reservations": slot.max_reservations,
        "max_covers": slot.max_covers,
    }


def blocked_out(block: BlockedDate) -> dict:
    return {
        "id": block.pk,
        "date": block.date,
        "reason": block.reason,
        "is_full_day": block.is_full_day,
        "blocked_from": block.blocked_from,
        "blocked_until": block.blocked_until,
    }


# ── How the book names a record (a read by id's ``label``) ──────────────────────────────────────
# In the words the assistant's card says a day and a time (base/assistant.py: CLDR's medium day and short
# time, as the screens' formatters), in the caller's language: «Ana García · 15 oct 2026 · 21:00».


def _said_day(day: dt.date, language: str) -> str:
    return format_date(day, "medium", locale=babel_locale(language))


def _said_time(at: dt.time, language: str) -> str:
    return format_time(at.replace(tzinfo=None), "short", locale=babel_locale(language))


def _said_hours(start: dt.time, end: dt.time, language: str) -> str:
    return f"{_said_time(start, language)}–{_said_time(end, language)}"


def _named(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def reservation_label(reservation: Reservation, language: str) -> str:
    """As the book's dialogs say a reservation before a step: its guest (her phone when she booked herself
    without a name; nothing once her data were erased), its day and its time."""
    who = reservation.guest_name or reservation.guest_phone
    return _named(who, _said_day(reservation.date, language), _said_time(reservation.time, language))


def entry_label(entry: WaitlistEntry, language: str) -> str:
    """As the waitlist's dialogs say an entry: its guest, the day and the time they would like."""
    who = entry.guest_name or entry.guest_phone
    return _named(who, _said_day(entry.date, language), _said_time(entry.preferred_time, language))


def slot_label(slot: TimeSlot, language: str) -> str:
    """As the slots' list says a slot: its weekday and its hours («Jueves · 20:00–23:30»)."""
    weekday = capfirst(get_day_names("wide", locale=babel_locale(language))[slot.day_of_week])
    return _named(weekday, _said_hours(slot.start_time, slot.end_time, language))


def blocked_label(block: BlockedDate, language: str) -> str:
    """As the blocked dates' list says one: its day and, when it blocks only some hours, those hours."""
    hours = (
        ""
        if block.is_full_day
        else _said_hours(block.blocked_from, block.blocked_until, language)
    )
    return _named(_said_day(block.date, language), hours)


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    window = queryset[params.offset : params.offset + params.limit]
    return {
        "rows": [row(item) for item in window],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def _ordered(queryset, sort: str, columns: dict, tail: tuple):
    descending = sort.startswith("-")
    fields = columns[sort.lstrip("-")]
    order = [f"-{field}" if descending else field for field in fields]
    return queryset.order_by(*order, *tail)


def _phone_matches(said: str) -> Q:
    """Part of the guest's phone, as typed or by its digits alone (spaces, dashes, a prefix)."""
    text = said.strip()
    match = Q(guest_phone__icontains=text)
    digits = DIGITS.sub("", text)
    if len(digits) >= 3:
        match |= Q(guest_phone__icontains=digits)
    return match


def _guest_matches(said: str) -> Q:
    """The guest by part of the name, the email or the phone (however typed: spaces, prefix)."""
    text = said.strip()
    return Q(guest_name__icontains=text) | Q(guest_email__icontains=text) | _phone_matches(text)


def _hhmm(field: str) -> Func:
    """A time column as ``HH:MM`` text, to filter it by part of what the screen shows («21»)."""
    return Func(F(field), Value("HH24:MI"), function="to_char", output_field=CharField())


def _when(day: dt.date, at: dt.time) -> str:
    return f"{day:%Y-%m-%d} {at:%H:%M}"


# ── Lookups shared with services.py ──────────────────────────────────────────────────────────────


def find_reservation(
    reservation_id: UUID | None,
    guest: str | None,
    day: dt.date | None,
    *,
    lock: bool = False,
) -> Reservation:
    """A live reservation by id or, as a person says it, by its guest's name or phone and its day (the
    coming ones when no day is said; among several, the open ones)."""
    rows = reservations()
    if reservation_id is None:
        named = rows.filter(_guest_matches(guest or ""))
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
    entry_id: UUID | None, guest: str | None, day: dt.date | None, *, lock: bool = False
) -> WaitlistEntry:
    """A live waitlist entry by id or by its guest (and day); among several, the ones still waiting."""
    rows = waiting_entries()
    if entry_id is None:
        named = rows.filter(_guest_matches(guest or ""))
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


# ── What the gate reads ──────────────────────────────────────────────────────────────────────────


def counted(day: dt.date, exclude: tuple = ()) -> QuerySet[Reservation]:
    """The reservations a day's slots count: live, not cancelled nor a no-show."""
    return (
        Reservation.objects.filter(is_deleted=False, date=day)
        .exclude(status__in=UNCOUNTED)
        .exclude(pk__in=exclude)
    )


def slots_of(day: dt.date, exclude: tuple = ()) -> list[engine.Slot]:
    """The slots of ``day``'s weekday, by start, with the reservations and guests they hold that day."""
    taken = list(counted(day, exclude).values("time", "party_size"))
    out = []
    for slot in TimeSlot.objects.filter(
        is_deleted=False, day_of_week=day.weekday()
    ).order_by("start_time", "id"):
        inside = [
            row for row in taken if slot.start_time <= row["time"] < slot.end_time
        ]
        out.append(
            engine.Slot(
                id=slot.pk,
                start=slot.start_time,
                end=slot.end_time,
                max_reservations=slot.max_reservations,
                max_covers=slot.max_covers,
                reserved=len(inside),
                covers=sum(row["party_size"] for row in inside),
            )
        )
    return out


def blocks_of(day: dt.date) -> list[BlockedDate]:
    return list(
        BlockedDate.objects.filter(is_deleted=False, date=day).order_by(
            "blocked_from", "id"
        )
    )


def engine_blocks(blocks: list[BlockedDate]) -> tuple[engine.Block, ...]:
    return tuple(
        engine.Block(block.is_full_day, block.blocked_from, block.blocked_until)
        for block in blocks
    )


def reader(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the business's hours (booking needs no right in Schedules)."""
    return replace(ctx, permissions=ctx.permissions | {"schedule.view"})


def hours_of(ctx: OperationContext, day: dt.date) -> engine.Hours:
    """The business's opening spans of ``day`` and of its eve (past midnight), from Schedules.

    What governs a day: a special day or a temporary change always; the usual week only once the
    business saved or confirmed it — the default week Schedules ships with (Monday to Friday, 09:00 to
    18:00) is a suggestion, and would turn away every dinner of a restaurant that never opened Schedules.
    """
    confirmed = get_week(reader(ctx), NoParamsIn()).confirmed
    answer = hours_for_range(
        reader(ctx), HoursRangeIn(date_from=day - dt.timedelta(days=1), date_to=day)
    )

    def governs(entry) -> bool:
        return entry.source in EXCEPTIONS or (entry.source == "weekly" and confirmed)

    governed = [entry for entry in answer.days if governs(entry)]
    spans = [(span.start, span.end) for entry in governed for span in entry.spans]
    return engine.Hours(
        restricted=any(entry.date == day for entry in governed), spans=tuple(spans)
    )


def in_service(table: Table) -> bool:
    """A table may be booked: in use, not deleted, not blocked, and its zone (if any) in use."""
    if table.is_deleted or not table.is_active or table.blocked:
        return False
    return table.zone_id is None or (table.zone.is_active and not table.zone.is_deleted)


def booked_windows(
    table_id: UUID, window: engine.Window, exclude: tuple = ()
) -> list[tuple[Reservation, engine.Window]]:
    """The live reservations holding ``table_id`` around ``window`` (the days it touches and their
    neighbours), each with its window."""
    first = wall_clock(window.start).date()
    days = {first + dt.timedelta(days=offset) for offset in (-1, 0, 1)} | {
        wall_clock(window.end).date()
    }
    rows = (
        Reservation.objects.filter(
            is_deleted=False, table_id=table_id, status__in=HOLDING, date__in=days
        )
        .exclude(pk__in=exclude)
        .order_by("date", "time", "id")
    )
    out = []
    for row in rows:
        theirs = window_of(row.date, row.time, row.duration_minutes)
        if theirs.overlaps(window):
            out.append((row, theirs))
    return out


def table_facts(
    table: Table, window: engine.Window, exclude: tuple = ()
) -> engine.TableFacts:
    return engine.TableFacts(
        label=table_label(table),
        in_service=in_service(table),
        booked=tuple(theirs for _, theirs in booked_windows(table.pk, window, exclude)),
    )


# ── Operations ───────────────────────────────────────────────────────────────────────────────────


RESERVATION_SORTS = {
    "starts_at": ("date", "time"),
    "time": ("time", "date"),
    "guest_name": ("guest_name",),
    "guest_phone": ("guest_phone",),
    "party_size": ("party_size",),
    "table": ("table__number",),
    "status": ("status",),
    "created_at": ("created_at",),
}


@operation(
    "reservation.reservation.list",
    kind="query",
    permission="reservation.view_reservation",
    input=ReservationListIn,
    output=ReservationPage,
    expose_api=True,
    ai={
        "description": "Lists reservations: of some days (date_from, date_to) or, with `search` (a guest's name, phone "
        "or email), of the whole book; filters by status, table, customer, party size and time; in calendar order by "
        "default; pages of up to 100."
    },
)
def list_reservations(ctx: OperationContext, params: ReservationListIn) -> dict:
    rows = reservations()
    if params.search:
        rows = rows.filter(_guest_matches(params.search))
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.status:
        rows = rows.filter(status=params.status)
    if params.table_id:
        rows = rows.filter(table_id=params.table_id)
    if params.customer_id:
        rows = rows.filter(customer_id=params.customer_id)
    if params.guest_name:
        rows = rows.filter(guest_name__icontains=params.guest_name)
    if params.guest_phone:
        rows = rows.filter(_phone_matches(params.guest_phone))
    if params.time:
        rows = rows.annotate(time_text=_hhmm("time")).filter(
            time_text__contains=params.time
        )
    if params.party_size_from:
        rows = rows.filter(party_size__gte=params.party_size_from)
    if params.party_size_to:
        rows = rows.filter(party_size__lte=params.party_size_to)
    return _page(
        _ordered(rows, params.sort, RESERVATION_SORTS, ("id",)),
        params,
        lambda reservation: reservation_out(ctx, reservation),
    )


@operation(
    "reservation.reservation.get",
    kind="query",
    permission="reservation.view_reservation",
    input=ReservationRefIn,
    output=ReservationDetailOut,
    expose_api=True,
    ai={
        "description": "Reads one reservation with all its detail: by id, or by its guest's name or phone and its day "
        "(«Ana's reservation tomorrow»); without a day, her coming ones."
    },
)
def get_reservation(ctx: OperationContext, params: ReservationRefIn) -> dict:
    found = find_reservation(params.id, params.guest, params.day)
    return {**reservation_out(ctx, found), "label": reservation_label(found, ctx.language)}


@operation(
    "reservation.availability.day",
    kind="query",
    permission="reservation.view_reservation",
    input=DayIn,
    output=DayOut,
    expose_api=True,
    ai={
        "description": "How a service day looks (today if no date): its covers and reservations, whether it is blocked, "
        "the business's opening hours, and each slot with its reservations, guests, maximum and what is left (full or "
        "not, inside the opening hours or not). Counts exactly what booking checks."
    },
)
def day_availability(ctx: OperationContext, params: DayIn) -> dict:
    today = business_now().date()
    day = params.date or today
    blocks = blocks_of(day)
    hours = hours_of(ctx, day)
    slots = slots_of(day)
    totals = counted(day).aggregate(reservations=Count("id"), covers=Sum("party_size"))
    return {
        "date": day,
        "today": today,
        "timezone": zone_name(),
        "closed": any(block.is_full_day for block in blocks),
        "blocks": [blocked_out(block) for block in blocks],
        "hours_restricted": hours.restricted,
        "spans": [
            {"start": start, "end": end}
            for start, end in hours.spans
            if end > dt.datetime.combine(day, dt.time.min) and start.date() <= day
        ],
        "slots": [
            {
                "id": slot.id,
                "start_time": slot.start,
                "end_time": slot.end,
                "max_reservations": slot.max_reservations,
                "max_covers": slot.max_covers,
                "reserved": slot.reserved,
                "covers": slot.covers,
                "available": slot.available,
                "full": slot.full,
                "in_hours": hours.open_at(dt.datetime.combine(day, slot.start)),
            }
            for slot in slots
        ],
        "reservations": totals["reservations"] or 0,
        "covers": totals["covers"] or 0,
    }


@operation(
    "reservation.availability.tables",
    kind="query",
    permission="reservation.view_reservation",
    input=TablesIn,
    output=FreeTablesOut,
    expose_api=True,
    ai={
        "description": "The tables in service for a day, time and party: whether each one is free then (no live "
        "reservation overlaps the stay) and whether the party fits its seats; free and fitting first. Use it to pick "
        "the table of a reservation («is table 5 free tomorrow at 21?»)."
    },
)
def free_tables(ctx: OperationContext, params: TablesIn) -> dict:
    minutes = params.duration_minutes or current_settings().default_duration_minutes
    window = window_of(params.date, params.time, minutes)
    exclude = (params.exclude_id,) if params.exclude_id else ()
    tables = Table.objects.filter(
        is_deleted=False, is_active=True, blocked=False
    ).select_related("zone")
    tables = tables.filter(
        Q(zone__isnull=True) | Q(zone__is_active=True, zone__is_deleted=False)
    )
    if params.search:
        said = params.search.strip()
        tables = tables.filter(
            Q(number__icontains=said)
            | Q(name__icontains=said)
            | Q(zone__name__icontains=said)
        )
    out = []
    for table in tables.order_by(natural_key("number"), "id"):
        clash = booked_windows(table.pk, window, exclude)
        fits = params.party_size is None or table.capacity >= params.party_size
        out.append(
            {
                "id": table.pk,
                "number": table.number,
                "label": table_label(table),
                "zone_name": table.zone.name if table.zone_id else "",
                "capacity": table.capacity,
                "fits": fits,
                "free": not clash,
                "taken_from": wall_clock(clash[0][1].start).time() if clash else None,
                "taken_until": wall_clock(clash[0][1].end).time() if clash else None,
            }
        )
    out.sort(key=lambda row: (not row["free"], not row["fits"]))
    return {"rows": out}


SLOT_SORTS = {
    "day_of_week": ("day_of_week", "start_time"),
    "start_time": ("start_time", "day_of_week"),
    "end_time": ("end_time", "day_of_week"),
    "max_reservations": ("max_reservations",),
}


@operation(
    "reservation.time_slot.list",
    kind="query",
    permission="reservation.view_timeslot",
    input=TimeSlotListIn,
    output=TimeSlotPage,
    expose_api=True,
    ai={
        "description": "Lists the slots the book takes reservations in (weekday 0 = Monday … 6 = Sunday, from, to, "
        "maximum reservations and guests), by weekday and start."
    },
)
def list_slots(ctx: OperationContext, params: TimeSlotListIn) -> dict:
    rows = TimeSlot.objects.filter(is_deleted=False)
    if params.day_of_week is not None:
        rows = rows.filter(day_of_week=params.day_of_week)
    return _page(_ordered(rows, params.sort, SLOT_SORTS, ("id",)), params, slot_out)


@operation(
    "reservation.time_slot.get",
    kind="query",
    permission="reservation.view_timeslot",
    input=TimeSlotRefIn,
    output=TimeSlotDetailOut,
    expose_api=True,
    ai={
        "description": "Reads one slot the book takes reservations in: by id, or by its weekday (0 = Monday … 6 = "
        "Sunday) and its start."
    },
)
def get_slot(ctx: OperationContext, params: TimeSlotRefIn) -> dict:
    slot = find_slot(params.id, params.day_of_week, params.start_time)
    return {**slot_out(slot), "label": slot_label(slot, ctx.language)}


BLOCKED_SORTS = {
    "date": ("date", "blocked_from"),
    "reason": ("reason", "date"),
    "is_full_day": ("is_full_day", "date"),
}


@operation(
    "reservation.blocked_date.list",
    kind="query",
    permission="reservation.view_blockeddate",
    input=BlockedDateListIn,
    output=BlockedDatePage,
    expose_api=True,
    ai={
        "description": "Lists the days (or hours) the book takes no reservations, with their reason, by date."
    },
)
def list_blocked(ctx: OperationContext, params: BlockedDateListIn) -> dict:
    rows = BlockedDate.objects.filter(is_deleted=False)
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_full_day is not None:
        rows = rows.filter(is_full_day=params.is_full_day)
    return _page(
        _ordered(rows, params.sort, BLOCKED_SORTS, ("id",)), params, blocked_out
    )


@operation(
    "reservation.blocked_date.get",
    kind="query",
    permission="reservation.view_blockeddate",
    input=BlockedDateRefIn,
    output=BlockedDateDetailOut,
    expose_api=True,
    ai={
        "description": "Reads one blocked date (a day, or some hours of it, the book takes no reservations) with its "
        "reason: by id, or by its date when it is blocked once."
    },
)
def get_blocked(ctx: OperationContext, params: BlockedDateRefIn) -> dict:
    block = find_block(params.id, params.date)
    return {**blocked_out(block), "label": blocked_label(block, ctx.language)}


WAITLIST_SORTS = {
    "position": ("date", "preferred_time", "created_at"),
    "date": ("date", "preferred_time", "created_at"),
    "preferred_time": ("preferred_time", "date", "created_at"),
    "guest_name": ("guest_name",),
    "guest_phone": ("guest_phone",),
    "party_size": ("party_size",),
    "is_contacted": ("is_contacted", "date", "preferred_time", "created_at"),
}


@operation(
    "reservation.waitlist.list",
    kind="query",
    permission="reservation.view_waitlistentry",
    input=WaitlistListIn,
    output=WaitlistPage,
    expose_api=True,
    ai={
        "description": "Lists the waitlist in the order people were written down (day, preferred time, arrival): who, "
        "for how many, contacted or not, and converted into a reservation or still waiting."
    },
)
def list_waitlist(ctx: OperationContext, params: WaitlistListIn) -> dict:
    rows = waiting_entries()
    if params.search:
        rows = rows.filter(_guest_matches(params.search))
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_contacted is not None:
        rows = rows.filter(is_contacted=params.is_contacted)
    if params.is_converted is not None:
        rows = rows.filter(reservation__isnull=not params.is_converted)
    if params.guest_name:
        rows = rows.filter(guest_name__icontains=params.guest_name)
    if params.guest_phone:
        rows = rows.filter(_phone_matches(params.guest_phone))
    return _page(
        _ordered(rows, params.sort, WAITLIST_SORTS, ("id",)), params, entry_out
    )


@operation(
    "reservation.waitlist.get",
    kind="query",
    permission="reservation.view_waitlistentry",
    input=WaitlistRefIn,
    output=WaitlistDetailOut,
    expose_api=True,
    ai={
        "description": "Reads one waitlist entry: by id, or by its guest's name or phone (and its day, when they wait "
        "for several); among several, the ones still waiting."
    },
)
def get_entry(ctx: OperationContext, params: WaitlistRefIn) -> dict:
    entry = find_entry(params.id, params.guest, params.day)
    return {**entry_out(entry), "label": entry_label(entry, ctx.language)}


@operation(
    "reservation.settings.get",
    kind="query",
    permission="reservation.view_settings",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Reads the book's rules: guests per reservation, notice and days ahead, default duration, "
        "automatic confirmation, phone or email required, when an unconfirmed reservation is released, and the "
        "business's time zone."
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_row(current_settings())
