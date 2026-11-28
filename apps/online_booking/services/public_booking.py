"""The public booking (F01): the page's checks, the limits, the customer's card and the booking in the diary."""

import datetime as dt
import secrets

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import get, operation
from live.outbox import record_event

from apps.appointment.models.appointments import Appointment
from apps.appointment.queries.booking import bookable_members
from apps.appointment.queries.business import now
from apps.appointment.schemas import booking as diary_booking
from apps.customer.models import Customer
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries.reads import business_country
from apps.customer.schemas.cards import CustomerIn
from apps.customer.search import normalize
from apps.online_booking.events import BOOKING_CREATED
from apps.online_booking.models import Booking, Settings
from apps.online_booking.queries.bookings import ONLINE, S
from apps.online_booking.queries.offer import chosen_member, services_to_book
from apps.online_booking.queries.settings import page_settings
from apps.online_booking.queries.visitors import PUBLIC, delegated, hash_token, visitor_key
from apps.online_booking.schemas.public import BookedOut, PublicBookIn
from apps.service.models.catalog import Service
from apps.staff.models import Member
from base.business import business_zone

from .bookings import _diary

#: Bookings one visitor (one device) may make in an hour, and the whole business.
VISITOR_PER_HOUR = 5
BUSINESS_PER_HOUR = 100
#: What makes a time taken for a professional (with «anyone», the next one is tried).
TAKEN = frozenset(
    {
        "appointment.slot_taken",
        "appointment.outside_staff_hours",
        "appointment.blocked",
        "appointment.overlap_needs_confirmation",
        "appointment.staff_not_bookable",
        "appointment.staff_not_eligible",
    }
)

TOO_MANY_BOOKINGS = _(
    "Too many bookings from this device in the last hour. Try again later, or call the business."
)
BUSY = _(
    "This business is receiving many online bookings right now. Try again in a few minutes."
)
# Public: it never says how many bookings that mobile holds.
TOO_MANY_UPCOMING = _(
    "This mobile already has upcoming bookings with this business: cancel one, or call the business to book more."
)
TIME_TAKEN = _("That time is no longer free. Pick another one.")
EMAIL_REQUIRED = _("Enter your email: this business needs it to book.")
NOTES_DISABLED = _("This business does not take notes with a booking.")
PHONE_INVALID = _(
    "That mobile is not a valid number. Check it, or type it with its international prefix (for example +44…)."
)
DEFAULT_CONFIRMED = _("Your booking is confirmed. See you soon!")
DEFAULT_PENDING = _(
    "We have received your booking. The business will confirm it shortly."
)


def _refuse_field(message, code: str, field: str) -> None:
    raise InvalidPayload(str(message), code=code, fields={field: str(message)})


def _mobile(ctx: OperationContext, raw: str) -> str:
    try:
        return to_e164(raw, business_country(ctx))
    except InvalidPhone:
        _refuse_field(PHONE_INVALID, "online_booking.phone_invalid", "phone")


def _check_form(own: Settings, data: PublicBookIn) -> None:
    if own.require_email and not data.email:
        _refuse_field(EMAIL_REQUIRED, "online_booking.email_required", "email")
    if data.notes and not own.allow_notes:
        _refuse_field(NOTES_DISABLED, "online_booking.notes_disabled", "notes")


def _check_limits(visitor: str) -> None:
    since = now() - dt.timedelta(hours=1)
    recent = Booking.objects.filter(created_at__gte=since)
    if recent.filter(requester=visitor).count() >= VISITOR_PER_HOUR:
        raise OperationError(
            str(TOO_MANY_BOOKINGS), code="online_booking.too_many_bookings", status=429
        )
    if recent.count() >= BUSINESS_PER_HOUR:
        raise OperationError(str(BUSY), code="online_booking.busy", status=429)


def _card_for(ctx: OperationContext, name: str, phone: str, email: str) -> Customer:
    """The customer's card: the live one with her mobile (her name first), locked; or a new one."""
    # Locked in the read that finds them, in id order as a merge locks them: a merge waits for the booking.
    found = Customer.objects.live().select_for_update().filter(phone=phone).order_by("id").values_list("id", flat=True)
    cards = list(Customer.objects.filter(pk__in=list(found)).order_by("name", "id"))
    wanted = normalize(name)
    card = next((card for card in cards if normalize(card.name) == wanted), cards[0] if cards else None)
    if card is not None:
        return card
    create = get("customer.customer.create")
    created = create(
        ctx, CustomerIn(name=name, phone=phone, email=email, source="website")
    )
    return Customer.objects.get(pk=created.id)


