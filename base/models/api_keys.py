"""The business's API: the keys other systems call it with and whether its documentation is shown."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from base.models.access import ACTOR_MAX_LENGTH


class ApiKey(UUIDModel):
    """A key with which another system calls this business's API (``erpk_live_…``).

    Its token is shown once, when it is made or rotated: the hub keeps only its SHA-256 (a random token of 256 bits
    needs no slow hash) and its first characters, to tell it apart. What it may do: everything, read only, write only,
    or per app (``scopes``: app → ``read``/``write``); read reaches an app's published queries and write its published
    commands (``expose_api``). It lives in its hub's own database, so a key of one business does not exist in another.
    A revoked key is kept, for the record, and never works again.

    ``owner`` is whoever made it, and its ceiling: at the door a key holds only what that person holds on the business
    today (``base.services.api_keys.authenticate_api_key``). Empty for a key made before it was recorded, until the next
    photo of erplora.com gives it to the business's owner (``base.hub_user.sync``).
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
    owner = models.ForeignKey(
        "base.HubUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=pgettext_lazy("api key", "maker"),
    )
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


class ApiSettings(UUIDModel):
    """Whether the business shows the documentation of its API: one row at most; without it, hidden."""

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
