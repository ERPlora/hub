"""Models of base, the platform app of hub-next.

Phase 1 has no tenancy: a user's role on a hub is a ``Membership`` keyed by the first label of the
Host (``a`` for ``a.localhost``). Phase 2 replaces it with the hub's own staff in its database.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
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
