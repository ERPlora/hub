"""Read operations of the appointment app (``READ ONLY``), and the helpers services.py reuses inside its
own transaction: the business's clock, the settings, who sees what, how a booking's customer, services
and professional are resolved, and the agenda the rules (engine.py) judge.

- **Who sees what**: ``appointment.view_appointment`` sees the whole diary; ``…view_own_appointment``
  only the appointments of the staff record linked to the caller's account (none when it has none).
- **Availability = Schedules ∩ Staff ∩ appointments**: ``load_agenda`` reads ``schedule.hours.for_range``
  and ``staff.availability.for_member`` (their operations, with a reading context that adds
  ``schedule.view`` and ``staff.view``: booking needs no right in those apps), the blocks and the
  professional's appointments, and hands them to ``engine``.
- **Who may do a service**: the active, bookable professionals with an active assignment for it; a
  service nobody is assigned to may be done by the whole bookable team (the diary's rule, not Staff's
  nor Services'). Several services: whoever may do every one.
- Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break.
"""

import datetime as dt
from dataclasses import replace
from uuid import UUID

from django.db.models import Count, Exists, OuterRef, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation

from apps.appointment import engine
from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    History,
    Recurring,
    Settings,
)
from apps.appointment.schemas import (
    AppointmentListIn,
    AppointmentOut,
    AppointmentPage,
    AppointmentRefIn,
    BlockedTimeListIn,
    BlockedTimePage,
    CheckIn,
    CheckOut,
    CountForServiceIn,
    CountOut,
    ForCustomerIn,
    HistoryIn,
    HistoryPage,
    LanesIn,
    LanesOut,
    NoIn,
    RecurringDetailOut,
    RecurringGetIn,
    RecurringListIn,
    RecurringPage,
    ServiceRefIn,
    SettingsOut,
    SlotsIn,
    SlotsOut,
    VisitPage,
)
from apps.customer.queries import find_customer
from apps.schedule.queries import hours_for_range
from apps.schedule.schemas import HoursRangeIn
from apps.service.models import Assignment, Service
from apps.service.queries import find_service
from apps.staff.models import Member
from apps.staff.queries import member_availability, own_member, resolve_member
from apps.staff.schemas import AvailabilityIn

VIEW_ALL = "appointment.view_appointment"
VIEW_OWN = "appointment.view_own_appointment"
ADD_ALL = "appointment.add_appointment"
ADD_OWN = "appointment.add_own_appointment"
CHANGE_ALL = "appointment.change_appointment"
CHANGE_OWN = "appointment.change_own_appointment"

S = Appointment.Status
#: What occupies the professional's time.
BUSY = (S.PENDING, S.CONFIRMED, S.IN_PROGRESS)
#: What can still move.
MOVABLE = (S.PENDING, S.CONFIRMED)
CUSTOMER_SOURCES = (Appointment.Source.ONLINE, Appointment.Source.WHATSAPP)
#: The window a series books when the maximum advance is 0 (no limit).
SERIES_DEFAULT_WINDOW = 90
#: How many professionals the free times of «anybody who does it» look at.
MAX_PROFESSIONALS = 30
#: Schedules answers at most 366 days at once, Staff 731.
HOURS_CHUNK = 366
STAFF_CHUNK = 731

APPOINTMENT_NOT_FOUND = _("That appointment does not exist in this business.")
RECURRING_NOT_FOUND = _("That repeating appointment does not exist in this business.")
SERVICE_NOT_BOOKABLE = _("“%(name)s” cannot be booked: it is archived or not bookable.")
STAFF_NOT_BOOKABLE = _("%(name)s cannot take appointments: inactive or not bookable.")
STAFF_NOT_ELIGIBLE = _("%(name)s does not perform “%(service)s”.")
INVALID_LOCAL_TIME = _(
    "That time does not exist on the business's clock: the change of time skips it. Pick another one."
)

#: Why a time cannot be booked (engine.CODES) → what the person reads.
VERDICTS = {
    "invalid_start": _("That start date and time is not valid."),
    "in_past": _("That time has already passed."),
    "too_soon": _("This appointment must be booked further in advance."),
    "too_far": _("This appointment cannot be booked that far in advance."),
    "outside_schedule": _("That time is outside the business's opening hours."),
    "outside_staff_hours": _(
        "That professional does not work at that time. Pick another time or another professional."
    ),
    "blocked": _("That time is blocked in the agenda."),
    "overlap": _(
        "That professional already has an appointment at that time. Pick another time or another professional."
    ),
    "service_unavailable": _("A service of this series can no longer be booked."),
}


