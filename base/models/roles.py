"""A role the business makes for itself by duplicating a basic one, kept in its own database (``base.roles``)."""

from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

NAME_UNIQUE = "base_businessrole_name_unique"


class BusinessRole(UUIDModel):
    """A role of this business, given to a person in ``HubUser.business_role``; it rules over the role of their
    invitation (``base.permissions.access_for``).

    ``origin`` is the basic role it was duplicated from (a ``Membership.Role`` value): an app none of whose permissions
    ``states`` names gives what it gives that role. ``states`` keeps ``{permission: "on" | "approval" | "off"}`` for
    every permission of the apps it was saved with. The basic roles live in control and come from erplora.com; this
    one never leaves the business.
    """

    name = models.CharField(_("name"), max_length=80)
    description = models.TextField(_("description"), blank=True)
    origin = models.CharField(_("based on"), max_length=16)
    states = models.JSONField(_("what it allows"), default=dict, blank=True)

    class Meta:
        verbose_name = _("role of the business")
        verbose_name_plural = _("roles of the business")
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(Lower("name"), name=NAME_UNIQUE)]

    def __str__(self) -> str:
        return self.name
