"""Write operations of the reservation app: taking, changing and moving a reservation through its states,
the slots, the blocked dates, the waitlist, the rules, and the reactions to Customers.

Each one is one transaction with its events in the outbox; a refusal writes nothing and announces nothing.

- **The gate** (engine.py) is asked under a lock: every write that books (take, change, convert) first
  locks the book's settings row, so the reservations of a business go one after the other and two of them
  on the last place of a slot, or on the same table and time, leave one.
- **Tables, in the same transaction** (phase 1 has no relay): a reservation confirmed, cancelled, not shown
  or deleted calls ``table.hold.sync_reservation``; a confirmed one changed calls it again with its new
  data, or ``table.hold.move_reservation`` when it loses its table; seating calls ``table.session.open``
  with the session of whoever seats and releases with ``table.hold.release`` a hold that was not yet in its
  window. Tables' platform operations are called with only ``table.system`` added to the caller's context.
  The events of the contract (``status_changed``, ``updated``) are recorded as well, for the relay.
- **Customers**: with no card chosen and a phone, the live card with that number is used, or one is
  created, with the caller's session.
"""

import datetime as dt
import unicodedata
from dataclasses import replace
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound
from live.operations import UnknownOperation, get, operation
from live.models import OutboxEvent
from live.outbox import record_event

from apps.customer.models import Customer
from apps.customer.queries import find_customer
from apps.reservation import engine, events
from apps.reservation.models import (
    ACTOR_MAX_LENGTH,
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)
from apps.reservation.queries import (
    blocks_of,
    business_now,
    engine_blocks,
    entry_out,
    find_entry,
    find_reservation,
    hours_of,
    in_service,
    rules_of,
    blocked_out,
    reservation_out,
    settings_row,
    slot_out,
    slots_of,
    table_facts,
)
from apps.reservation.schemas import (
    BlockedDateIn,
    BlockedDateOut,
    BlockedDateRefIn,
    CancelIn,
    ChangedOut,
    ConvertedOut,
    CustomerEventIn,
    DeletedOut,
    MergedIn,
    NoIn,
    ReleasedOut,
    ReservationIn,
    ReservationOut,
    ReservationPatchIn,
    ReservationRefIn,
    SettingsIn,
    SettingsOut,
    TimeSlotIn,
    TimeSlotOut,
    TimeSlotRefIn,
    WaitlistIn,
    WaitlistOut,
    WaitlistPatchIn,
    WaitlistConvertIn,
    WaitlistRefIn,
)
from apps.table.models import Hold, Table
from apps.table.queries import find_table, live_sessions, seatable, table_label

S = Reservation.Status
#: The platform's own writes (reactions): the system has «*»; no role is given this one.
SYSTEM = "reservation.system"
#: Tables' platform operations (the holds of reservations).
TABLE_SYSTEM = "table.system"
#: The reason a reservation released unconfirmed keeps (the screen translates it).
UNCONFIRMED = "unconfirmed"

#: The steps a reservation may take: target → the statuses it may come from.
STEPS = {
    S.CONFIRMED: (S.PENDING,),
    S.SEATED: (S.PENDING, S.CONFIRMED),
    S.COMPLETED: (S.SEATED,),
    S.CANCELLED: (S.PENDING, S.CONFIRMED),
    S.NO_SHOW: (S.PENDING, S.CONFIRMED),
}
TERMINAL = (S.COMPLETED, S.CANCELLED, S.NO_SHOW)
#: What a reservation may still change once seated, completed, cancelled or not shown.
NOTES_ONLY = {"notes", "internal_notes"}