def verdict_message(code: str) -> str:
    return str(VERDICTS.get(code, VERDICTS["invalid_start"]))


# ── The business's clock and settings ────────────────────────────────────────────────────────


def business_zone():
    """The business's time zone (phase 1: ``settings.TIME_ZONE``; the Hub keeps no zone yet)."""
    return timezone.get_current_timezone()


def zone_name() -> str:
    zone = business_zone()
    return getattr(zone, "key", str(zone))


def now() -> dt.datetime:
    return timezone.now()


def today() -> dt.date:
    return engine.wall(now(), business_zone()).date()


def read_moment(value: dt.datetime, field: str) -> dt.datetime:
    """A time as sent (wall clock or instant) read on the business's clock; 422 on ``field`` if skipped."""
    try:
        return engine.aware(value.replace(second=0, microsecond=0), business_zone())
    except engine.NonexistentTime:
        message = str(INVALID_LOCAL_TIME)
        raise InvalidPayload(
            message, code="appointment.invalid_local_time", fields={field: message}
        ) from None


def current_settings() -> Settings:
    """The saved settings, or the factory ones (unsaved) while nobody saved them."""
    return Settings.objects.first() or Settings()


def rules_of(settings: Settings) -> engine.Rules:
    return engine.Rules(
        min_notice=settings.min_booking_notice,
        max_advance_days=settings.max_advance_booking,
        allow_overlap=settings.allow_overlapping,
        calendar_start_hour=settings.calendar_start_hour,
        calendar_end_hour=settings.calendar_end_hour,
        slot_interval=settings.slot_interval,
    )


def settings_out(settings: Settings) -> dict:
    fields = (
        "default_duration",
        "min_booking_notice",
        "max_advance_booking",
        "allow_overlapping",
        "allow_customer_cancellation",
        "cancellation_notice_hours",
        "calendar_start_hour",
        "calendar_end_hour",
        "slot_interval",
        "auto_confirm_online",
    )
    return {
        **{field: getattr(settings, field) for field in fields},
        "timezone": zone_name(),
    }


def day_bounds(
    date_from: dt.date, date_to: dt.date | None
) -> tuple[dt.datetime, dt.datetime]:
    """The instants of the business days ``date_from`` … ``date_to`` (included)."""
    zone = business_zone()
    last = date_to or date_from
    return engine.midnight(date_from, zone), engine.midnight(
        last + dt.timedelta(days=1), zone
    )


# ── Who sees what ────────────────────────────────────────────────────────────────────────────


def own_staff_id(ctx: OperationContext) -> UUID | None:
    member = own_member(ctx)
    return member.id if member else None


def sees_everyone(ctx: OperationContext) -> bool:
    return ctx.has(VIEW_ALL)


def visible(ctx: OperationContext, rows: QuerySet) -> QuerySet:
    """``rows`` the caller may see: all of them, or those of their own staff record."""
    if sees_everyone(ctx):
        return rows
    own = own_staff_id(ctx)
    return rows.filter(staff_id=own) if own else rows.none()


def sees_member(ctx: OperationContext, staff_id: UUID) -> bool:
    """Whether the caller may see the appointments of the professional ``staff_id``."""
    return sees_everyone(ctx) or staff_id == own_staff_id(ctx)


def may_change(ctx: OperationContext, staff_id: UUID | None) -> bool:
    return ctx.has(CHANGE_ALL) or (
        ctx.has(CHANGE_OWN) and staff_id is not None and staff_id == own_staff_id(ctx)
    )


def may_book_for(ctx: OperationContext, staff_id: UUID | None) -> bool:
    return ctx.has(ADD_ALL) or (
        ctx.has(ADD_OWN) and staff_id is not None and staff_id == own_staff_id(ctx)
    )


# ── Appointments ─────────────────────────────────────────────────────────────────────────────


def appointments() -> QuerySet[Appointment]:
    return Appointment.objects.filter(deleted_at__isnull=True).prefetch_related("lines")


def find_appointment(
    ctx: OperationContext,
    appointment_id: UUID | None,
    number: str | None,
    *,
    lock: bool = False,
) -> Appointment:
    """The live appointment named by id or number that the caller may see (``NotFound`` otherwise)."""
    rows = visible(ctx, Appointment.objects.filter(deleted_at__isnull=True))
    rows = (
        rows.filter(pk=appointment_id)
        if appointment_id
        else rows.filter(number__iexact=number or "")
    )
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = rows.first()
    if found is None:
        raise NotFound(
            str(APPOINTMENT_NOT_FOUND), code="appointment.appointment_not_found"
        )
    return found


