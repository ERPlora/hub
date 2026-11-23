"""Permissions of a user on a host: the customer role of its Membership on that host (a superuser's ``*`` is the
platform scope's alone: ERPlora's staff is no customer, tests/test_guardrails_permissions.py).

The owner gets every permission of every app; an administrator, all but what is the owner's alone (``OWNER_ONLY``:
owning the business); manager and employee, what each app declares.

The businesses are ``hub_a`` and ``hub_b``, each on a database of its own; the memberships live in control.
"""

from types import SimpleNamespace

import pytest
from django.apps import apps
from live.context import Scope
from live.meta import all_live_app_configs

from base import permissions as permissions_module

from base.models import Membership
from base.permissions import OWN_BUSINESS, OWNER_ONLY, permissions_for, permissions_of_role, reload_user
from base.tests.test_auth_views import ON_HUB_A
from base.tests.test_auth_views import A as SLUG_A
from base.tests.test_auth_views import B as SLUG_B

pytestmark = ON_HUB_A

A = Scope("host", SLUG_A)
B = Scope("host", SLUG_B)


def of_apps(permissions, *labels: str) -> set[str]:
    """The permissions that belong to the given apps (``<label>.<action>``), whatever else is installed."""
    return {permission for permission in permissions if permission.split(".", 1)[0] in labels}


def test_nobody_has_nothing():
    assert permissions_for(None, A) == frozenset()


def test_anonymous_has_nothing():
    from django.contrib.auth.models import AnonymousUser

    assert permissions_for(AnonymousUser(), A) == frozenset()


def test_a_superuser_without_a_membership_has_nothing_on_a_host(superuser):
    assert permissions_for(superuser, A) == frozenset()
    assert permissions_for(superuser, Scope("host", "zzz")) == frozenset()


def test_inactive_user_has_nothing(make_user):
    user = make_user(host=SLUG_A, role="hub_admin", is_active=False)
    assert permissions_for(user, A) == frozenset()


def test_role_permissions_on_its_host_only(make_user):
    user = make_user(host=SLUG_A, role="hub_employee")
    # demo is the reference app; the other modules' grants are pinned by their own tests.
    assert of_apps(permissions_for(user, A), "demo") == {"demo.view"}
    assert permissions_for(user, B) == frozenset()


#: An app that names only some roles: owner and admin are not in its role_permissions.
SHOP = SimpleNamespace(
    permissions={"shop.view": "See the shop", "shop.sell": "Sell", "shop.refund": "Refund"},
    role_permissions={"hub_manager": ["shop.view", "shop.sell"], "hub_employee": ["shop.view"]},
)


@pytest.fixture
def with_shop(monkeypatch):
    """Every installed app plus SHOP."""
    monkeypatch.setattr(permissions_module, "all_live_app_configs", lambda: [*all_live_app_configs(), SHOP])


@pytest.fixture
def only_demo_and_shop(monkeypatch):
    """demo and SHOP alone, so a role's grants can be compared whole, whatever other modules exist."""
    monkeypatch.setattr(permissions_module, "all_live_app_configs", lambda: [apps.get_app_config("demo"), SHOP])


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager"])
def test_owner_admin_and_manager_get_all_of_demo(make_user, role):
    assert of_apps(permissions_for(make_user(host=SLUG_A, role=role), A), "demo") == {"demo.view", "demo.manage"}


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin"])
def test_owner_and_admin_get_every_permission_of_every_app_even_unlisted(make_user, with_shop, role):
    granted = permissions_for(make_user(host=SLUG_A, role=role), A)
    everything = {"demo.view", "demo.manage", "shop.view", "shop.sell", "shop.refund"}
    assert of_apps(granted, "demo", "shop") == everything


def test_the_owner_gets_every_permission_declared(make_user, with_shop):
    declared = {permission for config in [*all_live_app_configs(), SHOP] for permission in config.permissions}

    assert permissions_for(make_user(host=SLUG_A, role="hub_owner"), A) == declared


def test_an_administrator_gets_every_permission_declared_but_owning_the_business(make_user, with_shop):
    declared = {permission for config in [*all_live_app_configs(), SHOP] for permission in config.permissions}

    assert permissions_for(make_user(host=SLUG_A, role="hub_admin"), A) == declared - {OWN_BUSINESS}


def test_owning_the_business_is_declared_by_base_and_is_all_that_is_the_owners_alone():
    assert OWNER_ONLY == {OWN_BUSINESS} == {"base.own_business"}
    assert OWN_BUSINESS in apps.get_app_config("base").permissions


@pytest.mark.parametrize("role", [role for role in Membership.Role.values if role != Membership.Role.OWNER])
def test_no_role_but_the_owner_owns_the_business(role):
    """Whatever an app grants a role (``base.*`` included), what is the owner's alone stays the owner's."""
    assert not permissions_of_role(role) & OWNER_ONLY


def test_manager_and_employee_get_what_each_app_declares(make_user, only_demo_and_shop):
    manager = make_user("marta", host=SLUG_A, role="hub_manager")
    employee = make_user("eva", host=SLUG_A, role="hub_employee")
    assert permissions_for(manager, A) == {"demo.view", "demo.manage", "shop.view", "shop.sell"}
    assert permissions_for(employee, A) == {"demo.view", "shop.view"}


@pytest.mark.parametrize("role", ["owner", "admin", "employee"])
def test_a_role_without_the_hub_prefix_gets_nothing(make_user, role):
    assert permissions_for(make_user(host=SLUG_A, role=role), A) == frozenset()


def test_reload_user_reads_the_database_again(make_user):
    user = make_user()
    user.__class__.objects.filter(pk=user.pk).update(is_superuser=True)
    assert user.is_superuser is False
    assert reload_user(user).is_superuser is True


def test_reload_user_of_a_deleted_user_is_none(make_user):
    user = make_user()
    user.__class__.objects.filter(pk=user.pk).delete()
    assert reload_user(user) is None


def test_reload_user_of_nobody_is_none():
    assert reload_user(None) is None


def test_membership_role_change_is_seen(make_user):
    user = make_user(host=SLUG_A, role="hub_employee")
    Membership.objects.filter(user=user, host=SLUG_A).update(role="hub_admin")
    assert "demo.manage" in permissions_for(user, A)
