"""Models of the task app: projects, tasks with their subtasks, comments and the per-day counter.

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications
are per scope. Phase 2 moves them to each hub's database. The assignee and a project's owner are
staff records (``staff.Member``, the app's only requirement); the creator of a task and the author of
a comment hang from the person in the business's own database (``base.HubUser``), like ``staff.TimeOff``'s
approver, never from control's user (tenancy W10): their columns ``*_hub_user_id`` are new, the old ones wait empty
for a later deploy to drop them (``migrations/0002_hub_users``).
"""

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.staff.models import Member

#: Longest title, description and comment (the old module's JSON Schema).
TITLE_MAX_LENGTH = 255
TEXT_MAX_LENGTH = 5000


class Project(UUIDModel):
    """A bucket of related tasks («Opening», «Summer refit»); its code is its key."""

    code = models.CharField(_("code"), max_length=40)
    name = models.CharField(_("name"), max_length=200)
    # Empty, or #RRGGBB.
    color = models.CharField(_("colour"), max_length=7, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    owner = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("owner"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(Lower("code"), name="task_project_code_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Task(UUIDModel):
    """A piece of the team's work; ``parent`` makes it a subtask of another one."""

    # Short labels carry a context: Django merges the apps' catalogues, and another app may translate
    # the same word otherwise («Done» → «Hecho»).
    class Status(models.TextChoices):
        TODO = "todo", pgettext_lazy("task status", "To Do")
        IN_PROGRESS = "in_progress", pgettext_lazy("task status", "In Progress")
        BLOCKED = "blocked", pgettext_lazy("task status", "Blocked")
        DONE = "done", pgettext_lazy("task status", "Done")
        CANCELLED = "cancelled", pgettext_lazy("task status", "Cancelled")

    class Priority(models.TextChoices):
        LOW = "low", pgettext_lazy("task priority", "Low")
        MEDIUM = "medium", pgettext_lazy("task priority", "Medium")
        HIGH = "high", pgettext_lazy("task priority", "High")
        URGENT = "urgent", pgettext_lazy("task priority", "Urgent")

    #: The statuses of a task nobody has to work on any more.
    CLOSED = (Status.DONE, Status.CANCELLED)

    number = models.CharField(_("number"), max_length=24, unique=True)
    title = models.CharField(_("title"), max_length=TITLE_MAX_LENGTH)
    description = models.TextField(_("description"), blank=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name=_("project"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtasks",
        verbose_name=_("parent task"),
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.TODO
    )
    priority = models.CharField(
        _("priority"), max_length=8, choices=Priority.choices, default=Priority.MEDIUM
    )
    assigned_to = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("assigned to"),
    )
    created_by = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="created_by_hub_user_id",
        verbose_name=_("created by"),
    )
    due_date = models.DateField(_("due date"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    tags = models.JSONField(_("tags"), default=list, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("task")
        verbose_name_plural = _("tasks")
        # The order of task.task.list: the newest first, id as the tie-break.
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["status", "due_date"], name="task_task_status_due_idx"),
            models.Index(fields=["assigned_to", "status"], name="task_task_assignee_idx"),
            models.Index(fields=["project", "created_at"], name="task_task_project_idx"),
            models.Index(fields=["parent", "created_at"], name="task_task_parent_idx"),
        ]
        constraints = [
            # Done stamps the completion date; leaving done clears it.
            models.CheckConstraint(
                condition=Q(status="done", completed_at__isnull=False)
                | (~Q(status="done") & Q(completed_at__isnull=True)),
                name="task_task_completed_iff_done",
            ),
            models.CheckConstraint(
                condition=~Q(parent=F("id")), name="task_task_not_own_parent"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.title}"

    @property
    def is_closed(self) -> bool:
        return self.status in self.CLOSED


class Comment(UUIDModel):
    """A comment of a task's thread; the thread is a record: never edited nor deleted by the app."""

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="comments", verbose_name=_("task")
    )
    author = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="author_hub_user_id",
        verbose_name=_("author"),
    )
    text = models.TextField(_("comment"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        # The order of task.comment.list: the newest first.
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["task", "created_at"], name="task_comment_task_idx")]

    def __str__(self) -> str:
        return self.text


class TaskCounter(UUIDModel):
    """The last task number given on a business day (``TSK-<day>-<NNNN>``)."""

    day = models.DateField(_("day"), unique=True)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("task counter")
        verbose_name_plural = _("task counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day:%Y%m%d}: {self.last_number}"