def _lines(appointment: Appointment) -> list[dict]:
    return [
        {
            "service_id": line.service_id,
            "name": line.name,
            "price": line.price,
            "duration_minutes": line.duration_minutes,
        }
        for line in appointment.lines.all()
    ]


def row(appointment: Appointment) -> dict:
    """An ``AppointmentRow``: what the agenda lists (no contact, no notes), on the business's clock."""
    zone = business_zone()
    lines = _lines(appointment)
    return {
        "id": appointment.id,
        "number": appointment.number,
        "customer_id": appointment.customer_id,
        "customer_name": appointment.customer_name,
        "staff_id": appointment.staff_id,
        "staff_name": appointment.staff_name,
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
        "source": appointment.source,
        "services": lines,
        "service_names": ", ".join(line["name"] for line in lines),
        "total": sum(line["price"] for line in lines),
        "booked_by_customer": appointment.source in CUSTOMER_SOURCES,
        "sale_id": appointment.sale_id,
        "order_id": appointment.order_id,
        "recurring_id": appointment.recurring_id,
        "occurrence_date": appointment.occurrence_date,
    }


def detail(appointment: Appointment) -> dict:
    """An ``AppointmentOut``: everything, contact and notes included."""
    return {
        **row(appointment),
        "customer_phone": appointment.customer_phone,
        "customer_email": appointment.customer_email,
        "notes": appointment.notes,
        "internal_notes": appointment.internal_notes,
        "cancelled_at": appointment.cancelled_at,
        "cancellation_reason": appointment.cancellation_reason,
        "cancelled_by_customer": appointment.cancelled_by_customer,
        "charged_at": appointment.charged_at,
        "created_at": appointment.created_at,
        "updated_at": appointment.updated_at,
    }


def load_detail(appointment_id: UUID) -> dict:
    return detail(Appointment.objects.prefetch_related("lines").get(pk=appointment_id))


APPOINTMENT_ORDER = {
    "start": ("start",),
    "number": ("number",),
    "customer_name": ("customer_name",),
    "staff_name": ("staff_name",),
    "status": ("status",),
}


def _sorted(
    rows: QuerySet, sort: str, order: dict, default: tuple[str, ...]
) -> QuerySet:
    key = sort.lstrip("-")
    columns = order.get(key, default)
    prefix = "-" if sort.startswith("-") else ""
    return rows.order_by(*(f"{prefix}{column}" for column in columns), f"{prefix}id")


def _page(rows: QuerySet, limit: int, offset: int, out) -> dict:
    return {
        "rows": [out(item) for item in rows[offset : offset + limit]],
        "total": rows.count(),
        "limit": limit,
        "offset": offset,
    }


@operation(
    "appointment.appointment.list",
    kind="query",
    permission=VIEW_OWN,
    input=AppointmentListIn,
    output=AppointmentPage,
    expose_api=True,
    ai={
        "description": "List the appointments of one business day or a range of days (on the business's clock), "
        "with customer, services, professional, status and whether they are charged; filter by professional (name), "
        "status, customer or a search text. Contact details and notes are not included."
    },
)
def list_appointments(ctx: OperationContext, params: AppointmentListIn) -> dict:
    start, end = day_bounds(params.date_from, params.date_to)
    rows = visible(ctx, appointments()).filter(start__gte=start, start__lt=end)
    if params.staff_id or params.staff:
        rows = rows.filter(staff=resolve_member(params.staff_id, params.staff))
    if params.unassigned is not None:
        rows = rows.filter(staff__isnull=params.unassigned)
    if params.customer_id:
        rows = rows.filter(customer_id=params.customer_id)
    if params.status:
        rows = rows.filter(status=params.status)
    if params.search:
        text = params.search
        named = AppointmentService.objects.filter(
            appointment=OuterRef("pk"), name__icontains=text
        )
        rows = rows.filter(
            Q(number__icontains=text) | Q(customer_name__icontains=text) | Exists(named)
        )
    page = _page(
        _sorted(rows, params.sort, APPOINTMENT_ORDER, ("start",)),
        params.limit,
        params.offset,
        row,
    )
    return {**page, "timezone": zone_name()}


@operation(
    "appointment.appointment.get",
    kind="query",
    permission=VIEW_OWN,
    input=AppointmentRefIn,
    output=AppointmentOut,
    expose_api=True,
    ai={
        "description": "Get one appointment by its id or its number (APT-…), with contact, notes and charge."
    },
)
def get_appointment(ctx: OperationContext, data: AppointmentRefIn) -> dict:
    return detail(find_appointment(ctx, data.id, data.number))


