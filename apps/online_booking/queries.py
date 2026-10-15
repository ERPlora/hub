"""Read operations of the online booking app (``READ ONLY``), and the helpers services.py reuses inside its own
transaction: the page's settings, the inbox over the diary's online appointments, how a booking is named,
the public context and the visitor's fingerprint.

- **A booking is an appointment** of Citas with ``source = "online"``: the inbox reads the diary's table (Citas
  is a requirement) and who sees what is the diary's rule (``appointment.queries.visible``: the employee sees
  her own agenda).
- **The public reads** (``online_booking.public``) answer only while the page is on, and ask the other apps
  with ``delegated(ctx)``: the same context with exactly what they need of Citas, Clientes, Servicios,
  Horarios and Personal (as ``appointment.queries.reader`` does), never a role's.
- Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break.
"""

import datetime as dt
import hashlib
import hmac
from dataclasses import replace

from django.conf import settings as django_settings
from django.db.models import Exists, F, OuterRef, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import get, operation

from apps.appointment.models import Appointment, AppointmentService
from apps.appointment.queries import (
    bookable_members,
    check_member,
    day_bounds,
    now,
    visible,
    zone_name,
)
from apps.appointment.queries import business_zone
from apps.appointment.queries import current_settings as current_rules
from apps.appointment.schemas import SlotsIn
from apps.customer.phones import candidates
from apps.customer.queries import business_country
from apps.customer.search import normalize
from apps.online_booking.models import Booking, Settings
from apps.online_booking.schemas import (
    BookingListIn,
    BookingOut,
    BookingPage,
    BookingRefIn,
    NoIn,
    PageOut,
    PublicBookingOut,
    PublicServicePage,
    PublicServicesIn,
    PublicSlotsIn,
    PublicSlotsOut,
    SettingsOut,
    TokenIn,
)
from apps.service.models import Service
from apps.service.queries import current_settings as service_settings
from apps.staff.models import Member
from apps.staff.queries import resolve_member

VIEW = "online_booking.view_booking"
PUBLIC = "online_booking.public"
ONLINE = Appointment.Source.ONLINE
S = Appointment.Status
#: Who books when nobody is signed in (the appointment's «created by»; its history says «the customer»).
ONLINE_ACTOR = "online booking"
#: What the public operations need of the other apps, and nothing else: read the agenda and the free times,
#: book and cancel in it, find or create the customer's card, read the catalog, the hours and the team.
DELEGATED = frozenset(
    {
        "appointment.view_appointment",
        "appointment.view_own_appointment",
        "appointment.add_appointment",
        "appointment.add_own_appointment",
        "appointment.change_appointment",
        "appointment.change_own_appointment",
        "appointment.view_schedule",
        "customer.view",
        "customer.manage",
        "service.view_service",
        "schedule.view",
        "staff.view",
    }
)
#: How many bookings an ambiguous reference names back.
MAX_MATCHES = 5

PAGE_DISABLED = _("This business does not take online bookings right now.")
BOOKING_NOT_FOUND = _("That booking does not exist or its link is no longer valid.")
BOOKING_AMBIGUOUS = _(
    "Several online bookings fit “%(reference)s”: %(matches)s. Say which one by its number."
)
SERVICE_NOT_ONLINE = _("“%(name)s” cannot be booked online.")
UNKNOWN_SERVICE_NOT_ONLINE = _("That service cannot be booked online.")
STAFF_CHOICE_DISABLED = _(
    "This business assigns the professional itself: book without choosing one."
)
DEFAULT_TITLE = _("Book an appointment")

_OWN_FIELDS = (
    "is_enabled",
    "page_title",
    "welcome_message",
    "primary_color",
    "logo_url",
    "require_email",
    "max_upcoming_per_customer",
    "allow_staff_selection",
    "allow_notes",
    "confirmation_message",
    "cancellation_policy",
)
#: The diary's rules the page shows and the settings change (Citas' settings).
RULE_FIELDS = (
    "min_booking_notice",
    "max_advance_booking",
    "slot_interval",
    "auto_confirm_online",
    "allow_customer_cancellation",
    "cancellation_notice_hours",
)


# ── Settings and the public context ──────────────────────────────────────────────────────────


