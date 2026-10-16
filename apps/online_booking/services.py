"""Write operations of the online booking app: one operation = one transaction, with its events in the outbox.

- **The diary does it**: confirming, completing, a no-show, cancelling and deleting a booking are the
  operations of Citas, run by name with the caller's own context (this app's right and the diary's, both).
- **The public booking** checks the page (on, the services online, the professional's choice, the form),
  the limits (per visitor and hour, per business and hour, upcoming per mobile), finds the customer's card by
  her mobile or creates it (``customer.customer.create``), and books with ``appointment.appointment.create``
  (``source = "online"``: the diary's notice, window, no overlap and auto-confirm). With «anyone», each
  professional who does the services is tried in name order, each attempt in its own savepoint. Then the
  link: a random token handed out once, kept as its hash.
- **Every check runs before the first write** or rolls back with it: a refusal leaves no appointment, no
  card, no link and no event.
- The platform's reaction (``SYSTEM``) is run by the outbox relay as the system; it is idempotent.
"""

import datetime as dt
import secrets

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import get, operation
from live.outbox import record_event

from apps.appointment.models import Appointment
from apps.appointment.queries import bookable_members, business_zone, now
from apps.appointment.schemas import AppointmentCreateIn
from apps.appointment.schemas import CancelIn as AppointmentCancelIn
from apps.appointment.schemas import SettingsIn as RulesIn
from apps.customer.models import Customer
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country, find_customer
from apps.customer.schemas import CustomerIn
from apps.customer.search import normalize
from apps.online_booking.events import BOOKING_CREATED, SETTINGS_UPDATED
from apps.online_booking.models import Booking, Settings
from apps.online_booking.queries import (
    ONLINE,
    PUBLIC,
    RULE_FIELDS,
    S,
    chosen_member,
    delegated,
    find_booking,
    find_by_token,
    hash_token,
    load_detail,
    page_settings,
    public_booking_out,
    services_to_book,
    settings_out,
    visitor_key,
)
from apps.online_booking.schemas import (
    BookedOut,
    BookingOut,
    BookingRefIn,
    CancelIn,
    CustomerEventIn,
    DeletedOut,
    PublicBookIn,
    PublicBookingOut,
    PublicCancelIn,
    ReactionOut,
    SettingsIn,
    SettingsOut,
)
from apps.service.models import Service
from apps.staff.models import Member

#: Run only by the platform (events.py): outside ``online_booking.*``, so no role and no API key holds it.
SYSTEM = "system.online_booking"
CHANGE = "online_booking.change_booking"
CONFIRM = "online_booking.confirm_booking"
DELETE = "online_booking.delete_booking"
MANAGE = "online_booking.manage_settings"
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


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it: an account's full name, else its email, else its username."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.email or actor.get_username())[:128]
    return str(actor)[:128]


def _diary(ctx: OperationContext, name: str, appointment: Appointment, **extra):
    """Runs the diary's operation ``name`` on ``appointment`` with ``ctx`` (its rules and its permission)."""
    op = get(name)
    return op(ctx, op.input.model_validate({"id": str(appointment.id), **extra}))


# ── The inbox (F02–F06) ──────────────────────────────────────────────────────────────────────


@operation(
    "online_booking.booking.confirm",
    kind="command",
    permission=CONFIRM,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "description": "Confirm a booking a customer made online that is waiting (pending), named by its number or "
        "as a person says it: the customer and the day (e.g. confirm Ana's booking of tomorrow).",
        "risk": "normal",
    },
)
def confirm_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.confirm", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.complete",
    kind="command",
    permission=CHANGE,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "description": "Mark an online booking (confirmed or in progress) as completed, named by its number or by the "
        "customer and the day. It does not charge it: that is the till.",
        "risk": "normal",
    },
)
def complete_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.complete", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.no_show",
    kind="command",
    permission=CHANGE,
    input=BookingRefIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "description": "Record that the customer of an online booking did not show up (only once its time has "
        "passed), named by its number or by the customer and the day. Ask the person before doing it.",
        "risk": "high",
    },
)
def no_show_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.mark_no_show", booking)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.cancel",
    kind="command",
    permission=CHANGE,
    input=CancelIn,
    output=BookingOut,
    expose_api=True,
    ai={
        "description": "Cancel (or decline) an online booking, named by its number or by the customer and the day, "
        "with an optional reason; its time becomes free. Ask the person before doing it.",
        "risk": "high",
    },
)
def cancel_booking(ctx: OperationContext, data: CancelIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.cancel", booking, reason=data.reason)
    return load_detail(booking.id)


@operation(
    "online_booking.booking.delete",
    kind="command",
    permission=DELETE,
    input=BookingRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete an online booking from the inbox and the diary (archived, not destroyed), named by "
        "its number or by the customer and the day. Cancelling keeps its history and is usually what is wanted; "
        "ask the person first.",
        "risk": "high",
    },
)
def delete_booking(ctx: OperationContext, data: BookingRefIn) -> dict:
    booking = find_booking(ctx, data)
    _diary(ctx, "appointment.appointment.delete", booking)
    return {"id": booking.id, "deleted": True}


