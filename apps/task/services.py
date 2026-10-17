"""Write operations of the task app: one operation = one transaction, with its events in the outbox.

A write on a task locks its row (``select_for_update``) before it looks at its status, so two people
completing it at once are queued and the second one sees the first one's work. A write that names a
person (an assignee, a project's owner) holds their staff record first, before the task or the project:
the Hub admin's «Delete» of a person takes the record and then clears what names it, so it waits for the
write, or the write waits for it and hears the person is gone. A task the caller does
not see does not exist for them (404); one they see but may not change is a 403. Refusals about a field
carry it, so the screen puts them next to it. Nothing fails in silence: a refused create writes nothing
and spends no number.
"""

import datetime as dt
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.staff.models import Member
from apps.staff.queries import resolve_member
from apps.task import events
from apps.task.models import Comment, Project, Task, TaskCounter
from apps.task.queries import (
    Caller,
    business_today,
    comment_row,
    load_project,
    load_task,
    resolve_project,
    resolve_task,
)
from apps.task.schemas import (
    AssignIn,
    CommentIn,
    CommentOut,
    DeletedOut,
    MemberReleaseIn,
    ProjectIn,
    ProjectOut,
    ProjectPatchIn,
    ProjectRefIn,
    ReleasedOut,
    SetStatusIn,
    TaskIn,
    TaskOut,
    TaskPatchIn,
    TaskRefIn,
)

TASK_ALREADY_CLOSED = _("That task is already closed, so it was left as it was.")
MEMBER_INACTIVE = _("That person is not active in the team.")
NO_OWN_RECORD = _("You have no staff record: you cannot be assigned tasks.")
PROJECT_EXISTS = _("There is already a project with that code.")

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "task.system"


# --- Shared steps ----------------------------------------------------------------------------------


def _field_refusal(error: NotFound, field: str) -> InvalidPayload:
    """A reference of a write that does not exist is a 422 on its field, not a 404 of the write."""
    return InvalidPayload(error.message, code="invalid_field", fields={field: error.message})


def _project(project_id: UUID | None, text: str | None) -> Project | None:
    if project_id is None and text is None:
        return None
    try:
        return resolve_project(project_id, text)
    except NotFound as error:
        raise _field_refusal(error, "project_id" if project_id else "project") from None


def _member(member_id: UUID | None, name: str | None, *, id_field: str, name_field: str) -> Member | None:
    """A staff record that may take tasks: live (not terminated) and not inactive, held until the end of
    the command so that it is not deleted under the task or project that names it. Called before the task
    or the project is locked: the deletion of a person holds them and then waits for those rows."""
    if member_id is None and name is None:
        return None
    field = id_field if member_id else name_field
    try:
        member = resolve_member(member_id, name, lock=True)
    except NotFound as error:
        raise _field_refusal(error, field) from None
    if member.status == Member.Status.INACTIVE:
        raise InvalidPayload(str(MEMBER_INACTIVE), code="invalid_field", fields={field: str(MEMBER_INACTIVE)})
    return member


def _locked(caller: Caller, task_id: UUID | None, text: str | None) -> Task:
    """The task, seen by the caller and locked until the end of the command."""
    task = resolve_task(caller, task_id, text)
    return Task.objects.select_for_update().get(pk=task.pk)


def _changeable(caller: Caller, task_id: UUID | None, text: str | None) -> Task:
    """The task, locked, if the caller may change it: their own, or any with ``task.change_all``."""
    task = _locked(caller, task_id, text)
    if not caller.may_change(task):
        raise PermissionDenied(gettext("You can only change your own tasks."))
    return task


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


# --- Tasks (TASK-F01, F05–F09, F11) --------------------------------------------------------------


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
    },
)
def create_task(ctx: OperationContext, data: TaskIn) -> dict:
    caller = Caller(ctx)
    project = _project(data.project_id, data.project)
    parent = None
    if data.parent_id is not None or data.parent is not None:
        try:
            parent = resolve_task(caller, data.parent_id, data.parent)
        except NotFound as error:
            raise _field_refusal(error, "parent_id" if data.parent_id else "parent") from None
        if project is None:
            project = parent.project
    assignee = _member(data.assigned_to_id, data.assignee, id_field="assigned_to_id", name_field="assignee")
    task = Task.objects.create(
        number=_next_number(business_today()),
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        project=project,
        parent=parent,
        assigned_to=assignee,
        created_by_id=caller.user_id,
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
    permission="task.change",
    input=TaskPatchIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Change a task's title, description, priority, due date, project or tags; only the "
        "fields sent change (null clears the due date or the project).",
        "risk": "normal",
    },
)
def update_task(ctx: OperationContext, data: TaskPatchIn) -> dict:
    caller = Caller(ctx)
    task = _changeable(caller, data.id, data.task)
    sent = data.model_fields_set
    changes: dict = {}
    for field in ("title", "description", "priority", "tags"):
        value = getattr(data, field)
        if field in sent and value is not None and value != getattr(task, field):
            changes[field] = value
    if "due_date" in sent and data.due_date != task.due_date:
        changes["due_date"] = data.due_date
    if "project" in sent and data.project is not None:
        project = _project(None, data.project)
        if project.pk != task.project_id:
            changes["project"] = project
    elif "project_id" in sent:
        project = _project(data.project_id, None)
        if (project.pk if project else None) != task.project_id:
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
    permission="task.change",
    input=SetStatusIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Change a task's status: todo, in_progress (start it), blocked, done or cancelled. "
        "Done stamps the completion date and leaving done clears it.",
        "risk": "normal",
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
    permission="task.change",
    input=TaskRefIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Mark an open task as done («complete the task clean the store room»). A task "
        "already done or cancelled is left as it was.",
        "risk": "normal",
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
    permission="task.change",
    input=AssignIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Assign a task to a person of the team (by id or name, or to the caller with "
        "to_me), or unassign it when no person is given.",
        "risk": "normal",
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
    permission="task.delete",
    input=TaskRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a task for good, with its subtasks and its comments.",
        "risk": "high",
    },
)
def delete_task(ctx: OperationContext, data: TaskRefIn) -> dict:
    task = _locked(Caller(ctx), data.id, data.task)
    payload = {"id": str(task.pk), "number": task.number}
    task.delete()
    record_event(ctx, events.TASK_DELETED, payload)
    return {"id": UUID(payload["id"])}


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


