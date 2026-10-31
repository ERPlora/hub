"""Input and output schemas of the task app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

Every input refuses a field it does not declare (a filter that does not exist is a 422). A task can be
named by its id, its number or its title; a project by its id, its code or its name; a person by
their id or their name: the assistant is used by voice («complete the task clean the store room»,
«assign it to Ana»). ``queries.resolve_task``, ``queries.resolve_project`` and Staff's
``resolve_member`` turn the text into the record.
"""

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from apps.task.models import TEXT_MAX_LENGTH, TITLE_MAX_LENGTH, Task

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
NO_TASK = _("Say which task: its id, its number or its title.")
NO_PROJECT = _("Say which project: its id, its code or its name.")
ONE_PERSON = _("Choose one person: an id, a name or yourself.")
DATE_RANGE = _("Choose a date between 1900 and 2200.")
TAG_LIMIT = _("A task takes at most 20 tags.")

#: The calendar a date may fall in (the schedule app's bounds): beyond it, date arithmetic overflows.
FIRST_YEAR, LAST_YEAR = 1900, 2200
MAX_TAGS = 20

TaskStatus = Literal[*Task.Status.values]
TaskPriority = Literal[*Task.Priority.values]

# The columns each list sorts by, both ways ("-" first = descending); id is always the tie-break.
TASK_SORTS = (
    "number",
    "title",
    "status",
    "priority",
    "due_date",
    "completed_at",
    "created_at",
    "project_name",
    "assignee_name",
    "id",
)
PROJECT_SORTS = (
    "code",
    "name",
    "color",
    "is_active",
    "owner_name",
    "task_count",
    "open_task_count",
    "created_at",
    "id",
)


def _both_ways(keys: tuple[str, ...]):
    return Literal[tuple(f"{sign}{key}" for key in keys for sign in ("", "-"))]


