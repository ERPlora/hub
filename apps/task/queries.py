"""Read operations of the task app (``READ ONLY``), and the loaders services.py reuses.

Who sees what: a caller with ``task.view_all`` sees every task; anyone else, their own — the ones
assigned to their staff record (the one linked to their account) and the ones they created. A task the
caller does not see does not exist for them (404, never 403). «Today» is the business's day
(``timezone.localdate()``, phase 1 ``TIME_ZONE`` = Europe/Madrid). A task may be named by its id, its
number or its title, a project by its id, its code or its name: the assistant speaks names.
"""

import datetime as dt
from typing import Any
from uuid import UUID

from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.staff.queries import actor_user_id, own_member
from apps.task.models import Comment, Project, Task
from apps.task.schemas import (
    CommentListIn,
    CommentPage,
    PageIn,
    ProjectListIn,
    ProjectOut,
    ProjectPage,
    ProjectRefIn,
    SubtaskListIn,
    TaskListIn,
    TaskMineIn,
    TaskOut,
    TaskPage,
    TaskRefIn,
)

TASK_NOT_FOUND = _("That task does not exist in this business.")
PROJECT_NOT_FOUND = _("That project does not exist in this business.")
AMBIGUOUS_TASK = _("There are several tasks called “%(text)s”: %(matches)s. Say which one.")
AMBIGUOUS_PROJECT = _("There are several projects called “%(text)s”: %(matches)s. Say which one.")

VIEW_ALL = "task.view_all"
CHANGE = "task.change"
CHANGE_ALL = "task.change_all"
#: How many candidates an ambiguous reference lists.
MAX_CANDIDATES = 5

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
PROJECT_ORDER = {
    "code": ("code",),
    "name": ("name",),
    "color": ("color",),
    "is_active": ("is_active",),
    "owner_name": ("owner_name",),
    "task_count": ("task_count",),
    "open_task_count": ("open_task_count",),
    "created_at": ("created_at",),
    "id": (),
}


# --- Who sees and who changes ------------------------------------------------------------------


class Caller:
    """The caller's identity for «their own tasks», read once per operation."""

    def __init__(self, ctx: OperationContext) -> None:
        self.ctx = ctx
        self.user_id = actor_user_id(ctx)
        self.member = own_member(ctx)

    def own(self, prefix: str = "") -> Q:
        """The tasks assigned to the caller's staff record or created by the caller (``prefix``:
        the path to the tasks from another model, ``tasks__`` from a project)."""
        own = Q(**{f"{prefix}pk__in": []})
        if self.member is not None:
            own |= Q(**{f"{prefix}assigned_to_id": self.member.pk})
        if self.user_id is not None:
            own |= Q(**{f"{prefix}created_by_id": self.user_id})
        return own

    def sees(self, task: Task) -> bool:
        return self.ctx.has(VIEW_ALL) or self.is_own(task)

    def is_own(self, task: Task) -> bool:
        return (self.member is not None and task.assigned_to_id == self.member.pk) or (
            self.user_id is not None and task.created_by_id == self.user_id
        )

    def visible(self, tasks: QuerySet[Task]) -> QuerySet[Task]:
        return tasks if self.ctx.has(VIEW_ALL) else tasks.filter(self.own())

    def may_change(self, task: Task) -> bool:
        return self.ctx.has(CHANGE_ALL) or (self.ctx.has(CHANGE) and self.is_own(task))


def business_today() -> dt.date:
    """Today in the business's time zone (phase 1: ``settings.TIME_ZONE``)."""
    return timezone.localdate()


# --- Tasks -----------------------------------------------------------------------------------------


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


def _full_name(member: str) -> Case:
    """«First Last» of a staff record; NULL without one (so it sorts last, never as a blank)."""
    return Case(
        When(**{f"{member}__isnull": True}, then=Value(None)),
        default=Concat(f"{member}__first_name", Value(" "), f"{member}__last_name"),
    )


def user_name(user: Any) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.email or user.get_username()


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


