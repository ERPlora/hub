"""The steps every write of the appointment app shares: who acts, the history and the events, the locks in id order, the
overlap check and the booking of one appointment with its number.
"""

import datetime as dt
from uuid import UUID

from django.db.models import F
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, PermissionDenied
from live.outbox import record_event

from apps.appointment import engine, events
from apps.appointment.models.appointments import Appointment, AppointmentService, History
from apps.appointment.models.numbering import Counter
from apps.appointment.models.series import Recurring
from apps.appointment.models.settings import Settings
from apps.appointment.queries.access import by_person, may_book_for
from apps.appointment.queries.agenda import conflicts_of, load_agenda, verdict_message
from apps.appointment.queries.booking import check_member, lines_for, resolve_services
from apps.appointment.queries.business import now, today
from apps.appointment.queries.reads import CUSTOMER_SOURCES
from apps.customer.queries.reads import find_customer
from apps.service.models.catalog import Service
from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member
from base.business import business_zone
from base.queries.people import actor_name

#: Run only by the platform (events.py): outside ``appointment.*``, so no role and no API key holds it.
SYSTEM = "system.appointment"
S = Appointment.Status
A = History.Action
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
ALREADY_CHARGED = _("This appointment is already charged.")
CHECK_OPEN = _(
    "This appointment has a check open in the till: charge it or void it there first."
)
OVERLAP_NEEDS_CONFIRMATION = _("This time overlaps with %(conflicts)s. Book it anyway?")
BOOK_OWN_ONLY = _("You may only book your own appointments.")
CHANGE_OWN_ONLY = _("You may only change your own appointments.")


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a colleague reads it in the appointment's history: never their e-mail address."""
    return actor_name(ctx.actor)[:128]


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


def _history(  # noqa: PLR0913
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


def _locked_card(ctx: OperationContext, data):
    """The customer's card a booking or a series is for, locked as Customers' writes and the Hub admin's
    «Delete» of a card take it: a deletion under way is waited for and the card is gone (404), and one that
    comes after waits for the booking and finds the row that protects the card."""
    return find_customer(ctx, data.customer_id, data.customer, lock=True)


def _booking_basis(ctx: OperationContext, data) -> tuple:
    """What a booking and a batch of bookings start from: the customer's card (locked, ``_locked_card``), the
    professional who performs the services, their lines and the minutes (the ones sent, else the services')."""
    customer = _locked_card(ctx, data)
    services = resolve_services(data.services)
    member = _member_for_booking(ctx, data.staff_id, data.staff, services)
    lines = lines_for(member, services)
    minutes = data.duration_minutes or sum(line["duration_minutes"] for line in lines)
    return customer, member, lines, minutes


def lock_appointments(ids) -> list[UUID]:
    """Locks the appointments ``ids`` (deleted ones too) in id order; the ids of those still there.

    Every write on an appointment locks it before what hangs from it (its history, its service lines), and so
    does the Hub admin's «Delete» (admin.py) before Django gathers all that and deletes it: it waits for the
    write under way and takes what that write added, instead of failing on it at its COMMIT. Every write that
    locks several takes them here, in id order (after their series): two writes never wait in a circle.
    """
    rows = Appointment.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


def lock_series(ids) -> list[UUID]:
    """Locks the series ``ids`` (deleted ones too) in id order; the ids of those still there.

    Every write on a series locks it before what hangs from it (its services, the appointments it books, the
    series it splits into), and so does the Hub admin's «Delete» (admin.py) before Django checks what protects
    it and gathers the rest: booked appointments it sees answer «Cannot delete».
    """
    rows = Recurring.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


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


def _judge(  # noqa: PLR0913
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
    """Refuses ``[start, end)`` with its reason (409), or asks to confirm an overlap; returns the agenda read.

    ``customer``: judged by the customer's rules; a caller who is not a person always is (``by_person``).
    """
    customer = customer or not by_person(ctx)
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


def _create(  # noqa: PLR0913
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
        end=engine.ends_at(start, minutes),
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