@operation(
    "appointment.appointment.history",
    kind="query",
    permission=VIEW_OWN,
    input=HistoryIn,
    output=HistoryPage,
    expose_api=True,
    ai={
        "description": "The history of one appointment: every change, when, who did it (or that the customer asked), "
        "and what changed (time, professional, service, status, charge)."
    },
)
def appointment_history(ctx: OperationContext, data: HistoryIn) -> dict:
    appointment = find_appointment(ctx, data.id, data.number)
    rows = History.objects.filter(appointment=appointment).order_by("at", "id")

    def out(line: History) -> dict:
        return {
            "id": line.id,
            "action": line.action,
            "at": line.at.astimezone(business_zone()),
            "actor": line.actor,
            "by_customer": line.by_customer,
            "reason": line.reason,
            "old_value": line.old_value,
            "new_value": line.new_value,
        }

    return _page(rows, data.limit, data.offset, out)


@operation(
    "appointment.appointment.list_for_customer",
    kind="query",
    permission=VIEW_OWN,
    input=ForCustomerIn,
    output=VisitPage,
    expose_api=True,
    ai={
        "description": "A customer's appointments, the newest first (named by her name, phone or email), with "
        "services, professional, status and the visit's notes (the internal one may hold a colour formula)."
    },
)
def list_for_customer(ctx: OperationContext, params: ForCustomerIn) -> dict:
    customer = find_customer(
        params.customer_id, params.customer, live=params.customer_id is None
    )
    rows = (
        visible(ctx, appointments()).filter(customer=customer).order_by("-start", "-id")
    )
    return _page(
        rows,
        params.limit,
        params.offset,
        lambda item: {
            **row(item),
            "notes": item.notes,
            "internal_notes": item.internal_notes,
        },
    )


@operation(
    "appointment.appointment.count_active_for_service",
    kind="query",
    permission=VIEW_OWN,
    input=CountForServiceIn,
    output=CountOut,
    expose_api=True,
    ai={
        "description": "How many upcoming live appointments (pending or confirmed) carry a service, and when the "
        "first one is: what to warn about before archiving the service."
    },
)
def count_active_for_service(ctx: OperationContext, data: CountForServiceIn) -> dict:
    service = find_service(data.service_id, data.service)
    rows = (
        appointments()
        .filter(status__in=MOVABLE, start__gte=now(), lines__service=service)
        .distinct()
    )
    first = rows.order_by("start", "id").first()
    return {
        "count": rows.count(),
        "earliest": first.start.astimezone(business_zone()) if first else None,
    }


@operation(
    "appointment.appointment.count_to_confirm",
    kind="query",
    permission=VIEW_OWN,
    input=NoIn,
    output=CountOut,
    expose_api=True,
    ai={
        "description": "How many upcoming appointments are still pending: bookings to confirm."
    },
)
def count_to_confirm(ctx: OperationContext, data: NoIn) -> dict:
    rows = visible(ctx, appointments()).filter(status=S.PENDING, start__gte=now())
    first = rows.order_by("start", "id").first()
    return {
        "count": rows.count(),
        "earliest": first.start.astimezone(business_zone()) if first else None,
    }


# ── The agenda's lanes ───────────────────────────────────────────────────────────────────────


def takes_bookings(member: Member) -> bool:
    return member.status == Member.Status.ACTIVE and member.is_bookable


@operation(
    "appointment.agenda.lanes",
    kind="query",
    permission=VIEW_OWN,
    input=LanesIn,
    output=LanesOut,
    expose_api=True,
    ai={
        "description": "The rows of the agenda by professional for some days: the bookable team, then whoever no "
        "longer takes bookings but still has appointments those days, and how many appointments have no professional."
    },
)
def agenda_lanes(ctx: OperationContext, data: LanesIn) -> dict:
    start, end = day_bounds(data.date_from, data.date_to)
    in_range = visible(ctx, appointments()).filter(start__gte=start, start__lt=end)
    own = own_staff_id(ctx)

    def lane(member: Member) -> dict:
        return {
            "staff_id": member.id,
            "name": member.full_name,
            "color": member.color,
            "takes_bookings": takes_bookings(member),
        }

    if sees_everyone(ctx):
        bookable = list(
            Member.objects.filter(
                status=Member.Status.ACTIVE, is_bookable=True
            ).order_by("first_name", "last_name", "id")
        )
        shown = {member.id for member in bookable}
        kept = Member.objects.filter(
            pk__in=in_range.exclude(staff__isnull=True).values("staff_id")
        ).exclude(pk__in=shown)
        members = bookable + list(kept.order_by("first_name", "last_name", "id"))
        unassigned = in_range.filter(staff__isnull=True).count()
    else:
        members = list(Member.objects.filter(pk=own)) if own else []
        unassigned = 0
    return {
        "rows": [lane(member) for member in members],
        "unassigned": unassigned,
        "own_staff_id": own,
        "sees_everyone": sees_everyone(ctx),
        "timezone": zone_name(),
    }


