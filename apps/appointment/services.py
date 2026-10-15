"""Write operations of the appointment app: one operation = one transaction, with its events in the outbox.

- **Every check runs before the first write**, so a refusal leaves no trace (no row, no history line, no
  event).
- **Overlaps are decided under a lock**: booking, moving and editing lock the professional's staff record
  first (``resolve_member(lock=True)``; two of them in id order), so two bookings of the same
  professional at once wait for each other and the second one sees the first.
- **The front desk overlaps knowingly**: with overlaps allowed, a booking that touches another
  appointment of the professional is refused with 409 ``appointment.overlap_needs_confirmation`` (naming
  what it touches) until it is sent again with ``confirm_overlap``; with them off, it is
  ``appointment.slot_taken``. The customer (``online``, ``whatsapp``) and the series never overlap, and
  keep the notice and the past.
- **Charged is final**: a charged appointment is completed and is not moved, cancelled, marked a no-show
  nor deleted (void the sale first); a cancelled or no-show one is not charged.
- The platform's reactions (``SYSTEM``) are run by the outbox relay as the system; they are idempotent.
"""

import datetime as dt
from uuid import UUID

from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import (
    AppInactive,
    Conflict,
    InvalidPayload,
    NotFound,
    PermissionDenied,
)
from live.operations import UnknownOperation, get, operation
from live.outbox import record_event

from apps.appointment import engine, events
from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    Counter,
    History,
    Recurring,
    RecurringService,
    Settings,
)
from apps.appointment.queries import (
    ADD_OWN,
    APPOINTMENT_NOT_FOUND,
    BUSY,
    CHANGE_OWN,
    CUSTOMER_SOURCES,
    MOVABLE,
    SERIES_DEFAULT_WINDOW,
    blocked_out,
    business_zone,
    check_member,
    conflicts_of,
    current_settings,
    find_appointment,
    find_series,
    lines_for,
    load_agenda,
    load_detail,
    load_series,
    may_book_for,
    may_change,
    now,
    pattern_of,
    read_moment,
    resolve_services,
    settings_out,
    today,
    verdict_message,
)
from apps.appointment.schemas import (
    END_BEFORE_START,
    AppointmentCreateIn,
    AppointmentOut,
    AppointmentRefIn,
    AppointmentsOut,
    BlockedTimeCreateIn,
    BlockedTimeOut,
    BlockedTimeRefIn,
    BulkCreateIn,
    BulkDeletedOut,
    BulkDeleteIn,
    CancelIn,
    ChargeOut,
    CustomerEventIn,
    DeletedOut,
    MaterializeIn,
    MaterializeOut,
    MemberEventIn,
    MergedIn,
    ReactionOut,
    RecurringCreateIn,
    RecurringDeletedOut,
    RecurringOut,
    RecurringRefIn,
    RecurringUpdatedOut,
    RecurringUpdateIn,
    RescheduleIn,
    OrderVoidedIn,
    SaleFromAppointmentIn,
    SaleVoidedIn,
    SettingsIn,
    SettingsOut,
    UpdateIn,
)
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country, find_customer
from apps.service.models import Service
from apps.service.queries import needs_tax_setup
from apps.staff.models import Member
from apps.staff.queries import resolve_member

#: Run only by the platform (events.py): outside ``appointment.*``, so no role and no API key holds it.
SYSTEM = "system.appointment"
DELETE = "appointment.delete_appointment"
MANAGE_SCHEDULE = "appointment.manage_schedule"
MANAGE_SETTINGS = "appointment.manage_settings"
S = Appointment.Status
A = History.Action
#: The most a series books in one run (the current product's 50).
MATERIALIZE_PER_RUN = 50

CANNOT = {
    "confirm": _(
        "This appointment can no longer be confirmed: it is not pending any more."
    ),
    "start": _("This appointment cannot be started in its current state."),
    "complete": _("This appointment cannot be completed in its current state."),
    "mark_no_show": _(
        "This appointment cannot be marked as a no-show in its current state."
    ),
    "cancel": _("This appointment can no longer be cancelled in its current state."),
    "reschedule": _("This appointment can no longer be moved in its current state."),
    "delete": _(
        "This appointment cannot be deleted: it is in progress, completed or charged."
    ),
    "charge": _("A cancelled or no-show appointment is not charged."),
}
NO_SHOW_TOO_EARLY = _(
    "It is not the appointment's time yet: it cannot be marked as a no-show."
)
ALREADY_CHARGED = _("This appointment is already charged.")
CHECK_OPEN = _(
    "This appointment has a check open in the till: charge it or void it there first."
)
NEEDS_TAX_SETUP = _(
    "“%(name)s” has no tax category: set it in Services before charging."
)
SALE_UNAVAILABLE = _(
    "The till (Sales) is not active in this business: the appointment cannot be charged there."
)
OVERLAP_NEEDS_CONFIRMATION = _("This time overlaps with %(conflicts)s. Book it anyway?")
BOOK_OWN_ONLY = _("You may only book your own appointments.")
CHANGE_OWN_ONLY = _("You may only change your own appointments.")
CANCELLATION_DISABLED = _(
    "Online cancellation is not available. Please contact the business."
)
CANCELLATION_NOTICE = _(
    "This appointment can only be cancelled online %(hours)s hours ahead. Please contact the business."
)
PHONE_INVALID = _(
    "That phone is not a valid number for the business's country. Check it, or type it with its international "
    "prefix (for example +44…)."
)
PATTERN_CHANGED = _("The repeating appointment changed its pattern")
RECURRING_INACTIVE = _(
    "That repeating appointment is paused: reactivate it to book its appointments."
)
RECURRING_ENDED = _("This repeating appointment has no dates left to book.")
RECURRING_NO_STAFF = _(
    "This repeating appointment has no professional: edit it and choose who does it."
)
CALENDAR_UPSIDE_DOWN = _("The calendar has to end after it starts.")
BATCH_AT = _("%(time)s: %(reason)s")


# ── Shared steps ─────────────────────────────────────────────────────────────────────────────


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it: an account's full name, else its email, else its username."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.email or actor.get_username())[:128]
    return str(actor)[:128]


def _wall_text(moment: dt.datetime) -> str:
    return moment.astimezone(business_zone()).isoformat()


def _short(moment: dt.datetime) -> str:
    return f"{moment.astimezone(business_zone()):%d/%m %H:%M}"


def _refuse_with_open_check(appointment: Appointment) -> None:
    """A check open in the till for it (not charged yet) holds it: cancelling, a no-show or deleting it
    would leave that check charging an appointment that is gone (the market: void the check first)."""
    if appointment.order_id and not appointment.sale_id:
        raise Conflict(str(CHECK_OPEN), code="appointment.check_open")


def _event(ctx: OperationContext, name: str, appointment: Appointment, **extra) -> None:
    """An appointment's event: ids and the time, never notes nor a reason (they may hold health data)."""
    record_event(
        ctx,
        name,
        {
            "id": str(appointment.id),
            "number": appointment.number,
            "customer_id": str(appointment.customer_id),
            "staff_id": str(appointment.staff_id) if appointment.staff_id else None,
            "start": appointment.start.isoformat(),
            **extra,
        },
    )


