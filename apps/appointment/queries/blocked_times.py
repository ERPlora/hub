"""The blocked periods of the agenda and how a person names one."""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.appointment.models import BlockedTime
from apps.appointment.schemas import BlockedTimeListIn, BlockedTimeNamedOut, BlockedTimePage, BlockedTimeRefIn
from base.business import business_zone

from .business import day_bounds
from .reads import _page, start_labels

BLOCK_NOT_FOUND = _("That blocked period does not exist in this business.")


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
        "asks": {
            "en": (
                "which blocked periods are on the agenda this month?",
                "is anything blocked off next week?",
            ),
            "es": (
                "¿qué bloqueos tiene la agenda este mes?",
                "¿hay algún rato bloqueado la semana que viene?",
            ),
        },
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


def block_label(ctx: OperationContext, block: dict) -> str:
    """How a person names a blocked period (``blocked_out``): its title, as the Agenda paints it, its day, its hour (none
    for a whole day) and its professional (none for the whole business's)."""
    said = start_labels(ctx, block["start"])
    hour = "" if block["all_day"] else said["start_time_label"]
    parts = (block["title"], said["start_date_label"], hour, block["staff_name"])
    return " · ".join(part for part in parts if part)


@operation(
    "appointment.blocked_time.get",
    kind="query",
    permission="appointment.view_schedule",
    input=BlockedTimeRefIn,
    output=BlockedTimeNamedOut,
    ai=INTERNAL,
)
def get_blocked_time(ctx: OperationContext, data: BlockedTimeRefIn) -> dict:
    """One blocked period with its name: what names one on the assistant's card (``schemas.A_BLOCK``); the model and the
    Agenda read the blocks by their list."""
    block = BlockedTime.objects.select_related("staff").filter(pk=data.id).first()
    if block is None:
        raise NotFound(str(BLOCK_NOT_FOUND), code="appointment.blocked_time_not_found")
    said = blocked_out(block)
    return {**said, "label": block_label(ctx, said)}
