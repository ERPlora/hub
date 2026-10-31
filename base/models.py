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

    class Credential(models.TextChoices):
        ACCOUNT = "account", pgettext_lazy("way in", "Account")
        PIN = "pin", pgettext_lazy("way in", "PIN")
        BADGE = "badge", pgettext_lazy("way in", "Badge")

    session = models.OneToOneField(
        "sessions.Session", on_delete=models.CASCADE, related_name="owner", verbose_name=_("session")
    )
    saas_user_id = models.CharField(_("SaaS account"), max_length=64)
    host = models.CharField(_("host"), max_length=63, help_text=_("The hub's slug, or the platform host's mark."))
    created_at = models.DateTimeField(pgettext_lazy("session owner", "created at"), auto_now_add=True)
    # APP-BASE-3: the hub's device the session was opened on (a ``TrustedDevice``'s id: a hub's row, so no foreign key
    # from control) and how its person proved who they are. A session with no device (the admin's, a demo's) has none.
    device_id = models.UUIDField(_("device"), null=True, blank=True)
    credential = models.CharField(
        _("way in"),
        max_length=8,
        choices=Credential.choices,
        default=Credential.ACCOUNT,
        db_default=Credential.ACCOUNT,
    )

    class Meta:
        verbose_name = _("session owner")
        verbose_name_plural = _("session owners")
        ordering = ["saas_user_id", "host"]
        indexes = [
            models.Index(fields=["saas_user_id", "host"], name="base_sessionowner_user_host"),
            models.Index(fields=["host", "device_id"], name="base_sessionowner_host_device"),
        ]

    def __str__(self) -> str:
        return f"{self.saas_user_id} @ {self.host}"


# ── The way in: devices, PIN, badge, the business's dial and the person's profile (APP-BASE-3) ───────────────────
# Hub models (``base.tenancy.inventory``: base's), like any module's: phase 1 keeps them in the shared tables of every
# scope, phase 2 in each hub's database. A person is named by the ``username`` of its local copy (``saas:<id>``,
# ``base.services.username_for``), never by a foreign key: the users are control's and a hub's database has none.

#: The longest «who did it» kept beside a row (``str(actor)``), as the apps keep it.
ACTOR_MAX_LENGTH = 150


