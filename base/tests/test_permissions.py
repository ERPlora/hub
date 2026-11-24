"""Permissions of a user on a host: the customer role of its Membership on that host, unless the business gave the
person a role of its own (a superuser's ``*`` is the platform scope's alone: ERPlora's staff is no customer,
tests/test_guardrails_permissions.py).

The owner gets every permission of every app; an administrator, all but what is the owner's alone (``OWNER_ONLY``:
owning the business); manager and employee, what each app declares. A role of the business rules over the one of the
invitation, for everyone but the owner, and never gives what is the owner's alone.

The businesses are ``hub_a`` and ``hub_b``, each on a database of its own; the memberships live in control, the roles
of a business in its own database. Business A is entered for every test, as a request to its host is.
"""

from types import SimpleNamespace

import pytest
from django.apps import apps
from live.context import Scope
from live.meta import all_live_app_configs

from base import permissions as permissions_module

from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import OWN_BUSINESS, OWNER_ONLY, access_for, grantable, permissions_of_role, reload_user
from base.roles import OFF, ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import in_business_a
from base.tests.test_auth_views import ON_HUB_A
from base.tests.test_auth_views import A as SLUG_A
from base.tests.test_auth_views import B as SLUG_B

__all__ = ["in_business_a"]

pytestmark = ON_HUB_A

A = Scope("host", SLUG_A)
B = Scope("host", SLUG_B)


def of_apps(permissions, *labels: str) -> set[str]:
    """The permissions that belong to the given apps (``<label>.<action>``), whatever else is installed."""
    return {permission for permission in permissions if permission.split(".", 1)[0] in labels}


def test_nobody_has_nothing():
    assert access_for(None, A) == frozenset()


def test_anonymous_has_nothing():
    from django.contrib.auth.models import AnonymousUser

    assert access_for(AnonymousUser(), A) == frozenset()


def test_a_superuser_without_a_membership_has_nothing_on_a_host(superuser):
    assert access_for(superuser, A) == frozenset()
    assert access_for(superuser, Scope("host", "zzz")) == frozenset()


def test_inactive_user_has_nothing(make_user):
    user = make_user(host=SLUG_A, role="hub_admin", is_active=False)
    assert access_for(user, A) == frozenset()


def test_role_permissions_on_its_host_only(make_user):
    user = make_user(host=SLUG_A, role="hub_employee")
    # demo is the reference app; the other modules' grants are pinned by their own tests.
    assert of_apps(access_for(user, A), "demo") == {"demo.view"}
    assert access_for(user, B) == frozenset()


