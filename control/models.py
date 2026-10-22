"""The control database's models (PLAN-DB §2; plan 2026-10-22-fase-2-tenencia, S1).

``Hub`` is the registry of the hubs this Hub serves (docs/plans/2026-10-17-demo-hubs-fase-1.md, §1.1): the SaaS
writes it through ``/internal/hubs/{id}`` (``base.internal``) and the host gate reads it (``base.registry``).
``DemoCode`` is a one-time code into a demo hub, which the SaaS asks for (``POST /internal/demos/{slug}/codes``) and
the demo's ``/auth/callback`` redeems here, without calling the SaaS back. Both moved from ``base`` in S1 keeping
their tables (``base_hub``, ``base_democode``): their migration only moved them in Django's state.

``Hub.db_name`` says where a hub's data lives: its own database (``<control>_<hex>``, ``demo_<hex>``;
``base.tenancy.names``) or, empty, control's, where every hub of phase 1 keeps its data until the cut of S5 (plan,
decision 1). ``Cluster`` is a database cluster a hub's database is on; ``HubDue``, the work a hub has due (the
worker's index, PLAN-DB §8): both wait for S2.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import connections, models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel
from live.slugs import hub_slug_validator, validate_hub_slug

from base.tenancy import names


def registry_slug_validator(value: str) -> None:
    """A hub's slug as the registry takes it: ``live.slugs``' rule, ``demo-…`` included (the Hub's own demos)."""
    try:
        validate_hub_slug(value, allow_demo=True)
    except ValueError:
        # Whatever the registry refuses, a customer's slug field refuses too: it raises with its message and code.
        hub_slug_validator(value)


def db_name_validator(value: str) -> None:
    """A hub's or a demo's database next to this control database (``base.tenancy.names``)."""
    try:
        names.validate(value, control=connections.settings["default"]["NAME"])
    except names.InvalidDatabaseName as invalid:
        raise ValidationError(str(invalid), code="invalid") from None


class Cluster(UUIDModel):
    """A database cluster that holds hubs' databases: its writer (the migrator's way in) and the PgBouncer of the
    tasks in front of it (every request's). ``is_open``: new hubs may be placed on it (PLAN-DB §6, «Colocación»)."""

    name = models.CharField(_("name"), max_length=63, unique=True)
    host = models.CharField(_("writer host"), max_length=255)
    port = models.PositiveIntegerField(_("writer port"), default=5432)
    pooler_host = models.CharField(_("PgBouncer host"), max_length=255)
    pooler_port = models.PositiveIntegerField(_("PgBouncer port"), default=6432)
    is_open = models.BooleanField(_("open to new hubs"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("cluster")
        verbose_name_plural = _("clusters")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Hub(models.Model):
    """One hub this Hub serves, keyed by the SaaS's id (``PUT /internal/hubs/{id}``) or its own (a demo, ``a``/``b``).

    ``status`` is PLAN-DB §6's vocabulary, the part phase 1 uses: ``requested`` → ``ready`` (at once: there is no
    database to clone yet) → ``cancelled`` (the SaaS deleted the business; ``restore`` brings it back) or, for a
    demo, ``expired`` → ``purged``. The host gate answers 404 to a slug without a row, 410 to one that is gone and
    503 to one still being prepared. ``state`` is the SaaS's last photo (``PUT …/state``) as it came, with its
    monotonic ``state_version``: an older or equal one changes nothing. ``demo_session_key`` is the sha256 of the
    SaaS's browser session that owns a demo, never the session key itself.

    ``db_name`` is the hub's own database, or empty while it shares control's (``base.tenancy.context.use_hub``);
    ``schema_state`` and ``schema_apps`` are what the migrator confirmed of its schema (S3); ``cluster`` the cluster
    its database is on (none: the settings' own); ``is_platform`` marks ERPlora's own hub (PLAN-SAAS §4).
    """

    class Status(models.TextChoices):
        # With a context: the apps translate the same English words for their own things («Lista», «Cancelada»).
        REQUESTED = "requested", pgettext_lazy("hub status", "Requested")
        READY = "ready", pgettext_lazy("hub status", "Ready")
        FAILED = "failed", pgettext_lazy("hub status", "Failed")
        CANCELLED = "cancelled", pgettext_lazy("hub status", "Cancelled")
        EXPIRED = "expired", pgettext_lazy("hub status", "Expired")
        PURGED = "purged", pgettext_lazy("hub status", "Purged")

    class SchemaState(models.TextChoices):
        CURRENT = "current", pgettext_lazy("hub schema", "Current")
        BEHIND = "behind", pgettext_lazy("hub schema", "Behind")

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
    db_name = models.CharField(
        _("database"), max_length=63, blank=True, default="", db_default="", validators=[db_name_validator]
    )
    schema_state = models.CharField(
        _("schema"),
        max_length=16,
        choices=SchemaState.choices,
        default=SchemaState.CURRENT,
        db_default=SchemaState.CURRENT,
    )
    schema_apps = models.JSONField(_("created apps"), default=dict, blank=True, db_default={})
    cluster = models.ForeignKey(
        Cluster, on_delete=models.PROTECT, null=True, blank=True, related_name="hubs", verbose_name=_("cluster")
    )
    is_platform = models.BooleanField(_("platform hub"), default=False, db_default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    purged_at = models.DateTimeField(_("purged at"), null=True, blank=True)

    class Meta:
        db_table = "base_hub"
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
        db_table = "base_democode"
        verbose_name = _("demo code")
        verbose_name_plural = _("demo codes")
        ordering = ["expires_at"]

    def __str__(self) -> str:
        return f"{self.hub} ({self.expires_at:%Y-%m-%d %H:%M:%S})"


class HubDue(models.Model):
    """When a hub has work due in the worker (PLAN-DB §8): its outbox, tasks, fiscal sending or activations.

    One row per hub, keyed by it: ``mark_due`` moves ``due_at`` earlier, the worker takes the due ones with
    ``SKIP LOCKED`` and a lease (``lease_until``), and ``fiscal_oldest_pending_at`` feeds the oldest-pending metric.
    """

    hub = models.OneToOneField(
        Hub, on_delete=models.CASCADE, primary_key=True, related_name="due", verbose_name=_("hub")
    )
    due_at = models.DateTimeField(_("due at"))
    lease_until = models.DateTimeField(_("leased until"), null=True, blank=True)
    fiscal_oldest_pending_at = models.DateTimeField(_("oldest fiscal record pending since"), null=True, blank=True)

    class Meta:
        verbose_name = _("hub due")
        verbose_name_plural = _("hubs due")
        ordering = ["due_at"]
        indexes = [models.Index(fields=["due_at"], name="control_hubdue_due_at")]

    def __str__(self) -> str:
        return f"{self.hub_id} @ {self.due_at:%Y-%m-%d %H:%M:%S}"
