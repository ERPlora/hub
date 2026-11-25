"""What the task writes share: a reference that is not there is refused under its field, and the rows a write
names (the person, the project, the task) are held until the end of the command, in the order the deletions take
them."""

from uuid import UUID

from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.errors import InvalidPayload, NotFound, PermissionDenied

from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member
from apps.task.models import Project, Task
from apps.task.queries.reads import PROJECT_NOT_FOUND, TASK_NOT_FOUND, Caller, resolve_project, resolve_task

MEMBER_INACTIVE = _("That person is not active in the team.")


def _field_refusal(error: NotFound, field: str) -> InvalidPayload:
    """A reference of a write that does not exist is a 422 on its field, not a 404 of the write."""
    return InvalidPayload(error.message, code="invalid_field", fields={field: error.message})


def _hold(model: type[Task] | type[Project], pk: UUID) -> Task | Project | None:
    """The row ``pk``, locked until the end of the command; ``None`` when it was deleted after it was found.

    Every deletion of a task or a project locks it first (``_locked``, ``_locked_project`` and the Hub
    admin's «Delete», ``lock_tasks``/``lock_projects``): held, it is not deleted under the write that names
    it, and a deletion that went first is seen as gone. A write holds what it names in the order the
    deletions take them: the person (``_member``), the project, then the task.
    """
    return model.objects.select_for_update().filter(pk=pk).first()


def _project(project_id: UUID | None, text: str | None) -> Project | None:
    """The project a write names, held until the end of the command (a 422 on its field if it is not there)."""
    if project_id is None and text is None:
        return None
    try:
        return _locked_project(project_id, text)
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
    """The task, seen by the caller and locked until the end of the command. Deleted after it was found
    (the business's «Delete» or the Hub admin's), it is not found, as one deleted before."""
    task = _hold(Task, resolve_task(caller, task_id, text).pk)
    if task is None:
        raise NotFound(str(TASK_NOT_FOUND))
    return task


def _changeable(caller: Caller, task_id: UUID | None, text: str | None) -> Task:
    """The task, locked, if the caller may change it: their own, or any with ``task.change_all``."""
    task = _locked(caller, task_id, text)
    if not caller.may_change(task):
        raise PermissionDenied(gettext("You can only change your own tasks."))
    return task


def _locked_project(project_id: UUID | None, text: str | None) -> Project:
    """The project, locked until the end of the command; deleted after it was found, it is not found (as
    ``_locked``)."""
    project = _hold(Project, resolve_project(project_id, text).pk)
    if project is None:
        raise NotFound(str(PROJECT_NOT_FOUND))
    return project


def lock_tasks(ids) -> list[UUID]:
    """Locks the tasks ``ids`` and every subtask under them, a level after the one above it and each level in
    id order; the ids of those still there.

    A deletion of tasks (``task.task.delete`` and the Hub admin's «Delete», admin.py) locks them all before
    Django gathers their subtasks and comments and deletes them: a write that adds to one of them (a subtask,
    a comment) holds it first, so the deletion waits for it and takes what it added, instead of failing on it
    at its COMMIT. A subtask is only added under a held task, so a level read once the one above is held is
    complete.
    """
    locked: list[UUID] = []
    level = list(ids)
    while level:
        rows = Task.objects.select_for_update().filter(pk__in=level).order_by("id")
        held = list(rows.values_list("id", flat=True))
        locked += held
        level = list(Task.objects.filter(parent_id__in=held).exclude(pk__in=locked).values_list("id", flat=True))
    return locked


def lock_projects(ids) -> list[UUID]:
    """Locks the projects ``ids`` in id order (as ``lock_tasks``, before their tasks are cleared)."""
    rows = Project.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))
