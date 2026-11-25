"""Writes of the tasks (TASK-F01, F05–F09, F11): create one with the day's number, edit it, change its status,
complete it, assign it and delete it with its subtasks and comments."""

import datetime as dt
from uuid import UUID

from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.task import events
from apps.task.models import Project, Task, TaskCounter
from apps.task.queries.reads import TASK_NOT_FOUND, Caller, business_today, resolve_task
from apps.task.queries.tasks import load_task
from apps.task.schemas import AssignIn, DeletedOut, SetStatusIn, TaskIn, TaskOut, TaskPatchIn, TaskRefIn
from apps.task.services.writes import _changeable, _field_refusal, _hold, _locked, _member, _project, lock_tasks
from base.services.sessions import acting_hub_user

TASK_ALREADY_CLOSED = _("That task is already closed, so it was left as it was.")
NO_OWN_RECORD = _("You have no staff record: you cannot be assigned tasks.")


def _parent(caller: Caller, data: TaskIn, project: Project | None) -> tuple[Task | None, Project | None]:
    """The parent task a new subtask names and the subtask's project, both held: the one it was told, or else
    its parent's, held before the parent (as its deletion takes them) and none if it was deleted meanwhile,
    as the parent then has none either."""
    if data.parent_id is None and data.parent is None:
        return None, project
    field = "parent_id" if data.parent_id else "parent"
    try:
        found = resolve_task(caller, data.parent_id, data.parent)
    except NotFound as error:
        raise _field_refusal(error, field) from None
    if project is None and found.project_id is not None:
        project = _hold(Project, found.project_id)
    parent = _hold(Task, found.pk)
    if parent is None:
        raise _field_refusal(NotFound(str(TASK_NOT_FOUND)), field)
    return parent, project


def _next_number(day: dt.date) -> str:
    """``TSK-<day>-<NNNN>``, with no gaps: the counter's row stays locked until the task commits."""
    TaskCounter.objects.bulk_create([TaskCounter(day=day)], ignore_conflicts=True)
    TaskCounter.objects.filter(day=day).update(last_number=F("last_number") + 1)
    last = TaskCounter.objects.filter(day=day).values_list("last_number", flat=True).get()
    return f"TSK-{day:%Y%m%d}-{last:04d}"


def _set_status(ctx: OperationContext, task: Task, status: str) -> None:
    """Moves ``task`` to ``status`` with its completion date and its events."""
    previous = task.status
    task.status = status
    task.completed_at = timezone.now() if status == Task.Status.DONE else None
    task.save(update_fields=["status", "completed_at", "updated_at"])
    record_event(ctx, events.TASK_STATUS_CHANGED, {"id": str(task.pk), "from": previous, "to": status})
    if status == Task.Status.DONE:
        record_event(ctx, events.TASK_COMPLETED, {"id": str(task.pk)})


@operation(
    "task.task.create",
    kind="command",
    permission="task.add",
    input=TaskIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Create a task for the team («clean the store room tomorrow, assign it to Ana»), "
        "optionally inside a project or as a subtask of another task. It is born to do, numbered TSK-…",
        "risk": "normal",
        "asks": {
            "en": (
                "create a task to clean the store room tomorrow",
                "add a task for Ana: call the technician",
            ),
            "es": (
                "crea una tarea: limpiar el almacén mañana",
                "apunta una tarea para Ana: llamar al técnico",
            ),
        },
    },
)
def create_task(ctx: OperationContext, data: TaskIn) -> dict:
    # Who creates it signs it (made if their session came before their person): first, so the caller owns it.
    creator = acting_hub_user(ctx)
    caller = Caller(ctx)
    # What it names is held until the end, in the order the deletions take it: person, project, parent.
    assignee = _member(data.assigned_to_id, data.assignee, id_field="assigned_to_id", name_field="assignee")
    parent, project = _parent(caller, data, _project(data.project_id, data.project))
    task = Task.objects.create(
        number=_next_number(business_today()),
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        project=project,
        parent=parent,
        assigned_to=assignee,
        created_by=creator,
        tags=data.tags,
    )
    record_event(
        ctx,
        events.TASK_CREATED,
        {
            "id": str(task.pk),
            "number": task.number,
            "project_id": str(project.pk) if project else None,
            "parent_id": str(parent.pk) if parent else None,
            "assigned_to_id": str(assignee.pk) if assignee else None,
        },
    )
    return load_task(task.pk, caller)