def _history(
    ctx: OperationContext,
    appointment: Appointment,
    action: str,
    *,
    by_customer: bool = False,
    reason: str = "",
    old: dict | None = None,
    new: dict | None = None,
) -> None:
    History.objects.create(
        appointment=appointment,
        action=action,
        actor=_actor(ctx),
        by_customer=by_customer,
        reason=reason,
        old_value=old or {},
        new_value=new or {},
    )


def _lock_members(*members: Member | None) -> None:
    """Locks the staff records (in id order: two writes on the same pair never deadlock)."""
    ids = sorted({member.id for member in members if member is not None})
    if ids:
        list(
            Member.objects.select_for_update()
            .filter(pk__in=ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )


def _next_number() -> str:
    """``APT-YYYYMMDD-NNNN`` of today's business day, from its counter row (locked by the UPDATE)."""
    day = today()
    Counter.objects.bulk_create([Counter(day=day)], ignore_conflicts=True)
    Counter.objects.filter(day=day).update(last_number=F("last_number") + 1)
    number = Counter.objects.get(day=day).last_number
    return f"APT-{day:%Y%m%d}-{number:04d}"


def _refuse(code: str) -> None:
    raise Conflict(
        verdict_message(code),
        code="appointment.slot_taken" if code == "overlap" else f"appointment.{code}",
    )


def _judge(
    ctx: OperationContext,
    member: Member | None,
    start: dt.datetime,
    end: dt.datetime,
    *,
    customer: bool,
    confirm_overlap: bool,
    exclude: tuple = (),
    agenda: engine.Agenda | None = None,
) -> engine.Agenda:
    """Refuses ``[start, end)`` with its reason (409), or asks to confirm an overlap; returns the agenda read."""
    zone = business_zone()
    if agenda is None:
        agenda = load_agenda(
            ctx,
            member,
            engine.wall(start, zone).date(),
            engine.wall(end, zone).date(),
            exclude=exclude,
        )
    code = engine.verdict(agenda, start, end, now=now(), customer=customer)
    if code:
        _refuse(code)
    if member is not None and not customer and not confirm_overlap:
        touched = conflicts_of(agenda, start, end)
        if touched:
            names = ", ".join(
                f"{item['number']} {item['customer_name']} ({item['start']:%H:%M}–{item['end']:%H:%M})"
                for item in touched
            )
            raise Conflict(
                str(OVERLAP_NEEDS_CONFIRMATION) % {"conflicts": names},
                code="appointment.overlap_needs_confirmation",
            )
    return agenda


def _save_lines(appointment: Appointment, lines: list[dict]) -> None:
    AppointmentService.objects.bulk_create(
        AppointmentService(
            appointment=appointment,
            service=line["service"],
            name=line["name"],
            price=line["price"],
            duration_minutes=line["duration_minutes"],
            position=line["position"],
        )
        for line in lines
    )


def _create(
    ctx: OperationContext,
    *,
    customer,
    member: Member,
    lines: list[dict],
    start: dt.datetime,
    minutes: int,
    source: str,
    notes: str = "",
    internal_notes: str = "",
    recurring: Recurring | None = None,
    occurrence: dt.date | None = None,
    settings: Settings,
) -> Appointment:
    """Writes a booking already judged: the appointment, its lines, its history and its events."""
    by_customer = source in CUSTOMER_SOURCES
    # The customer's own booking waits for the business when it says so, or when a service of it requires
    # confirmation (Services' «requires confirmation»).
    pending = by_customer and (
        not settings.auto_confirm_online
        or any(line["service"].requires_confirmation for line in lines)
    )
    appointment = Appointment.objects.create(
        number=_next_number(),
        customer=customer,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_email=customer.email,
        staff=member,
        staff_name=member.full_name,
        start=start,
        end=start + dt.timedelta(minutes=minutes),
        duration_minutes=minutes,
        status=S.PENDING if pending else S.CONFIRMED,
        source=source,
        notes=notes,
        internal_notes=internal_notes,
        recurring=recurring,
        occurrence_date=occurrence,
        created_by=_actor(ctx),
    )
    _save_lines(appointment, lines)
    _history(
        ctx,
        appointment,
        A.CREATED,
        by_customer=by_customer,
        new={
            "customer_name": customer.name,
            "start": _wall_text(start),
            "staff": member.full_name,
        },
    )
    _event(ctx, events.APPOINTMENT_CREATED, appointment, customer_name=customer.name)
    if by_customer and not pending:
        _history(ctx, appointment, A.CONFIRMED, by_customer=True)
        _event(ctx, events.APPOINTMENT_CONFIRMED, appointment)
    return appointment


def _member_for_booking(
    ctx: OperationContext, staff_id, staff, services: list[Service]
) -> Member:
    member = resolve_member(staff_id, staff)
    if not may_book_for(ctx, member.id):
        raise PermissionDenied(str(BOOK_OWN_ONLY))
    _lock_members(member)
    check_member(member, services)
    return member


# ── Booking (F01, F18, F21) ──────────────────────────────────────────────────────────────────


@operation(
    "appointment.appointment.create",
    kind="command",
    permission=ADD_OWN,
    input=AppointmentCreateIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Book an appointment: a customer (by name, phone or email), one or more services (by name) and a "
        "professional (by name) at a wall-clock time of the business (e.g. tomorrow at 10:00 with Ana for a haircut). "
        "Names, prices and lengths are frozen from the catalog. It is refused with its reason when the business is "
        "shut, the professional does not work then or is off, the time is blocked, or too far ahead; when it overlaps "
        "another appointment of the professional, ask the person and send confirm_overlap=true to book anyway. "
        "source=online or whatsapp when the customer books herself.",
        "risk": "normal",
    },
)
def create_appointment(ctx: OperationContext, data: AppointmentCreateIn) -> dict:
    customer = find_customer(data.customer_id, data.customer)
    services = resolve_services(data.services)
    member = _member_for_booking(ctx, data.staff_id, data.staff, services)
    lines = lines_for(member, services)
    minutes = data.duration_minutes or sum(line["duration_minutes"] for line in lines)
    start = read_moment(data.start, "start")
    by_customer = data.source in CUSTOMER_SOURCES
    _judge(
        ctx,
        member,
        start,
        start + dt.timedelta(minutes=minutes),
        customer=by_customer,
        confirm_overlap=data.confirm_overlap,
    )
    appointment = _create(
        ctx,
        customer=customer,
        member=member,
        lines=lines,
        start=start,
        minutes=minutes,
        source=data.source,
        notes=data.notes,
        internal_notes=data.internal_notes,
        settings=current_settings(),
    )
    return load_detail(appointment.id)


