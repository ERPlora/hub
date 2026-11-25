"""What a user may do on a host.

Exception to "only services.py and queries.py touch the ORM": the context builder needs the Membership, the role the
business gave the person (in the business's own database) and a fresh copy of the user before any operation runs, so it
cannot go through one. This module only reads.
"""

from collections.abc import Collection, Iterable
from typing import Any, NamedTuple

from django.contrib.auth import get_user_model
from live.context import Scope
from live.meta import LiveAppConfig, all_live_app_configs, permissions_for_role

from base import roles
from base.models import Membership
from base.models.roles import BusinessRole
from base.tenancy.context import PLATFORM_SCOPE_KIND


#: Everyone of the hub sees the Home; who runs it (owner, admin) is told the platform's steps and counters, and keeps
#: its devices and the way in. Here, not in ``base.queries``, so ``base.services`` can name them too.
VIEW_HOME = "base.view_home"
ADMINISTER_HUB = "base.administer_hub"
#: Who makes, adjusts and deletes the roles of the business (``base.role.*``): the owner, an administrator and whoever a
#: role of the business lets.
MANAGE_ROLES = "base.manage_roles"
#: Who may open this business on erplora.com's panel from the bar (``base/apps.py``: owner, admin and manager).
OPEN_MANAGEMENT = "base.open_management"

#: Owning the business: buying for it on erplora.com (the plan, an app of the Store), resetting it and its copies. Only
#: its owner, as on erplora.com, where the plan, the billing and the hand-over are the owner's alone.
OWN_BUSINESS = "base.own_business"
#: What the owner holds and no other role does: an administrator runs the business, it does not own it.
OWNER_ONLY = frozenset({OWN_BUSINESS})


class RoleHeld(NamedTuple):
    """What a person is in a business: the role of their invitation (a ``Membership.Role`` value) and, if they were given
    one, the role of the business that rules over it."""

    invitation: str
    own: BusinessRole | None


def is_a_person(actor: Any) -> bool:
    """Whether ``actor`` is a signed-in person (a control user), not the platform, an API key or nobody."""
    return hasattr(actor, "get_username") and bool(getattr(actor, "is_authenticated", False))


def role_held(user: Any, scope: Scope) -> RoleHeld | None:
    """The role of ``user`` on ``scope``, read from the business at work; ``None`` without a ``Membership`` there, as for
    whoever is no person. The owner keeps the role of their invitation whatever role of the business their row names."""
    if not is_a_person(user):
        return None
    invitation = Membership.objects.filter(user=user, host=scope.key).values_list("role", flat=True).first()
    if invitation is None:
        return None
    own = None
    if invitation != Membership.Role.OWNER:
        own = BusinessRole.objects.filter(people__username=user.get_username()).first()
    return RoleHeld(invitation, own)


def access_for(user: Any, scope: Scope) -> frozenset[str]:
    """What ``user`` may do on ``scope``: ``{"*"}`` for an active superuser on the platform's scope; else what the role
    the business gave them allows, or without one, what the role of their invitation there gives; else nothing.

    A superuser is ERPlora's staff, whose place is the Hub admin on the platform host: on a
    business's host it holds only what a ``Membership`` there gives it, like anyone (the staff copy ``saas-staff:<id>``
    never has one). What each basic role gets, ``permissions_of_role``. The owner keeps the role of their invitation
    whatever role of the business their row names: nobody takes owning the business from them. The role of the business
    is read from the business's own database, the one at work (``use_hub``); outside one it fails, as any model of a
    business does.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return frozenset()
    if user.is_superuser and scope.kind == PLATFORM_SCOPE_KIND:
        return frozenset({"*"})
    held = role_held(user, scope)
    if held is None:
        return frozenset()
    return permissions_of_role(held.invitation) if held.own is None else permissions_of_business_role(held.own)


def states_of_business_role(
    role: BusinessRole, configs: Iterable[LiveAppConfig], approvable: Collection[str] = frozenset()
) -> dict[str, str]:
    """What a role of the business does with each permission of ``configs`` it may hold. An app turned on after it was
    saved does what it does for the basic role it came from (``base.roles``): what that role lacks of ``approvable`` it
    leaves to approval."""
    return roles.effective(role.states, grantable(configs), given=permissions_of_role(role.origin), approvable=approvable)


def permissions_of_business_role(role: BusinessRole) -> frozenset[str]:
    """What a role of the business allows, of every app of this deployment."""
    allowed = states_of_business_role(role, all_live_app_configs())
    return frozenset(permission for permission, state in allowed.items() if state == roles.ON)


def refused_outright(user: Any, scope: Scope, approvable: Collection[str]) -> frozenset[str]:
    """Which of ``approvable``, the permissions of commands a manager may approve (``base.approvals``), the role the
    business gave ``user`` on ``scope`` says no to: refused, with no approval to ask for. A basic role says no to none."""
    held = role_held(user, scope)
    if held is None or held.own is None:
        return frozenset()
    states = states_of_business_role(held.own, all_live_app_configs(), approvable)
    return frozenset(permission for permission in approvable if states.get(permission, roles.OFF) == roles.OFF)


def grantable(configs: Iterable[LiveAppConfig]) -> dict[str, tuple[str, ...]]:
    """Each app's permissions a role of the business may hold: all it declares but what is the owner's alone."""
    return {
        config.label: tuple(permission for permission in config.permissions if permission not in OWNER_ONLY)
        for config in configs
    }


def permissions_of_role(role: str) -> frozenset[str]:
    """What ``role`` (a ``Membership.Role``) gives on a host: the owner, every permission declared by every app; an
    administrator, all of them but ``OWNER_ONLY``; manager and employee, what each app's ``role_permissions`` gives
    them, which never names ``OWNER_ONLY`` (``base/tests/test_permissions.py``)."""
    configs = all_live_app_configs()
    declared = frozenset(permission for config in configs for permission in config.permissions)
    if role == Membership.Role.OWNER:
        return declared
    if role == Membership.Role.ADMIN:
        return declared - OWNER_ONLY
    return permissions_for_role(configs, role)


def reload_user(user: Any) -> Any:
    """The same user read again from the database (``None`` if there is no user or it was deleted)."""
    if user is None or not user.is_authenticated:
        return None
    return get_user_model().objects.filter(pk=user.pk).first()