#: The gate's refusals, by code: their message and the field of the form they belong to.
REFUSALS = {
    "phone_required": (
        _("This business requires a phone number for every reservation."),
        "guest_phone",
    ),
    "email_required": (
        _("This business requires an email address for every reservation."),
        "guest_email",
    ),
    "party_size_exceeded": (
        _(
            "That party size is outside the limits of this business (%(min)s–%(max)s guests)."
        ),
        "party_size",
    ),
    "in_past": (_("That time has already passed."), "time"),
    "too_soon": (
        _("Reservations have to be made at least %(hours)s h in advance."),
        "time",
    ),
    "too_far": (_("Reservations are taken up to %(days)s days ahead."), "date"),
    "date_blocked": (
        _("That date is blocked (holiday or closure): no reservations are taken then."),
        "date",
    ),
    "outside_schedule": (_("The business is closed at that time."), "time"),
    "no_service_day": (
        _("There is no service at that time: no time slot covers it."),
        "time",
    ),
    "no_capacity": (_("That time slot is fully booked for that date."), "time"),
    "table_unavailable": (
        _("Table %(table)s cannot be booked: it is blocked or out of service."),
        "table_id",
    ),
    "table_taken": (
        _("Table %(table)s already has a reservation from %(start)s to %(end)s."),
        "table_id",
    ),
}
OVERBOOK_HINT = _("Send overbook as true to book this full slot anyway.")
STATUS_FINAL = _("This reservation is %(status)s: its status can no longer change.")
COMPLETE_BEFORE_SEAT = _(
    "This reservation is %(status)s: it cannot be completed before it is seated."
)
STEP_REFUSED = _("This reservation is %(status)s: it cannot be %(target)s.")
#: The verbs of each step, as the refusal says them («it cannot be confirmed»).
TARGET_WORDS = {
    S.CONFIRMED: pgettext_lazy("reservation step", "confirmed"),
    S.SEATED: pgettext_lazy("reservation step", "seated"),
    S.COMPLETED: pgettext_lazy("reservation step", "completed"),
    S.CANCELLED: pgettext_lazy("reservation step", "cancelled"),
    S.NO_SHOW: pgettext_lazy("reservation step", "marked a no-show"),
}
NOT_EDITABLE = _("This reservation can no longer change: only its notes.")
ENTRY_CONVERTED = _("This entry was already converted into a reservation.")
SLOT_OVERLAPS = _("That slot overlaps another one of the same day (%(start)s–%(end)s).")
SLOT_NOT_FOUND = _("That time slot does not exist in this business.")
BLOCK_EXISTS = _("That date is already blocked at that time.")
BLOCK_NOT_FOUND = _("That blocked date does not exist in this business.")
BLOCK_AMBIGUOUS = _("That date is blocked at several times: say which one by its id.")
MIN_ABOVE_MAX = _("The minimum guests cannot be more than the maximum.")
TABLE_NOT_FREE = _(
    "Table %(table)s is taken right now: free it, or move the reservation to another table before seating it."
)
TABLES_UNAVAILABLE = _(
    "Tables is not available in this business: the reservation's table cannot be held or seated."
)


# ── Who acts ─────────────────────────────────────────────────────────────────────────────────────


def actor_label(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:ACTOR_MAX_LENGTH]


def _stamp(row, ctx: OperationContext, *, created: bool = False) -> None:
    row.updated_by = actor_label(ctx)
    if created:
        row.created_by = row.updated_by


# ── Other apps, by their operations ──────────────────────────────────────────────────────────────


def call_app(ctx: OperationContext, name: str, data: dict) -> Any:
    """Runs another app's operation ``name`` with ``ctx``, in this transaction."""
    try:
        op = get(name)
    except UnknownOperation:
        raise Conflict(
            str(TABLES_UNAVAILABLE), code="reservation.tables_unavailable"
        ) from None
    try:
        return op(ctx, op.input.model_validate(data))
    except AppInactive:
        raise Conflict(
            str(TABLES_UNAVAILABLE), code="reservation.tables_unavailable"
        ) from None


def table_system(ctx: OperationContext) -> OperationContext:
    """``ctx`` with Tables' platform permission added, for the holds of reservations only."""
    return replace(ctx, permissions=ctx.permissions | {TABLE_SYSTEM})


def contract(reservation: Reservation, status: str) -> dict:
    """The reservation as Tables reads it (TABLE-F25–F27): the payload of ``status_changed``."""
    return {
        "id": str(reservation.pk),
        "status": status,
        "table_id": str(reservation.table_id) if reservation.table_id else None,
        "date": reservation.date.isoformat(),
        "time": f"{reservation.time:%H:%M}",
        "duration_minutes": reservation.duration_minutes,
        "party_size": reservation.party_size,
        "guest_name": reservation.guest_name,
        "customer_id": str(reservation.customer_id)
        if reservation.customer_id
        else None,
    }


def sync_hold(ctx: OperationContext, reservation: Reservation, status: str) -> None:
    """Tables holds, moves or releases the reservation's table (only when it has one)."""
    if reservation.table_id is not None:
        call_app(
            table_system(ctx),
            "table.hold.sync_reservation",
            contract(reservation, status),
        )


