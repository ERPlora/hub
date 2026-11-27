"""The business's service settings, and the length of the «by whom» fields every model of the app shares."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128


class ServiceSettings(UUIDModel):
    """The business's service settings: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    # What a new service takes when it does not say (form, assistant, API, bulk create).
    default_duration = models.PositiveIntegerField(
        _("default duration (min)"), default=60
    )
    default_buffer_time = models.PositiveIntegerField(
        _("default buffer time (min)"), default=0
    )
    default_tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("default tax category"),
    )
    # For the public booking page, when it exists.
    show_prices = models.BooleanField(_("show prices"), default=True)
    show_duration = models.BooleanField(_("show duration"), default=True)
    allow_online_booking = models.BooleanField(_("allow online booking"), default=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("service settings")
        verbose_name_plural = _("service settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="service_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="service_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(default_duration__gte=1), name="service_settings_duration"
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)