def resolve_task(
    caller: Caller, task_id: UUID | None, text: str | None, rows: QuerySet[Task] | None = None
) -> Task:
    """A task the caller sees, by id, or by its number or title.

    The title is tried exact before partial, and an open task before a closed one: the first step
    with one match wins; several → 409 ``task.ambiguous_task`` naming them; none → ``NotFound``. It comes
    from ``rows`` when given (e.g. with what its detail shows): the read that finds it is the only one,
    so a deletion committed meanwhile is either not seen yet or not found, never a row gone between two.
    """
    tasks = caller.visible(Task.objects.all() if rows is None else rows)
    if task_id is not None:
        task = tasks.filter(pk=task_id).first()
    else:
        task = tasks.filter(number__iexact=text).first()
        if task is None:
            ordered = tasks.order_by("-created_at", "id")
            open_tasks = ordered.exclude(status__in=Task.CLOSED)
            for step in (
                open_tasks.filter(title__iexact=text),
                ordered.filter(title__iexact=text),
                open_tasks.filter(title__icontains=text),
                ordered.filter(title__icontains=text),
            ):
                matches = list(step[: MAX_CANDIDATES + 1])
                if len(matches) > 1:
                    names = ", ".join(f"{match.number} {match.title}" for match in matches[:MAX_CANDIDATES])
                    raise Conflict(
                        str(AMBIGUOUS_TASK) % {"text": text, "matches": names},
                        code="task.ambiguous_task",
                    )
                if matches:
                    task = matches[0]
                    break
    if task is None:
        raise NotFound(str(TASK_NOT_FOUND))
    return task


def filter_tasks(tasks: QuerySet[Task], params: TaskListIn) -> QuerySet[Task]:
    if params.search:
        text = params.search
        tasks = tasks.filter(
            Q(number__icontains=text)
            | Q(title__icontains=text)
            | Q(description__icontains=text)
            | Q(assignee_name__icontains=text)
            | Q(project__name__icontains=text)
            | Q(project__code__icontains=text)
        )
    if params.number:
        tasks = tasks.filter(number__icontains=params.number)
    if params.title:
        tasks = tasks.filter(title__icontains=params.title)
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
        tasks = tasks.filter(assignee_name__icontains=params.assignee)
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
        "due date, assignee and project; filters by status, priority, project, assignee, overdue and dates."
    },
)
def list_tasks(ctx: OperationContext, params: TaskListIn) -> dict:
    caller = Caller(ctx)
    tasks = filter_tasks(annotated(caller.visible(Task.objects.all()), caller), params)
    return _page(_sorted(tasks, params.sort, TASK_ORDER), params, lambda task: task_row(task, caller))


@operation(
    "task.task.mine",
    kind="query",
    permission="task.view",
    input=TaskMineIn,
    output=TaskPage,
    expose_api=True,
    ai={
        "description": "Lists the caller's own open tasks (assigned to their staff record): dated ones "
        "first, the soonest due on top, then the undated ones; optionally only those due within N days."
    },
)
def my_tasks(ctx: OperationContext, params: TaskMineIn) -> dict:
    caller = Caller(ctx)
    if caller.member is None:
        tasks = Task.objects.none()
    else:
        tasks = Task.objects.filter(assigned_to_id=caller.member.pk).exclude(status__in=Task.CLOSED)
    if params.search:
        tasks = tasks.filter(Q(number__icontains=params.search) | Q(title__icontains=params.search))
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
    ai={"description": "Returns one task, by id, by its number (TSK-…) or by its title."},
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
    ai={"description": "Lists the subtasks of a task (by id, number or title), in the order they were added."},
)
def list_subtasks(ctx: OperationContext, params: SubtaskListIn) -> dict:
    caller = Caller(ctx)
    parent = resolve_task(caller, params.id, params.task)
    tasks = annotated(caller.visible(Task.objects.filter(parent=parent)), caller).order_by("created_at", "id")
    return _page(tasks, params, lambda task: task_row(task, caller))


# --- Comments --------------------------------------------------------------------------------------


def comment_row(comment: Comment) -> dict:
    return {
        "id": comment.pk,
        "task_id": comment.task_id,
        "text": comment.text,
        "author_id": comment.author_id,
        "author_name": user_name(comment.author),
        "created_at": comment.created_at,
    }


@operation(
    "task.comment.list",
    kind="query",
    permission="task.view",
    input=CommentListIn,
    output=CommentPage,
    expose_api=True,
    ai={"description": "Lists the comments of a task (by id, number or title), the newest first."},
)
def list_comments(ctx: OperationContext, params: CommentListIn) -> dict:
    task = resolve_task(Caller(ctx), params.task_id, params.task)
    comments = Comment.objects.filter(task=task).select_related("author").order_by("-created_at", "-id")
    return _page(comments, params, comment_row)


# --- Projects --------------------------------------------------------------------------------------