@operation(
    "appointment.appointment.bulk_create",
    kind="command",
    permission=ADD_OWN,
    input=BulkCreateIn,
    output=AppointmentsOut,
    expose_api=True,
    ai={
        "description": "Book several times at once (1 to 50) for the same customer, services and professional (a "
        "voucher's sessions, a course). All or none: the first time that does not fit refuses the whole batch with "
        "its reason.",
        "risk": "normal",
    },
)
def bulk_create(ctx: OperationContext, data: BulkCreateIn) -> dict:
    customer = find_customer(data.customer_id, data.customer)
    services = resolve_services(data.services)
    member = _member_for_booking(ctx, data.staff_id, data.staff, services)
    lines = lines_for(member, services)
    minutes = data.duration_minutes or sum(line["duration_minutes"] for line in lines)
    starts = sorted(read_moment(value, "starts") for value in data.starts)
    zone = business_zone()
    agenda = load_agenda(
        ctx,
        member,
        engine.wall(starts[0], zone).date(),
        engine.wall(starts[-1] + dt.timedelta(minutes=minutes), zone).date(),
    )
    settings = current_settings()
    created = []
    for start in starts:
        end = start + dt.timedelta(minutes=minutes)
        try:
            _judge(
                ctx,
                member,
                start,
                end,
                customer=False,
                confirm_overlap=data.confirm_overlap,
                agenda=agenda,
            )
        except Conflict as refusal:
            raise Conflict(
                str(BATCH_AT) % {"time": _short(start), "reason": refusal.message},
                code=refusal.code,
            ) from None
        appointment = _create(
            ctx,
            customer=customer,
            member=member,
            lines=lines,
            start=start,
            minutes=minutes,
            source=Appointment.Source.COUNTER,
            notes=data.notes,
            settings=settings,
        )
        agenda = engine.Agenda(
            agenda.zone,
            agenda.rules,
            agenda.business,
            agenda.staff,
            agenda.blocks,
            [
                *agenda.busy,
                engine.Period(start, end, id=appointment.id, label=appointment.number),
            ],
        )
        created.append(appointment.id)
    return {"rows": [load_detail(appointment_id) for appointment_id in created]}


# ── Moving and editing (F04, F06, F22) ───────────────────────────────────────────────────────


def _acting_for_customer(ctx: OperationContext, appointment: Appointment, data) -> bool:
    """Whether the customer asked. For her, the appointment must be hers (else «does not exist»); either
    way whoever writes it down may change it (acting for her never widens their own permissions)."""
    by_customer = bool(data.on_behalf_of_customer)
    if by_customer:
        asking = find_customer(data.customer_id, data.customer)
        if asking.id != appointment.customer_id:
            raise NotFound(
                str(APPOINTMENT_NOT_FOUND), code="appointment.appointment_not_found"
            )
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    return by_customer


def _move(
    ctx: OperationContext,
    appointment: Appointment,
    *,
    start: dt.datetime | None,
    minutes: int | None,
    staff_id: UUID | None,
    staff: str | None,
    service_refs,
    by_customer: bool,
    reason: str,
    confirm_overlap: bool,
    strict: bool = False,
) -> bool:
    """Moves ``appointment`` (time, length, professional, services) after judging it; whether anything changed.

    ``by_customer``: the customer asked (her history mark, the notice). ``strict``: judged as the customer
    would be without being her (a series edit: the notice applies and nothing overlaps).
    """
    if appointment.status not in MOVABLE or appointment.sale_id:
        raise Conflict(str(CANNOT["reschedule"]), code="appointment.cannot_reschedule")
    current = list(
        appointment.lines.select_related("service").order_by("position", "id")
    )
    old_member = appointment.staff
    member = resolve_member(staff_id, staff) if (staff_id or staff) else old_member
    services = (
        resolve_services(service_refs)
        if service_refs
        else [line.service for line in current]
    )
    handed = member is not None and member != old_member
    if handed and not may_change(ctx, member.id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    _lock_members(old_member, member)
    if member is not None and (handed or service_refs):
        check_member(member, services)
    new_lines = lines_for(member, services) if service_refs else None
    explicit_minutes = minutes is not None
    if minutes is None:
        minutes = (
            sum(line["duration_minutes"] for line in new_lines)
            if new_lines
            else appointment.duration_minutes
        )
    new_start = start or appointment.start
    new_end = new_start + dt.timedelta(minutes=minutes)
    _judge(
        ctx,
        member,
        new_start,
        new_end,
        customer=by_customer or strict,
        confirm_overlap=confirm_overlap,
        exclude=(appointment.id,),
    )
    changes = []
    # A new length that only follows new services is the services' change, not a move.
    lengthened = explicit_minutes and minutes != appointment.duration_minutes
    if new_start != appointment.start or lengthened:
        changes.append(
            (
                A.RESCHEDULED,
                {
                    "start": _wall_text(appointment.start),
                    "duration_minutes": appointment.duration_minutes,
                },
                {"start": _wall_text(new_start), "duration_minutes": minutes},
            )
        )
    if handed:
        changes.append(
            (
                A.STAFF_CHANGED,
                {"staff": appointment.staff_name},
                {"staff": member.full_name},
            )
        )
    if new_lines is not None:
        before = [(line.service_id, line.name, line.price) for line in current]
        after = [
            (line["service"].id, line["name"], line["price"]) for line in new_lines
        ]
        if before != after:
            changes.append(
                (
                    A.SERVICE_CHANGED,
                    {"services": [line.name for line in current]},
                    {
                        "services": [line["name"] for line in new_lines],
                        "duration_minutes": minutes,
                    },
                )
            )
            appointment.lines.all().delete()
            _save_lines(appointment, new_lines)
    if not changes:
        return False
    appointment.start, appointment.end, appointment.duration_minutes = (
        new_start,
        new_end,
        minutes,
    )
    if handed:
        appointment.staff, appointment.staff_name = member, member.full_name
    appointment.updated_by = _actor(ctx)
    appointment.save()
    for action, old, new in changes:
        _history(
            ctx,
            appointment,
            action,
            by_customer=by_customer,
            reason=reason,
            old=old,
            new=new,
        )
    _event(ctx, events.APPOINTMENT_RESCHEDULED, appointment)
    return True


@operation(
    "appointment.appointment.reschedule",
    kind="command",
    permission=CHANGE_OWN,
    input=RescheduleIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Move an appointment (by its number or id) to another wall-clock time, change its length, hand "
        "it to another professional (by name) or change its services; only pending or confirmed, uncharged ones move. "
        "Judged like a new booking. on_behalf_of_customer=true (with the customer) when she asks herself: it must be "
        "hers and keep the notice.",
        "risk": "normal",
    },
)
def reschedule(ctx: OperationContext, data: RescheduleIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    by_customer = _acting_for_customer(ctx, appointment, data)
    _move(
        ctx,
        appointment,
        start=read_moment(data.start, "start") if data.start else None,
        minutes=data.duration_minutes,
        staff_id=data.staff_id,
        staff=data.staff,
        service_refs=data.services,
        by_customer=by_customer,
        reason=data.reason,
        confirm_overlap=data.confirm_overlap and not by_customer,
    )
    return load_detail(appointment.id)


@operation(
    "appointment.appointment.update",
    kind="command",
    permission=CHANGE_OWN,
    input=UpdateIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Edit an appointment: only what is sent changes — its notes (the visit's notes, e.g. the colour "
        "formula, in any state), the customer's phone (saved as +34…) or email on it, and, judged like a move, its "
        "time, length, professional or services.",
        "risk": "normal",
    },
)
def update_appointment(ctx: OperationContext, data: UpdateIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    sent = data.model_fields_set
    details = {}
    for field in ("notes", "internal_notes", "customer_email"):
        if field in sent:
            details[field] = getattr(data, field) or ""
    if "customer_phone" in sent:
        try:
            details["customer_phone"] = to_e164(
                data.customer_phone, business_country(ctx)
            )
        except InvalidPhone:
            message = str(PHONE_INVALID)
            raise InvalidPayload(
                message,
                code="appointment.phone_invalid",
                fields={"customer_phone": message},
            ) from None
    if sent & {"start", "duration_minutes", "staff_id", "staff", "services"}:
        _move(
            ctx,
            appointment,
            start=read_moment(data.start, "start") if data.start else None,
            minutes=data.duration_minutes,
            staff_id=data.staff_id,
            staff=data.staff,
            service_refs=data.services,
            by_customer=False,
            reason="",
            confirm_overlap=data.confirm_overlap,
        )
    changed = {
        field: value
        for field, value in details.items()
        if getattr(appointment, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(appointment, field, value)
        appointment.updated_by = _actor(ctx)
        appointment.save(update_fields=[*changed, "updated_by", "updated_at"])
        _event(ctx, events.APPOINTMENT_UPDATED, appointment)
    return load_detail(appointment.id)


# ── States (F03, F05, F07, F08, F09) ─────────────────────────────────────────────────────────


def _transition(
    ctx: OperationContext,
    data: AppointmentRefIn,
    *,
    allowed: tuple,
    to: str,
    action: str,
    event: str,
    cannot: str,
) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if appointment.status not in allowed:
        raise Conflict(str(CANNOT[cannot]), code=f"appointment.cannot_{cannot}")
    appointment.status = to
    appointment.updated_by = _actor(ctx)
    appointment.save(update_fields=["status", "updated_by", "updated_at"])
    _history(ctx, appointment, action)
    _event(ctx, event, appointment)
    return load_detail(appointment.id)


@operation(
    "appointment.appointment.confirm",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Confirm a pending appointment (a booking the customer made, waiting for review).",
        "risk": "normal",
    },
)
def confirm(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.PENDING,),
        to=S.CONFIRMED,
        action=A.CONFIRMED,
        event=events.APPOINTMENT_CONFIRMED,
        cannot="confirm",
    )


@operation(
    "appointment.appointment.start",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "The customer arrived: start the service of a pending or confirmed appointment.",
        "risk": "normal",
    },
)
def start(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.PENDING, S.CONFIRMED),
        to=S.IN_PROGRESS,
        action=A.STARTED,
        event=events.APPOINTMENT_STARTED,
        cannot="start",
    )


