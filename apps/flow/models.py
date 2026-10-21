"""Models of the flow app: the automation (``Flow``), each time it ran (``FlowRun``), what the assistant
proposed (``Draft``), the secrets its calls to other systems use (``Secret``) and the questions its runs
ask a person (``Question``).

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
#: ``<app>/<id>`` of a factory recipe.
RECIPE_MAX_LENGTH = 96


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
    # The factory recipe it was built from (``<app>/<id>``, FLOW-F33); empty for the owner's own.
    recipe = models.CharField(_("factory recipe"), max_length=RECIPE_MAX_LENGTH, blank=True, default="")
    # The fingerprint of that recipe when it was built or restored: a newer one is «New version».
    recipe_digest = models.CharField(_("recipe fingerprint"), max_length=64, blank=True, default="")

    class Meta:
        verbose_name = _("automation")
        verbose_name_plural = _("automations")
        ordering = ["-updated_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe"],
                condition=Q(deleted_at__isnull=True) & ~Q(recipe=""),
                name="flow_flow_one_per_recipe",
            ),
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
        # A «Call another system» step is out (FLOW-F27): the call goes after the COMMIT.
        CALLING = "calling", pgettext_lazy("run status", "Calling another system")
        # A «Ask somebody first» step waits for its answer (FLOW-F28).
        ASKING = "asking", pgettext_lazy("run status", "Waiting for an answer")
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
    # When a wait ends; for a call (``calling``), when it may be sent (again): a lease of CALL_LEASE_MINUTES.
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
                        "calling",
                        "asking",
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


#: A secret's name: upper case, digits and ``_``, up to 64 characters (the old hub's rule).
SECRET_NAME_RE = r"^[A-Z][A-Z0-9_]{0,63}$"


class Secret(UUIDModel):
    """A value a «Call another system» step sends (an API key, a token), kept sealed (``vault``): only its
    name is ever shown again (FLOW-F26). Shared by every automation of the business."""

    name = models.CharField(_("name"), max_length=64, unique=True)
    # Fernet token under settings.FLOW_SECRETS_KEY; never the value.
    ciphertext = models.TextField(_("sealed value"))
    created_by = models.CharField(_("created by"), max_length=128, blank=True)
    updated_by = models.CharField(_("updated by"), max_length=128, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("secret")
        verbose_name_plural = _("secrets")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(name__regex=SECRET_NAME_RE), name="flow_secret_name_valid"
            ),
        ]

    def __str__(self) -> str:
        return self.name


#: Who a question is asked of (FLOW-F28): «whoever runs the business» (owner and admin), the managers or the
#: employees; whoever runs the business may always answer.
QUESTION_ROLES = ("", "manager", "employee")


class Question(UUIDModel):
    """What a run's «Ask someone first» step asked (FLOW-F28), waiting in «Waiting for your answer» (FLOW-F29) until a
    person of its role answers it or its time runs out (FLOW-F30). Its texts were filled in when asked, and
    what to do with a no and with silence travels in the row: editing the automation changes neither."""

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("question status", "Waiting for an answer")
        APPROVED = "approved", pgettext_lazy("question status", "Yes")
        REJECTED = "rejected", pgettext_lazy("question status", "No")
        EXPIRED = "expired", pgettext_lazy("question status", "Nobody answered in time")
        CANCELLED = "cancelled", pgettext_lazy("question status", "Cancelled")

    run = models.ForeignKey(FlowRun, on_delete=models.CASCADE, related_name="questions", verbose_name=_("run"))
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name="+", verbose_name=_("automation"))
    step_id = models.CharField(_("step"), max_length=32)
    title = models.CharField(_("question"), max_length=300)
    details = models.TextField(_("details"), blank=True, default="")
    role = models.CharField(_("asked of"), max_length=16, blank=True, default="")
    on_no = models.CharField(_("if they say no"), max_length=16, default="stop")
    on_timeout = models.CharField(_("if nobody answers"), max_length=16, default="no")
    expires_at = models.DateTimeField(_("answer before"))
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PENDING)
    decided_by = models.CharField(_("answered by"), max_length=128, blank=True, default="")
    decided_at = models.DateTimeField(_("answered at"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=500, blank=True, default="")
    created_at = models.DateTimeField(_("asked at"), default=timezone.now)

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ["expires_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "step_id"], name="flow_question_once_per_step"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected", "expired", "cancelled"]),
                name="flow_question_status_valid",
            ),
            models.CheckConstraint(condition=Q(role__in=list(QUESTION_ROLES)), name="flow_question_role_valid"),
            models.CheckConstraint(condition=Q(on_no__in=["stop", "continue"]), name="flow_question_on_no_valid"),
            models.CheckConstraint(
                condition=Q(on_timeout__in=["no", "stop", "continue"]), name="flow_question_on_timeout_valid"
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_at"], name="flow_question_due_idx")]

    def __str__(self) -> str:
        return self.title