# ── What a booking is made of ────────────────────────────────────────────────────────────────


def resolve_services(refs: list[ServiceRefIn]) -> list[Service]:
    """The services named, in order: each offered and bookable (409 ``appointment.service_not_bookable``)."""
    services = []
    for ref in refs:
        try:
            service = find_service(ref.service_id, ref.service)
        except NotFound:
            if ref.service_id is not None:
                raise
            # Named, it may be an archived one: say so, not «does not exist».
            service = find_service(None, ref.service, archived=True)
        if not (service.is_active and service.is_bookable):
            raise Conflict(
                str(SERVICE_NOT_BOOKABLE) % {"name": service.name},
                code="appointment.service_not_bookable",
            )
        services.append(service)
    return services


def _assignments(services: list[Service]) -> QuerySet[Assignment]:
    return Assignment.objects.filter(
        service__in=services,
        is_active=True,
        member__status=Member.Status.ACTIVE,
        member__is_bookable=True,
    )


def bookable_members(services: list[Service]) -> list[Member]:
    """Whoever may do every service: its assigned professionals, or the bookable team when nobody is."""
    team = Member.objects.filter(status=Member.Status.ACTIVE, is_bookable=True)
    assigned = _assignments(services)
    for service in services:
        ids = [a.member_id for a in assigned if a.service_id == service.id]
        if ids:
            team = team.filter(pk__in=ids)
    return list(team.order_by("first_name", "last_name", "id")[:MAX_PROFESSIONALS])


def check_member(member: Member, services: list[Service]) -> None:
    """``member`` takes bookings and may do every service (409 otherwise)."""
    if not takes_bookings(member):
        raise Conflict(
            str(STAFF_NOT_BOOKABLE) % {"name": member.full_name},
            code="appointment.staff_not_bookable",
        )
    assigned = list(_assignments(services))
    for service in services:
        ids = {a.member_id for a in assigned if a.service_id == service.id}
        if ids and member.id not in ids:
            raise Conflict(
                str(STAFF_NOT_ELIGIBLE)
                % {"name": member.full_name, "service": service.name},
                code="appointment.staff_not_eligible",
            )


def lines_for(member: Member | None, services: list[Service]) -> list[dict]:
    """Each service as the booking freezes it: its name, and the professional's own price and length if set."""
    own = (
        {
            a.service_id: a
            for a in Assignment.objects.filter(
                member=member, service__in=services, is_active=True
            )
        }
        if member
        else {}
    )
    out = []
    for position, service in enumerate(services):
        assignment = own.get(service.id)
        out.append(
            {
                "service": service,
                "name": service.name,
                "price": assignment.custom_price
                if assignment and assignment.custom_price is not None
                else service.price,
                "duration_minutes": (
                    assignment.custom_duration
                    if assignment and assignment.custom_duration is not None
                    else service.duration_minutes
                ),
                "position": position,
            }
        )
    return out


# ── The agenda the rules judge ───────────────────────────────────────────────────────────────


