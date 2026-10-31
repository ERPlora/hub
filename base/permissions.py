"""What a user may do on a host: the phase-1 session seam (plan §4.4).

Exception to "only services.py and queries.py touch the ORM": the context builder needs the
Membership (and a fresh copy of the user) before any operation runs, so it cannot go through one.
This module only reads. Phase 2 replaces it with the hub's staff and its roles.
"""

from typing import Any

from django.contrib.auth import get_user_model
from live.context import Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.models import Membership
from base.tenancy.context import PLATFORM_SCOPE_KIND


#: Everyone of the hub sees the Home; who runs it (owner, admin) is told the platform's steps and counters, and keeps
#: its devices and the way in (APP-BASE-3). Here, not in ``base.queries``, so ``base.services`` can name them too.
VIEW_HOME = "base.view_home"
ADMINISTER_HUB = "base.administer_hub"

#: Customer roles that run the hub: every permission of every app, whether the app lists them or not.
FULL_ACCESS_ROLES = frozenset({Membership.Role.OWNER, Membership.Role.ADMIN})


def permissions_for(user: Any, scope: Scope) -> frozenset[str]:
    """``{"*"}`` for an active superuser on the platform's scope; else the permissions of its role on ``scope``; else
    none.

    A superuser is ERPlora's staff, whose place is the Hub admin on the platform host (Ioan, 2026-10-31): on a
    business's host it holds only what a ``Membership`` there gives it, like anyone (the staff copy ``saas-staff:<id>``
    never has one). Owner and admin get every permission declared by every app; manager and employee get what each
    app's ``role_permissions`` gives them.
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
    """What ``role`` (a ``Membership.Role``) gives on a host: owner and admin, every permission declared by every app;
    manager and employee, what each app's ``role_permissions`` gives them."""
    configs = all_live_app_configs()
    if role in FULL_ACCESS_ROLES:
        return frozenset(permission for config in configs for permission in config.permissions)
    return permissions_for_role(configs, role)


def reload_user(user: Any) -> Any:
    """The same user read again from the database (``None`` if there is no user or it was deleted)."""
    if user is None or not user.is_authenticated:
        return None
    return get_user_model().objects.filter(pk=user.pk).first()
