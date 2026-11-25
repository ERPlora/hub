"""The people of the «Person» filter: whose working days can be listed, and one of them by id
(attendance.person.list and .detail)."""

from django.db.models import OuterRef, Q, QuerySet
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.attendance.models import Record
from apps.attendance.schemas import PersonListIn, PersonOut, PersonPage, PersonRefIn
from apps.staff.models import Member

from .people import MEMBER_NOT_FOUND, actor_user, member_name_expression, person_out
from .reads import READS_ANY_PERSON, VIEW_ALL, _page, _reads_any


def listed_people() -> QuerySet:
    """The people whose days can be listed, named: every staff record that is not terminated, and the terminated
    ones that have days."""
    with_days = Record.objects.filter(member=OuterRef("pk"))
    return Member.objects.annotate(name=member_name_expression()).filter(
        ~Q(status=Member.Status.TERMINATED) | Q(pk__in=with_days.values("member"))
    )


@operation(
    "attendance.person.list",
    kind="query",
    permission=VIEW_ALL,
    input=PersonListIn,
    output=PersonPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "whose clock-ins can I see?",
                "list the people of the time clock",
                "find Marta in the time clock",
            ),
            "es": (
                "¿de quién puedo ver los fichajes?",
                "lista la gente del control horario",
                "¿a quién puedo elegir en el filtro «Persona»?",
            ),
        },
        "description": "The people whose working days can be listed: every staff record that is not "
        "terminated, and the terminated ones that have days (kept four years). Search by name."
    },
)
def list_people(ctx: OperationContext, params: PersonListIn) -> dict:
    people = listed_people().order_by("first_name", "last_name", "id")
    if params.search:
        people = people.filter(name__icontains=params.search)
    rows = [person_out(m) for m in people[params.offset : params.offset + params.limit]]
    return _page(rows, people.count(), params)


@operation(
    "attendance.person.detail",
    kind="query",
    permission="attendance.clock",
    input=PersonRefIn,
    output=PersonOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is Marta still active in the time clock?",
                "give me Luis's details in the time clock",
                "has Pedro left the business? check the time clock",
            ),
            "es": (
                "¿sigue activa Marta en el control horario?",
                "dame la ficha de Luis en el control horario",
                "¿Pedro sigue de alta para fichar?",
            ),
        },
        "description": "One person of the time clock by id, as the «Person» filter names them: their name and "
        "the staff record's status. Your own for whoever clocks; anyone for whoever sees the team, clocks others "
        "or corrects days."
    },
)
def person_detail(ctx: OperationContext, params: PersonRefIn) -> dict:
    people = listed_people().filter(pk=params.id)
    if not _reads_any(ctx, READS_ANY_PERSON):
        user = actor_user(ctx)
        people = people.filter(user_id=user.pk) if user is not None else people.none()
    member = people.first()
    if member is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return person_out(member)
