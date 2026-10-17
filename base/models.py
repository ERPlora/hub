"""Models of base, the platform app of hub-next.

Phase 1 has no tenancy: a user's role on a hub is a ``Membership`` keyed by the first label of the
Host (``a`` for ``a.localhost``). Phase 2 replaces it with the hub's own staff in its database.

``Hub`` is the registry of the hubs this Hub serves (docs/plans/2026-10-17-demo-hubs-fase-1.md, §1.1): the SaaS
writes it through ``/internal/hubs/{id}`` (``base.internal``) and the host gate reads it (``base.registry``). Phase 2
moves it to ``control.Hub``, the same columns plus ``db_name``, ``schema_state``, ``schema_apps`` and ``cluster``.
``DemoCode`` is a one-time code into a demo hub, which the SaaS asks for (``POST /internal/demos/{slug}/codes``) and
the demo's ``/auth/callback`` redeems here, without calling the SaaS back.
"""

import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel
from live.slugs import hub_slug_validator, validate_hub_slug

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


def registry_slug_validator(value: str) -> None:
    """A hub's slug as the registry takes it: ``live.slugs``' rule, ``demo-…`` included (the Hub's own demos)."""
    try:
        validate_hub_slug(value, allow_demo=True)
    except ValueError:
        # Whatever the registry refuses, a customer's slug field refuses too: it raises with its message and code.
        hub_slug_validator(value)


class Hub(models.Model):
    """One hub this Hub serves, keyed by the SaaS's id (``PUT /internal/hubs/{id}``) or its own (a demo, ``a``/``b``).

    ``status`` is PLAN-DB §6's vocabulary, the part phase 1 uses: ``requested`` → ``ready`` (at once: there is no
    database to clone yet) → ``cancelled`` (the SaaS deleted the business; ``restore`` brings it back) or, for a
    demo, ``expired`` → ``purged``. The host gate answers 404 to a slug without a row, 410 to one that is gone and
    503 to one still being prepared. ``state`` is the SaaS's last photo (``PUT …/state``) as it came, with its
    monotonic ``state_version``: an older or equal one changes nothing. ``demo_session_key`` is the sha256 of the
    SaaS's browser session that owns a demo, never the session key itself.
    """

    class Status(models.TextChoices):
        # With a context: the apps translate the same English words for their own things («Lista», «Cancelada»).
        REQUESTED = "requested", pgettext_lazy("hub status", "Requested")
        READY = "ready", pgettext_lazy("hub status", "Ready")
        FAILED = "failed", pgettext_lazy("hub status", "Failed")
        CANCELLED = "cancelled", pgettext_lazy("hub status", "Cancelled")
        EXPIRED = "expired", pgettext_lazy("hub status", "Expired")
        PURGED = "purged", pgettext_lazy("hub status", "Purged")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    slug = models.CharField(_("slug"), max_length=63, unique=True, validators=[registry_slug_validator])
    name = models.CharField(_("name"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=2, blank=True)
    timezone = models.CharField(_("time zone"), max_length=64, blank=True)
    language = models.CharField(_("language"), max_length=8, blank=True)
    vertical = models.CharField(_("vertical"), max_length=63, blank=True)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.REQUESTED)
    is_demo = models.BooleanField(_("demo"), default=False)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    demo_session_key = models.CharField(_("demo session"), max_length=64, blank=True)
    state = models.JSONField(_("state"), default=dict, blank=True)
    state_version = models.PositiveBigIntegerField(_("state version"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    purged_at = models.DateTimeField(_("purged at"), null=True, blank=True)

    class Meta:
        verbose_name = _("hub")
        verbose_name_plural = _("hubs")
        ordering = ["slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["demo_session_key"],
                condition=Q(is_demo=True, status="ready") & ~Q(demo_session_key=""),
                name="base_hub_one_live_demo_per_session",
            )
        ]
        indexes = [models.Index(fields=["is_demo", "status", "expires_at"], name="base_hub_demo_expiry")]

    def __str__(self) -> str:
        return self.slug


class DemoCode(UUIDModel):
    """A one-time code into a demo hub (plan 2026-10-17, §1.1 and §1.6), kept by its sha256 only, never in clear.

    The SaaS asks for one for the browser that owns the demo and posts it to the demo's ``/auth/callback`` in a form
    (never in a URL); it opens one session, within its minute (``expires_at``), and ``used_at`` says it was spent. A
    demo has several (a visitor who lost the cookie enters again); they go with it when the worker purges it.
    """

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="demo_codes", verbose_name=_("hub"))
    code_hash = models.CharField(_("code hash"), max_length=64, unique=True)
    language = models.CharField(_("language"), max_length=8, blank=True)
    expires_at = models.DateTimeField(_("expires at"))
    used_at = models.DateTimeField(_("used at"), null=True, blank=True)

    class Meta:
        verbose_name = _("demo code")
        verbose_name_plural = _("demo codes")
        ordering = ["expires_at"]

    def __str__(self) -> str:
        return f"{self.hub} ({self.expires_at:%Y-%m-%d %H:%M:%S})"