@operation(
    "appointment.appointment.complete",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Complete an appointment in progress (or confirmed). Charging it also completes it.",
        "risk": "normal",
    },
)
def complete(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return _transition(
        ctx,
        data,
        allowed=(S.CONFIRMED, S.IN_PROGRESS),
        to=S.COMPLETED,
        action=A.COMPLETED,
        event=events.APPOINTMENT_COMPLETED,
        cannot="complete",
    )


@operation(
    "appointment.appointment.mark_no_show",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Record that the customer did not show up, once the appointment's time has passed (pending or "
        "confirmed, not charged). Ask the person before doing it.",
        "risk": "high",
    },
)
def mark_no_show(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number)
    _refuse_with_open_check(appointment)
    if (
        appointment.status in MOVABLE
        and not appointment.sale_id
        and appointment.start > now()
    ):
        raise Conflict(str(NO_SHOW_TOO_EARLY), code="appointment.no_show_too_early")
    allowed = (S.PENDING, S.CONFIRMED) if not appointment.sale_id else ()
    return _transition(
        ctx,
        data,
        allowed=allowed,
        to=S.NO_SHOW,
        action=A.NO_SHOW,
        event=events.APPOINTMENT_MARKED_NO_SHOW,
        cannot="mark_no_show",
    )


@operation(
    "appointment.appointment.cancel",
    kind="command",
    permission=CHANGE_OWN,
    input=CancelIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Cancel an appointment (pending, confirmed or no-show; not a charged one), with an optional "
        "reason; its time becomes free. on_behalf_of_customer=true (with the customer) when she cancels herself: it "
        "must be hers and the business's cancellation policy applies. Ask the person before doing it.",
        "risk": "high",
    },
)
def cancel(ctx: OperationContext, data: CancelIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    by_customer = _acting_for_customer(ctx, appointment, data)
    if (
        appointment.status not in (S.PENDING, S.CONFIRMED, S.NO_SHOW)
        or appointment.sale_id
    ):
        raise Conflict(str(CANNOT["cancel"]), code="appointment.cannot_cancel")
    _refuse_with_open_check(appointment)
    if by_customer:
        settings = current_settings()
        if not settings.allow_customer_cancellation:
            raise Conflict(
                str(CANCELLATION_DISABLED),
                code="appointment.customer_cancellation_disabled",
            )
        if appointment.start - now() < dt.timedelta(
            hours=settings.cancellation_notice_hours
        ):
            raise Conflict(
                str(CANCELLATION_NOTICE)
                % {"hours": settings.cancellation_notice_hours},
                code="appointment.cancellation_notice_required",
            )
    appointment.status = S.CANCELLED
    appointment.cancelled_at = timezone.now()
    appointment.cancellation_reason = data.reason
    appointment.cancelled_by_customer = by_customer
    appointment.updated_by = _actor(ctx)
    appointment.save()
    _history(ctx, appointment, A.CANCELLED, by_customer=by_customer, reason=data.reason)
    _event(ctx, events.APPOINTMENT_CANCELLED, appointment, by_customer=by_customer)
    return load_detail(appointment.id)


# ── Deleting (F11) ───────────────────────────────────────────────────────────────────────────


def _delete(ctx: OperationContext, appointment: Appointment) -> None:
    if appointment.status in (S.IN_PROGRESS, S.COMPLETED) or appointment.sale_id:
        raise Conflict(str(CANNOT["delete"]), code="appointment.cannot_delete")
    _refuse_with_open_check(appointment)
    appointment.deleted_at = timezone.now()
    appointment.updated_by = _actor(ctx)
    appointment.save(update_fields=["deleted_at", "updated_by", "updated_at"])
    _history(ctx, appointment, A.DELETED)
    _event(ctx, events.APPOINTMENT_DELETED, appointment)


@operation(
    "appointment.appointment.delete",
    kind="command",
    permission=DELETE,
    input=AppointmentRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete an appointment from the agenda (it is archived, not destroyed): pending, confirmed, "
        "cancelled or no-show and not charged. Cancelling keeps the record and is usually what is wanted; ask first.",
        "risk": "high",
    },
)
def delete_appointment(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    _delete(ctx, appointment)
    return {"id": appointment.id}


@operation(
    "appointment.appointment.bulk_delete",
    kind="command",
    permission=DELETE,
    input=BulkDeleteIn,
    output=BulkDeletedOut,
    expose_api=True,
    ai={
        "description": "Delete several appointments at once (all or none). Ask first.",
        "risk": "high",
    },
)
def bulk_delete(ctx: OperationContext, data: BulkDeleteIn) -> dict:
    deleted = []
    for appointment_id in dict.fromkeys(data.ids):
        appointment = find_appointment(ctx, appointment_id, None, lock=True)
        _delete(ctx, appointment)
        deleted.append(appointment.id)
    return {"deleted": deleted}


# ── Charging (F17) ───────────────────────────────────────────────────────────────────────────


@operation(
    "appointment.appointment.charge",
    kind="command",
    permission=CHANGE_OWN,
    input=AppointmentRefIn,
    output=ChargeOut,
    expose_api=True,
    ai={
        "description": "Charge an appointment at the till: opens a check in Sales linked to it, titled with the customer "
        "and the appointment's number, with a line per service at the price booked and the professional who did it, "
        "so a voucher of the customer can pay one. While that check is open, charging again goes back to it. "
        "Charging the check then marks the appointment charged and completed. Ask first.",
        "risk": "high",
    },
)
def charge(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number, lock=True)
    if not may_change(ctx, appointment.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if appointment.status in (S.CANCELLED, S.NO_SHOW):
        raise Conflict(str(CANNOT["charge"]), code="appointment.cannot_charge")
    if appointment.sale_id:
        raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
    try:
        if appointment.order_id:
            # One check per appointment: while the one it opened is open, charging goes back to it; once
            # charged (the sale's notice may not have arrived yet) it is charged; voided, a new one opens.
            current = _check_of(ctx, appointment.order_id)
            if current is not None and current.status == "open":
                return _charge_out(appointment, current)
            if current is not None and current.status == "completed":
                raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
        order = _open_check(ctx, appointment)
    except UnknownOperation, AppInactive:
        raise Conflict(
            str(SALE_UNAVAILABLE), code="appointment.sale_unavailable"
        ) from None
    if appointment.order_id != order.id:
        appointment.order_id = order.id
        appointment.save(update_fields=["order_id", "updated_at"])
        _event(
            ctx, events.APPOINTMENT_CHECK_OPENED, appointment, order_id=str(order.id)
        )
    return _charge_out(appointment, order)


def _check_of(ctx: OperationContext, order_id: UUID):
    """The check of the till (Sales) ``order_id``, or ``None`` when it no longer exists."""
    read = get("sale.order.get")
    try:
        return read(ctx, read.input.model_validate({"order_id": str(order_id)}))
    except NotFound:
        return None


def _open_check(ctx: OperationContext, appointment: Appointment):
    """Opens the appointment's check in the till: titled «customer · number», a service line per service
    (SALE-F38: a voucher of the customer can pay it, SALE-F27) at its booked price, by the professional
    who did it. Sales answers the check already open for it, if any (``already``)."""
    staff_id = str(appointment.staff_id) if appointment.staff_id else None
    lines = []
    for line in appointment.lines.select_related("service__tax_category").order_by(
        "position", "id"
    ):
        if needs_tax_setup(line.service):
            raise Conflict(
                str(NEEDS_TAX_SETUP) % {"name": line.name},
                code="appointment.service_needs_tax_setup",
            )
        # Charged what was booked (the professional's own price included, whatever the catalog says
        # today): Sales checks it against this appointment.
        lines.append(
            {
                "service_id": str(line.service_id),
                "staff_id": staff_id,
                "booked_price": line.price,
            }
        )
    label = f"{appointment.customer_name or appointment.number} · {appointment.number}"[
        :60
    ]
    open_check = get("sale.order.open")
    return open_check(
        ctx,
        open_check.input.model_validate(
            {
                "label": label,
                "appointment_id": str(appointment.id),
                "service_lines": lines,
            }
        ),
    )


def _charge_out(appointment: Appointment, order) -> dict:
    return {
        "appointment_id": appointment.id,
        "order_id": order.id,
        "label": order.label,
    }


# ── Blocks (F16) ─────────────────────────────────────────────────────────────────────────────


@operation(
    "appointment.blocked_time.create",
    kind="command",
    permission=MANAGE_SCHEDULE,
    input=BlockedTimeCreateIn,
    output=BlockedTimeOut,
    expose_api=True,
    ai={
        "description": "Block a period of the agenda (a holiday, a training, a professional's break): for the whole "
        "business or one professional (by name), between two wall-clock times or whole days (all_day). Nobody books it.",
        "risk": "normal",
    },
)
def create_blocked_time(ctx: OperationContext, data: BlockedTimeCreateIn) -> dict:
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else None
    )
    zone = business_zone()
    if data.all_day:
        first = engine.wall(read_moment(data.start, "start"), zone).date()
        last = engine.wall(read_moment(data.end, "end"), zone).date()
        start, end = (
            engine.midnight(first, zone),
            engine.midnight(last + dt.timedelta(days=1), zone),
        )
    else:
        start, end = read_moment(data.start, "start"), read_moment(data.end, "end")
    block = BlockedTime.objects.create(
        title=data.title,
        block_type=data.block_type,
        start=start,
        end=end,
        all_day=data.all_day,
        staff=member,
        reason=data.reason,
        created_by=_actor(ctx),
    )
    record_event(
        ctx,
        events.BLOCKED_TIME_CREATED,
        {"id": str(block.id), "staff_id": str(member.id) if member else None},
    )
    return blocked_out(block)


@operation(
    "appointment.blocked_time.delete",
    kind="command",
    permission=MANAGE_SCHEDULE,
    input=BlockedTimeRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a blocked period: its time can be booked again. Ask first.",
        "risk": "high",
    },
)
def delete_blocked_time(ctx: OperationContext, data: BlockedTimeRefIn) -> dict:
    block = BlockedTime.objects.select_for_update().filter(pk=data.id).first()
    if block is None:
        raise NotFound(
            str(_("That blocked period does not exist in this business.")),
            code="appointment.blocked_time_not_found",
        )
    block.delete()
    record_event(ctx, events.BLOCKED_TIME_DELETED, {"id": str(data.id)})
    return {"id": data.id}