def annotated_projects(projects: QuerySet[Project], caller: Caller) -> QuerySet[Project]:
    """Projects with their owner's name and how many tasks (and open ones) the caller sees in them."""
    seen = Q() if caller.ctx.has(VIEW_ALL) else caller.own("tasks__")
    return projects.annotate(
        owner_name=_full_name("owner"),
        task_count=Count("tasks", filter=seen, distinct=True),
        open_task_count=Count("tasks", filter=seen & ~Q(tasks__status__in=Task.CLOSED), distinct=True),
    )


def project_row(project: Project) -> dict:
    return {
        "id": project.pk,
        "code": project.code,
        "name": project.name,
        "color": project.color,
        "is_active": project.is_active,
        "owner_id": project.owner_id,
        "owner_name": project.owner_name,
        "task_count": project.task_count,
        "open_task_count": project.open_task_count,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def load_project(project_id: UUID, caller: Caller) -> dict:
    return project_row(annotated_projects(Project.objects.filter(pk=project_id), caller).get())


def resolve_project(
    project_id: UUID | None, text: str | None, rows: QuerySet[Project] | None = None
) -> Project:
    """A project by id, or by its code, its exact name or a part of its name.

    Several matches → 409 ``task.ambiguous_project`` naming them; none → ``NotFound``. From ``rows`` when
    given, in one read (as ``resolve_task``).
    """
    projects = (Project.objects.all() if rows is None else rows).order_by("name", "id")
    if project_id is not None:
        project = projects.filter(pk=project_id).first()
    else:
        project = projects.filter(code__iexact=text).first()
        if project is None:
            for step in (projects.filter(name__iexact=text), projects.filter(name__icontains=text)):
                matches = list(step[: MAX_CANDIDATES + 1])
                if len(matches) > 1:
                    names = ", ".join(f"{match.name} ({match.code})" for match in matches[:MAX_CANDIDATES])
                    raise Conflict(
                        str(AMBIGUOUS_PROJECT) % {"text": text, "matches": names},
                        code="task.ambiguous_project",
                    )
                if matches:
                    project = matches[0]
                    break
    if project is None:
        raise NotFound(str(PROJECT_NOT_FOUND))
    return project


@operation(
    "task.project.list",
    kind="query",
    permission="task.view",
    input=ProjectListIn,
    output=ProjectPage,
    expose_api=True,
    ai={
        "description": "Lists the task projects with their code, colour, whether they are active and how "
        "many tasks (and open tasks) each one has."
    },
)
def list_projects(ctx: OperationContext, params: ProjectListIn) -> dict:
    projects = annotated_projects(Project.objects.all(), Caller(ctx))
    if params.search:
        projects = projects.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    if params.code:
        projects = projects.filter(code__icontains=params.code)
    if params.name:
        projects = projects.filter(name__icontains=params.name)
    if params.color:
        projects = projects.filter(color__icontains=params.color)
    if params.is_active is not None:
        projects = projects.filter(is_active=params.is_active)
    if params.owner_id:
        projects = projects.filter(owner_id=params.owner_id)
    return _page(_sorted(projects, params.sort, PROJECT_ORDER), params, project_row)


@operation(
    "task.project.detail",
    kind="query",
    permission="task.view",
    input=ProjectRefIn,
    output=ProjectOut,
    expose_api=True,
    ai={"description": "Returns one task project, by id, by its code or by its name."},
)
def project_detail(ctx: OperationContext, data: ProjectRefIn) -> dict:
    rows = annotated_projects(Project.objects.all(), Caller(ctx))
    return project_row(resolve_project(data.id, data.project, rows=rows))


# --- Helpers ---------------------------------------------------------------------------------------


def _sorted(rows: QuerySet[Any], sort: str, columns: dict[str, tuple[str, ...]]) -> QuerySet[Any]:
    """``rows`` by the columns of ``sort`` («-» first = descending), empty values last, then by id in
    the same direction (the old product's rule, hub#2355): a touched row keeps its place and pages
    neither repeat nor lose rows."""
    descending = sort.startswith("-")
    key = sort.removeprefix("-")
    order = [
        F(column).desc(nulls_last=True) if descending else F(column).asc(nulls_last=True)
        for column in columns[key]
    ]
    return rows.order_by(*order, "-id" if descending else "id")


def _page(rows: QuerySet[Any], params: PageIn, row) -> dict:
    return {
        "rows": [row(item) for item in rows[params.offset : params.offset + params.limit]],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
