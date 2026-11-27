"""Reads of the tasks (TASK-F02 to F04): the team's list with its filters and sorts, the caller's own open ones, one
task by what the caller calls it and its subtasks; and the row a write answers with."""

import datetime as dt
from uuid import UUID

from django.db.models import Case, Count, F, IntegerField, OuterRef, QuerySet, Subquery, Value, When
from django.db.models.functions import Coalesce
from live.context import OperationContext
from live.operations import operation

from base.ordering import list_order_for
from base.text_search import contains_text
from apps.task.models import Comment, Task
from apps.task.queries.reads import Caller, _full_name, _page, business_today, resolve_project, resolve_task, user_name
from apps.task.schemas import SubtaskListIn, TaskListIn, TaskMineIn, TaskOut, TaskPage, TaskRefIn


PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
STATUS_RANK = {"todo": 0, "in_progress": 1, "blocked": 2, "done": 3, "cancelled": 4}

# The model columns behind each sort key of the schemas.
TASK_ORDER = {
    "number": ("number",),
    "title": ("title",),
    "status": ("status_rank",),
    "priority": ("priority_rank",),
    "due_date": ("due_date",),
    "completed_at": ("completed_at",),
    "created_at": ("created_at",),
    "project_name": ("project__name",),
    "assignee_name": ("assignee_name",),
    "id": (),
}


def annotated(tasks: QuerySet[Task], caller: "Caller") -> QuerySet[Task]:
    """Tasks with what a row shows: project, parent, assignee and creator, and the two counts (the
    subtasks counted are the ones the caller sees)."""
    subtasks = (
        caller.visible(Task.objects.filter(parent=OuterRef("pk")))
        .order_by()
        .values("parent")
        .annotate(n=Count("id"))
        .values("n")
    )
    comments = (
        Comment.objects.filter(task=OuterRef("pk")).order_by().values("task").annotate(n=Count("id")).values("n")
    )
    return tasks.select_related("project", "parent", "assigned_to", "created_by").annotate(
        assignee_name=_full_name("assigned_to"),
        subtask_count=Coalesce(Subquery(subtasks, output_field=IntegerField()), 0),
        comment_count=Coalesce(Subquery(comments, output_field=IntegerField()), 0),
        priority_rank=Case(
            *(When(priority=key, then=Value(rank)) for key, rank in PRIORITY_RANK.items()),
            output_field=IntegerField(),
        ),
        status_rank=Case(
            *(When(status=key, then=Value(rank)) for key, rank in STATUS_RANK.items()),
            output_field=IntegerField(),
        ),
    )


def task_row(task: Task, caller: Caller) -> dict:
    """What ``TaskOut`` shows of an annotated task, for this caller: nothing of a parent they do not see."""
    project = task.project
    parent = task.parent if task.parent is not None and caller.sees(task.parent) else None
    return {
        "id": task.pk,
        "number": task.number,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "project_id": task.project_id,
        "project_name": project.name if project else None,
        "project_color": project.color if project else None,
        "parent_id": task.parent_id,
        "parent_number": parent.number if parent else None,
        "parent_title": parent.title if parent else None,
        "assigned_to_id": task.assigned_to_id,
        "assignee_name": task.assignee_name,
        "created_by_id": task.created_by_id,
        "created_by_name": user_name(task.created_by),
        "due_date": task.due_date,
        "completed_at": task.completed_at,
        "tags": list(task.tags or []),
        "subtask_count": task.subtask_count,
        "comment_count": task.comment_count,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "can_change": caller.may_change(task),
    }


def load_task(task_id: UUID, caller: Caller) -> dict:
    """The row of a task right after a write (whether or not the caller still sees it)."""
    return task_row(annotated(Task.objects.filter(pk=task_id), caller).get(), caller)


def filter_tasks(tasks: QuerySet[Task], params: TaskListIn) -> QuerySet[Task]:  # noqa: C901, PLR0912
    if params.search:
        text = params.search
        tasks = tasks.filter(
            contains_text(text, "number", "title", "description", "assignee_name", "project__name", "project__code")
        )
    if params.number:
        tasks = tasks.filter(contains_text(params.number, "number"))
    if params.title:
        tasks = tasks.filter(contains_text(params.title, "title"))
    if params.status:
        tasks = tasks.filter(status=params.status)
    if params.priority:
        tasks = tasks.filter(priority=params.priority)
    if params.open is True:
        tasks = tasks.exclude(status__in=Task.CLOSED)
    elif params.open is False:
        tasks = tasks.filter(status__in=Task.CLOSED)
    if params.overdue:
        tasks = tasks.exclude(status__in=Task.CLOSED).filter(due_date__lt=business_today())
    if params.project_id:
        tasks = tasks.filter(project_id=params.project_id)
    if params.project:
        tasks = tasks.filter(project=resolve_project(None, params.project))
    if params.assigned_to_id:
        tasks = tasks.filter(assigned_to_id=params.assigned_to_id)
    if params.assignee:
        tasks = tasks.filter(contains_text(params.assignee, "assignee_name"))
    if params.unassigned:
        tasks = tasks.filter(assigned_to__isnull=True)
    if params.parent_id:
        tasks = tasks.filter(parent_id=params.parent_id)
    if params.top_level:
        tasks = tasks.filter(parent__isnull=True)
    if params.tag:
        tasks = tasks.filter(tags__contains=[params.tag])
    if params.due_from:
        tasks = tasks.filter(due_date__gte=params.due_from)
    if params.due_to:
        tasks = tasks.filter(due_date__lte=params.due_to)
    # A moment's day is the business's: completed and created dates compare in its time zone.
    if params.completed_from:
        tasks = tasks.filter(completed_at__date__gte=params.completed_from)
    if params.completed_to:
        tasks = tasks.filter(completed_at__date__lte=params.completed_to)
    if params.created_from:
        tasks = tasks.filter(created_at__date__gte=params.created_from)
    if params.created_to:
        tasks = tasks.filter(created_at__date__lte=params.created_to)
    return tasks