def reader(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the hours of Schedules and Staff (booking needs no right in those apps)."""
    return replace(ctx, permissions=ctx.permissions | {"schedule.view", "staff.view"})


def _chunks(date_from: dt.date, date_to: dt.date, size: int):
    start = date_from
    while start <= date_to:
        end = min(date_to, start + dt.timedelta(days=size - 1))
        yield start, end
        start = end + dt.timedelta(days=1)


def business_days(ctx: OperationContext, date_from: dt.date, date_to: dt.date) -> dict:
    """The business's hours of ``date_from - 1`` … ``date_to`` (the eve too: its overnight tail)."""
    out = {}
    for start, end in _chunks(date_from - dt.timedelta(days=1), date_to, HOURS_CHUNK):
        hours = hours_for_range(reader(ctx), HoursRangeIn(date_from=start, date_to=end))
        for day in hours.days:
            out[day.date] = engine.BusinessDay(
                day.date,
                restricted=day.source != "none",
                spans=tuple((span.start, span.end) for span in day.spans),
            )
    return out


def staff_days(
    ctx: OperationContext, member: Member, date_from: dt.date, date_to: dt.date
) -> dict:
    out = {}
    for start, end in _chunks(date_from, date_to, STAFF_CHUNK):
        answer = member_availability(
            reader(ctx),
            AvailabilityIn(member_id=member.id, date_from=start, date_to=end),
        )
        for day in answer.days:
            out[day.date] = engine.StaffDay(
                day.date,
                has_schedule=day.schedule_id is not None,
                available=tuple((span.start, span.end) for span in day.available),
                absences=tuple(
                    (None, None)
                    if absence.is_full_day
                    else (absence.start_time, absence.end_time)
                    for absence in day.time_off
                ),
            )
    return out


def load_agenda(
    ctx: OperationContext,
    member: Member | None,
    date_from: dt.date,
    date_to: dt.date,
    *,
    exclude: tuple = (),
    settings: Settings | None = None,
) -> engine.Agenda:
    """Everything the rules need about ``member`` (or the business alone) from ``date_from`` to ``date_to``."""
    zone = business_zone()
    start, end = day_bounds(
        date_from - dt.timedelta(days=1), date_to + dt.timedelta(days=1)
    )
    blocks = BlockedTime.objects.filter(start__lt=end, end__gt=start)
    blocks = (
        blocks.filter(Q(staff__isnull=True) | Q(staff=member))
        if member
        else blocks.filter(staff__isnull=True)
    )
    busy = []
    if member is not None:
        busy = [
            engine.Period(
                item.start,
                item.end,
                id=item.id,
                label=f"{item.number} {item.customer_name}",
            )
            for item in appointments()
            .filter(staff=member, status__in=BUSY, start__lt=end, end__gt=start)
            .exclude(pk__in=exclude)
            .order_by("start", "id")
        ]
    return engine.Agenda(
        zone=zone,
        rules=rules_of(settings or current_settings()),
        business=business_days(ctx, date_from, date_to),
        staff=staff_days(ctx, member, date_from, date_to) if member else None,
        blocks=[
            engine.Period(block.start, block.end, id=block.id, label=block.title)
            for block in blocks
        ],
        busy=busy,
    )


def conflicts_of(
    agenda: engine.Agenda, start: dt.datetime, end: dt.datetime
) -> list[dict]:
    rows = appointments().filter(
        pk__in=[period.id for period in engine.overlapping(agenda, start, end)]
    )
    zone = business_zone()
    return [
        {
            "id": item.id,
            "number": item.number,
            "customer_name": item.customer_name,
            "start": item.start.astimezone(zone),
            "end": item.end.astimezone(zone),
        }
        for item in rows.order_by("start", "id")
    ]


def _who_and_how_long(
    services_refs, staff_id, staff, minutes
) -> tuple[list[Service], list[Member], dict]:
    """The services, the professionals to look at and each one's length (``minutes`` wins)."""
    services = resolve_services(services_refs) if services_refs else []
    if staff_id or staff:
        members = [resolve_member(staff_id, staff)]
    elif services:
        members = bookable_members(services)
    else:
        members = list(
            Member.objects.filter(
                status=Member.Status.ACTIVE, is_bookable=True
            ).order_by("first_name", "last_name", "id")[:MAX_PROFESSIONALS]
        )
    lengths = {
        member.id: minutes
        or sum(line["duration_minutes"] for line in lines_for(member, services))
        for member in members
    }
    return services, members, lengths


@operation(
    "appointment.availability.slots",
    kind="query",
    permission="appointment.view_schedule",
    input=SlotsIn,
    output=SlotsOut,
    expose_api=True,
    ai={
        "description": "The free times of a business day to book some services (or a length), for one professional "
        "(by name) or for anybody who does them: each time says which professionals are free. It crosses the "
        "opening hours (Schedules), each professional's shift and time off (Staff), blocked time and the appointments "
        "already booked. for_customer=true when the customer books herself (the minimum notice applies)."
    },
)
def availability_slots(ctx: OperationContext, data: SlotsIn) -> dict:
    services, members, lengths = _who_and_how_long(
        data.service_refs(), data.staff_id, data.staff, data.duration_minutes
    )
    settings = current_settings()
    moment = now()
    found: dict[dt.datetime, dict] = {}
    for member in members:
        agenda = load_agenda(
            ctx,
            member,
            data.date,
            data.date,
            exclude=(data.exclude_id,),
            settings=settings,
        )
        for slot in engine.slots(
            agenda,
            data.date,
            lengths[member.id],
            now=moment,
            customer=data.for_customer,
        ):
            entry = found.setdefault(
                slot.start,
                {
                    "start": slot.start,
                    "end": slot.end,
                    "within_notice": slot.within_notice,
                    "staff_ids": [],
                },
            )
            entry["staff_ids"].append(member.id)
    if not members:
        agenda = load_agenda(ctx, None, data.date, data.date, settings=settings)
        minutes = (
            data.duration_minutes
            or sum(s.duration_minutes for s in services)
            or settings.default_duration
        )
        for slot in engine.slots(
            agenda, data.date, minutes, now=moment, customer=data.for_customer
        ):
            found[slot.start] = {
                "start": slot.start,
                "end": slot.end,
                "within_notice": slot.within_notice,
                "staff_ids": [],
            }
    zone = business_zone()
    duration = (
        lengths[members[0].id]
        if len(members) == 1
        else data.duration_minutes
        or sum(s.duration_minutes for s in services)
        or settings.default_duration
    )
    return {
        "date": data.date,
        "timezone": zone_name(),
        "duration_minutes": duration,
        "slots": [
            {
                **entry,
                "start": entry["start"].astimezone(zone),
                "end": entry["end"].astimezone(zone),
            }
            for _, entry in sorted(found.items())
        ],
    }


@operation(
    "appointment.availability.check",
    kind="query",
    permission="appointment.view_schedule",
    input=CheckIn,
    output=CheckOut,
    expose_api=True,
    ai={
        "description": "Whether a time can be booked (for a professional, by name, or the business alone) and why not: "
        "invalid_start, in_past, too_soon, too_far, outside_schedule (the business is shut), outside_staff_hours (the "
        "professional does not work then or is off), blocked or overlap (with the appointments it overlaps). The same "
        "rules a booking applies."
    },
)
def availability_check(ctx: OperationContext, data: CheckIn) -> dict:
    start = read_moment(data.start, "start")
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else None
    )
    refs = data.service_refs()
    services = resolve_services(refs) if refs else []
    minutes = data.duration_minutes or sum(
        line["duration_minutes"] for line in lines_for(member, services)
    )
    end = start + dt.timedelta(minutes=minutes)
    zone = business_zone()
    agenda = load_agenda(
        ctx,
        member,
        engine.wall(start, zone).date(),
        engine.wall(end, zone).date(),
        exclude=(data.exclude_id,),
    )
    code = engine.verdict(agenda, start, end, now=now(), customer=data.for_customer)
    return {
        "available": code is None,
        "code": code,
        "message": verdict_message(code) if code else "",
        # Whose appointments they are only for who may see that agenda: a colleague's time is just taken.
        "conflicts": conflicts_of(agenda, start, end) if member and sees_member(ctx, member.id) else [],
    }


