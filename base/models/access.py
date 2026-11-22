"""The way in: the devices, the PIN and the badge, and how the business asks who is at the till.

Hub models (``base.tenancy.inventory``: base's), like any module's: kept in each hub's own database. A person is named
by the ``username`` of its local copy (``saas:<id>``, ``base.services.sessions.username_for``), never by a foreign key:
the users are control's and a hub's database has none.
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


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