TaskSort = _both_ways(TASK_SORTS)
ProjectSort = _both_ways(PROJECT_SORTS)


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
    ]


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _business_day(value: Any) -> Any:
    """A moment is the day it falls on in the business's time zone; a plain day stays as it is."""
    if isinstance(value, str) and len(value.strip()) > 10:
        try:
            value = dt.datetime.fromisoformat(value.strip())
        except ValueError:
            return value  # pydantic says «Enter a valid date.»
    if isinstance(value, dt.datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    return value


def _in_calendar(value: dt.date) -> dt.date:
    if not FIRST_YEAR <= value.year <= LAST_YEAR:
        raise ValueError(str(DATE_RANGE))
    return value


def _unique_tags(tags: list[str]) -> list[str]:
    if len(tags) > MAX_TAGS:
        raise ValueError(str(TAG_LIMIT))
    return list(dict.fromkeys(tags))


Title = _text(TITLE_MAX_LENGTH, 1)
Description = _text(TEXT_MAX_LENGTH)
CommentText = _text(TEXT_MAX_LENGTH, 1)
Search = _text(100)
Reference = _text(255, 1)
MemberName = _text(200, 1)
Code = _text(40, 1)
ProjectName = _text(200, 1)
Tag = _text(50, 1)
Tags = Annotated[list[Tag], AfterValidator(_unique_tags)]
# Empty, or #RRGGBB: it is painted in a style attribute, so nothing else gets in.
Color = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^(#[0-9A-Fa-f]{6})?$")]
Day = Annotated[dt.date, BeforeValidator(_business_day), AfterValidator(_in_calendar)]
DueDate = Annotated[Day | None, BeforeValidator(_blank_to_none)]

# Field descriptions shared by several schemas (the assistant reads them).
D_TASK_ID = "The task's id. Give it, or its number or title in `task`."
D_TASK = "The task's number (TSK-20261014-0001) or its title, or part of it, when the id is not known."
D_PROJECT_ID = "The project's id. Give it, or its code or name in `project`."
D_PROJECT = "The project's code or name, when its id is not known."
D_MEMBER_ID = "Id of the staff member (Staff app)."
D_MEMBER = "The staff member's name (first name, full name or part of it) when the id is not known."
D_TITLE = "What has to be done, in a short sentence."
D_DESCRIPTION = "Details of the task; empty for none."
D_PRIORITY = "Priority: low, medium, high or urgent."
D_DUE_DATE = "The day it is due (YYYY-MM-DD); a date and time counts as its day in the business's time zone."
D_TAGS = "Free labels of the task (at most 20, each up to 50 characters)."
D_COLOR = "Colour of the project, as #RRGGBB; empty for none."


def _named(value: str | None, info: ValidationInfo, id_field: str, message) -> str | None:
    """The text reference is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(message))
    return value


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(50, ge=1, le=100, description="How many rows to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many rows to skip, for the next pages.")


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int = Field(description="Rows that match, over all pages.")
    limit: int
    offset: int


# References


class TaskRefIn(In):
    id: UUID | None = Field(None, description=D_TASK_ID)
    task: Reference | None = Field(None, validate_default=True, description=D_TASK)

    @field_validator("task")
    @classmethod
    def _task_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "id", NO_TASK)


class ProjectRefIn(In):
    id: UUID | None = Field(None, description=D_PROJECT_ID)
    project: Reference | None = Field(None, validate_default=True, description=D_PROJECT)

    @field_validator("project")
    @classmethod
    def _project_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "id", NO_PROJECT)


class MemberReleaseIn(In):
    """The payload of ``staff.member.terminated``."""

    id: UUID = Field(description="The staff member who left.")


# Tasks


class TaskListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the number, title, description, assignee or project."
    )
    number: Search | None = Field(None, description="Keep the tasks whose number contains this.")
    title: Search | None = Field(None, description="Keep the tasks whose title contains this.")
    status: TaskStatus | None = Field(
        None, description="Keep the tasks in this status: todo, in_progress, blocked, done or cancelled."
    )
    priority: TaskPriority | None = Field(None, description="Keep the tasks of this priority.")
    open: bool | None = Field(
        None, description="true: only open tasks (to do, in progress, blocked); false: only done or cancelled."
    )
    overdue: bool | None = Field(
        None, description="true: only open tasks whose due date has passed (the business's today)."
    )
    project_id: UUID | None = Field(None, description="Keep the tasks of this project (by id).")
    project: Reference | None = Field(
        None, description="Keep the tasks of this project, by its code or its name."
    )
    assigned_to_id: UUID | None = Field(
        None, description="Keep the tasks assigned to this staff member (by id)."
    )
    assignee: Search | None = Field(
        None, description="Keep the tasks whose assignee's name contains this (Ana, Ana López)."
    )
    unassigned: bool | None = Field(None, description="true: only the tasks nobody is assigned to.")
    parent_id: UUID | None = Field(None, description="Keep the subtasks of this task (by id).")
    top_level: bool | None = Field(None, description="true: only tasks that are not a subtask.")
    tag: Tag | None = Field(None, description="Keep the tasks with this tag.")
    due_from: Day | None = Field(None, description="Keep the tasks due on or after this day.")
    due_to: Day | None = Field(None, description="Keep the tasks due on or before this day.")
    completed_from: Day | None = Field(
        None, description="Keep the tasks completed on or after this day."
    )
    completed_to: Day | None = Field(
        None, description="Keep the tasks completed on or before this day."
    )
    created_from: Day | None = Field(None, description="Keep the tasks created on or after this day.")
    created_to: Day | None = Field(None, description="Keep the tasks created on or before this day.")
    sort: TaskSort = Field(
        "-created_at", description="Column to sort by; a leading '-' sorts descending."
    )


class TaskMineIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the number or the title.")
    due_within_days: int | None = Field(
        None,
        ge=0,
        le=366,
        description="Only the tasks due within this many days from today (undated ones are left out).",
    )


class SubtaskListIn(PageIn, TaskRefIn):
    """The subtasks of the task named by ``id`` or ``task``."""


class TaskIn(In):
    title: Title = Field(description=D_TITLE)
    description: Description = Field("", description=D_DESCRIPTION)
    priority: TaskPriority = Field("medium", description=D_PRIORITY)
    due_date: DueDate = Field(None, description=D_DUE_DATE)
    project_id: UUID | None = Field(None, description=D_PROJECT_ID)
    project: Reference | None = Field(None, description=D_PROJECT)
    parent_id: UUID | None = Field(
        None, description="Id of the task this one is a subtask of. Give it, or its number or title in `parent`."
    )
    parent: Reference | None = Field(
        None, description="Number or title of the task this one is a subtask of, when its id is not known."
    )
    assigned_to_id: UUID | None = Field(None, description="Id of the staff member who will do it.")
    assignee: MemberName | None = Field(
        None,
        title=gettext_noop("Assigned to"),
        description="Name of the staff member who will do it, when the id is not known.",
    )
    tags: Tags = Field(default_factory=list, description=D_TAGS)


class TaskPatchIn(TaskRefIn):
    """Only the fields sent are changed. ``null`` clears ``due_date`` and ``project_id``."""

    title: Title | None = Field(None, description=D_TITLE)
    description: Description | None = Field(None, description=D_DESCRIPTION)
    priority: TaskPriority | None = Field(None, description=D_PRIORITY)
    due_date: DueDate = Field(None, description=D_DUE_DATE + " Send null to clear it.")
    project_id: UUID | None = Field(None, description=D_PROJECT_ID + " Send null to take it out.")
    project: Reference | None = Field(None, description=D_PROJECT)
    tags: Tags | None = Field(None, description=D_TAGS + " Replaces the list.")


class SetStatusIn(TaskRefIn):
    status: TaskStatus = Field(
        description="The new status: todo, in_progress, blocked, done or cancelled."
    )


class AssignIn(TaskRefIn):
    """One person (by id, by name or the caller); nobody unassigns the task."""

    member_id: UUID | None = Field(None, title=gettext_noop("Assigned to"), description=D_MEMBER_ID)
    member: MemberName | None = Field(None, title=gettext_noop("Assigned to"), description=D_MEMBER)
    to_me: bool = Field(
        False, title=gettext_noop("Assign to me"), description="true: assign it to the caller's own staff record."
    )

    @field_validator("member")
    @classmethod
    def _one_by_name(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and info.data.get("member_id") is not None:
            raise ValueError(str(ONE_PERSON))
        return value

    @field_validator("to_me")
    @classmethod
    def _one_or_me(cls, value: bool, info: ValidationInfo) -> bool:
        if value and (info.data.get("member_id") is not None or info.data.get("member") is not None):
            raise ValueError(str(ONE_PERSON))
        return value


# Comments


class CommentListIn(PageIn):
    task_id: UUID | None = Field(None, description=D_TASK_ID)
    task: Reference | None = Field(None, validate_default=True, description=D_TASK)

    @field_validator("task")
    @classmethod
    def _task_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "task_id", NO_TASK)


class CommentIn(In):
    task_id: UUID | None = Field(None, description=D_TASK_ID)
    task: Reference | None = Field(None, validate_default=True, description=D_TASK)
    text: CommentText = Field(description="The comment (up to 5000 characters).")

    @field_validator("task")
    @classmethod
    def _task_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "task_id", NO_TASK)


# Projects


class ProjectListIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the code or the name.")
    code: Search | None = Field(None, description="Keep the projects whose code contains this.")
    name: Search | None = Field(None, description="Keep the projects whose name contains this.")
    color: Search | None = Field(None, description="Keep the projects whose colour (#RRGGBB) contains this.")
    is_active: bool | None = Field(
        None, description="true: only the active projects; false: only the inactive ones."
    )
    owner_id: UUID | None = Field(None, description="Keep the projects of this owner (staff member id).")
    sort: ProjectSort = Field(
        "-created_at", description="Column to sort by; a leading '-' sorts descending."
    )


class ProjectIn(In):
    code: Code = Field(description="Short code of the project, unique in the business (q3-audit).")
    name: ProjectName = Field(description="Name of the project.")
    color: Color = Field("", description=D_COLOR)
    owner_id: UUID | None = Field(None, description="Id of the staff member who owns the project.")
    owner: MemberName | None = Field(
        None, description="Name of the staff member who owns the project, when the id is not known."
    )


class ProjectPatchIn(ProjectRefIn):
    """Only the fields sent are changed; the code never changes (it is the project's key)."""

    name: ProjectName | None = Field(None, description="New name.")
    color: Color | None = Field(None, description=D_COLOR)
    is_active: bool | None = Field(
        None, description="false takes the project out of use (its tasks stay); true brings it back."
    )
    owner_id: UUID | None = Field(
        None, description="Id of the staff member who owns the project. Send null to clear it."
    )
    owner: MemberName | None = Field(None, description="Name of the owner, when the id is not known.")


# Outputs


class TaskOut(Schema):
    id: UUID
    number: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    project_id: UUID | None
    project_name: str | None
    project_color: str | None
    parent_id: UUID | None
    parent_number: str | None
    parent_title: str | None
    assigned_to_id: UUID | None
    assignee_name: str | None
    created_by_id: UUID | None
    created_by_name: str | None
    due_date: dt.date | None
    completed_at: dt.datetime | None
    tags: list[str]
    subtask_count: int
    comment_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    can_change: bool = Field(description="Whether the caller may change this task.")


TaskPage = Page[TaskOut]


class CommentOut(Schema):
    id: UUID
    task_id: UUID
    text: str
    author_id: UUID | None
    author_name: str | None
    created_at: dt.datetime


CommentPage = Page[CommentOut]


class ProjectOut(Schema):
    id: UUID
    code: str
    name: str
    color: str
    is_active: bool
    owner_id: UUID | None
    owner_name: str | None
    task_count: int
    open_task_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


ProjectPage = Page[ProjectOut]


class DeletedOut(Schema):
    id: UUID


class ReleasedOut(Schema):
    released: int = Field(description="How many open tasks were left unassigned.")
