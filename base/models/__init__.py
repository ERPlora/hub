"""Models of base, the Hub's platform app: one module per entity or use case, each imported here so that Django
registers its models.

A user's role on a hub is a ``Membership`` in control, keyed by the first label of the Host (``a`` for
``a.localhost``); what a person does in a business hangs from its ``HubUser`` in the business's own database.

The registry of hubs (``Hub``) and the demos' codes (``DemoCode``) live in ``control``, keeping their tables; they are
still importable from here. ``identity.HubIdentity`` is the row that says which hub a hub's database is.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from . import (
    access as access,
    activation as activation,
    api_keys as api_keys,
    approvals as approvals,
    blueprints as blueprints,
    identity as identity,
    locations as locations,
    profile as profile,
    relay as relay,
    roles as roles,
    scheduler as scheduler,
    sessions as sessions,
    support_access as support_access,
)

# One DNS label, lowercase: what HostScopeResolver takes from the Host.
HOST_LABEL_RE = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"


class MembershipQuerySet(models.QuerySet):
    def team(self, host: str) -> "MembershipQuerySet":
        """The active people of the business of ``host``: ERPlora's support, who only comes in to help, is none of
        them."""
        return self.filter(host=host, user__is_active=True).exclude(role=Membership.SUPPORT)


class Membership(UUIDModel):
    """The role a person has on a hub, as the SaaS sent it (``hub_`` prefix included).

    The prefix keeps the hub's roles apart from the platform's (superuser, ``support``), which reach the Hub admin only
    through the ``hub-admin`` audience, on a staff copy (``saas-staff:<id>``) with no membership. None makes a user
    staff. :attr:`SUPPORT` is ERPlora's support inside a business that lets it in, on a copy of its own
    (``saas-support:<id>``): no role of the business, so never among its team (:meth:`MembershipQuerySet.team`).
    """

    class Role(models.TextChoices):
        OWNER = "hub_owner", _("Owner")
        ADMIN = "hub_admin", _("Admin")
        MANAGER = "hub_manager", _("Manager")
        EMPLOYEE = "hub_employee", _("Employee")
        ACCOUNTANT = "hub_accountant", _("Accountant")

    SUPPORT = "hub_support"

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
    role = models.CharField(_("role"), max_length=16, choices=[*Role.choices, (SUPPORT, _("ERPlora support"))])

    objects = MembershipQuerySet.as_manager()

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ["host", "user_id"]
        constraints = [models.UniqueConstraint(fields=["user", "host"], name="base_membership_user_host_unique")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.host} ({self.get_role_display()})"


class HubUser(UUIDModel):
    """A person of this business in its own database: who a staff record hangs from, who signed a task, a clock-in or
    a message.

    Control keeps the session's user (``auth.User``) and the role (``Membership``); a key between two databases does
    not exist, so the apps hang what a person did from this row instead. ``username`` is how the Hub knows them at its
    doors (``saas:<id>``, ``demo:<slug>``: the key of ``Credential`` and ``Profile`` too); ``account_id`` is the
    erplora.com account (none for a demo's owner); name and email are what erplora.com last said. Made or brought up to
    date at every entry and from the SaaS's photo (``base.services.sessions.ensure_hub_user``, ``base.hub_user.sync``),
    never deleted: whoever leaves keeps their name on what they signed and is no longer active.
    """

    account_id = models.UUIDField(_("SaaS account"), null=True, blank=True, unique=True)
    username = models.CharField(_("person"), max_length=150, unique=True)
    email = models.EmailField(pgettext_lazy("person", "email"), blank=True)
    name = models.CharField(_("name"), max_length=150, blank=True)
    is_active = models.BooleanField(pgettext_lazy("person", "active"), default=True)
    created_at = models.DateTimeField(_("added at"), auto_now_add=True)
    #: The role of this business they were given; none is the role of their invitation (``Membership``).
    business_role = models.ForeignKey(
        roles.BusinessRole,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="people",
        verbose_name=_("role in this business"),
    )

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


# The registry lives in control: base/migrations/0004 and 0005 name the validator here, and older code imports the
# models from here.
from control.models.hubs import DemoCode, Hub, registry_slug_validator  # noqa: E402, F401
