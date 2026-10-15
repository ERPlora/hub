"""Models of the flow app: the automation (``Flow``), each time it ran (``FlowRun``) and what the assistant
proposed (``Draft``).

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications are
per scope. Phase 2 moves them to each hub's database. An automation names other apps' operations and
events by their names, never their rows: nothing here points at another app's table.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

#: Longest name of an automation (the old module's draft schema).
NAME_MAX_LENGTH = 120
#: An event name of the outbox (``live.models.OutboxEvent.name``).
EVENT_MAX_LENGTH = 96


class Flow(UUIDModel):
    """An automation: when it starts (its trigger) and the steps it runs, with what it may do."""

    class Trigger(models.TextChoices):
        EVENT = "event", _("Something happens")
        SCHEDULE = "schedule", _("On a schedule")
        AT = "at", _("Once, at a date and time")
        MANUAL = "manual", _("Only by hand")

    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    enabled = models.BooleanField(pgettext_lazy("automation", "on"), default=False)
    trigger_kind = models.CharField(
        _("starts with"), max_length=16, choices=Trigger.choices, default=Trigger.MANUAL
    )
    # An event of an active app (``<app>.<entity>.<fact>``), for ``event``.
    trigger_event = models.CharField(
        _("event"), max_length=EVENT_MAX_LENGTH, blank=True
    )
    # «Only when…»: a condition on what the event brings (``document.holds``).
    trigger_filter = models.JSONField(_("only when"), default=dict, blank=True)
    # ``{"every": "day|week|month", "weekday": 0-6, "day": 1-31, "time": "HH:MM"}``, for ``schedule``.
    schedule = models.JSONField(_("schedule"), default=dict, blank=True)
    run_at = models.DateTimeField(_("date and time"), null=True, blank=True)
    # When ``schedule`` or ``at`` starts it next (``fire_due``); empty while it never will.
    next_fire_at = models.DateTimeField(
        _("next start"), null=True, blank=True, db_index=True
    )
    steps = models.JSONField(_("steps"), default=list, blank=True)
    # The operations (actions and reads) it may run: the list the owner granted.
    grants = models.JSONField(_("permissions"), default=list, blank=True)
    # Goes up when the trigger or the steps change: a run keeps the version it started with.
    version = models.PositiveIntegerField(_("version"), default=1)
    # The language of whoever saved it last: what its runs' messages are written in.
    language = models.CharField(_("language"), max_length=8, default="en")
    # Name, event and the operations of its steps: what the list's search looks in.
    search_text = models.TextField(_("search text"), blank=True, default="")
    created_by = models.CharField(_("created by"), max_length=128, blank=True)
    updated_by = models.CharField(_("updated by"), max_length=128, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    # Deleted automations stop at once and keep their history.
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("automation")
        verbose_name_plural = _("automations")
        ordering = ["-updated_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(trigger_kind__in=["event", "schedule", "at", "manual"]),
                name="flow_flow_trigger_kind_valid",
            ),
            models.CheckConstraint(
                condition=~Q(trigger_kind="event") | ~Q(trigger_event=""),
                name="flow_flow_event_needs_its_event",
            ),
        ]
        indexes = [
            models.Index(
                fields=["trigger_kind", "trigger_event"], name="flow_flow_trigger_idx"
            )
        ]

    def __str__(self) -> str:
        return self.name


class FlowRun(UUIDModel):
    """One time an automation ran: what started it, where it is and what each step did."""

    class Status(models.TextChoices):
        RUNNING = "running", pgettext_lazy("run status", "Running")
        WAITING = "waiting", pgettext_lazy("run status", "Waiting")
        SUCCEEDED = "succeeded", pgettext_lazy("run status", "Finished well")
        STOPPED = "stopped", pgettext_lazy("run status", "Stopped by a condition")
        FAILED = "failed", pgettext_lazy("run status", "Stopped by an error")
        CANCELLED = "cancelled", pgettext_lazy("run status", "Cancelled")

    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name=_("automation"),
    )
    flow_version = models.PositiveIntegerField(_("version"))
    # ``{"steps": […]}`` as they were when it started: a waiting run goes on with them.
    definition = models.JSONField(_("steps it runs"), default=dict)
    trigger_kind = models.CharField(
        _("started by"), max_length=16, choices=Flow.Trigger.choices
    )
    # The outbox event's id, the scheduled instant or a fresh id by hand: one run per flow and key.
    trigger_key = models.CharField(_("trigger reference"), max_length=128)
    event_name = models.CharField(_("event"), max_length=EVENT_MAX_LENGTH, blank=True)
    input = models.JSONField(_("input"), default=dict, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    # The next step to run (its position in ``definition["steps"]``).
    step_index = models.PositiveIntegerField(_("next step"), default=0)
    # What each step did, in words the history composes (``{step, kind, outcome, …}``).
    log = models.JSONField(_("log"), default=list, blank=True)
    # ``steps.<id>``: what each step left for the next ones.
    outputs = models.JSONField(_("outputs"), default=dict, blank=True)
    error_code = models.CharField(_("error code"), max_length=96, blank=True)
    error_message = models.TextField(_("error"), blank=True)
    resume_at = models.DateTimeField(_("resumes at"), null=True, blank=True)
    # The automations whose steps caused the event that started this one (loop guard).
    chain = models.JSONField(_("chain"), default=list, blank=True)
    started_by = models.CharField(_("started by"), max_length=128, blank=True)
    started_at = models.DateTimeField(_("started at"), default=timezone.now)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("run")
        verbose_name_plural = _("runs")
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["flow", "trigger_key"], name="flow_run_once_per_trigger"
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "running",
                        "waiting",
                        "succeeded",
                        "stopped",
                        "failed",
                        "cancelled",
                    ]
                ),
                name="flow_run_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "resume_at"], name="flow_run_waiting_idx"),
            models.Index(fields=["flow", "-started_at"], name="flow_run_history_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.flow} · {self.started_at:%Y-%m-%d %H:%M}"


class Draft(UUIDModel):
    """An automation the assistant proposed: not an automation until a person creates it."""

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("draft status", "Pending")
        USED = "used", pgettext_lazy("draft status", "Used")
        DISMISSED = "dismissed", pgettext_lazy("draft status", "Dismissed")

    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    # ``{"trigger": {…}, "steps": […]}`` as the assistant wrote it.
    definition = models.JSONField(_("definition"), default=dict)
    # What the assistant could not work out, one sentence each.
    notes = models.JSONField(_("notes"), default=list, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.PENDING
    )
    flow = models.ForeignKey(
        Flow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("automation"),
    )
    created_by = models.CharField(_("created by"), max_length=128, blank=True)
    decided_by = models.CharField(_("decided by"), max_length=128, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    class Meta:
        verbose_name = _("draft")
        verbose_name_plural = _("drafts")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["pending", "used", "dismissed"]),
                name="flow_draft_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name