# ── Series (F12 to F15) ──────────────────────────────────────────────────────────────────────


def _window(settings: Settings) -> tuple[dt.date, dt.date]:
    days = settings.max_advance_booking or SERIES_DEFAULT_WINDOW
    first = today()
    return first, first + dt.timedelta(days=days)


def _series_services(series: Recurring) -> list[Service]:
    return [
        line.service
        for line in series.lines.select_related("service").order_by("position", "id")
    ]


def _book_window(
    ctx: OperationContext,
    series: Recurring,
    *,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
) -> dict:
    """Books the series' dates of its window not booked yet (at most 50 a run); the report of what happened."""
    settings = current_settings()
    window_from, window_to = _window(settings)
    first = max(from_date or window_from, window_from, series.start_date)
    last = min(to_date or window_to, window_to)
    dates, upcoming = engine.dates(pattern_of(series), until=last)
    dates = [day for day in dates if day >= first]
    report = {
        "booked": 0,
        "already_booked": 0,
        "skipped": [],
        "next_from": None,
        "to": last,
        "upcoming_date": upcoming if not dates else None,
    }
    if not dates:
        return report
    member = series.staff
    services = _series_services(series)
    unavailable = any(
        not (service.is_active and service.is_bookable) for service in services
    )
    _lock_members(member)
    lines = lines_for(member, services)
    minutes = series.duration_minutes
    taken = set(
        Appointment.objects.filter(
            recurring=series, deleted_at__isnull=True
        ).values_list("occurrence_date", flat=True)
    )
    agenda = load_agenda(
        ctx, member, dates[0], dates[-1] + dt.timedelta(days=1), settings=settings
    )
    zone = business_zone()
    for index, day in enumerate(dates):
        if day in taken:
            report["already_booked"] += 1
            continue
        if report["booked"] >= MATERIALIZE_PER_RUN:
            report["next_from"] = day
            break
        code = "service_unavailable" if unavailable else None
        if code is None:
            try:
                start = engine.aware(dt.datetime.combine(day, series.time), zone)
            except engine.NonexistentTime:
                start, code = None, "invalid_start"
        if code is None:
            end = start + dt.timedelta(minutes=minutes)
            code = engine.verdict(agenda, start, end, now=now(), customer=True)
        if code:
            report["skipped"].append(
                {"occurrence_date": day, "code": code, "message": verdict_message(code)}
            )
            continue
        appointment = _create(
            ctx,
            customer=series.customer,
            member=member,
            lines=lines,
            start=start,
            minutes=minutes,
            source=Appointment.Source.COUNTER,
            recurring=series,
            occurrence=day,
            settings=settings,
        )
        agenda = engine.Agenda(
            agenda.zone,
            agenda.rules,
            agenda.business,
            agenda.staff,
            agenda.blocks,
            [*agenda.busy, engine.Period(start, end, id=appointment.id)],
        )
        report["booked"] += 1
    return report


