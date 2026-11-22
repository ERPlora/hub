"""What a user may do on a host.

Exception to "only services.py and queries.py touch the ORM": the context builder needs the
Membership (and a fresh copy of the user) before any operation runs, so it cannot go through one.
This module only reads.
"""

from typing import Any

from django.contrib.auth import get_user_model
from live.context import Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.models import Membership
from base.tenancy.context import PLATFORM_SCOPE_KIND


#: Everyone of the hub sees the Home; who runs it (owner, admin) is told the platform's steps and counters, and keeps
#: its devices and the way in. Here, not in ``base.queries``, so ``base.services`` can name them too.
VIEW_HOME = "base.view_home"
ADMINISTER_HUB = "base.administer_hub"
#: Who may open this business on erplora.com's panel from the bar (``base/apps.py``: owner, admin and manager).
OPEN_MANAGEMENT = "base.open_management"

#: Owning the business: buying for it on erplora.com (the plan, an app of the Store), resetting it and its copies. Only
#: its owner, as on erplora.com, where the plan, the billing and the hand-over are the owner's alone.
OWN_BUSINESS = "base.own_business"
#: What the owner holds and no other role does, whatever an app grants it: an administrator runs the business, it does
#: not own it.
OWNER_ONLY = frozenset({OWN_BUSINESS})


def permissions_for(user: Any, scope: Scope) -> frozenset[str]:
    """``{"*"}`` for an active superuser on the platform's scope; else the permissions of its role on ``scope``; else
    none.

    A superuser is ERPlora's staff, whose place is the Hub admin on the platform host: on a
    business's host it holds only what a ``Membership`` there gives it, like anyone (the staff copy ``saas-staff:<id>``
    never has one). What each role gets, ``permissions_of_role``.
    """
    if user is None or not user.is_authenticated or not user.is_active:
        return frozenset()
    if user.is_superuser and scope.kind == PLATFORM_SCOPE_KIND:
        return frozenset({"*"})
    role = Membership.objects.filter(user=user, host=scope.key).values_list("role", flat=True).first()
    if role is None:
        return frozenset()
    return permissions_of_role(role)


def permissions_of_role(role: str) -> frozenset[str]:
    """What ``role`` (a ``Membership.Role``) gives on a host: the owner, every permission declared by every app; an
    administrator, all of them but ``OWNER_ONLY``; manager and employee, what each app's ``role_permissions`` gives
    them, never ``OWNER_ONLY``."""
    configs = all_live_app_configs()
    declared = frozenset(permission for config in configs for permission in config.permissions)
    if role == Membership.Role.OWNER:
        return declared
    if role == Membership.Role.ADMIN:
        return declared - OWNER_ONLY
    return permissions_for_role(configs, role) - OWNER_ONLY


def reload_user(user: Any) -> Any:
    """The same user read again from the database (``None`` if there is no user or it was deleted)."""
    if user is None or not user.is_authenticated:
        return None
    return get_user_model().objects.filter(pk=user.pk).first()
