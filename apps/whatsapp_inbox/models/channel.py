"""The business's WhatsApp number and its plan's monthly allowance of messages, as erplora.com reports them."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class Channel(UUIDModel):
    """The business's WhatsApp number as erplora.com reports it: one row per business, written only by what the SaaS
    says (its photo, and its answer when the Hub connects or disconnects the number).

    Each business keeps one row in its own database: the database holds it to one by the unique business column left
    from when the businesses shared these tables (``migrations/0005``), empty in every row the code writes since
    ``0011`` and ``0012``.
    """

    class Status(models.TextChoices):
        NOT_CONNECTED = "not_connected", pgettext_lazy("whatsapp channel", "Not connected")
        CONNECTED = "connected", pgettext_lazy("whatsapp channel", "Connected")
        RECONNECT_NEEDED = "reconnect_needed", pgettext_lazy("whatsapp channel", "Needs reconnecting")

    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.NOT_CONNECTED
    )
    # The business's own number (E.164) and the name WhatsApp shows for it.
    phone_number = models.CharField(_("phone number"), max_length=16, blank=True)
    display_name = models.CharField(_("display name"), max_length=200, blank=True)
    # The plan's monthly allowance of messages sent (0 = the plan includes none; there is no
    # «unlimited») and what is spent, with the month (``YYYY-MM``) the figure counts: another month's figure
    # counts as nothing spent.
    monthly_limit = models.PositiveIntegerField(_("monthly limit"), default=0)
    monthly_usage = models.PositiveIntegerField(_("used this month"), default=0)
    usage_month = models.CharField(_("month of the figure"), max_length=7, blank=True)
    # The SaaS's version of this state: an older push is ignored.
    version = models.BigIntegerField(_("version"), default=0)
    synced_at = models.DateTimeField(pgettext_lazy("whatsapp channel", "synced at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("WhatsApp channel")
        verbose_name_plural = _("WhatsApp channels")

    def __str__(self) -> str:
        return self.phone_number or str(self.get_status_display())

    def cap_reached(self, month: str) -> bool:
        """Whether the plan's messages of ``month`` (``YYYY-MM``) are spent: from the first one when the plan
        includes none. Never before erplora.com spoke: until then the 0 is the row's default, not the plan's."""
        if self.synced_at is None:
            return False
        spent = self.monthly_usage if self.usage_month == month else 0
        return spent >= self.monthly_limit
