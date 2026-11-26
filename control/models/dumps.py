"""The copies of a hub's database kept in the dumps bucket."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from control.models.hubs import Hub


class HubDump(UUIDModel):
    """A copy of a hub's database (``pg_dump -Fc``) in the dumps bucket: made before its data is reset (``reset``) and
    when the business leaves (``offboarding``), at ``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump`` (``key``, unique: no
    versions in the bucket), kept 90 days by the bucket's lifecycle rule. ``created_at`` is when it was made, the key's
    time; ``requested_by`` who asked for it (the reset's person; empty for a business that left)."""

    class Kind(models.TextChoices):
        RESET = "reset", pgettext_lazy("data copy", "Before a reset")
        OFFBOARDING = "offboarding", pgettext_lazy("data copy", "On leaving")

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="dumps", verbose_name=_("hub"))
    kind = models.CharField(pgettext_lazy("data copy", "kind"), max_length=16, choices=Kind.choices)
    key = models.CharField(pgettext_lazy("data copy", "key"), max_length=512, unique=True)
    bytes = models.PositiveBigIntegerField(_("size (bytes)"))
    created_at = models.DateTimeField(pgettext_lazy("data copy", "made at"))
    requested_by = models.CharField(pgettext_lazy("data copy", "asked by"), max_length=150, blank=True, default="")

    class Meta:
        verbose_name = _("data copy")
        verbose_name_plural = _("data copies")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["hub", "-created_at"], name="control_hubdump_hub_created")]

    def __str__(self) -> str:
        return self.key
