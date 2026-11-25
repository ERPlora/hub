"""What a booking is made of: its services, who may do them and the lines it freezes."""

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.appointment.schemas.references import ServiceRefIn
from apps.service.models import Assignment, Service
from apps.service.queries import catalog
from apps.staff.models import Member

from .lanes import takes_bookings

#: How many professionals the free times of «anybody who does it» look at.
MAX_PROFESSIONALS = 30

SERVICE_NOT_BOOKABLE = _("“%(name)s” cannot be booked: it is archived or not bookable.")
STAFF_NOT_BOOKABLE = _("%(name)s cannot take appointments: inactive or not bookable.")
STAFF_NOT_ELIGIBLE = _("%(name)s does not perform “%(service)s”.")


def resolve_services(refs: list[ServiceRefIn]) -> list[Service]:
    """The services named, in order: each offered and bookable (409 ``appointment.service_not_bookable``)."""
    services = []
    for ref in refs:
        try:
            service = catalog.find_service(ref.service_id, ref.service)
        except NotFound:
            if ref.service_id is not None:
                raise
            # Named, it may be an archived one: say so, not «does not exist».
            service = catalog.find_service(None, ref.service, archived=True)
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
