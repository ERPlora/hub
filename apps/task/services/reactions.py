"""The platform's reaction to a person who leaves the team (TASK-F15): their open tasks are left without an
assignee."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.task import events
from apps.task.models import Task
from apps.task.schemas import MemberReleaseIn, ReleasedOut

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "task.system"


@operation(
    "task.task.release_member",
    kind="command",
    permission=SYSTEM,
    input=MemberReleaseIn,
    output=ReleasedOut,
    ai={
        "description": "Platform reaction to staff.member.terminated: the open tasks of the person who "
        "left are left without an assignee.",
        "risk": "normal",
    },
)
def release_member(ctx: OperationContext, data: MemberReleaseIn) -> dict:
    tasks = list(
        Task.objects.select_for_update()
        .filter(assigned_to_id=data.id)
        .exclude(status__in=Task.CLOSED)
        .order_by("id")
    )
    for task in tasks:
        task.assigned_to = None
        task.save(update_fields=["assigned_to", "updated_at"])
        record_event(ctx, events.TASK_ASSIGNED, {"id": str(task.pk), "assigned_to_id": None})
    return {"released": len(tasks)}