def _bookable_series(series: Recurring) -> None:
    if not series.is_active:
        raise Conflict(str(RECURRING_INACTIVE), code="appointment.recurring_inactive")
    if series.staff is None:
        raise Conflict(str(RECURRING_NO_STAFF), code="appointment.recurring_no_staff")


def _materialize_out(series: Recurring, report: dict) -> dict:
    return {"recurring": load_series(series.id), **report}


@operation(
    "appointment.recurring.create",
    kind="command",
    permission=ADD_OWN,
    input=RecurringCreateIn,
    output=MaterializeOut,
    expose_api=True,
    ai={
        "description": "Create a repeating appointment (every day, week, two weeks or month) for a customer, services "
        "and a professional (all by name) at a wall-clock time, from a date, optionally until a date or for a number "
        "of appointments; it books the dates of the booking window at once and lists the dates that did not fit with "
        "their reason.",
        "risk": "normal",
    },
)
def create_series(ctx: OperationContext, data: RecurringCreateIn) -> dict:
    customer = find_customer(data.customer_id, data.customer)
    services = resolve_services(data.services)
    member = _member_for_booking(ctx, data.staff_id, data.staff, services)
    minutes = data.duration_minutes or sum(
        line["duration_minutes"] for line in lines_for(member, services)
    )
    weekly = data.frequency in ("weekly", "biweekly")
    series = Recurring.objects.create(
        customer=customer,
        customer_name=customer.name,
        staff=member,
        staff_name=member.full_name,
        frequency=data.frequency,
        day_of_week=(
            data.day_of_week
            if data.day_of_week is not None
            else data.start_date.weekday()
        )
        if weekly
        else None,
        time=data.time.replace(second=0, microsecond=0),
        duration_minutes=minutes,
        start_date=data.start_date,
        end_date=data.end_date,
        max_occurrences=data.max_occurrences,
        created_by=_actor(ctx),
    )
    RecurringService.objects.bulk_create(
        RecurringService(recurring=series, service=service, position=position)
        for position, service in enumerate(services)
    )
    record_event(
        ctx,
        events.RECURRING_CREATED,
        {"id": str(series.id), "customer_id": str(customer.id)},
    )
    return _materialize_out(series, _book_window(ctx, series))


@operation(
    "appointment.recurring.materialize",
    kind="command",
    permission=ADD_OWN,
    input=MaterializeIn,
    output=MaterializeOut,
    expose_api=True,
    ai={
        "description": "Book the dates of a repeating appointment's window not booked yet (at most 50 a run; run it "
        "again from next_from until there is none). A date that does not fit is skipped and listed with its reason; a "
        "date cancelled by hand is never booked again.",
        "risk": "normal",
    },
)
def materialize(ctx: OperationContext, data: MaterializeIn) -> dict:
    series = find_series(ctx, data.id, lock=True)
    if not may_book_for(ctx, series.staff_id):
        raise PermissionDenied(str(BOOK_OWN_ONLY))
    _bookable_series(series)
    remaining, upcoming = engine.dates(
        pattern_of(series), until=_window(current_settings())[1]
    )
    if not [day for day in remaining if day >= today()] and upcoming is None:
        raise Conflict(str(RECURRING_ENDED), code="appointment.recurring_ended")
    return _materialize_out(
        series,
        _book_window(ctx, series, from_date=data.from_date, to_date=data.to_date),
    )