# --- Comments (TASK-F10) -------------------------------------------------------------------------


@operation(
    "task.comment.add",
    kind="command",
    permission="task.change",
    input=CommentIn,
    output=CommentOut,
    expose_api=True,
    ai={
        "description": "Add a comment to a task's thread, signed by the caller.",
        "risk": "normal",
    },
)
def add_comment(ctx: OperationContext, data: CommentIn) -> dict:
    caller = Caller(ctx)
    task = _changeable(caller, data.task_id, data.task)
    comment = Comment.objects.create(task=task, author_id=caller.user_id, text=data.text)
    record_event(ctx, events.COMMENT_ADDED, {"id": str(comment.pk), "task_id": str(task.pk)})
    comment.author = ctx.actor if caller.user_id is not None else None
    return comment_row(comment)


# --- Projects (TASK-F12–F14) ---------------------------------------------------------------------


def _locked_project(project_id: UUID | None, text: str | None) -> Project:
    project = resolve_project(project_id, text)
    return Project.objects.select_for_update().get(pk=project.pk)


def _project_exists() -> Conflict:
    return Conflict(str(PROJECT_EXISTS), code="task.project_exists", fields={"code": str(PROJECT_EXISTS)})


@operation(
    "task.project.create",
    kind="command",
    permission="task.manage_project",
    input=ProjectIn,
    output=ProjectOut,
    expose_api=True,
    ai={
        "description": "Create a project to group related tasks, with a unique code, a name and an "
        "optional colour and owner.",
        "risk": "normal",
    },
)
def create_project(ctx: OperationContext, data: ProjectIn) -> dict:
    owner = _member(data.owner_id, data.owner, id_field="owner_id", name_field="owner")
    if Project.objects.filter(code__iexact=data.code).exists():
        raise _project_exists()
    try:
        with transaction.atomic():
            project = Project.objects.create(code=data.code, name=data.name, color=data.color, owner=owner)
    except IntegrityError:  # two saves of the same code at once: the code is the only unique field
        raise _project_exists() from None
    record_event(ctx, events.PROJECT_CREATED, {"id": str(project.pk), "code": project.code})
    return load_project(project.pk, Caller(ctx))


@operation(
    "task.project.update",
    kind="command",
    permission="task.manage_project",
    input=ProjectPatchIn,
    output=ProjectOut,
    expose_api=True,
    ai={
        "description": "Change a project's name, colour or owner, or take it out of use (is_active false) "
        "and back; only the fields sent change. The code never changes.",
        "risk": "normal",
    },
)
def update_project(ctx: OperationContext, data: ProjectPatchIn) -> dict:
    sent = data.model_fields_set
    owner_sent = True
    if "owner" in sent and data.owner is not None:
        owner = _member(None, data.owner, id_field="owner_id", name_field="owner")
    elif "owner_id" in sent:
        owner = _member(data.owner_id, None, id_field="owner_id", name_field="owner")
    else:
        owner_sent, owner = False, None
    project = _locked_project(data.id, data.project)
    changes: dict = {}
    for field in ("name", "color", "is_active"):
        value = getattr(data, field)
        if field in sent and value is not None and value != getattr(project, field):
            changes[field] = value
    if owner_sent and (owner.pk if owner else None) != project.owner_id:
        changes["owner"] = owner
    if changes:
        for field, value in changes.items():
            setattr(project, field, value)
        project.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.PROJECT_UPDATED, {"id": str(project.pk)})
    return load_project(project.pk, Caller(ctx))


@operation(
    "task.project.delete",
    kind="command",
    permission="task.manage_project",
    input=ProjectRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a project for good; its tasks stay, without a project.",
        "risk": "high",
    },
)
def delete_project(ctx: OperationContext, data: ProjectRefIn) -> dict:
    project = _locked_project(data.id, data.project)
    payload = {"id": str(project.pk), "code": project.code}
    project.delete()
    record_event(ctx, events.PROJECT_DELETED, payload)
    return {"id": UUID(payload["id"])}