def drop_hold(ctx: OperationContext, reservation: Reservation) -> None:
    """A confirmed reservation left without a table: Tables releases its hold."""
    call_app(
        table_system(ctx),
        "table.hold.move_reservation",
        {"id": str(reservation.pk), "table_id": None},
    )


def status_changed(
    ctx: OperationContext,
    reservation: Reservation,
    previous: str | None,
    status: str | None = None,
) -> None:
    record_event(
        ctx,
        events.RESERVATION_STATUS_CHANGED,
        {
            **contract(reservation, status or reservation.status),
            "previous_status": previous,
        },
    )


# ── The gate ─────────────────────────────────────────────────────────────────────────────────────


def lock_book() -> Settings:
    """The book's settings row, locked until the end of the transaction: every write that books waits
    here for the one before it (created the first time, with its factory rules)."""
    Settings.objects.get_or_create(singleton=True)
    return Settings.objects.select_for_update().get(singleton=True)


def refuse(refusal: engine.Refusal) -> Conflict:
    """The refusal as the 409 the form, the API and the assistant read: its message on its field and, when
    the staff may book it anyway (a full slot), the input that does it (`overbook`)."""
    message, field = REFUSALS[refusal.code]
    params = {key: value for key, value in refusal.params.items() if key != "overbook"}
    text = str(message) % params if params else str(message)
    fields = {field: text}
    if refusal.params.get("overbook"):
        fields["overbook"] = str(OVERBOOK_HINT)
    return Conflict(text, code=f"reservation.{refusal.code}", fields=fields)


def judge(
    ctx: OperationContext,
    settings: Settings,
    request: engine.Request,
    table: Table | None,
    exclude: tuple = (),
) -> None:
    """Raises the first reason that refuses ``request`` (engine.verdict), with what the gate reads."""
    window = request.window
    verdict = engine.verdict(
        request,
        rules=rules_of(settings),
        now=business_now(),
        blocks=engine_blocks(blocks_of(request.date)),
        hours=hours_of(ctx, request.date),
        slots=slots_of(request.date, exclude),
        table=table_facts(table, window, exclude) if table is not None else None,
    )
    if verdict is not None:
        raise refuse(verdict)


def choose_table(table_id, said: str | None, zone: str | None) -> Table | None:
    if table_id is None and not said:
        return None
    return find_table(table_id, said, zone)


# ── The guest's card ─────────────────────────────────────────────────────────────────────────────


def _folded(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in plain if not unicodedata.combining(char)).strip()


#: Where a card made from a reservation comes from, as Customers names it.
CARD_SOURCES = {"phone": "phone", "in_person": "walk_in", "whatsapp": "whatsapp", "online": "website"}


def chosen_card(customer_id, customer_said: str | None) -> Customer | None:
    """The card the caller chose (by id, or by name, phone or email), or ``None``."""
    if customer_id is None and not customer_said:
        return None
    return find_customer(customer_id, customer_said)


def card_for_phone(
    ctx: OperationContext, name: str, phone: str, email: str, source: str
) -> Customer:
    """The live card with ``phone`` (among several, the one with ``name``, case and accents ignored; else
    the first) or a new one with the guest's name, phone and email, made by Customers."""
    matches = call_app(ctx, "customer.customer.by_phone", {"phone": phone}).rows
    if matches:
        wanted = _folded(name)
        match = next(
            (row for row in matches if _folded(row.name) == wanted), matches[0]
        )
        return Customer.objects.get(pk=match.id)
    try:
        created = call_app(
            ctx,
            "customer.customer.create",
            {"name": name, "phone": phone, "email": email, "source": source},
        )
    except InvalidPayload as error:
        fields = {f"guest_{key}": text for key, text in (error.fields or {}).items()}
        raise InvalidPayload(error.message, fields=fields or None) from None
    return Customer.objects.get(pk=created.id)


# ── Reservations ─────────────────────────────────────────────────────────────────────────────────


def _loaded(reservation: Reservation) -> dict:
    """The reservation's row, read again with its table and its waitlist entry."""
    return reservation_out(
        Reservation.objects.select_related("table__zone").get(pk=reservation.pk)
    )


