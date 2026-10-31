"""Permissions of a user on a host: the customer role of its Membership on that host (a superuser's ``*`` is the
platform scope's alone: ERPlora's staff is no customer, tests/test_guardrails_permissions.py).

Owner and admin get every permission of every app; manager and employee, what each app declares.
"""

from types import SimpleNamespace

import pytest
from django.apps import apps
from live.context import Scope
from live.meta import all_live_app_configs

from base import permissions as permissions_module

from base.models import Membership
from base.permissions import permissions_for, reload_user

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")


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
    user = make_user(host="a", role="hub_admin", is_active=False)
    assert permissions_for(user, A) == frozenset()


def test_role_permissions_on_its_host_only(make_user):
    user = make_user(host="a", role="hub_employee")
    # demo is the reference app; the other modules' grants are pinned by their own tests.
    assert of_apps(permissions_for(user, A), "demo") == {"demo.view"}
    assert permissions_for(user, B) == frozenset()


#: An app that names only some roles: owner and admin are not in its role_permissions.
SHOP = SimpleNamespace(
    permissions=["shop.view", "shop.sell", "shop.refund"],
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
    assert of_apps(permissions_for(make_user(host="a", role=role), A), "demo") == {"demo.view", "demo.manage"}


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin"])
def test_owner_and_admin_get_every_permission_of_every_app_even_unlisted(make_user, with_shop, role):
    granted = permissions_for(make_user(host="a", role=role), A)
    everything = {"demo.view", "demo.manage", "shop.view", "shop.sell", "shop.refund"}
    assert of_apps(granted, "demo", "shop") == everything
    # Every permission each installed app declares, and nothing else.
    declared = {permission for config in [*all_live_app_configs(), SHOP] for permission in config.permissions}
    assert granted == declared


def test_manager_and_employee_get_what_each_app_declares(make_user, only_demo_and_shop):
    manager = make_user("marta", host="a", role="hub_manager")
    employee = make_user("eva", host="a", role="hub_employee")
    assert permissions_for(manager, A) == {"demo.view", "demo.manage", "shop.view", "shop.sell"}
    assert permissions_for(employee, A) == {"demo.view", "shop.view"}


@pytest.mark.parametrize("role", ["owner", "admin", "employee"])
def test_a_role_without_the_hub_prefix_gets_nothing(make_user, role):
    assert permissions_for(make_user(host="a", role=role), A) == frozenset()


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
    user = make_user(host="a", role="hub_employee")
    Membership.objects.filter(user=user, host="a").update(role="hub_admin")
    assert "demo.manage" in permissions_for(user, A)