# ── Blocks ───────────────────────────────────────────────────────────────────────────────────


def blocked_out(block: BlockedTime) -> dict:
    zone = business_zone()
    return {
        "id": block.id,
        "title": block.title,
        "block_type": block.block_type,
        "start": block.start.astimezone(zone),
        "end": block.end.astimezone(zone),
        "all_day": block.all_day,
        "staff_id": block.staff_id,
        "staff_name": block.staff.full_name if block.staff else "",
        "reason": block.reason,
    }


@operation(
    "appointment.blocked_time.list",
    kind="query",
    permission="appointment.view_schedule",
    input=BlockedTimeListIn,
    output=BlockedTimePage,
    expose_api=True,
    ai={
        "description": "The blocked periods (holidays, a professional's break) that touch some business days."
    },
)
def list_blocked_times(ctx: OperationContext, params: BlockedTimeListIn) -> dict:
    start, end = day_bounds(params.date_from, params.date_to)
    rows = BlockedTime.objects.select_related("staff").filter(
        start__lt=end, end__gt=start
    )
    if params.staff_id:
        rows = rows.filter(Q(staff__isnull=True) | Q(staff_id=params.staff_id))
    return _page(rows.order_by("start", "id"), params.limit, params.offset, blocked_out)


# ── Series ───────────────────────────────────────────────────────────────────────────────────


def series_with_lines() -> QuerySet[Recurring]:
    """The series with the services they book (what ``series_out`` shows)."""
    return Recurring.objects.prefetch_related("lines__service")


def series_rows(ctx: OperationContext) -> QuerySet[Recurring]:
    return visible(ctx, series_with_lines().filter(deleted_at__isnull=True))