@operation(
    "reservation.reservation.create",
    kind="command",
    permission="reservation.add_reservation",
    input=ReservationIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Takes a reservation («a table for 4 tomorrow at 21:00 for Ana, phone 600 111 222, table 5»): "
        "the guest's customer card (by id, name or phone; with only a name and phone, the card with that phone or a new "
        "one), the day, time and guests, optionally the table, duration, source and notes. It must pass the book's gate "
        "(guests, time, blocked days, opening hours, a slot with room, a free table); it is born pending, or confirmed "
        "when the book confirms by itself, which holds its table.",
        "risk": "normal",
    },
)
def create_reservation(ctx: OperationContext, data: ReservationIn) -> dict:
    settings = lock_book()
    card = chosen_card(data.customer_id, data.customer)
    name = data.guest_name or (card.name if card else "")
    phone = data.guest_phone or (card.phone if card else "")
    email = data.guest_email or (card.email if card else "")
    table = choose_table(data.table_id, data.table, data.zone)
    minutes = data.duration_minutes or settings.default_duration_minutes
    # The card before the gate: a phone Customers refuses is said first, never after «Book anyway?». A
    # refusal of the gate rolls the new card back with everything else.
    if card is None and phone:
        card = card_for_phone(ctx, name, phone, email, CARD_SOURCES[data.source])
        phone = card.phone or phone
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
    return _loaded(reservation)


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
    permission="reservation.change_reservation",
    input=ReservationPatchIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Changes a reservation (by id, or by its guest and day): its day, time, guests, duration, table "
        "(or `no_table` to leave it without one), the guest's name, phone or email, or its notes. Only what is sent "
        "changes; the change passes the same gate as booking. A confirmed reservation moves its hold on the floor plan. "
        "Once seated, completed, cancelled or not shown, only its notes change.",
        "risk": "normal",
    },
)
def update_reservation(ctx: OperationContext, data: ReservationPatchIn) -> dict:
    settings = lock_book()
    reservation = find_reservation(data.id, data.guest, data.day, lock=True)
    sent = data.model_fields_set - {"id", "guest", "day", "zone"}
    changes: dict[str, Any] = {
        field: getattr(data, field)
        for field in (*SLOT_FIELDS, *CONTACT_FIELDS, "notes", "internal_notes")
        if field in sent and getattr(data, field) is not None
    }
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
            source=reservation.source,
            check_when=bool({"date", "time"} & set(changes)),
            overbook=data.overbook,
        )
        judge(ctx, settings, request, new_table, exclude=(reservation.pk,))
    if not changes and not table_changed:
        return _loaded(reservation)
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
    return _loaded(reservation)


def step(ctx: OperationContext, reservation: Reservation, target: str) -> str:
    """Moves ``reservation`` to ``target`` if it may (stamping the time), else the readable refusal."""
    current = reservation.status
    if current not in STEPS[target]:
        label = str(Reservation.Status(current).label).lower()
        if current in TERMINAL:
            message = str(STATUS_FINAL) % {"status": label}
        elif target == S.COMPLETED:
            message = str(COMPLETE_BEFORE_SEAT) % {"status": label}
        else:
            message = str(STEP_REFUSED) % {
                "status": label,
                "target": TARGET_WORDS[target],
            }
        raise Conflict(message, code="reservation.illegal_transition")
    now = timezone.now()
    reservation.status = target
    stamp_field = {
        S.CONFIRMED: "confirmed_at",
        S.SEATED: "seated_at",
        S.COMPLETED: "completed_at",
        S.CANCELLED: "cancelled_at",
        S.NO_SHOW: "no_show_at",
    }[target]
    setattr(reservation, stamp_field, now)
    _stamp(reservation, ctx)
    return current


def held_table(reservation: Reservation) -> None:
    """A reservation confirmed with a table holds it: a table out of service (blocked, out of use, deleted,
    or in a zone out of use) would hold nothing (TABLE-F25), so it is refused."""
    if reservation.table_id is None:
        return
    table = Table.objects.select_related("zone").get(pk=reservation.table_id)
    if not in_service(table):
        raise refuse(engine.Refusal("table_unavailable", {"table": table_label(table)}))


def _named(data: ReservationRefIn) -> Reservation:
    return find_reservation(data.id, data.guest, data.day, lock=True)


