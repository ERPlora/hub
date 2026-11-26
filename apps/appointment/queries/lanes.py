"""The agenda's lanes: who takes bookings, and who else keeps appointments those days."""

from live.context import OperationContext
from live.operations import operation

from apps.appointment.schemas.agenda import LanesIn, LanesOut
from apps.staff.models import Member
from base.business import zone_name
from base.queries.ownership import only_theirs

from .access import VIEW_OWN, own_staff_id
from .business import day_bounds
from .ownership import APPOINTMENTS
from .reads import appointments


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
        "asks": {
            "en": (
                "show tomorrow's agenda split by stylist",
                "Thursday's agenda in one column per hairdresser",
            ),
            "es": (
                "la agenda del jueves por columnas de cada peluquera",
                "enséñame la agenda de mañana repartida por persona",
            ),
        },
        "description": "The rows of the agenda by professional for some days: the bookable team, then whoever no "
        "longer takes bookings but still has appointments those days, and how many appointments have no professional."
    },
)
def agenda_lanes(ctx: OperationContext, data: LanesIn) -> dict:
    start, end = day_bounds(data.date_from, data.date_to)
    in_range = appointments(ctx).filter(start__gte=start, start__lt=end)
    own, everyone = own_staff_id(ctx), APPOINTMENTS.sees_all(ctx)

    def lane(member: Member) -> dict:
        return {
            "staff_id": member.id,
            "name": member.full_name,
            "color": member.color,
            "takes_bookings": takes_bookings(member),
        }

    if everyone:
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
        only_theirs()
        members = list(Member.objects.filter(pk=own)) if own else []
        unassigned = 0
    return {
        "rows": [lane(member) for member in members],
        "unassigned": unassigned,
        "own_staff_id": own,
        "sees_everyone": everyone,
        "timezone": zone_name(),
    }