def _check_upcoming(own: Settings, card: Customer, phone: str) -> None:
    upcoming = Appointment.objects.filter(
        Q(customer=card) | Q(customer_phone=phone),
        source=ONLINE,
        deleted_at__isnull=True,
        status__in=(S.PENDING, S.CONFIRMED),
        start__gte=now(),
    ).count()
    if upcoming >= own.max_upcoming_per_customer:
        raise Conflict(
            str(TOO_MANY_UPCOMING),
            code="online_booking.too_many_upcoming",
        )


def _book(
    ctx: OperationContext,
    card: Customer,
    services: list[Service],
    member: Member | None,
    data: PublicBookIn,
) -> Appointment:
    """Books with the professional chosen or, with «anyone», the first one the diary accepts."""
    create = get("appointment.appointment.create")
    refusals: list[Conflict] = []
    for person in [member] if member else bookable_members(services):
        booking = diary_booking.AppointmentCreateIn.model_validate(
            {
                "customer_id": str(card.id),
                "services": [{"service_id": str(service.id)} for service in services],
                "staff_id": str(person.id),
                "start": data.start,
                "notes": data.notes,
                "source": ONLINE,
            }
        )
        try:
            answer = create(ctx, booking)
        except Conflict as refusal:
            if member is not None:
                raise
            refusals.append(refusal)
            continue
        return Appointment.objects.prefetch_related("lines").get(pk=answer.id)
    codes = {refusal.code for refusal in refusals}
    if len(codes) == 1 and not codes & TAKEN:
        raise refusals[0]
    raise Conflict(str(TIME_TAKEN), code="online_booking.time_taken")


@operation(
    "online_booking.public.book",
    kind="command",
    permission=PUBLIC,
    input=PublicBookIn,
    output=BookedOut,
    ai={
        "asks": {
            "en": (
                "book Maite in by herself for a cut on Thursday at 5 pm, mobile 622 000 111",
                "make a self-booking as the customer would, anyone free is fine",
            ),
            "es": (
                "resérvale a Maite por internet un tinte el jueves a las 17:00, móvil 622 000 111",
                "reserva por internet como lo haría la clienta, con cualquiera que esté libre",
            ),
        },
        "description": "Book from the public booking page as the customer: services (their ids, from "
        "online_booking.public.services), a professional or anyone, a free time (one of online_booking.public.slots), "
        "her name and mobile. Hands back the appointment number and her personal link token.",
        "risk": "normal",
    },
)
def public_book(ctx: OperationContext, data: PublicBookIn) -> dict:
    # First: the hub's public bookings wait for each other here (the limits and a new mobile's card).
    own = page_settings(lock=True)
    acting = delegated(ctx)
    services = services_to_book(data.service_ids)
    member = chosen_member(own, data.staff_id, services)
    _check_form(own, data)
    phone = _mobile(ctx, data.phone)
    visitor = visitor_key(ctx)
    _check_limits(visitor)
    card = _card_for(acting, data.name, phone, data.email)
    _check_upcoming(own, card, phone)
    appointment = _book(acting, card, services, member, data)
    if data.email and not appointment.customer_email:
        # Her card has no email: the one she typed is the booking's contact (the card is not changed from here).
        _diary(acting, "appointment.appointment.update", appointment, customer_email=data.email)
        appointment.refresh_from_db()
    token = secrets.token_urlsafe(32)
    Booking.objects.create(
        appointment=appointment, token_hash=hash_token(token), requester=visitor
    )
    record_event(
        acting,
        BOOKING_CREATED,
        {
            "appointment_id": str(appointment.id),
            "number": appointment.number,
            "customer_id": str(appointment.customer_id),
            "start": appointment.start.isoformat(),
        },
    )
    default = DEFAULT_PENDING if appointment.status == S.PENDING else DEFAULT_CONFIRMED
    zone = business_zone()
    return {
        "number": appointment.number,
        "status": appointment.status,
        "start": appointment.start.astimezone(zone),
        "end": appointment.end.astimezone(zone),
        "timezone": getattr(zone, "key", str(zone)),
        "service_names": ", ".join(line.name for line in appointment.lines.all()),
        "staff_name": appointment.staff_name,
        "message": own.confirmation_message or str(default),
        "token": token,
    }