@operation(
    "reservation.reservation.confirm",
    kind="command",
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Confirms a pending reservation (by id, or by its guest and day). With a table, the floor plan "
        "shows it Reserved from an hour before.",
        "risk": "normal",
    },
)
def confirm_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(data)
    held_table(reservation)
    previous = step(ctx, reservation, S.CONFIRMED)
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.CONFIRMED)
    return _loaded(reservation)


@operation(
    "reservation.reservation.seat",
    kind="command",
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Seats a pending or confirmed reservation when the party arrives (by id, or by its guest and "
        "day). If its table is free, the party is seated there in Tables with its guests and customer: the table's "
        "check opens in Sales. A table that is taken is refused (free it or move the reservation first), unless "
        "this party was already seated at it from the floor plan: then only the reservation is marked.",
        "risk": "normal",
    },
)
def seat_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(data)
    previous = step(ctx, reservation, S.SEATED)
    if reservation.table_id is not None:
        reservation.table_session_id = seat_at_table(ctx, reservation)
    reservation.save()
    status_changed(ctx, reservation, previous)
    return _loaded(reservation)


def seat_at_table(ctx: OperationContext, reservation: Reservation):
    """Seats the party at its table in Tables (its check opens in Sales); the id of the table's check.

    Market (duda 3): one gesture seats the reservation and the table; a table out of service is refused,
    and so is one that is taken, to be freed or the reservation moved — unless this very reservation's
    hold was already spent by seating its table from the floor plan (TABLE-F28) and no other reservation
    owns the check sitting there: then the party is there, and its check is the table's. Tables spends
    every hold of the table inside the hour when anybody sits, so a spent hold alone proves nothing: the
    party of another reservation seated there earlier also spends it (WORKBOOK «Lo que queda fuera»).
    """
    now = timezone.now()
    table = Table.objects.select_related("zone").get(pk=reservation.table_id)
    if not in_service(table):
        raise refuse(engine.Refusal("table_unavailable", {"table": table_label(table)}))
    holds = Hold.objects.filter(source=Hold.Source.RESERVATION, source_ref=str(reservation.pk))
    if not seatable(table, now):
        sitting = live_sessions().filter(table=table).order_by("opened_at", "id").first()
        owned = (
            sitting is not None
            and Reservation.objects.filter(table_session_id=sitting.pk, is_deleted=False)
            .exclude(pk=reservation.pk)
            .exists()
        )
        if sitting is not None and not owned and holds.filter(status=Hold.Status.CONSUMED).exists():
            return sitting.pk
        text = str(TABLE_NOT_FREE) % {"table": table_label(table)}
        raise Conflict(text, code="reservation.table_not_free")
    seat = {"table_id": str(table.pk), "guests_count": reservation.party_size}
    if reservation.customer_id and Customer.objects.live().filter(pk=reservation.customer_id).exists():
        seat["customer_id"] = str(reservation.customer_id)
    session_id = call_app(ctx, "table.session.open", seat).id
    if holds.filter(status=Hold.Status.HELD).exists():
        # Seated before its hold's window (more than an hour early): it would paint the table later.
        call_app(ctx, "table.hold.release", {"source": "reservation", "source_ref": str(reservation.pk)})
    return session_id


@operation(
    "reservation.reservation.complete",
    kind="command",
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Completes a seated reservation when the party leaves (by id, or by its guest and day).",
        "risk": "normal",
    },
)
def complete_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(data)
    previous = step(ctx, reservation, S.COMPLETED)
    reservation.save()
    status_changed(ctx, reservation, previous)
    return _loaded(reservation)


@operation(
    "reservation.reservation.cancel",
    kind="command",
    permission="reservation.change_reservation",
    input=CancelIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Cancels a pending or confirmed reservation (by id, or by its guest and day), with an optional "
        "reason: its place and its table are freed. Ask first.",
        "risk": "high",
    },
)
def cancel_reservation(ctx: OperationContext, data: CancelIn) -> dict:
    reservation = _named(data)
    previous = step(ctx, reservation, S.CANCELLED)
    reservation.cancellation_reason = data.reason
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.CANCELLED)
    return _loaded(reservation)


@operation(
    "reservation.reservation.no_show",
    kind="command",
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "description": "Marks a pending or confirmed reservation as a no-show (by id, or by its guest and day): its "
        "place and its table are freed. Ask first.",
        "risk": "high",
    },
)
def no_show_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(data)
    previous = step(ctx, reservation, S.NO_SHOW)
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.NO_SHOW)
    return _loaded(reservation)