# ── Settings (F07) ───────────────────────────────────────────────────────────────────────────


@operation(
    "online_booking.settings.update",
    kind="command",
    permission=MANAGE,
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change the booking page's settings and the diary's booking rules it uses; only what is sent "
        "changes, all of it or nothing (e.g. switch the page on, ask for the email, or set the minimum notice).",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    sent = {
        field: getattr(data, field)
        for field in data.model_fields_set
        if getattr(data, field) is not None
    }
    rules = {field: value for field, value in sent.items() if field in RULE_FIELDS}
    settings = Settings.objects.select_for_update().first() or Settings()
    changed = {
        field: value
        for field, value in sent.items()
        if field not in RULE_FIELDS and getattr(settings, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save()
        record_event(ctx, SETTINGS_UPDATED, {})
    if rules:
        # The diary's own operation, with the caller's right to change its settings: all or nothing.
        get("appointment.settings.update")(ctx, RulesIn(**rules))
    return settings_out(settings)


# ── The public booking (F01) ─────────────────────────────────────────────────────────────────


def _refuse_field(message, code: str, field: str) -> None:
    raise InvalidPayload(str(message), code=code, fields={field: str(message)})


def _mobile(raw: str) -> str:
    try:
        return to_e164(raw, business_country())
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
    cards = list(Customer.objects.live().filter(phone=phone).order_by("name", "id"))
    wanted = normalize(name)
    card = next(
        (card for card in cards if normalize(card.name) == wanted),
        cards[0] if cards else None,
    )
    if card is not None:
        return find_customer(card.id, None, lock=True)
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
        booking = AppointmentCreateIn.model_validate(
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
        "description": "Book from the public booking page as the customer: services, a professional or anyone, a "
        "free time, her name and mobile. Hands back the appointment number and her personal link token.",
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
    phone = _mobile(data.phone)
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


# ── Cancelling by the link (F11) ─────────────────────────────────────────────────────────────


@operation(
    "online_booking.public.cancel",
    kind="command",
    permission=PUBLIC,
    input=PublicCancelIn,
    output=PublicBookingOut,
    ai={
        "description": "Cancel the booking behind a customer's personal link, as the customer: the business's "
        "cancellation policy applies. Ask the person before doing it.",
        "risk": "high",
    },
)
def public_cancel(ctx: OperationContext, data: PublicCancelIn) -> dict:
    appointment = find_by_token(data.token, lock=True).appointment
    cancel = get("appointment.appointment.cancel")
    cancel(
        delegated(ctx),
        AppointmentCancelIn(
            id=appointment.id,
            on_behalf_of_customer=True,
            customer_id=appointment.customer_id,
            reason=data.reason,
        ),
    )
    return public_booking_out(
        Appointment.objects.prefetch_related("lines").get(pk=appointment.pk)
    )


# ── The platform's reaction (events.py, F12) ─────────────────────────────────────────────────


@operation(
    "online_booking.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "Platform reaction to customer.customer.erased: the customer's personal links stop working "
        "and the fingerprint of the device she booked with is forgotten.",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    rows = Booking.objects.filter(appointment__customer_id=data.id).exclude(
        token_hash__isnull=True, requester=""
    )
    return {"changed": rows.update(token_hash=None, requester="")}