@operation(
    "task.task.list",
    kind="query",
    permission="task.view",
    input=TaskListIn,
    output=TaskPage,
    expose_api=True,
    ai={
        "description": "Lists the team's tasks (an employee, only their own) with their status, priority, "
        "due date, assignee and project; filters by status, priority, project, assignee, overdue and dates.",
        "asks": {
            "en": (
                "which tasks are still open?",
                "show me the overdue tasks",
            ),
            "es": (
                "¿qué tareas siguen abiertas?",
                "enséñame las tareas vencidas",
            ),
        },
    },
)
def list_tasks(ctx: OperationContext, params: TaskListIn) -> dict:
    caller = Caller(ctx)
    tasks = filter_tasks(annotated(caller.visible(Task.objects.all()), caller), params)
    ordered = tasks.order_by(*list_order_for(params.sort, columns=TASK_ORDER, nulls_last=True))
    return _page(ordered, params, lambda task: task_row(task, caller))


@operation(
    "task.task.mine",
    kind="query",
    permission="task.view",
    input=TaskMineIn,
    output=TaskPage,
    expose_api=True,
    ai={
        "description": "Lists the caller's own open tasks (assigned to their staff record): dated ones "
        "first, the soonest due on top, then the undated ones; optionally only those due within N days.",
        "asks": {
            "en": (
                "which of the open tasks are mine?",
                "what is left on my own to-do list?",
            ),
            "es": (
                "¿qué tareas me tocan a mí?",
                "¿qué tareas tengo yo sin acabar?",
            ),
        },
    },
)
def my_tasks(ctx: OperationContext, params: TaskMineIn) -> dict:
    caller = Caller(ctx)
    if caller.member is None:
        tasks = Task.objects.none()
    else:
        tasks = Task.objects.filter(assigned_to_id=caller.member.pk).exclude(status__in=Task.CLOSED)
    if params.search:
        tasks = tasks.filter(contains_text(params.search, "number", "title"))
    if params.due_within_days is not None:
        horizon = business_today() + dt.timedelta(days=params.due_within_days)
        tasks = tasks.filter(due_date__isnull=False, due_date__lte=horizon)
    tasks = annotated(tasks, caller).order_by(F("due_date").asc(nulls_last=True), "-created_at", "id")
    return _page(tasks, params, lambda task: task_row(task, caller))


@operation(
    "task.task.detail",
    kind="query",
    permission="task.view",
    input=TaskRefIn,
    output=TaskOut,
    expose_api=True,
    ai={
        "description": "Returns one task, by id, by its number (TSK-…) or by its title.",
        "asks": {
            "en": (
                "show me the task TSK-0042",
                "what does the task change the gas bottle say?",
            ),
            "es": (
                "enséñame la tarea de cambiar la bombona",
                "¿qué dice la tarea TSK-0042?",
            ),
        },
    },
)
def task_detail(ctx: OperationContext, data: TaskRefIn) -> dict:
    caller = Caller(ctx)
    rows = annotated(Task.objects.all(), caller)
    return task_row(resolve_task(caller, data.id, data.task, rows=rows), caller)


@operation(
    "task.task.subtasks",
    kind="query",
    permission="task.view",
    input=SubtaskListIn,
    output=TaskPage,
    expose_api=True,
    ai={
        "description": "Lists the subtasks of a task (by id, number or title), in the order they were added.",
        "asks": {
            "en": (
                "what subtasks does the Saturday opening task have?",
                "list the subtasks of task TSK-0042",
            ),
            "es": (
                "¿qué subtareas tiene la tarea de la apertura del sábado?",
                "dime las subtareas de la TSK-0042",
            ),
        },
    },
)
def list_subtasks(ctx: OperationContext, params: SubtaskListIn) -> dict:
    caller = Caller(ctx)
    parent = resolve_task(caller, params.id, params.task)
    tasks = annotated(caller.visible(Task.objects.filter(parent=parent)), caller).order_by("created_at", "id")
    return _page(tasks, params, lambda task: task_row(task, caller))