@operation(
    "reservation.reservation.delete",
    kind="command",
    permission="reservation.delete_reservation",
    input=ReservationRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Deletes a reservation from the book for good (by id, or by its guest and day); its table is "
        "freed. Cancelling keeps it with its reason: prefer it. Ask first.",
        "risk": "high",
    },
)
def delete_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(data)
    reservation.is_deleted = True
    reservation.deleted_at = timezone.now()
    _stamp(reservation, ctx)
    reservation.save()
    record_event(ctx, events.RESERVATION_DELETED, {"id": str(reservation.pk)})
    status_changed(ctx, reservation, reservation.status, status="deleted")
    sync_hold(ctx, reservation, "deleted")
    return {"id": reservation.pk}


@operation(
    "reservation.reservation.release_unconfirmed",
    kind="command",
    permission="reservation.change_reservation",
    input=NoIn,
    output=ReleasedOut,
    expose_api=True,
    ai={
        "description": "Releases the pending reservations nobody confirmed whose time passed more than the book's "
        "window (15 minutes): they are cancelled as «unconfirmed» and free their place. Runs every quarter of an hour; "
        "safe to run by hand.",
        "risk": "normal",
    },
)
def release_unconfirmed(ctx: OperationContext, data: NoIn) -> dict:
    window = dt.timedelta(minutes=lock_book().no_show_window_minutes)
    now = business_now()
    stale = [
        row
        for row in Reservation.objects.select_for_update()
        .filter(is_deleted=False, status=S.PENDING, date__lte=now.date())
        .order_by("date", "time", "id")
        if dt.datetime.combine(row.date, row.time) + window < now
    ]
    stamp = timezone.now()
    for row in stale:
        row.status, row.cancelled_at, row.cancellation_reason = (
            S.CANCELLED,
            stamp,
            UNCONFIRMED,
        )
        _stamp(row, ctx)
        row.save()
    if stale:
        record_event(
            ctx, events.RESERVATION_UNCONFIRMED_RELEASED, {"count": len(stale)}
        )
    return {"released": len(stale)}


# ── Slots ────────────────────────────────────────────────────────────────────────────────────────


@operation(
    "reservation.time_slot.create",
    kind="command",
    permission="reservation.change_timeslot",
    input=TimeSlotIn,
    output=TimeSlotOut,
    expose_api=True,
    ai={
        "description": "Creates a slot the book takes reservations in: a weekday (0 = Monday … 6 = Sunday), from and "
        "to, how many reservations fit and, optionally, how many guests. Slots of a day never overlap.",
        "risk": "normal",
    },
)
def create_slot(ctx: OperationContext, data: TimeSlotIn) -> dict:
    lock_book()
    clash = (
        TimeSlot.objects.filter(
            is_deleted=False,
            day_of_week=data.day_of_week,
            start_time__lt=data.end_time,
            end_time__gt=data.start_time,
        )
        .order_by("start_time")
        .first()
    )
    if clash is not None:
        text = str(SLOT_OVERLAPS) % {
            "start": f"{clash.start_time:%H:%M}",
            "end": f"{clash.end_time:%H:%M}",
        }
        raise Conflict(
            text, code="reservation.slot_overlaps", fields={"start_time": text}
        )
    slot = TimeSlot(**data.model_dump())
    _stamp(slot, ctx, created=True)
    slot.save()
    record_event(ctx, events.TIME_SLOT_CREATED, {"id": str(slot.pk)})
    return slot_out(slot)


@operation(
    "reservation.time_slot.delete",
    kind="command",
    permission="reservation.change_timeslot",
    input=TimeSlotRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Removes a slot (by id, or by its weekday and start): no more reservations are taken in it; the "
        "ones it had stay. Ask first.",
        "risk": "high",
    },
)
def delete_slot(ctx: OperationContext, data: TimeSlotRefIn) -> dict:
    rows = TimeSlot.objects.select_for_update().filter(is_deleted=False)
    if data.id is not None:
        rows = rows.filter(pk=data.id)
    else:
        rows = rows.filter(day_of_week=data.day_of_week, start_time=data.start_time)
    slot = rows.first()
    if slot is None:
        raise NotFound(str(SLOT_NOT_FOUND), code="reservation.slot_not_found")
    slot.is_deleted, slot.deleted_at = True, timezone.now()
    _stamp(slot, ctx)
    slot.save()
    record_event(ctx, events.TIME_SLOT_DELETED, {"id": str(slot.pk)})
    return {"id": slot.pk}