#: An app that names only some roles: owner and admin are not in its role_permissions.
SHOP = SimpleNamespace(
    label="shop",
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
    assert of_apps(access_for(make_user(host=SLUG_A, role=role), A), "demo") == {"demo.view", "demo.manage"}


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin"])
def test_owner_and_admin_get_every_permission_of_every_app_even_unlisted(make_user, with_shop, role):
    granted = access_for(make_user(host=SLUG_A, role=role), A)
    everything = {"demo.view", "demo.manage", "shop.view", "shop.sell", "shop.refund"}
    assert of_apps(granted, "demo", "shop") == everything


def test_the_owner_gets_every_permission_declared(make_user, with_shop):
    declared = {permission for config in [*all_live_app_configs(), SHOP] for permission in config.permissions}

    assert access_for(make_user(host=SLUG_A, role="hub_owner"), A) == declared


def test_an_administrator_gets_every_permission_declared_but_owning_the_business(make_user, with_shop):
    declared = {permission for config in [*all_live_app_configs(), SHOP] for permission in config.permissions}

    assert access_for(make_user(host=SLUG_A, role="hub_admin"), A) == declared - {OWN_BUSINESS}


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
    assert access_for(manager, A) == {"demo.view", "demo.manage", "shop.view", "shop.sell"}
    assert access_for(employee, A) == {"demo.view", "shop.view"}


@pytest.mark.parametrize("role", ["owner", "admin", "employee"])
def test_a_role_without_the_hub_prefix_gets_nothing(make_user, role):
    assert access_for(make_user(host=SLUG_A, role=role), A) == frozenset()


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
    assert "demo.manage" in access_for(user, A)


def given_a_role_of_the_business(username: str, origin: str, states: dict[str, str]) -> BusinessRole:
    """A role of business A, duplicated from the basic ``origin`` and saved with ``states``, held by ``username``."""
    role = BusinessRole.objects.create(name=f"Role of {username}", origin=origin, states=states)
    HubUser.objects.update_or_create(username=username, defaults={"business_role": role})
    return role


#: demo and SHOP saved whole: a cashier who sells and refunds and does not run the demo.
CASHIER = {"demo.view": ON, "demo.manage": OFF, "shop.view": ON, "shop.sell": ON, "shop.refund": ON}


class TestARoleOfTheBusiness:
    def test_it_rules_over_a_wider_invitation(self, make_user, only_demo_and_shop):
        marta = make_user("marta", host=SLUG_A, role="hub_manager")
        given_a_role_of_the_business("marta", "hub_employee", {**CASHIER, "shop.sell": OFF, "shop.refund": OFF})

        assert access_for(marta, A) == {"demo.view", "shop.view"}

    def test_it_rules_over_a_narrower_invitation(self, make_user, only_demo_and_shop):
        eva = make_user("eva", host=SLUG_A, role="hub_employee")
        given_a_role_of_the_business("eva", "hub_employee", CASHIER)

        assert access_for(eva, A) == {"demo.view", "shop.view", "shop.sell", "shop.refund"}

    def test_an_app_it_was_not_saved_with_gives_what_it_gives_the_basic_role_it_came_from(self, make_user, only_demo_and_shop):
        eva = make_user("eva", host=SLUG_A, role="hub_employee")
        given_a_role_of_the_business("eva", "hub_manager", {"demo.view": ON, "demo.manage": OFF})

        assert access_for(eva, A) == {"demo.view", "shop.view", "shop.sell"}

    def test_a_permission_an_app_added_after_it_was_saved_is_off(self, make_user, only_demo_and_shop):
        eva = make_user("eva", host=SLUG_A, role="hub_employee")
        given_a_role_of_the_business("eva", "hub_manager", {"demo.view": ON, "demo.manage": ON, "shop.view": ON})

        assert access_for(eva, A) == {"demo.view", "demo.manage", "shop.view"}

    def test_it_never_gives_what_is_the_owners_alone(self, make_user):
        adam = make_user("adam", host=SLUG_A, role="hub_admin")
        given_a_role_of_the_business("adam", "hub_owner", {OWN_BUSINESS: ON})

        assert access_for(adam, A) == permissions_of_role("hub_admin")

    def test_the_owner_keeps_everything_whatever_role_their_row_names(self, make_user):
        olga = make_user("olga", host=SLUG_A, role="hub_owner")
        given_a_role_of_the_business("olga", "hub_employee", {})

        assert access_for(olga, A) == permissions_of_role("hub_owner")

    def test_a_person_of_the_business_without_one_holds_the_role_of_their_invitation(self, make_user):
        eva = make_user("eva", host=SLUG_A, role="hub_employee")
        HubUser.objects.create(username="eva")

        assert access_for(eva, A) == permissions_of_role("hub_employee")

    def test_a_role_of_business_a_stays_in_business_a(self, make_user, hub_b, only_demo_and_shop):
        eva = make_user("eva", host=SLUG_A, role="hub_employee")
        Membership.objects.create(user=eva, host=SLUG_B, role="hub_employee")
        given_a_role_of_the_business("eva", "hub_employee", CASHIER)

        with use_hub(hub_b):
            assert access_for(eva, B) == {"demo.view", "shop.view"}
        assert "shop.refund" in access_for(eva, A)


def test_a_role_of_the_business_may_hold_every_permission_but_what_is_the_owners_alone():
    configs = all_live_app_configs()
    held = grantable(configs)

    assert {permission for permissions in held.values() for permission in permissions} == (
        {permission for config in configs for permission in config.permissions} - OWNER_ONLY
    )
    assert set(held["demo"]) == {"demo.view", "demo.manage"}