@operation(
    "task.task.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.change",
    input=TaskPatchIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Change a task's title, description, priority, due date, project or tags; only the "
        "fields sent change (null clears the due date or the project).",
        "risk": "normal",
        "check": "task.task.detail",
        "asks": {
            "en": (
                "move the due date of the task order ice to Friday",
                "raise task TSK-0042 to high priority",
            ),
            "es": (
                "cambia la fecha límite de la tarea pedir hielo al viernes",
                "sube la prioridad de la tarea TSK-0042 a alta",
            ),
        },
    },
)
def update_task(ctx: OperationContext, data: TaskPatchIn) -> dict:
    caller = Caller(ctx)
    sent = data.model_fields_set
    # The project it is moved to is held before the task, in the order its deletion takes them.
    project, moved = None, False
    if "project" in sent and data.project is not None:
        project, moved = _project(None, data.project), True
    elif "project_id" in sent:
        project, moved = _project(data.project_id, None), True
    task = _changeable(caller, data.id, data.task)
    changes: dict = {}
    for field in ("title", "description", "priority", "tags"):
        value = getattr(data, field)
        if field in sent and value is not None and value != getattr(task, field):
            changes[field] = value
    if "due_date" in sent and data.due_date != task.due_date:
        changes["due_date"] = data.due_date
    if moved and (project.pk if project else None) != task.project_id:
        changes["project"] = project
    if changes:
        for field, value in changes.items():
            setattr(task, field, value)
        task.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.TASK_UPDATED, {"id": str(task.pk)})
    return load_task(task.pk, caller)


@operation(
    "task.task.set_status",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.change",
    input=SetStatusIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Change a task's status: todo, in_progress (start it), blocked, done or cancelled. "
        "Done stamps the completion date and leaving done clears it.",
        "risk": "normal",
        "check": "task.task.detail",
        "asks": {
            "en": (
                "put the task tidy the cold room in progress, I have started it",
                "set task TSK-0042 to blocked",
            ),
            "es": (
                "pon en curso la tarea de ordenar la cámara",
                "la tarea TSK-0042 está bloqueada, cámbiale el estado",
            ),
        },
    },
)
def set_status(ctx: OperationContext, data: SetStatusIn) -> dict:
    caller = Caller(ctx)
    task = _changeable(caller, data.id, data.task)
    if task.status != data.status:
        _set_status(ctx, task, data.status)
    return load_task(task.pk, caller)


@operation(
    "task.task.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.change",
    input=TaskRefIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Mark an open task as done («complete the task clean the store room»). A task "
        "already done or cancelled is left as it was.",
        "risk": "normal",
        "check": "task.task.detail",
        "asks": {
            "en": (
                "complete the task scrub the patio",
                "task TSK-0042 is finished, tick it off as done",
            ),
            "es": (
                "da por hecha la tarea de fregar el patio",
                "ya he terminado la TSK-0042, márcala como hecha",
            ),
        },
    },
)
def complete_task(ctx: OperationContext, data: TaskRefIn) -> dict:
    caller = Caller(ctx)
    task = _changeable(caller, data.id, data.task)
    if task.is_closed:
        raise Conflict(str(TASK_ALREADY_CLOSED), code="task.task_already_closed")
    _set_status(ctx, task, Task.Status.DONE)
    return load_task(task.pk, caller)


@operation(
    "task.task.assign",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.change",
    input=AssignIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Assign a task to a person of the team (by id or name, or to the caller with "
        "to_me), or unassign it when no person is given.",
        "risk": "normal",
        "check": "task.task.detail",
        "asks": {
            "en": (
                "assign the task restock the napkins to Ana",
                "leave task TSK-0042 with nobody assigned",
            ),
            "es": (
                "asigna a Ana la tarea de reponer servilletas",
                "deja la tarea TSK-0042 sin nadie asignado",
            ),
        },
    },
)
def assign_task(ctx: OperationContext, data: AssignIn) -> dict:
    caller = Caller(ctx)
    if data.to_me:
        if caller.member is None:
            raise InvalidPayload(str(NO_OWN_RECORD), code="invalid_field", fields={"to_me": str(NO_OWN_RECORD)})
        assignee = _member(caller.member.pk, None, id_field="to_me", name_field="to_me")
    else:
        assignee = _member(data.member_id, data.member, id_field="member_id", name_field="member")
    task = _changeable(caller, data.id, data.task)
    new_id = assignee.pk if assignee else None
    if new_id != task.assigned_to_id:
        task.assigned_to = assignee
        task.save(update_fields=["assigned_to", "updated_at"])
        record_event(
            ctx,
            events.TASK_ASSIGNED,
            {"id": str(task.pk), "assigned_to_id": str(new_id) if new_id else None},
        )
    return load_task(task.pk, caller)


@operation(
    "task.task.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="task.delete",
    input=TaskRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a task for good, with its subtasks and its comments.",
        "risk": "high",
        "check": "task.task.detail",
        "asks": {
            "en": (
                "delete the task hang the poster",
                "remove task TSK-0042 for good",
            ),
            "es": (
                "borra la tarea de colgar el cartel",
                "quita del todo la tarea TSK-0042",
            ),
        },
    },
)
def delete_task(ctx: OperationContext, data: TaskRefIn) -> dict:
    task = _locked(Caller(ctx), data.id, data.task)
    lock_tasks([task.pk])  # and its subtasks, before Django gathers what goes with it
    payload = {"id": str(task.pk), "number": task.number}
    task.delete()
    record_event(ctx, events.TASK_DELETED, payload)
    return {"id": UUID(payload["id"])}