# ── Blocked dates ────────────────────────────────────────────────────────────────────────────────


@operation(
    "reservation.blocked_date.create",
    kind="command",
    permission="reservation.change_blockeddate",
    input=BlockedDateIn,
    output=BlockedDateOut,
    expose_api=True,
    ai={
        "description": "Blocks a day for reservations (a holiday, a closure, a private event), whole or only some hours "
        "(from, until). The reservations it already had stay.",
        "risk": "normal",
    },
)
def create_blocked(ctx: OperationContext, data: BlockedDateIn) -> dict:
    block = BlockedDate(
        date=data.date,
        reason=data.reason,
        is_full_day=data.is_full_day,
        blocked_from=None if data.is_full_day else data.blocked_from,
        blocked_until=None if data.is_full_day else data.blocked_until,
    )
    _stamp(block, ctx, created=True)
    try:
        with transaction.atomic():
            block.save()
    except IntegrityError:
        raise Conflict(
            str(BLOCK_EXISTS),
            code="reservation.blocked_date_exists",
            fields={"date": str(BLOCK_EXISTS)},
        ) from None
    record_event(
        ctx,
        events.BLOCKED_DATE_CREATED,
        {"id": str(block.pk), "date": block.date.isoformat()},
    )
    return blocked_out(block)


@operation(
    "reservation.blocked_date.delete",
    kind="command",
    permission="reservation.change_blockeddate",
    input=BlockedDateRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Unblocks a blocked date (by id, or by its date when it is blocked once): reservations are taken "
        "again. Ask first.",
        "risk": "high",
    },
)
def delete_blocked(ctx: OperationContext, data: BlockedDateRefIn) -> dict:
    rows = BlockedDate.objects.select_for_update().filter(is_deleted=False)
    rows = (
        rows.filter(pk=data.id) if data.id is not None else rows.filter(date=data.date)
    )
    found = list(rows[:2])
    if not found:
        raise NotFound(str(BLOCK_NOT_FOUND), code="reservation.blocked_date_not_found")
    if len(found) > 1:
        raise Conflict(str(BLOCK_AMBIGUOUS), code="reservation.blocked_date_ambiguous")
    block = found[0]
    block.is_deleted, block.deleted_at = True, timezone.now()
    _stamp(block, ctx)
    block.save()
    record_event(
        ctx,
        events.BLOCKED_DATE_DELETED,
        {"id": str(block.pk), "date": block.date.isoformat()},
    )
    return {"id": block.pk}


# ── Waitlist ─────────────────────────────────────────────────────────────────────────────────────


@operation(
    "reservation.waitlist.create",
    kind="command",
    permission="reservation.change_waitlistentry",
    input=WaitlistIn,
    output=WaitlistOut,
    expose_api=True,
    ai={
        "description": "Writes somebody on the waitlist for a day, around a time, for a number of guests: the guest's "
        "card (by id, name or phone; with a name and phone, the card with that phone or a new one).",
        "risk": "normal",
    },
)
def create_entry(ctx: OperationContext, data: WaitlistIn) -> dict:
    # No contact is required (market, duda 7): the phone is only for calling back.
    card = chosen_card(data.customer_id, data.customer)
    name = data.guest_name or (card.name if card else "")
    phone = data.guest_phone or (card.phone if card else "")
    email = data.guest_email or (card.email if card else "")
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
    permission="reservation.change_waitlistentry",
    input=WaitlistPatchIn,
    output=WaitlistOut,
    expose_api=True,
    ai={
        "description": "Marks a waitlist entry as contacted (or not) and changes its notes (by id, or by its guest).",
        "risk": "normal",
    },
)
def update_entry(ctx: OperationContext, data: WaitlistPatchIn) -> dict:
    entry = find_entry(data.id, data.guest, data.day, lock=True)
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
    permission="reservation.change_waitlistentry",
    input=WaitlistConvertIn,
    output=ConvertedOut,
    expose_api=True,
    ai={
        "description": "Turns a waitlist entry into a reservation with its own data (guest, day, preferred time, guests, "
        "notes) and the default duration. It only checks the blocked days, the opening hours and a slot with room; "
        "the entry is marked converted.",
        "risk": "normal",
    },
)
def convert_entry(ctx: OperationContext, data: WaitlistConvertIn) -> dict:
    settings = lock_book()
    entry = find_entry(data.id, data.guest, data.day, lock=True)
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
    return {"entry": entry_out(entry), "reservation": _loaded(reservation)}


