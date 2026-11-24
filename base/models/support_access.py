"""Support access: whether ERPlora's support staff may come into this business, and each time one of them did.

Hub models, in the business's own database. A person of support is named by the ``username`` of their local copy
(``saas-support:<id>``), never by a foreign key: the users are control's and a hub's database has none.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from base.models.access import ACTOR_MAX_LENGTH


class SupportAccess(UUIDModel):
    """Whether ERPlora's support may come into the business: one row at most; without it, off. It does not expire."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    enabled = models.BooleanField(pgettext_lazy("support access", "support may come in"), default=False)
    updated_at = models.DateTimeField(pgettext_lazy("support access", "updated at"), auto_now=True)
    updated_by = models.CharField(
        pgettext_lazy("support access", "updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = pgettext_lazy("support access", "support access")
        verbose_name_plural = pgettext_lazy("support access", "support access")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="base_supportaccess_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="base_supportaccess_singleton"),
        ]

    def __str__(self) -> str:
        return "Support may come in" if self.enabled else "Support may not come in"


class SupportVisit(UUIDModel):
    """A person of ERPlora's support came into the business: who, as erplora.com named them then, and when."""

    username = models.CharField(pgettext_lazy("support visit", "person"), max_length=150)
    name = models.CharField(pgettext_lazy("support visit", "name"), max_length=150, blank=True)
    email = models.EmailField(pgettext_lazy("support visit", "email"), blank=True)
    entered_at = models.DateTimeField(pgettext_lazy("support visit", "entered at"), default=timezone.now)

    class Meta:
        verbose_name = pgettext_lazy("support visit", "support entry")
        verbose_name_plural = pgettext_lazy("support visit", "support entries")
        ordering = ["-entered_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name or self.email or self.username} @ {self.entered_at:%Y-%m-%d %H:%M}"
