"""Models of base, the platform app of hub-next.

Phase 1 has no tenancy: a user's role on a hub is a ``Membership`` keyed by the first label of the
Host (``a`` for ``a.localhost``). Phase 2 replaces it with the hub's own staff in its database.

The registry of hubs (``Hub``) and the demos' codes (``DemoCode``) moved to ``control`` in phase 2's S1 (plan
2026-10-22), keeping their tables; they are still importable from here. ``HubIdentity`` is the row that says which hub
a hub's database is.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

# One DNS label, lowercase: what HostScopeResolver takes from the Host.
HOST_LABEL_RE = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"


class Membership(UUIDModel):
    """The customer role a person has on a hub, as the SaaS sent it (``hub_`` prefix included).

    The prefix keeps customer roles apart from the platform's (superuser, ``support``), which reach
    the Hub only through the ``hub-admin`` audience, on a separate staff copy (``saas-staff:<id>``)
    that never has a membership. No customer role makes the local user staff.
    """

    class Role(models.TextChoices):
        OWNER = "hub_owner", _("Owner")
        ADMIN = "hub_admin", _("Admin")
        MANAGER = "hub_manager", _("Manager")
        EMPLOYEE = "hub_employee", _("Employee")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("user"),
    )
    host = models.CharField(
        _("host"),
        max_length=63,
        validators=[RegexValidator(HOST_LABEL_RE, _("Enter the first label of the host, e.g. “a” for a.localhost."))],
        help_text=_("First label of the host, e.g. “a” for a.localhost."),
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ["host", "user_id"]
        constraints = [models.UniqueConstraint(fields=["user", "host"], name="base_membership_user_host_unique")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.host} ({self.get_role_display()})"


class SessionOwner(UUIDModel):
    """Whose and where a session of the Hub is: the SaaS account that logged in and the host it noted.

    Written at every login (``base.services``), so ``POST /internal/sessions/revoke`` ends exactly the sessions of
    one account (on one hub, or everywhere) through this index, never decoding the sessions of the table. It goes
    with its session (``CASCADE``): a logout or ``clearsessions`` takes it too. Control's, like the sessions.
    """

    session = models.OneToOneField(
        "sessions.Session", on_delete=models.CASCADE, related_name="owner", verbose_name=_("session")
    )
    saas_user_id = models.CharField(_("SaaS account"), max_length=64)
    host = models.CharField(_("host"), max_length=63, help_text=_("The hub's slug, or the platform host's mark."))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("session owner")
        verbose_name_plural = _("session owners")
        ordering = ["saas_user_id", "host"]
        indexes = [models.Index(fields=["saas_user_id", "host"], name="base_sessionowner_user_host")]

    def __str__(self) -> str:
        return f"{self.saas_user_id} @ {self.host}"


class TaskSchedule(UUIDModel):
    """When a scheduled task of an app runs next (``base.scheduler``; the old Hub's ``_scheduled_tasks``).

    One row per task an app declares (``LiveAppConfig.scheduled_tasks``), written by the worker when it
    starts: the operation and the cron come from the code, the clock is the row's. Phase 2 keeps it in
    each hub's database, beside the rest of the hub's business.
    """

    app_label = models.CharField(_("app"), max_length=100)
    name = models.CharField(_("name"), max_length=100)
    operation = models.CharField(_("operation"), max_length=200)
    cron = models.CharField(_("cron (UTC)"), max_length=100)
    next_run = models.DateTimeField(_("next run"))
    last_run = models.DateTimeField(_("last run"), null=True, blank=True)

    class Meta:
        verbose_name = _("scheduled task")
        verbose_name_plural = _("scheduled tasks")
        ordering = ["app_label", "name"]
        constraints = [
            models.UniqueConstraint(fields=["app_label", "name"], name="base_taskschedule_app_name_unique")
        ]
        indexes = [models.Index(fields=["next_run"], name="base_taskschedule_next_run")]

    def __str__(self) -> str:
        return f"{self.app_label}.{self.name}"


class EventDelivery(UUIDModel):
    """One app's delivery of one outbox event (``base.relay``; the old Hub's ``_event_delivery``).

    The relay writes one row per app that listens to the event, when it takes the event (and marks the event's
    ``delivered_at``); the reaction's writes and its row's ``delivered`` commit in one transaction, so an app
    never gets an event twice. A reaction that fails waits a little longer each time (``next_attempt_at``) and,
    after its last attempt or past the deepest level of events an event can start (``depth``), stays ``dead``
    with what went wrong. Phase 2 keeps it in each hub's database, beside its outbox.

    Who runs the business sees the ones given up in System › Failed events (APP-BASE-7): resending one puts it back
    ``pending``; discarding it closes it for good (``discarded``), with who, when and why, and keeps the row.
    """

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("event delivery status", "Pending")
        DELIVERED = "delivered", pgettext_lazy("event delivery status", "Delivered")
        DEAD = "dead", pgettext_lazy("event delivery status", "Given up")
        DISCARDED = "discarded", pgettext_lazy("event delivery status", "Discarded")

    event = models.ForeignKey(
        "live.OutboxEvent", on_delete=models.CASCADE, related_name="+", verbose_name=_("event")
    )
    app_label = models.CharField(_("app"), max_length=100)
    depth = models.PositiveSmallIntegerField(_("depth"), default=0)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(_("next attempt"))
    last_error = models.TextField(_("last error"), blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("discarded at"), null=True, blank=True)
    closed_by = models.CharField(_("discarded by"), max_length=128, blank=True, db_default="")
    close_reason = models.CharField(_("why it was discarded"), max_length=500, blank=True, db_default="")

    class Meta:
        verbose_name = _("event delivery")
        verbose_name_plural = _("event deliveries")
        ordering = ["next_attempt_at", "app_label"]
        constraints = [
            models.UniqueConstraint(fields=["event", "app_label"], name="base_eventdelivery_event_app_unique")
        ]
        indexes = [
            models.Index(
                fields=["next_attempt_at"], condition=Q(status="pending"), name="base_eventdelivery_due"
            )
        ]

    def __str__(self) -> str:
        return f"{self.event_id} → {self.app_label} ({self.status})"


class HubIdentity(models.Model):
    """The one row that says which hub a hub's database is (PLAN-DB §3; plan 2026-10-22, step 6).

    Written when the database is made (its clone, S2; the tests' ``conftest.py``) and read once per process and alias
    by ``use_hub`` (``base.tenancy.identity``): a database that says it is another hub is refused and nothing is served
    from it. Control's database, phase 1's shared one, has the table and no row.
    """

    hub_id = models.UUIDField(_("hub"), primary_key=True)

    class Meta:
        db_table = "base_hub_identity"
        verbose_name = _("hub identity")
        verbose_name_plural = _("hub identities")

    def __str__(self) -> str:
        return str(self.hub_id)


# The registry moved to control in S1 (plan 2026-10-22): base/migrations/0004 and 0005 name the validator here, and
# phase 1's code imports the models from here.
from control.models import DemoCode, Hub, registry_slug_validator  # noqa: E402, F401