@operation(
    "reservation.waitlist.delete",
    kind="command",
    permission="reservation.change_waitlistentry",
    input=WaitlistRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Takes somebody off the waitlist (by id, or by their name or phone). Ask first.",
        "risk": "high",
    },
)
def delete_entry(ctx: OperationContext, data: WaitlistRefIn) -> dict:
    entry = find_entry(data.id, data.guest, data.day, lock=True)
    entry.is_deleted, entry.deleted_at = True, timezone.now()
    _stamp(entry, ctx)
    entry.save()
    record_event(ctx, events.WAITLIST_DELETED, {"id": str(entry.pk)})
    return {"id": entry.pk}


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


@operation(
    "reservation.settings.update",
    kind="command",
    permission="reservation.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Changes the book's rules: fewest and most guests, notice for online and WhatsApp, days ahead, "
        "default duration, automatic confirmation, phone or email required, and the minutes after which an unconfirmed "
        "reservation is released. Only what is sent changes.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    settings = lock_book()
    changes = {
        field: value for field, value in data.model_dump(exclude_none=True).items()
    }
    for field, value in changes.items():
        setattr(settings, field, value)
    if settings.min_party_size > settings.max_party_size:
        raise InvalidPayload(
            str(MIN_ABOVE_MAX), fields={"min_party_size": str(MIN_ABOVE_MAX)}
        )
    if changes:
        settings.updated_by = actor_label(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)


# ── Reactions to Customers ───────────────────────────────────────────────────────────────────────


@operation(
    "reservation.customer.reassign",
    kind="command",
    permission=SYSTEM,
    input=MergedIn,
    output=ChangedOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's reservations and waitlist "
        "entries move to the card that stays (the names they were booked with do not change).",
        "risk": "normal",
    },
)
def reassign_customer(ctx: OperationContext, data: MergedIn) -> dict:
    if data.id is None or data.absorbed_id is None or data.id == data.absorbed_id:
        return {"changed": 0}
    moved = Reservation.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    moved += WaitlistEntry.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    if moved:
        record_event(
            ctx,
            events.CUSTOMER_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"changed": moved}


#: The events of the contract with Tables that carry the guest's name (the hold's label).
NAMED_EVENTS = (events.RESERVATION_STATUS_CHANGED, events.RESERVATION_UPDATED)


def forget_names_announced(customer_id) -> int:
    """Empties the guest's name in the events her reservations announced (`status_changed`, `updated`, the
    payload Tables reads): the outbox keeps them, and her erasure must reach them too. How many changed."""
    ids = [str(pk) for pk in Reservation.objects.filter(customer_id=customer_id).values_list("pk", flat=True)]
    if not ids:
        return 0
    named = OutboxEvent.objects.filter(name__in=NAMED_EVENTS, payload__id__in=ids, payload__has_key="guest_name")
    redacted = []
    for event in named:
        if event.payload.get("guest_name"):
            event.payload = {**event.payload, "guest_name": ""}
            redacted.append(event)
    OutboxEvent.objects.bulk_update(redacted, ["payload"])
    return len(redacted)


@operation(
    "reservation.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ChangedOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's name, phone, email, notes and "
        "cancellation reasons are emptied in her reservations and waitlist entries (deleted ones too); the bookings "
        "themselves stay.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    if data.id is None:
        return {"changed": 0}
    changed = forget_names_announced(data.id)
    changed += (
        Reservation.objects.filter(customer_id=data.id)
        .exclude(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            internal_notes="",
            cancellation_reason="",
        )
        .update(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            internal_notes="",
            cancellation_reason="",
            updated_at=timezone.now(),
        )
    )
    changed += (
        WaitlistEntry.objects.filter(customer_id=data.id)
        .exclude(guest_name="", guest_phone="", guest_email="", notes="")
        .update(
            guest_name="",
            guest_phone="",
            guest_email="",
            notes="",
            updated_at=timezone.now(),
        )
    )
    if changed:
        record_event(ctx, events.CUSTOMER_ERASED, {"id": str(data.id)})
    return {"changed": changed}