@operation(
    "appointment.recurring.update",
    kind="command",
    permission=CHANGE_OWN,
    input=RecurringUpdateIn,
    output=RecurringUpdatedOut,
    expose_api=True,
    ai={
        "description": "Edit a repeating appointment from one of its dates on (this and all following): its time, "
        "length, repetition, weekday, professional (by name) or services. Before that date nothing changes (the series "
        "is split); appointments already charged, in progress or completed are left alone; the booked ones that still "
        "fall on the pattern move, the others are cancelled, and the ones that do not fit stay and are listed.",
        "risk": "normal",
    },
)
def update_series(ctx: OperationContext, data: RecurringUpdateIn) -> dict:
    series = find_series(ctx, data.id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    sent = data.model_fields_set
    # The last date can be neither before the change (a split starts there) nor before the series starts.
    if data.end_date is not None and data.end_date < max(
        data.from_date, series.start_date
    ):
        message = str(END_BEFORE_START)
        raise InvalidPayload(message, fields={"end_date": message})
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else series.staff
    )
    if member is not None and member != series.staff and not may_change(ctx, member.id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    services = (
        resolve_services(data.services) if data.services else _series_services(series)
    )
    if member is not None:
        check_member(member, services)
    frequency = data.frequency or series.frequency
    weekly = frequency in ("weekly", "biweekly")
    day_of_week = data.day_of_week if "day_of_week" in sent else series.day_of_week
    if weekly and day_of_week is None:
        day_of_week = data.from_date.weekday()
    rule = {
        "frequency": frequency,
        "day_of_week": day_of_week if weekly else None,
        "time": (data.time or series.time).replace(second=0, microsecond=0),
        "duration_minutes": data.duration_minutes
        or (
            sum(line["duration_minutes"] for line in lines_for(member, services))
            if data.services
            else series.duration_minutes
        ),
        "end_date": data.end_date if "end_date" in sent else series.end_date,
        "staff": member,
        "staff_name": member.full_name if member else "",
    }
    old_pattern = pattern_of(series)
    # A pause stays (by hand, or the customer's data erased); only a series that lost its professional
    # (Staff's termination) comes back once it gets one.
    active = (series.is_active or series.staff is None) and member is not None
    if data.from_date <= engine.first_date(old_pattern):
        target = series
        for field, value in rule.items():
            setattr(target, field, value)
        if "max_occurrences" in sent:
            target.max_occurrences = data.max_occurrences
        target.is_active = active
        target.save()
    else:
        before = engine.count_before(old_pattern, data.from_date)
        remaining = (
            data.max_occurrences
            if "max_occurrences" in sent
            else (
                max(series.max_occurrences - before, 1)
                if series.max_occurrences
                else None
            )
        )
        series.end_date = data.from_date - dt.timedelta(days=1)
        series.save(update_fields=["end_date", "updated_at"])
        target = Recurring.objects.create(
            customer=series.customer,
            customer_name=series.customer_name,
            start_date=data.from_date,
            max_occurrences=remaining,
            split_from=series,
            is_active=active,
            created_by=_actor(ctx),
            **rule,
        )
    if data.services or target is not series:
        target.lines.all().delete()
        RecurringService.objects.bulk_create(
            RecurringService(recurring=target, service=service, position=position)
            for position, service in enumerate(services)
        )
    new_pattern = pattern_of(target)
    outcome = {"moved": 0, "cancelled": 0, "locked": 0, "skipped": [], "booked": 0}
    affected = (
        Appointment.objects.select_for_update()
        .filter(
            recurring=series,
            deleted_at__isnull=True,
            occurrence_date__gte=data.from_date,
        )
        .order_by("occurrence_date")
    )
    moment = now()
    zone = business_zone()
    for appointment in affected:
        in_pattern = engine.contains(new_pattern, appointment.occurrence_date)
        if (
            appointment.status in (S.IN_PROGRESS, S.COMPLETED)
            or appointment.sale_id
            or appointment.order_id
        ):
            outcome["locked"] += 1
        elif appointment.status in MOVABLE and appointment.start >= moment:
            if not in_pattern:
                appointment.status = S.CANCELLED
                appointment.cancelled_at = timezone.now()
                appointment.cancellation_reason = str(PATTERN_CHANGED)
                # Its date is no longer one of the series: a pattern changed back books it again.
                appointment.occurrence_date = None
                appointment.save()
                _history(ctx, appointment, A.CANCELLED, reason=str(PATTERN_CHANGED))
                _event(
                    ctx, events.APPOINTMENT_CANCELLED, appointment, by_customer=False
                )
                outcome["cancelled"] += 1
                continue
            code = None
            if member is None:
                code = "no_staff"
            else:
                try:
                    when = engine.aware(
                        dt.datetime.combine(appointment.occurrence_date, target.time),
                        zone,
                    )
                    if _move(
                        ctx,
                        appointment,
                        start=when,
                        minutes=target.duration_minutes,
                        staff_id=member.id,
                        staff=None,
                        service_refs=data.services,
                        by_customer=False,
                        reason="",
                        confirm_overlap=False,
                        strict=True,
                    ):
                        outcome["moved"] += 1
                except engine.NonexistentTime:
                    code = "invalid_start"
                except Conflict as refusal:
                    code = refusal.code.removeprefix("appointment.")
                    code = "overlap" if code == "slot_taken" else code
            if code:
                message = (
                    str(RECURRING_NO_STAFF)
                    if code == "no_staff"
                    else verdict_message(code)
                )
                outcome["skipped"].append(
                    {
                        "occurrence_date": appointment.occurrence_date,
                        "code": code,
                        "message": message,
                    }
                )
        if in_pattern and appointment.recurring_id != target.id:
            appointment.recurring = target
            appointment.save(update_fields=["recurring", "updated_at"])
    record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
    if target is not series:
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(target.id)})
    if target.is_active:
        outcome["booked"] = _book_window(ctx, target, from_date=data.from_date)[
            "booked"
        ]
    return {"recurring": load_series(target.id), **outcome}


def _set_active(ctx: OperationContext, series_id: UUID, active: bool) -> dict:
    series = find_series(ctx, series_id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    if active and series.staff is None:
        raise Conflict(str(RECURRING_NO_STAFF), code="appointment.recurring_no_staff")
    if series.is_active != active:
        series.is_active = active
        series.save(update_fields=["is_active", "updated_at"])
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
    return load_series(series.id)


@operation(
    "appointment.recurring.deactivate",
    kind="command",
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringOut,
    expose_api=True,
    ai={
        "description": "Pause a repeating appointment: it stops booking dates; the ones booked are kept.",
        "risk": "normal",
    },
)
def deactivate_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    return _set_active(ctx, data.id, False)


@operation(
    "appointment.recurring.activate",
    kind="command",
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringOut,
    expose_api=True,
    ai={
        "description": "Reactivate a paused repeating appointment (it books nothing by itself: materialize does).",
        "risk": "normal",
    },
)
def activate_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    return _set_active(ctx, data.id, True)


@operation(
    "appointment.recurring.delete",
    kind="command",
    permission=CHANGE_OWN,
    input=RecurringRefIn,
    output=RecurringDeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a repeating appointment; the appointments already booked are kept. Ask first.",
        "risk": "high",
    },
)
def delete_series(ctx: OperationContext, data: RecurringRefIn) -> dict:
    series = find_series(ctx, data.id, lock=True)
    if not may_change(ctx, series.staff_id):
        raise PermissionDenied(str(CHANGE_OWN_ONLY))
    series.deleted_at = timezone.now()
    series.is_active = False
    series.save(update_fields=["deleted_at", "is_active", "updated_at"])
    record_event(ctx, events.RECURRING_DELETED, {"id": str(series.id)})
    return {"id": series.id}


# ── Settings (F19) ───────────────────────────────────────────────────────────────────────────


