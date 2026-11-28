"""What of Tasks travels in an export of the business (BASE-F35), read with Tasks' own lists and written with its own
creates: the active projects, by their code, and the open tasks (to do, in progress, blocked), each with its project by
code, the task it is a subtask of by title, its priority, due date, tags and status. A task is named by its project and
its title. Done or cancelled tasks, comments and who a task or a project is assigned to never travel."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, attempt, by_name, count_of, create_each, given, ids_of, natural_key
from base.blueprint.calls import pages, remover, rows_of, text_of

PROJECT_FIELDS = ("code", "name", "color")
TASK_FIELDS = ("title", "description", "priority", "due_date", "project", "parent", "tags")
OPEN = {"open": True}


def _task_rows(ctx: OperationContext) -> list[dict]:
    codes = {row.id: row.code for row in pages(ctx, "task.project.list")}
    return [
        {
            "title": row.title,
            "description": row.description,
            "priority": row.priority,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "project": codes.get(row.project_id) or "",
            "parent": row.parent_title or "",
            "tags": row.tags,
            "status": row.status,
        }
        for row in pages(ctx, "task.task.list", **OPEN, sort="created_at")
    ]


def _task_key(project: str, title: str) -> str:
    return f"{natural_key(project)}\x00{natural_key(title)}" if title.strip() else ""


def _task_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    codes = {row.id: row.code for row in pages(ctx, "task.project.list")}
    existing = {_task_key(codes.get(row.project_id) or "", row.title) for row in pages(ctx, "task.task.list", **OPEN)}

    def set_status(row: dict, pk: str) -> None:
        if text_of(row, "status") not in ("", "todo"):
            attempt(ctx, loaded, text_of(row, "title"), "task.task.set_status", id=pk, status=text_of(row, "status"))

    # A task before its subtasks: the ones without a parent first.
    create_each(ctx, sorted(rows, key=lambda row: bool(text_of(row, "parent"))), loaded, name="task.task.create",
                key=lambda row: _task_key(text_of(row, "project"), text_of(row, "title")), existing=existing,
                build=lambda row: given(row, TASK_FIELDS), label=lambda row: text_of(row, "title"), after=set_status)


DATASETS = [
    Dataset(
        key="task.project",
        label=_("Projects"),
        rows=rows_of("task.project.list", PROJECT_FIELDS, is_active=True, sort="code"),
        ids=ids_of("task.project.list"),
        count=count_of("task.project.list", is_active=True),
        load=by_name("task.project.list", "task.project.create", PROJECT_FIELDS, named="code"),
        remove=remover("task.project.delete"),
        models=("Project",),
    ),
    Dataset(
        key="task.task",
        label=_("Open tasks"),
        rows=_task_rows,
        ids=ids_of("task.task.list"),
        count=count_of("task.task.list", **OPEN),
        load=_task_load,
        remove=remover("task.task.delete"),
        models=("Task",),
    ),
]
