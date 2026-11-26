"""What a customer may pick on the public page: the services booked online, who does them and their free times; and the
same choice checked when she books."""

from django.db.models import F, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import get, operation

from apps.appointment.queries.booking import bookable_members, check_member
from apps.appointment.schemas.availability import SlotsIn
from apps.online_booking.models import Settings
from apps.online_booking.schemas import PublicServicePage, PublicServicesIn, PublicSlotsIn, PublicSlotsOut
from apps.online_booking.service_price import shown_price
from apps.service.models.catalog import Service
from apps.service.queries.settings import current_settings as service_settings
from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member

from .settings import page_settings
from .visitors import PUBLIC, delegated

SERVICE_NOT_ONLINE = _("“%(name)s” cannot be booked online.")
UNKNOWN_SERVICE_NOT_ONLINE = _("That service cannot be booked online.")
STAFF_CHOICE_DISABLED = _(
    "This business assigns the professional itself: book without choosing one."
)


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
        "asks": {
            "en": (
                "which services can customers book by themselves?",
                "what can someone pick when booking through my link, and at what price?",
            ),
            "es": (
                "¿qué servicios se pueden reservar desde internet?",
                "¿qué tratamientos ofrece la web de reservas y cuánto valen?",
            ),
        },
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
            **shown_price(service, shown.show_prices),
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
        "asks": {
            "en": (
                "which free times can customers pick by themselves on Saturday?",
                "when could anyone book a manicure through my link this week?",
            ),
            "es": (
                "¿qué huecos libres ve cualquiera que reserve por la web el sábado?",
                "¿a qué horas puede coger cualquiera una manicura por internet el jueves?",
            ),
        },
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