@operation(
    "appointment.settings.update",
    kind="command",
    permission=MANAGE_SETTINGS,
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change the booking rules; only what is sent changes (e.g. turn off auto-confirming the "
        "customer's own bookings, or set the minimum notice).",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    settings = Settings.objects.select_for_update().first() or Settings()
    sent = {
        field: getattr(data, field)
        for field in data.model_fields_set
        if getattr(data, field) is not None
    }
    start = sent.get("calendar_start_hour", settings.calendar_start_hour)
    end = sent.get("calendar_end_hour", settings.calendar_end_hour)
    if end <= start:
        message = str(CALENDAR_UPSIDE_DOWN)
        field = (
            "calendar_end_hour"
            if "calendar_end_hour" in sent
            else "calendar_start_hour"
        )
        raise InvalidPayload(message, fields={field: message})
    changed = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(settings)


# ── The platform's reactions (events.py) ─────────────────────────────────────────────────────


@operation(
    "appointment.appointment.mark_charged",
    kind="command",
    permission=SYSTEM,
    input=SaleFromAppointmentIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.created_from_appointment: the appointment is charged with that "
        "sale and completed.",
        "risk": "normal",
    },
)
def mark_charged(ctx: OperationContext, data: SaleFromAppointmentIn) -> dict:
    appointment = (
        Appointment.objects.select_for_update().filter(pk=data.appointment_id).first()
    )
    if (
        appointment is None
        or appointment.deleted_at is not None
        or appointment.status in (S.CANCELLED, S.NO_SHOW)
    ):
        raise Conflict(str(CANNOT["charge"]), code="appointment.cannot_charge")
    if appointment.sale_id == data.sale_id:
        return {"changed": 0}
    if appointment.sale_id:
        raise Conflict(str(ALREADY_CHARGED), code="appointment.already_charged")
    appointment.sale_id = data.sale_id
    appointment.charged_at = timezone.now()
    completes = appointment.status in BUSY
    if completes:
        appointment.status = S.COMPLETED
    appointment.save()
    _history(ctx, appointment, A.CHARGED, new={"sale_id": str(data.sale_id)})
    _event(ctx, events.APPOINTMENT_CHARGED, appointment, sale_id=str(data.sale_id))
    if completes:
        _history(ctx, appointment, A.COMPLETED)
        _event(ctx, events.APPOINTMENT_COMPLETED, appointment)
    return {"changed": 1}


@operation(
    "appointment.appointment.unmark_charged",
    kind="command",
    permission=SYSTEM,
    input=SaleVoidedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.sale.voided: its appointment is no longer charged.",
        "risk": "normal",
    },
)
def unmark_charged(ctx: OperationContext, data: SaleVoidedIn) -> dict:
    changed = 0
    for appointment in (
        Appointment.objects.select_for_update()
        .filter(sale_id=data.sale_id)
        .order_by("id")
    ):
        appointment.sale_id = None
        appointment.charged_at = None
        appointment.order_id = None
        appointment.save(
            update_fields=["sale_id", "charged_at", "order_id", "updated_at"]
        )
        _history(ctx, appointment, A.UNCHARGED, old={"sale_id": str(data.sale_id)})
        _event(
            ctx, events.APPOINTMENT_UNCHARGED, appointment, sale_id=str(data.sale_id)
        )
        changed += 1
    return {"changed": changed}


@operation(
    "appointment.appointment.release_check",
    kind="command",
    permission=SYSTEM,
    input=OrderVoidedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to sale.order.voided: the appointment whose open check was voided can open a "
        "new one.",
        "risk": "normal",
    },
)
def release_check(ctx: OperationContext, data: OrderVoidedIn) -> dict:
    changed = 0
    for appointment in (
        Appointment.objects.select_for_update()
        .filter(order_id=data.order_id, sale_id__isnull=True)
        .order_by("id")
    ):
        appointment.order_id = None
        appointment.save(update_fields=["order_id", "updated_at"])
        _event(
            ctx,
            events.APPOINTMENT_CHECK_CLOSED,
            appointment,
            order_id=str(data.order_id),
        )
        changed += 1
    return {"changed": changed}


@operation(
    "appointment.customer.reassign",
    kind="command",
    permission=SYSTEM,
    input=MergedIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.merged: the absorbed card's appointments and series move "
        "to the card that stays (the names they were booked with do not change).",
        "risk": "normal",
    },
)
def reassign_customer(ctx: OperationContext, data: MergedIn) -> dict:
    moved = Appointment.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    moved += Recurring.objects.filter(customer_id=data.absorbed_id).update(
        customer_id=data.id
    )
    if moved:
        record_event(
            ctx,
            events.APPOINTMENT_REASSIGNED,
            {"id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"changed": moved}


@operation(
    "appointment.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's name, contact, notes and "
        "cancellation reasons are emptied in her appointments, series and their history; her series are paused.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    rows = Appointment.objects.filter(customer_id=data.id)
    changed = rows.exclude(
        customer_name="",
        customer_phone="",
        customer_email="",
        notes="",
        internal_notes="",
        cancellation_reason="",
    ).update(
        customer_name="",
        customer_phone="",
        customer_email="",
        notes="",
        internal_notes="",
        cancellation_reason="",
    )
    for line in History.objects.filter(appointment__customer_id=data.id):
        new_value = {
            key: value
            for key, value in line.new_value.items()
            if key != "customer_name"
        }
        if line.reason or new_value != line.new_value:
            line.reason = ""
            line.new_value = new_value
            line.save(update_fields=["reason", "new_value"])
    changed += (
        Recurring.objects.filter(customer_id=data.id)
        .exclude(customer_name="", is_active=False)
        .update(customer_name="", is_active=False)
    )
    if changed:
        record_event(ctx, events.APPOINTMENT_UPDATED, {"customer_id": str(data.id)})
    return {"changed": changed}


@operation(
    "appointment.staff.release",
    kind="command",
    permission=SYSTEM,
    input=MemberEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to staff.member.terminated: the professional's upcoming pending or confirmed "
        "appointments become unassigned (to hand to somebody else) and their series are paused.",
        "risk": "normal",
    },
)
def release_staff(ctx: OperationContext, data: MemberEventIn) -> dict:
    changed = 0
    upcoming = (
        Appointment.objects.select_for_update()
        .filter(
            staff_id=data.id,
            status__in=MOVABLE,
            start__gte=now(),
            deleted_at__isnull=True,
        )
        .order_by("start", "id")
    )
    for appointment in upcoming:
        name = appointment.staff_name
        appointment.staff = None
        appointment.save(update_fields=["staff", "updated_at"])
        _history(ctx, appointment, A.UNASSIGNED, old={"staff": name})
        _event(
            ctx,
            events.APPOINTMENT_UNASSIGNED,
            appointment,
            previous_staff_id=str(data.id),
        )
        changed += 1
    for series in Recurring.objects.select_for_update().filter(
        staff_id=data.id, deleted_at__isnull=True
    ):
        series.staff = None
        series.is_active = False
        series.save(update_fields=["staff", "is_active", "updated_at"])
        record_event(ctx, events.RECURRING_UPDATED, {"id": str(series.id)})
        changed += 1
    return {"changed": changed}