def find_series(
    ctx: OperationContext, series_id: UUID, *, lock: bool = False, rows=None
) -> Recurring:
    """The live series the caller may see (``NotFound`` otherwise). It comes from ``rows`` when given (e.g.
    ``series_with_lines()``, what its detail shows): one read, so a deletion committed meanwhile is either
    not seen yet or not found, never a series that vanished or changed between two reads."""
    found_in = Recurring.objects.all() if rows is None else rows
    rows = visible(ctx, found_in.filter(deleted_at__isnull=True, pk=series_id))
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = rows.first()
    if found is None:
        raise NotFound(str(RECURRING_NOT_FOUND), code="appointment.recurring_not_found")
    return found


def pattern_of(series: Recurring) -> engine.Pattern:
    return engine.Pattern(
        series.frequency,
        series.day_of_week,
        series.start_date,
        series.end_date,
        series.max_occurrences,
    )


def series_out(series: Recurring) -> dict:
    lines = [
        {"service_id": line.service_id, "name": line.service.name}
        for line in series.lines.all()
    ]
    return {
        "id": series.id,
        "customer_id": series.customer_id,
        "customer_name": series.customer_name,
        "staff_id": series.staff_id,
        "staff_name": series.staff_name,
        "services": lines,
        "service_names": ", ".join(line["name"] for line in lines),
        "frequency": series.frequency,
        "day_of_week": series.day_of_week,
        "time": series.time,
        "duration_minutes": series.duration_minutes,
        "start_date": series.start_date,
        "end_date": series.end_date,
        "max_occurrences": series.max_occurrences,
        "is_active": series.is_active,
        "split_from_id": series.split_from_id,
        "created_at": series.created_at,
    }


def load_series(series_id: UUID) -> dict:
    return series_out(series_with_lines().get(pk=series_id))


RECURRING_ORDER = {
    "customer_name": ("customer_name",),
    "staff_name": ("staff_name",),
    "start_date": ("start_date",),
    "time": ("time",),
}


@operation(
    "appointment.recurring.list",
    kind="query",
    permission=VIEW_OWN,
    input=RecurringListIn,
    output=RecurringPage,
    expose_api=True,
    ai={
        "description": "List the repeating appointments (series) with customer, services, professional, rule and "
        "whether they are active; search by a name, filter by active, repetition or professional."
    },
)
def list_series(ctx: OperationContext, params: RecurringListIn) -> dict:
    rows = series_rows(ctx)
    if params.search:
        text = params.search
        rows = rows.filter(
            Q(customer_name__icontains=text)
            | Q(staff_name__icontains=text)
            | Q(lines__service__name__icontains=text)
        ).distinct()
    if params.is_active is not None:
        rows = rows.filter(is_active=params.is_active)
    if params.frequency:
        rows = rows.filter(frequency=params.frequency)
    if params.staff_id:
        rows = rows.filter(staff_id=params.staff_id)
    return _page(
        _sorted(rows, params.sort, RECURRING_ORDER, ("customer_name",)),
        params.limit,
        params.offset,
        series_out,
    )


def series_reach(series: Recurring, from_date: dt.date) -> tuple[int, int]:
    """``(upcoming, charged)``: the live appointments of the series from ``from_date`` on, and how many are charged."""
    start, _ = day_bounds(from_date, from_date)
    rows = appointments().filter(
        recurring=series, status__in=MOVABLE, start__gte=max(start, now())
    )
    counts = rows.aggregate(
        upcoming=Count("id"), charged=Count("id", filter=Q(sale_id__isnull=False))
    )
    return counts["upcoming"], counts["charged"]


@operation(
    "appointment.recurring.get",
    kind="query",
    permission=VIEW_OWN,
    input=RecurringGetIn,
    output=RecurringDetailOut,
    expose_api=True,
    ai={
        "description": "One repeating appointment with its next date and how many booked appointments an edit from a "
        "date would reach (and how many of those are charged, which an edit never touches)."
    },
)
def get_series(ctx: OperationContext, data: RecurringGetIn) -> dict:
    series = find_series(ctx, data.id, rows=series_with_lines())
    dates, upcoming_date = engine.dates(pattern_of(series), until=today())
    remaining = [day for day in dates if day >= today()]
    next_date = remaining[0] if remaining else upcoming_date
    upcoming, charged = series_reach(series, data.from_date or today())
    return {
        **series_out(series),
        "next_date": next_date,
        "upcoming": upcoming,
        "charged": charged,
    }


# ── Settings ─────────────────────────────────────────────────────────────────────────────────


@operation(
    "appointment.settings.get",
    kind="query",
    permission=VIEW_OWN,
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The booking rules: default length, minimum notice and maximum advance, overlaps, the "
        "customer's cancellation policy, the calendar window, the slot interval and whether the customer's own "
        "bookings are born confirmed; and the business's time zone."
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_out(current_settings())