class TrustedDevice(UUIDModel):
    """A browser or an installed app in which someone entered this hub with their erplora.com account.

    Known by the token of its cookie ``hub_device`` (``base.access``), of which only the digest is kept. From that
    first entry on, the PIN and the badge work on it (when it is ``shared`` and the business asks). Removing it ends
    its sessions and takes the PIN away from it until someone enters with an account again.
    """

    class Mode(models.TextChoices):
        SHARED = "shared", pgettext_lazy("device mode", "Shared")
        PERSONAL = "personal", pgettext_lazy("device mode", "Personal")

    class EndedReason(models.TextChoices):
        DEVICE_LIMIT = "device_limit", _("Opened on another device")

    token_digest = models.CharField(_("token digest"), max_length=64, unique=True)
    mode = models.CharField(_("mode"), max_length=16, choices=Mode.choices, default=Mode.SHARED)
    mode_set_by = models.CharField(_("mode set by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    mode_set_at = models.DateTimeField(_("mode set at"), null=True, blank=True)
    name = models.CharField(_("name"), max_length=60, blank=True)
    agent = models.CharField(_("browser"), max_length=80, blank=True)
    last_username = models.CharField(_("last person in"), max_length=150, blank=True)
    last_user_label = models.CharField(_("last person in (name)"), max_length=150, blank=True)
    last_entry_at = models.DateTimeField(_("last entry"))
    created_at = models.DateTimeField(_("added at"), auto_now_add=True)
    # Why another device's entry ended its sessions (the plan covers fewer devices): its next way in says so.
    ended_reason = models.CharField(_("sessions ended because"), max_length=16, choices=EndedReason.choices, blank=True)
    ended_at = models.DateTimeField(_("sessions ended at"), null=True, blank=True)

    class Meta:
        verbose_name = _("device")
        verbose_name_plural = _("devices")
        ordering = ["-last_entry_at"]

    def __str__(self) -> str:
        return self.name or self.agent or str(self.pk)


class Credential(UUIDModel):
    """The PIN and the badge with which a person enters this hub on its shared devices.

    The PIN is kept as an argon2id hash and the badge as a keyed digest (``base.access.badge_digest``), never in
    clear. A badge opens one person's door only (unique among those that have one).
    """

    username = models.CharField(_("person"), max_length=150, unique=True)
    pin_hash = models.CharField(_("PIN"), max_length=128, blank=True)
    pin_set_at = models.DateTimeField(_("PIN set at"), null=True, blank=True)
    badge_digest = models.CharField(_("badge"), max_length=64, blank=True)
    badge_set_at = models.DateTimeField(_("badge set at"), null=True, blank=True)

    class Meta:
        verbose_name = _("way in")
        verbose_name_plural = _("ways in")
        constraints = [
            models.UniqueConstraint(
                fields=["badge_digest"], condition=~Q(badge_digest=""), name="base_credential_badge_unique"
            )
        ]

    def __str__(self) -> str:
        return self.username


class AccessSettings(UUIDModel):
    """How the business asks who is at the till: one row at most; without it, the factory values (``base.access``).

    ``badge_key`` is the key of the badges' digests, made once and kept: a key that changed would orphan every badge.
    """

    class PinPolicy(models.TextChoices):
        ALWAYS = "always", _("Always, and again after a while without use")
        PER_SHIFT = "per_shift", _("Once per shift")
        NEVER = "never", _("Never")

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    pin_policy = models.CharField(_("ask for the PIN"), max_length=16, choices=PinPolicy.choices, default="per_shift")
    pin_inactivity_minutes = models.PositiveSmallIntegerField(_("ask again after (minutes)"), default=5)
    pin_length = models.PositiveSmallIntegerField(_("PIN digits"), default=4)
    badge_key = models.CharField(_("badge key"), max_length=64, blank=True, editable=False)
    updated_at = models.DateTimeField(pgettext_lazy("access settings", "updated at"), auto_now=True)
    updated_by = models.CharField(
        pgettext_lazy("access settings", "updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("way in settings")
        verbose_name_plural = _("way in settings")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="base_accesssettings_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="base_accesssettings_singleton"),
            models.CheckConstraint(condition=Q(pin_policy__in=["always", "per_shift", "never"]), name="base_accesssettings_policy"),
            models.CheckConstraint(
                condition=Q(pin_inactivity_minutes__in=[1, 5, 10, 15, 30]), name="base_accesssettings_inactivity"
            ),
            models.CheckConstraint(condition=Q(pin_length__in=[4, 6]), name="base_accesssettings_pin_length"),
        ]

    def __str__(self) -> str:
        return f"{self.pin_policy}, {self.pin_length} digits"


class Profile(UUIDModel):
    """How a person appears in this hub and what they prefer: «My profile».

    The name and the contact email are this business's (receipts, Personal), not the erplora.com account's, which
    the SaaS keeps; the contact email never gives nor takes any access. ``language``, ``theme_mode`` and ``palette``
    empty = the business's.
    """

    class Language(models.TextChoices):
        BUSINESS = "", _("The business's language")
        SPANISH = "es", "Español"
        ENGLISH = "en", "English"

    class ThemeMode(models.TextChoices):
        BUSINESS = "", _("The business's appearance")
        SYSTEM = "system", _("System")
        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")

    class Palette(models.TextChoices):
        """The palettes of «My profile», by the names it shows them."""

        BUSINESS = "", pgettext_lazy("palette", "The business's palette")
        ERPLORA = "erplora", "ERPlora"
        TERRACOTTA = "terracotta", pgettext_lazy("palette", "Terracotta")
        CORPORATE = "corporate", pgettext_lazy("palette", "Corporate")
        MINIMAL = "minimal", pgettext_lazy("palette", "Minimal")
        FOREST = "forest", pgettext_lazy("palette", "Forest")
        OCEAN = "ocean", pgettext_lazy("palette", "Ocean")
        VIOLET = "violet", pgettext_lazy("palette", "Violet")

    username = models.CharField(_("person"), max_length=150, unique=True)
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    contact_email = models.EmailField(_("contact email"), blank=True)
    avatar = models.CharField(_("photo"), max_length=255, blank=True)
    language = models.CharField(_("language"), max_length=8, choices=Language.choices, blank=True)
    theme_mode = models.CharField(_("appearance"), max_length=8, choices=ThemeMode.choices, blank=True)
    palette = models.CharField(_("palette"), max_length=16, choices=Palette.choices, blank=True)
    updated_at = models.DateTimeField(pgettext_lazy("profile", "updated at"), auto_now=True)

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.username


class HubUser(UUIDModel):
    """A person of this business in its own database: who a staff record hangs from, who signed a task, a clock-in or
    a message (tenancy W10; PLAN-HUB §3, PLAN-DB §2).

    Control keeps the session's user (``auth.User``) and the role (``Membership``); a key between two databases does
    not exist, so the apps hang what a person did from this row instead. ``username`` is how the Hub knows them at its
    doors (``saas:<id>``, ``demo:<slug>``: the key of ``Credential`` and ``Profile`` too); ``account_id`` is the
    erplora.com account (none for a demo's owner); name and email are what erplora.com last said. Made or brought up to
    date at every entry and from the SaaS's photo (``base.services.ensure_hub_user``, ``base.hub_user.sync``), never
    deleted: whoever leaves keeps their name on what they signed and is no longer active.
    """

    account_id = models.UUIDField(_("SaaS account"), null=True, blank=True, unique=True)
    username = models.CharField(_("person"), max_length=150, unique=True)
    email = models.EmailField(pgettext_lazy("person", "email"), blank=True)
    name = models.CharField(_("name"), max_length=150, blank=True)
    is_active = models.BooleanField(pgettext_lazy("person", "active"), default=True)
    created_at = models.DateTimeField(_("added at"), auto_now_add=True)

    class Meta:
        verbose_name = _("business user")
        verbose_name_plural = _("business users")
        ordering = ["name", "email", "id"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """The name, else the email, else the username: how a screen names them."""
        return self.name or self.email or self.username


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
        "live.OutboxEvent",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=pgettext_lazy("event delivery", "event"),
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


# ── Data: blueprints, imports and reset (APP-BASE-2) ──


class ImportBatch(UUIDModel):
    """One load of a blueprint (PLAN-HUB round 2026-10-21, «Blueprints»; BASE-G105–G108): what it was, its report
    and the rows it created, by dataset, so that undoing it removes exactly those.

    A hub's model, like the business it loads (phase 1: the shared database; phase 2: each hub's own). ``apps`` are the
    apps chosen to load (all the blueprint's when the person chose none); a retry names the load it retries.
    """

    class Source(models.TextChoices):
        CATALOG = "catalog", pgettext_lazy("blueprint source", "Template")
        FILE = "file", pgettext_lazy("blueprint source", "File")

    class Status(models.TextChoices):
        COMPLETE = "complete", pgettext_lazy("import status", "Complete")
        PARTIAL = "partial", pgettext_lazy("import status", "Partly loaded")
        FAILED = "failed", pgettext_lazy("import status", "Failed")

    name = models.CharField(pgettext_lazy("blueprint load", "name"), max_length=120)
    source = models.CharField(pgettext_lazy("blueprint load", "source"), max_length=16, choices=Source.choices)
    template_key = models.CharField(pgettext_lazy("blueprint load", "template"), max_length=80, blank=True)
    template_version = models.CharField(pgettext_lazy("blueprint load", "template version"), max_length=32, blank=True)
    purpose = models.CharField(pgettext_lazy("blueprint load", "purpose"), max_length=16)
    apps = models.JSONField(pgettext_lazy("blueprint load", "apps"), default=list, blank=True)
    status = models.CharField(pgettext_lazy("blueprint load", "status"), max_length=16, choices=Status.choices)
    report = models.JSONField(pgettext_lazy("blueprint load", "report"), default=dict, blank=True)
    created_rows = models.JSONField(pgettext_lazy("blueprint load", "rows created"), default=dict, blank=True)
    created_by = models.CharField(pgettext_lazy("blueprint load", "loaded by"), max_length=150, blank=True)
    created_at = models.DateTimeField(pgettext_lazy("blueprint load", "loaded at"), auto_now_add=True)
    undone_at = models.DateTimeField(pgettext_lazy("blueprint load", "undone at"), null=True, blank=True)
    retry_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=pgettext_lazy("blueprint load", "retry of")
    )

    class Meta:
        verbose_name = pgettext_lazy("blueprint load", "blueprint load")
        verbose_name_plural = pgettext_lazy("blueprint load", "blueprint loads")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


# ── People and permissions: the business's API keys (APP-BASE-5) ──────────────────────────────────────────────────


class ApiKey(UUIDModel):
    """A key with which another system calls this business's API (``erpk_live_…``; PLAN-HUB §3, «API keys»).

    Its token is shown once, when it is made or rotated: the hub keeps only its SHA-256 (a random token of 256 bits
    needs no slow hash) and its first characters, to tell it apart. What it may do: everything, read only, write only,
    or per app (``scopes``: app → ``read``/``write``); read reaches an app's published queries and write its published
    commands (``expose_api``). It lives in its hub's own database, so a key of one business does not exist in another.
    A revoked key is kept, for the record, and never works again.
    """

    class Mode(models.TextChoices):
        FULL = "full", pgettext_lazy("api key", "Full access")
        READ = "read", pgettext_lazy("api key", "Read only")
        WRITE = "write", pgettext_lazy("api key", "Write only")
        PER_APP = "per_app", pgettext_lazy("api key", "Per app")

    name = models.CharField(pgettext_lazy("api key", "name"), max_length=80)
    prefix = models.CharField(pgettext_lazy("api key", "token start"), max_length=24)
    token_digest = models.CharField(pgettext_lazy("api key", "token digest"), max_length=64, unique=True)
    mode = models.CharField(pgettext_lazy("api key", "what it may do"), max_length=8, choices=Mode.choices)
    scopes = models.JSONField(pgettext_lazy("api key", "apps"), default=dict, blank=True)
    rate_per_minute = models.PositiveIntegerField(pgettext_lazy("api key", "requests a minute"), default=60)
    created_by = models.CharField(pgettext_lazy("api key", "created by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(pgettext_lazy("api key", "created at"), auto_now_add=True)
    rotated_at = models.DateTimeField(pgettext_lazy("api key", "rotated at"), null=True, blank=True)
    last_used_at = models.DateTimeField(pgettext_lazy("api key", "last used"), null=True, blank=True)
    revoked_at = models.DateTimeField(pgettext_lazy("api key", "revoked at"), null=True, blank=True)
    revoked_by = models.CharField(pgettext_lazy("api key", "revoked by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("api key", "API key")
        verbose_name_plural = pgettext_lazy("api key", "API keys")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(mode__in=["full", "read", "write", "per_app"]), name="base_apikey_mode"
            ),
            models.CheckConstraint(
                condition=Q(rate_per_minute__gte=1, rate_per_minute__lte=10_000), name="base_apikey_rate"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}…)"


# ── People and permissions: the API's documentation (APP-BASE-5) ───────────────────────────────────────────────────


class ApiSettings(UUIDModel):
    """Whether the business shows the documentation of its API (BASE-G100): one row at most; without it, hidden."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    docs_enabled = models.BooleanField(pgettext_lazy("api settings", "show the API documentation"), default=False)
    updated_at = models.DateTimeField(pgettext_lazy("api settings", "updated at"), auto_now=True)
    updated_by = models.CharField(pgettext_lazy("api settings", "updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("api settings", "API settings")
        verbose_name_plural = pgettext_lazy("api settings", "API settings")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="base_apisettings_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="base_apisettings_singleton"),
        ]

    def __str__(self) -> str:
        return "API documentation shown" if self.docs_enabled else "API documentation hidden"


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────


class Approval(UUIDModel):
    """A manager's approval of one refused command, given with their PIN or badge (BASE-G136), and its record (G145).

    The pass handed back is kept as its SHA-256 only, and works once, until ``expires_at``, for the person who asked
    (``requested_by``), that command (``operation``) and that very request of this business (``fingerprint``,
    ``base.approvals.fingerprint``). The names are kept as they were then: the record still reads when a person left.
    When the pass is spent, the figures of what it let through that its app's sentences name (``figures``, JSON; none
    before, or for a command said without figures), so the record says «a 50 % discount». Nobody edits or deletes a row.
    """

    class Way(models.TextChoices):
        PIN = "pin", pgettext_lazy("way in", "PIN")
        BADGE = "badge", pgettext_lazy("way in", "Badge")

    operation = models.CharField(pgettext_lazy("approval", "action"), max_length=120)
    permission = models.CharField(pgettext_lazy("approval", "permission"), max_length=120)
    fingerprint = models.CharField(pgettext_lazy("approval", "request fingerprint"), max_length=64)
    token_digest = models.CharField(pgettext_lazy("approval", "pass digest"), max_length=64, unique=True)
    requested_by = models.CharField(pgettext_lazy("approval", "asked by"), max_length=ACTOR_MAX_LENGTH)
    requested_by_name = models.CharField(pgettext_lazy("approval", "asked by (name)"), max_length=ACTOR_MAX_LENGTH)
    approved_by = models.CharField(pgettext_lazy("approval", "approved by"), max_length=ACTOR_MAX_LENGTH)
    approved_by_name = models.CharField(pgettext_lazy("approval", "approved by (name)"), max_length=ACTOR_MAX_LENGTH)
    way = models.CharField(pgettext_lazy("approval", "approved with"), max_length=8, choices=Way.choices)
    created_at = models.DateTimeField(pgettext_lazy("approval", "approved at"), auto_now_add=True)
    expires_at = models.DateTimeField(pgettext_lazy("approval", "valid until"))
    used_at = models.DateTimeField(pgettext_lazy("approval", "used at"), null=True, blank=True)
    figures = models.JSONField(pgettext_lazy("approval", "figures"), null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("approval", "approval")
        verbose_name_plural = pgettext_lazy("approval", "approvals")
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=Q(way__in=["pin", "badge"]), name="base_approval_way")]

    def __str__(self) -> str:
        return f"{self.operation} · {self.approved_by_name}"


# ── Locations (round 2026-10-24b, multi-location) ──────────────────────────────────────────────────────────────────

#: The name of the location every hub's database is born with (``base/migrations/0015_location``), kept in canonical
#: English and read in the reader's language while it keeps that name.
DEFAULT_LOCATION_NAME = "Main"
DEFAULT_LOCATION_LABEL = pgettext_lazy("location", "Main")
LOCATION_NAME_MAX_LENGTH = 100


class Location(UUIDModel):
    """A place where the business works: a shop, a bar, a salon (round 2026-10-24b).

    A hub is one business, with its tax id and one database: a business with several premises keeps them here, as
    Square, Shopify, Lightspeed and Odoo keep several shops in one company. Every hub's database is born with exactly
    one, the default «Main» (its migration plants it; a new hub inherits it from the template it is cloned from), so a
    business with one place never sees any. At most one is the default (a partial unique index) and the default is
    always active.
    """

    name = models.CharField(pgettext_lazy("location", "name"), max_length=LOCATION_NAME_MAX_LENGTH)
    is_default = models.BooleanField(pgettext_lazy("location", "default"), default=False)
    is_active = models.BooleanField(pgettext_lazy("location", "active"), default=True)
    created_at = models.DateTimeField(pgettext_lazy("location", "created at"), auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy("location", "location")
        verbose_name_plural = pgettext_lazy("location", "locations")
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=Q(is_default=True), name="base_location_one_default"
            ),
            models.CheckConstraint(
                condition=Q(is_active=True) | Q(is_default=False), name="base_location_default_active"
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """The default's factory name in the reader's language; any other name as it was given."""
        if self.is_default and self.name == DEFAULT_LOCATION_NAME:
            return str(DEFAULT_LOCATION_LABEL)
        return self.name


# ── Apps turned on and off by the business (PLAN-HUB §9; PLAN-DB §7) ──────────────────────────────────────────────


class AppActivation(UUIDModel):
    """Whether a module is on in a business, and whether the business chose it (the rules: ``base.activation``).

    ``chosen`` is what the plan's ``max_apps`` counts: an app the business turned on itself, never one the closure by
    ``requires`` brought along. A business without any row has every module off (the baseline, round 2026-10-27): its
    first change writes them all down. The hubs of before have every module on, its roots chosen (migration 0017). ``host`` is the business's slug (the scope's key, as ``Membership`` and the
    outbox keep it): phase 1's businesses share one database (plan 2026-10-22, decision 1), and the cut of S5 leaves
    one hub per database, where it is always the same.

    In a hub with its own database an app's tables are made the first time it is turned on (S3; PLAN-DB §7): the row is
    ``creating`` until the worker made them (``on``), or ``failed`` with ``attempts``, ``last_error`` and
    ``next_attempt_at`` (tried again then, or by hand). The tables of an app off are never dropped.
    """

    class State(models.TextChoices):
        ON = "on", pgettext_lazy("app state", "On")
        OFF = "off", pgettext_lazy("app state", "Off")
        CREATING = "creating", pgettext_lazy("app state", "Turning on")
        FAILED = "failed", pgettext_lazy("app state", "Could not turn on")

    host = models.CharField(_("host"), max_length=63, help_text=_("The hub's slug."))
    app = models.CharField(pgettext_lazy("app activation", "app"), max_length=100)
    state = models.CharField(pgettext_lazy("app activation", "state"), max_length=16, choices=State.choices)
    chosen = models.BooleanField(
        pgettext_lazy("app activation", "chosen"),
        default=False,
        help_text=pgettext_lazy(
            "app activation", "Turned on by the business itself; what came along with another app is not."
        ),
    )
    changed_at = models.DateTimeField(pgettext_lazy("app activation", "changed at"), auto_now=True)
    attempts = models.PositiveIntegerField(
        pgettext_lazy("app activation", "attempts"),
        default=0,
        db_default=0,
        help_text=pgettext_lazy("app activation", "How many times making its tables failed in a row."),
    )
    last_error = models.TextField(
        pgettext_lazy("app activation", "last error"),
        blank=True,
        default="",
        db_default="",
        help_text=pgettext_lazy("app activation", "Why making its tables failed the last time."),
    )
    next_attempt_at = models.DateTimeField(
        pgettext_lazy("app activation", "next attempt at"),
        null=True,
        blank=True,
        help_text=pgettext_lazy("app activation", "When the worker makes its tables again."),
    )

    class Meta:
        verbose_name = pgettext_lazy("app activation", "app activation")
        verbose_name_plural = pgettext_lazy("app activation", "app activations")
        ordering = ["host", "app"]
        constraints = [
            models.UniqueConstraint(fields=["host", "app"], name="base_appactivation_host_app"),
            models.CheckConstraint(
                condition=Q(state__in=["on", "off", "creating", "failed"]), name="base_appactivation_state"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.app} @ {self.host} ({self.state})"


# The registry moved to control in S1 (plan 2026-10-22): base/migrations/0004 and 0005 name the validator here, and
# phase 1's code imports the models from here.
from control.models import DemoCode, Hub, registry_slug_validator  # noqa: E402, F401