def current_settings() -> Settings:
    """The saved settings, or the factory ones (unsaved: the page off) while nobody saved them."""
    return Settings.objects.first() or Settings()


def page_settings(*, lock: bool = False) -> Settings:
    """The settings of a page that takes bookings; 404 ``online_booking.page_disabled`` while it is off.

    ``lock`` takes the settings row until the end of the command's transaction: the public bookings of the hub
    then run one after another, so their limits (per visitor, per business, per mobile) and the card of a new
    mobile are decided on what the previous booking wrote.
    """
    settings = (Settings.objects.select_for_update().first() if lock else Settings.objects.first()) or Settings()
    if not settings.is_enabled:
        raise NotFound(str(PAGE_DISABLED), code="online_booking.page_disabled")
    return settings


def settings_out(own: Settings) -> dict:
    rules = current_rules()
    return {
        **{field: getattr(own, field) for field in _OWN_FIELDS},
        **{field: getattr(rules, field) for field in RULE_FIELDS},
        "timezone": zone_name(),
    }


def delegated(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to do in the other apps what a public operation needs (and only that)."""
    actor = ctx.actor if ctx.actor is not None else ONLINE_ACTOR
    return replace(ctx, actor=actor, permissions=ctx.permissions | DELEGATED)


def hash_token(token: str) -> str:
    """What is kept of the customer's link: its SHA-256, never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()


def _client_address(request) -> str:
    """The visitor's address: the last hop of ``X-Forwarded-For`` (the one the load balancer adds), or the
    socket's when there is no proxy."""
    hops = [
        hop.strip()
        for hop in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if hop.strip()
    ]
    return hops[-1] if hops else request.META.get("REMOTE_ADDR", "")


def visitor_key(ctx: OperationContext) -> str:
    """A fingerprint of who books (HMAC of the address with the secret key): the limits count it, the address
    itself is never kept. Without a request, the actor stands for the visitor."""
    address = _client_address(ctx.request) if ctx.request is not None else ""
    source = address or f"actor:{getattr(ctx.actor, 'pk', ctx.actor)}"
    return hmac.new(
        django_settings.SECRET_KEY.encode(), source.encode(), hashlib.sha256
    ).hexdigest()


# ── The inbox ────────────────────────────────────────────────────────────────────────────────


def online(ctx: OperationContext) -> QuerySet[Appointment]:
    """The live online appointments the caller may see (the diary's rule), with their lines."""
    rows = Appointment.objects.filter(deleted_at__isnull=True, source=ONLINE)
    return visible(ctx, rows).prefetch_related("lines")


def _with_page(rows: QuerySet[Appointment]) -> QuerySet[Appointment]:
    return rows.annotate(
        via_page=Exists(Booking.objects.filter(appointment=OuterRef("pk")))
    )


def row(appointment: Appointment) -> dict:
    """A ``BookingRow`` on the business's clock."""
    zone = business_zone()
    lines = [
        {
            "service_id": line.service_id,
            "name": line.name,
            "price": line.price,
            "duration_minutes": line.duration_minutes,
        }
        for line in appointment.lines.all()
    ]
    via_page = getattr(appointment, "via_page", None)
    if via_page is None:
        via_page = Booking.objects.filter(appointment=appointment).exists()
    return {
        "id": appointment.id,
        "number": appointment.number,
        "customer_id": appointment.customer_id,
        "customer_name": appointment.customer_name,
        "customer_phone": appointment.customer_phone,
        "customer_email": appointment.customer_email,
        "staff_id": appointment.staff_id,
        "staff_name": appointment.staff_name,
        "services": lines,
        "service_names": ", ".join(line["name"] for line in lines),
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
        "total": sum(line["price"] for line in lines),
        "notes": appointment.notes,
        "booked_at": appointment.created_at.astimezone(zone),
        "via_page": via_page,
        "sale_id": appointment.sale_id,
        "order_id": appointment.order_id,
    }


def detail(appointment: Appointment) -> dict:
    return {
        **row(appointment),
        "cancelled_at": appointment.cancelled_at,
        "cancellation_reason": appointment.cancellation_reason,
        "cancelled_by_customer": appointment.cancelled_by_customer,
    }


def load_detail(appointment_id) -> dict:
    return detail(Appointment.objects.prefetch_related("lines").get(pk=appointment_id))


def _with_service(text: str) -> Exists:
    return Exists(
        AppointmentService.objects.filter(
            appointment=OuterRef("pk"), name__icontains=text
        )
    )


def _person(text: str) -> Q:
    """The appointments whose customer is ``text``: part of her name (with or without accents), her phone or
    her email."""
    if "@" in text:
        return Q(customer_email__iexact=text)
    found = Q(customer_name__icontains=text) | Q(
        customer__search_text__contains=normalize(text)
    )
    numbers = candidates(text, business_country())
    return found | Q(customer_phone__in=numbers) if numbers else found


def _searched(rows: QuerySet, text: str) -> QuerySet:
    digits = "".join(char for char in text if char.isdigit())
    found = (
        Q(number__icontains=text)
        | _person(text)
        | Q(customer_email__icontains=text)
        | Q(staff_name__icontains=text)
        | _with_service(text)
    )
    if len(digits) >= 3:
        found |= Q(customer_phone__contains=digits)
    return rows.filter(found)


SORT_COLUMNS = {
    "booked_at": "created_at",
    "start": "start",
    "number": "number",
    "customer_name": "customer_name",
    "staff_name": "staff_name",
    "status": "status",
}


@operation(
    "online_booking.booking.list",
    kind="query",
    permission=VIEW,
    input=BookingListIn,
    output=BookingPage,
    expose_api=True,
    ai={
        "description": "List the bookings customers made online (appointments of the diary booked through the "
        "booking page), the newest first: search by number, customer, phone, email, service or professional, and "
        "filter by status (pending = waiting to be confirmed), day or professional."
    },
)
def list_bookings(ctx: OperationContext, params: BookingListIn) -> dict:
    rows = _with_page(online(ctx))
    if params.search:
        rows = _searched(rows, params.search)
    if params.number:
        rows = rows.filter(number__icontains=params.number)
    if params.customer_name:
        rows = rows.filter(_person(params.customer_name))
    if params.service:
        rows = rows.filter(_with_service(params.service))
    if params.staff_name:
        rows = rows.filter(staff_name__icontains=params.staff_name)
    if params.status:
        rows = rows.filter(status=params.status)
    if params.staff_id:
        rows = rows.filter(staff_id=params.staff_id)
    if params.date_from or params.date_to:
        start, end = day_bounds(
            params.date_from or params.date_to, params.date_to or params.date_from
        )
        rows = rows.filter(start__gte=start, start__lt=end)
    prefix = "-" if params.dir == "desc" else ""
    rows = rows.order_by(f"{prefix}{SORT_COLUMNS[params.sort]}", f"{prefix}id")
    return {
        "rows": [
            row(item) for item in rows[params.offset : params.offset + params.limit]
        ],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _label(appointment: Appointment) -> str:
    when = appointment.start.astimezone(business_zone())
    return f"{appointment.number} {appointment.customer_name} ({when:%d/%m %H:%M})"


def find_booking(ctx: OperationContext, ref: BookingRefIn) -> Appointment:
    """The online booking ``ref`` names, among those the caller may see.

    By id or number; or as a person says it, by the customer and the day (without a day, her next one).
    404 ``online_booking.booking_not_found``; 409 ``online_booking.booking_ambiguous`` naming the candidates.
    """
    rows = online(ctx)
    if ref.id is not None or ref.number is not None:
        found = (
            rows.filter(pk=ref.id)
            if ref.id is not None
            else rows.filter(number__iexact=ref.number)
        ).first()
        if found is None:
            raise NotFound(
                str(BOOKING_NOT_FOUND), code="online_booking.booking_not_found"
            )
        return found
    rows = rows.filter(_person(ref.customer))
    if ref.date is not None:
        start, end = day_bounds(ref.date, ref.date)
        rows = rows.filter(start__gte=start, start__lt=end)
    else:
        rows = rows.filter(start__gte=now(), status__in=(S.PENDING, S.CONFIRMED))
    matches = list(rows.order_by("start", "id")[: MAX_MATCHES + 1])
    if not matches:
        raise NotFound(str(BOOKING_NOT_FOUND), code="online_booking.booking_not_found")
    several = (
        len(matches) > 1
        if ref.date is not None
        else len({item.customer_id for item in matches}) > 1
    )
    if several:
        raise Conflict(
            str(BOOKING_AMBIGUOUS)
            % {
                "reference": ref.customer,
                "matches": ", ".join(_label(item) for item in matches[:MAX_MATCHES]),
            },
            code="online_booking.booking_ambiguous",
        )
    return matches[0]


@operation(
    "online_booking.booking.get",
    kind="query",
    permission=VIEW,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "description": "One online booking, by its number (APT-…) or as a person says it: the customer (name, phone "
        "or email) and the day (e.g. Ana's booking of tomorrow); without a day, her next one."
    },
)
def get_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    return load_detail(find_booking(ctx, data).id)


# ── Settings ─────────────────────────────────────────────────────────────────────────────────


@operation(
    "online_booking.settings.get",
    kind="query",
    permission=VIEW,
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The booking page's settings (on or off, title, texts, colour, logo, email required, choose "
        "the professional, notes, upcoming bookings per customer) and the diary's booking rules it uses (minimum "
        "notice, maximum advance, slot interval, auto-confirm, customer cancellation and its notice)."
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_out(current_settings())


# ── The public page ──────────────────────────────────────────────────────────────────────────


@operation(
    "online_booking.public.page",
    kind="query",
    permission=PUBLIC,
    input=NoIn,
    output=PageOut,
    ai={
        "description": "What the public booking page shows: its title, texts, colour, logo and booking rules."
    },
)
def public_page(ctx: OperationContext, data: NoIn) -> dict:
    own = page_settings()
    rules = current_rules()
    return {
        "title": own.page_title or str(DEFAULT_TITLE),
        "welcome_message": own.welcome_message,
        "primary_color": own.primary_color,
        "logo_url": own.logo_url,
        "require_email": own.require_email,
        "allow_staff_selection": own.allow_staff_selection,
        "allow_notes": own.allow_notes,
        "cancellation_policy": own.cancellation_policy,
        "min_booking_notice": rules.min_booking_notice,
        "max_advance_booking": rules.max_advance_booking,
        "allow_customer_cancellation": rules.allow_customer_cancellation,
        "cancellation_notice_hours": rules.cancellation_notice_hours,
        "timezone": zone_name(),
    }


def online_services() -> QuerySet[Service]:
    """The services a customer may book online: offered, bookable in the diary and marked for online booking."""
    return Service.objects.filter(
        is_active=True, is_bookable=True, allow_online_booking=True
    ).select_related("category")


def services_to_book(ids) -> list[Service]:
    """The services ``ids`` names, in order, each bookable online (409 ``online_booking.service_not_online``)."""
    found = {service.id: service for service in Service.objects.filter(pk__in=ids)}
    bookable = set(online_services().filter(pk__in=ids).values_list("id", flat=True))
    out = []
    for service_id in ids:
        service = found.get(service_id)
        if service is None or service_id not in bookable:
            message = (
                str(SERVICE_NOT_ONLINE) % {"name": service.name}
                if service
                else str(UNKNOWN_SERVICE_NOT_ONLINE)
            )
            raise Conflict(message, code="online_booking.service_not_online")
        out.append(service)
    return out


def chosen_member(own: Settings, staff_id, services: list[Service]) -> Member | None:
    """The professional the customer chose (who must take bookings and do every service), or nobody."""
    if staff_id is None:
        return None
    if not own.allow_staff_selection:
        message = str(STAFF_CHOICE_DISABLED)
        raise InvalidPayload(
            message,
            code="online_booking.staff_choice_disabled",
            fields={"staff_id": message},
        )
    member = resolve_member(staff_id, None)
    check_member(member, services)
    return member


def _professionals(members: list[Member]) -> list[dict]:
    return [{"id": member.id, "name": member.full_name} for member in members]


@operation(
    "online_booking.public.services",
    kind="query",
    permission=PUBLIC,
    input=PublicServicesIn,
    output=PublicServicePage,
    ai={
        "description": "The services the public booking page offers, with price and duration when shown."
    },
)
def public_services(ctx: OperationContext, params: PublicServicesIn) -> dict:
    own = page_settings()
    shown = service_settings()
    rows = online_services()
    if params.search:
        rows = rows.filter(
            Q(name__icontains=params.search)
            | Q(category__name__icontains=params.search)
        )
    rows = rows.order_by(
        F("category__sort_order").asc(nulls_last=True),
        "category__name",
        "sort_order",
        "name",
        "id",
    )

    def out(service: Service) -> dict:
        return {
            "id": service.id,
            "name": service.name,
            "description": service.short_description or service.description,
            "category": service.category.name if service.category else "",
            "price": service.price if shown.show_prices else None,
            "duration_minutes": service.duration_minutes
            if shown.show_duration
            else None,
            "professionals": _professionals(bookable_members([service]))
            if own.allow_staff_selection
            else [],
        }

    return {
        "rows": [
            out(service)
            for service in rows[params.offset : params.offset + params.limit]
        ],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "online_booking.public.slots",
    kind="query",
    permission=PUBLIC,
    input=PublicSlotsIn,
    output=PublicSlotsOut,
    ai={
        "description": "The free times of a day for the services chosen on the public booking page."
    },
)
def public_slots(ctx: OperationContext, data: PublicSlotsIn) -> dict:
    own = page_settings()
    services = services_to_book(data.service_ids)
    member = chosen_member(own, data.staff_id, services)
    slots = get("appointment.availability.slots")
    answer = slots(
        delegated(ctx),
        SlotsIn(
            service_ids=[service.id for service in services],
            date=data.date,
            staff_id=member.id if member else None,
            for_customer=True,
        ),
    )
    names = {
        person.id: person.full_name
        for person in ([member] if member else bookable_members(services))
    }
    return {
        "date": answer.date,
        "timezone": answer.timezone,
        "duration_minutes": answer.duration_minutes,
        "slots": [
            {
                "start": slot.start,
                "end": slot.end,
                "professionals": [
                    {"id": staff_id, "name": names[staff_id]}
                    for staff_id in slot.staff_ids
                    if staff_id in names
                ]
                if own.allow_staff_selection
                else [],
            }
            for slot in answer.slots
        ],
    }


def find_by_token(token: str, *, lock: bool = False) -> Booking:
    """The live booking whose link is ``token`` (404 ``online_booking.booking_not_found`` otherwise)."""
    rows = Booking.objects.select_related("appointment").filter(
        token_hash=hash_token(token), appointment__deleted_at__isnull=True
    )
    if lock:
        rows = rows.select_for_update(of=("self",))
    found = rows.first()
    if found is None:
        raise NotFound(str(BOOKING_NOT_FOUND), code="online_booking.booking_not_found")
    return found


def cancel_until(appointment: Appointment) -> dt.datetime | None:
    """Until when the customer may cancel it herself (the diary's policy); ``None`` when she may not."""
    rules = current_rules()
    if (
        not rules.allow_customer_cancellation
        or appointment.status not in (S.PENDING, S.CONFIRMED)
        or appointment.sale_id
        or appointment.order_id
    ):
        return None
    return (
        appointment.start - dt.timedelta(hours=rules.cancellation_notice_hours)
    ).astimezone(business_zone())


def public_booking_out(appointment: Appointment) -> dict:
    zone = business_zone()
    until = cancel_until(appointment)
    return {
        "number": appointment.number,
        "status": appointment.status,
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "timezone": zone_name(),
        "service_names": ", ".join(line.name for line in appointment.lines.all()),
        "staff_name": appointment.staff_name,
        "can_cancel": until is not None and now() <= until,
        "cancel_until": until,
        "cancellation_policy": current_settings().cancellation_policy,
    }


@operation(
    "online_booking.public.booking",
    kind="query",
    permission=PUBLIC,
    input=TokenIn,
    output=PublicBookingOut,
    ai={
        "description": "The booking behind a customer's personal link, and whether she may still cancel it."
    },
)
def public_booking(ctx: OperationContext, data: TokenIn) -> dict:
    return public_booking_out(find_by_token(data.token).appointment)
