"""The schedules of a staff member, each with its week (STAFF-F13–F15)."""

from uuid import UUID

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.staff.models import Schedule
from apps.staff.schemas.fields import ByIdIn
from apps.staff.schemas.schedules import ScheduleListIn, ScheduleDetailOut, SchedulePage

from .reads import TERMINATED, _page, resolve_member

SCHEDULE_NOT_FOUND = _("That schedule does not exist in this business.")


@operation(
    "staff.schedule.list",
    kind="query",
    permission="staff.view",
    input=ScheduleListIn,
    output=SchedulePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which schedules does Lucía have?",
                "list Pablo's schedules",
                "what schedule is Ana on now?",
            ),
            "es": (
                "¿qué horarios tiene Lucía?",
                "lista los horarios de Pablo",
                "¿con qué horario está Ana ahora?",
            ),
        },
        "description": "Lists the work schedules of a staff member (by id or by name), each with its "
        "weekly working hours and breaks."
    },
)
def list_schedules(ctx: OperationContext, params: ScheduleListIn) -> dict:
    """A member's schedules, the default first, each with its week (STAFF-F13–F15)."""
    member = resolve_member(params.member_id, params.member)
    schedules = (
        live_schedules().filter(member=member).order_by("-is_default", "name", "id")
    )
    return _page(schedules, params)


@operation(
    "staff.schedule.detail",
    kind="query",
    permission="staff.view",
    input=ByIdIn,
    output=ScheduleDetailOut,
    ai={
        "asks": {
            "en": (
                "show me Lucía's schedule day by day",
                "what time is Pablo's break each day of his schedule?",
                "the hours of Ana's summer schedule",
            ),
            "es": (
                "enséñame el horario de Lucía día por día",
                "¿a qué hora descansa Pablo cada día de su horario?",
                "las horas del horario de verano de Ana",
            ),
        },
        "description": "Returns one work schedule with its weekly working hours.",
    },
)
def schedule_detail(ctx: OperationContext, data: ByIdIn) -> Schedule:
    schedule = load_schedule(data.id)
    if schedule is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    schedule.label = f"{schedule.member.full_name} · {schedule.name}"
    return schedule


def live_schedules() -> QuerySet[Schedule]:
    return Schedule.objects.exclude(member__status=TERMINATED).prefetch_related("days")


def load_schedule(schedule_id: UUID) -> Schedule | None:
    return live_schedules().filter(pk=schedule_id).first()
