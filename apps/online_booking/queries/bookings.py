"""The inbox over the diary's online appointments: which ones the caller sees (the diary's rule, ``APPOINTMENTS``), their
list, how a booking is named (its number, or the customer and the day) and one of them."""

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.appointment.models.appointments import Appointment, AppointmentService
from apps.appointment.queries.business import day_bounds, now
from apps.appointment.queries.ownership import APPOINTMENTS
from apps.customer.models import Customer
from apps.customer.phones import candidates
from apps.customer.queries.reads import business_country
from apps.customer.queries.contact import searched, sees_contact
from apps.customer.search import normalize
from apps.online_booking.models import Booking
from apps.online_booking.schemas import BookingListIn, BookingOut, BookingPage, BookingRefIn
from base.business import business_zone
from base.ordering import list_order
from base.text_search import contains_text

VIEW = "online_booking.view_booking"
ONLINE = Appointment.Source.ONLINE
S = Appointment.Status
#: How many bookings an ambiguous reference names back.
MAX_MATCHES = 5

BOOKING_NOT_FOUND = _("That booking does not exist or its link is no longer valid.")
BOOKING_AMBIGUOUS = _(
    "Several online bookings fit “%(reference)s”: %(matches)s. Say which one by its number."
)


def online(ctx: OperationContext) -> QuerySet[Appointment]:
    """The live online appointments the caller may see (the diary's rule), with their lines."""
    rows = APPOINTMENTS.visible(ctx).filter(deleted_at__isnull=True, source=ONLINE)
    return rows.prefetch_related("lines")


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
        AppointmentService.objects.filter(contains_text(text, "name"), appointment=OuterRef("pk"))
    )


def _person(ctx: OperationContext, text: str) -> Q:
    """The appointments whose customer is ``text``: part of her name (with or without accents) and, for whoever sees
    the customers' contact details, her phone or her email: a search by them would tell whose they are."""
    seen = sees_contact(ctx)
    if seen and "@" in text:
        return Q(customer_email__iexact=text)
    found = contains_text(text, "customer_name") | Q(customer__in=searched(ctx, Customer.objects.all(), normalize(text)))
    numbers = candidates(text, business_country(ctx)) if seen else []
    return found | Q(customer_phone__in=numbers) if numbers else found


def _searched(ctx: OperationContext, rows: QuerySet, text: str) -> QuerySet:
    digits = "".join(char for char in text if char.isdigit())
    found = contains_text(text, "number") | _person(ctx, text) | contains_text(text, "staff_name") | _with_service(text)
    if sees_contact(ctx):
        found |= contains_text(text, "customer_email")
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
        "asks": {
            "en": (
                "which bookings have customers made themselves this week?",
                "show me the self-booking inbox",
            ),
            "es": (
                "¿qué reservas han hecho las clientas desde internet?",
                "enséñame la bandeja de reservas de internet",
            ),
        },
        "description": "List the bookings customers made online (appointments of the diary booked through the "
        "booking page), the newest first: search by number, customer (her phone or email, for whoever sees them), "
        "service or professional, and "
        "filter by status (pending = waiting to be confirmed), day or professional."
    },
)
def list_bookings(ctx: OperationContext, params: BookingListIn) -> dict:
    rows = _with_page(online(ctx))
    if params.search:
        rows = _searched(ctx, rows, params.search)
    if params.number:
        rows = rows.filter(contains_text(params.number, "number"))
    if params.customer_name:
        rows = rows.filter(_person(ctx, params.customer_name))
    if params.service:
        rows = rows.filter(_with_service(params.service))
    if params.staff_name:
        rows = rows.filter(contains_text(params.staff_name, "staff_name"))
    if params.status:
        rows = rows.filter(status=params.status)
    if params.staff_id:
        rows = rows.filter(staff_id=params.staff_id)
    if params.date_from or params.date_to:
        start, end = day_bounds(
            params.date_from or params.date_to, params.date_to or params.date_from
        )
        rows = rows.filter(start__gte=start, start__lt=end)
    rows = rows.order_by(*list_order(SORT_COLUMNS[params.sort], descending=params.dir == "desc"))
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
    rows = rows.filter(_person(ctx, ref.customer))
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
        "asks": {
            "en": (
                "what did Ainhoa book by herself for Wednesday?",
                "who made the self-booking APT-20261120-0004?",
            ),
            "es": (
                "¿qué ha reservado Ainhoa por internet para el miércoles?",
                "¿quién hizo la reserva de internet APT-20261120-0004?",
            ),
        },
        "description": "One online booking, by its number (APT-…) or as a person says it: the customer (name, phone "
        "or email) and the day (e.g. Ana's booking of tomorrow); without a day, her next one."
    },
)
def get_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    # The booking as found: reading it again by its id raised DoesNotExist (a 500) on a deletion in between.
    return detail(find_booking(ctx, data))
