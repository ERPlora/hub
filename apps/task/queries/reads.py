"""What the task reads share, and services/ reuses: who the caller is and which tasks they see and may change, the
business's «today», how a task or a project is found by what the caller calls it, how a row names a person, and a
page of a list."""

import datetime as dt
from typing import Any
from uuid import UUID

from django.db.models import Case, Q, QuerySet, Value, When
from django.db.models.functions import Concat
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound

from apps.staff.queries.reads import actor_user_id, own_member
from base.business import business_zone
from base.models import HubUser
from base.queries.ownership import only_theirs
from apps.task.models import Project, Task
from apps.task.schemas import PageIn


TASK_NOT_FOUND = _("That task does not exist in this business.")
PROJECT_NOT_FOUND = _("That project does not exist in this business.")
AMBIGUOUS_TASK = _("There are several tasks called “%(text)s”: %(matches)s. Say which one.")
AMBIGUOUS_PROJECT = _("There are several projects called “%(text)s”: %(matches)s. Say which one.")

VIEW_ALL = "task.view_all"
CHANGE = "task.change"
CHANGE_ALL = "task.change_all"
#: How many candidates an ambiguous reference lists.
MAX_CANDIDATES = 5


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

    def seen(self, prefix: str = "") -> Q:
        """The tasks the caller reads (``prefix`` as in ``own``): all with «View all tasks», else their own, and the
        assistant hears the role keeps them to it (``only_theirs``)."""
        if self.ctx.has(VIEW_ALL):
            return Q()
        only_theirs()
        return self.own(prefix)

    def visible(self, tasks: QuerySet[Task]) -> QuerySet[Task]:
        return tasks.filter(self.seen())

    def may_change(self, task: Task) -> bool:
        return self.ctx.has(CHANGE_ALL) or (self.ctx.has(CHANGE) and self.is_own(task))


def business_today() -> dt.date:
    """Today in the business's time zone, the one its screens call «due today» on (hub#779)."""
    return timezone.localdate(timezone=business_zone())


def _full_name(member: str) -> Case:
    """«First Last» of a staff record; NULL without one (so it sorts last, never as a blank)."""
    return Case(
        When(**{f"{member}__isnull": True}, then=Value(None)),
        default=Concat(f"{member}__first_name", Value(" "), f"{member}__last_name"),
    )


def user_name(person: HubUser | None) -> str | None:
    """How a row names a person of the business's database: their name, else their email, else their username."""
    return None if person is None else person.display_name


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


def _page(rows: QuerySet[Any], params: PageIn, row) -> dict:
    return {
        "rows": [row(item) for item in rows[params.offset : params.offset + params.limit]],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
