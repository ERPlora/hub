"""Whose and where each session of the Hub is, in control like the sessions."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


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
    # The hub's device the session was opened on (a ``TrustedDevice``'s id: a hub's row, so no foreign key
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
