"""The roles a business makes for itself (``base.role.create``, ``update`` and ``delete``, BASE-F127 to BASE-F129).

Each is duplicated from a basic role or from another of the business, adjusted permission by permission and deleted once
nobody of the business holds it. Nobody gives what they do not hold, and no role gives what is the owner's alone.
"""

import json

import pytest
from live.context import OperationContext
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import events
from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import OWNER_ONLY, access_for, permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HOST, HUB_DB, in_business_a
from base.tests.roles import a_role, held_by
from base.tests.routes import bound_routes, spa_routes

__all__ = ["in_business_a"]

pytestmark = HUB_DB

EMPLOYEE = Membership.Role.EMPLOYEE


def get(client, path, host=HOST, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, body, host=HOST):
    return client.post(f"/api{path}", json.dumps(body), content_type="application/json", HTTP_HOST=host)


def code(response) -> str:
    return response.json()["error"]["code"]


def facts(name: str) -> list[dict]:
    return list(OutboxEvent.objects.filter(name=name).values_list("payload", flat=True))


def detail(client, role: BusinessRole) -> dict[str, str]:
    """Each permission of ``role`` as «What it allows» shows it."""
    answer = get(client, "/roles/detail", role=str(role.pk)).json()
    return {line["permission"]: line["state"] for app in answer["apps"] for line in app["permissions"]}


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")


@pytest.fixture
def adam(make_user):
    return make_user("saas:2", host=A.key, role=Membership.Role.ADMIN, first_name="Adam")


@pytest.fixture
def eva(make_user):
    return make_user("saas:3", host=A.key, role=EMPLOYEE, first_name="Eva")


@pytest.fixture
def rosa(make_user):
    """An employee whose role of the business lets her manage roles, and hardly anything else."""
    user = make_user("saas:5", host=A.key, role=EMPLOYEE, first_name="Rosa")
    held_by(user, a_role("People", base__view_home=ON, base__manage_roles=ON, sale__view_sale=ON))
    return user


class TestCreate:
    def test_a_copy_of_a_basic_role_allows_what_it_allows(self, client, olga):
        client.force_login(olga)

        response = post(client, "/roles", {"based_on": "hub_employee", "name": "  Cashier  ", "description": "The till"})

        assert response.status_code == 200, response.content
        role = BusinessRole.objects.get()
        assert (role.name, role.description, role.origin) == ("Cashier", "The till", "hub_employee")
        basic = get(client, "/roles/detail", role="hub_employee").json()
        assert detail(client, role) == {
            line["permission"]: line["state"]
            for app in basic["apps"]
            for line in app["permissions"]
            if line["permission"] not in OWNER_ONLY
        }
        assert response.json() == {
            "key": str(role.pk), "label": "Cashier", "description": "The till", "origin": "own", "members": 0,
            "permissions": len(permissions_of_role(EMPLOYEE)), "to_review": False,
        }
        assert facts(events.ROLE_CREATED) == [{"id": str(role.pk)}]

    def test_a_copy_of_a_role_of_the_business_keeps_what_was_saved_in_it_and_where_it_came_from(self, client, olga):
        source = a_role(origin=Membership.Role.MANAGER, sale__void_sale=OFF, sale__view_sale=ON)
        client.force_login(olga)

        assert post(client, "/roles", {"based_on": str(source.pk), "name": "Evening till"}).status_code == 200

        copy = BusinessRole.objects.get(name="Evening till")
        assert (copy.origin, copy.states) == ("hub_manager", source.states)

    def test_a_copy_of_the_owner_does_not_own_the_business(self, client, olga, eva):
        client.force_login(olga)

        assert post(client, "/roles", {"based_on": "hub_owner", "name": "Partner"}).status_code == 200

        role = BusinessRole.objects.get()
        held_by(eva, role)
        assert access_for(eva, A) == permissions_of_role(Membership.Role.OWNER) - OWNER_ONLY
        assert not OWNER_ONLY & set(role.states)

    def test_it_does_not_change_with_the_role_it_came_from(self, client, olga, eva, monkeypatch):
        client.force_login(olga)
        post(client, "/roles", {"based_on": "hub_employee", "name": "Cashier"})
        held_by(eva, BusinessRole.objects.get())

        monkeypatch.setattr("base.permissions.permissions_for_role", lambda configs, role: frozenset())

        assert "sale.view_sale" in access_for(eva, A)

    def test_an_administrator_gives_all_they_hold(self, client, adam):
        client.force_login(adam)

        assert post(client, "/roles", {"based_on": "hub_owner", "name": "Partner"}).status_code == 200

    def test_nobody_creates_a_role_that_allows_what_they_may_not_do(self, client, rosa):
        client.force_login(rosa)

        response = post(client, "/roles", {"based_on": "hub_manager", "name": "Boss"})

        assert (response.status_code, code(response)) == (403, "base.role_beyond_editor")
        assert not BusinessRole.objects.filter(name="Boss").exists()

    def test_nor_one_that_will_give_it_when_an_app_is_turned_on(self, client, rosa):
        """Its saved states give nothing, but an app turned on later gives what it gives the administrator."""
        source = a_role("Empty", origin=Membership.Role.ADMIN, base__view_home=ON)
        client.force_login(rosa)

        response = post(client, "/roles", {"based_on": str(source.pk), "name": "Empty too"})

        assert (response.status_code, code(response)) == (403, "base.role_beyond_editor")

    def test_nor_what_it_was_saved_with_of_an_app_that_is_off(self, client, rosa, monkeypatch):
        """An app that is off gives nothing today, but what the role keeps of it comes back when it is turned on."""
        held = a_role("Shelves", base__view_home=ON, sale__view_sale=ON, inventory__view_product=ON)
        beyond = a_role("Stock", base__view_home=ON, sale__view_sale=ON, inventory__adjust_stock=ON)
        client.force_login(rosa)
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: frozenset({"base", "sale"}))

        given = post(client, "/roles", {"based_on": str(held.pk), "name": "Shelves too"})
        refused = post(client, "/roles", {"based_on": str(beyond.pk), "name": "Stock too"})

        assert given.status_code == 200, given.content
        assert (refused.status_code, code(refused)) == (403, "base.role_beyond_editor")
        assert not BusinessRole.objects.filter(name="Stock too").exists()

    @pytest.mark.parametrize("name", ["", "   "])
    def test_a_role_has_a_name(self, client, olga, name):
        client.force_login(olga)

        response = post(client, "/roles", {"based_on": "hub_employee", "name": name})

        assert (response.status_code, code(response)) == (422, "base.role_name_required")
        assert not BusinessRole.objects.exists()

    def test_two_roles_of_the_business_do_not_share_a_name(self, client, olga):
        a_role("Cashier")
        client.force_login(olga)

        response = post(client, "/roles", {"based_on": "hub_employee", "name": "cashier"})

        assert (response.status_code, code(response)) == (409, "base.role_name_taken")
        assert BusinessRole.objects.count() == 1

    @pytest.mark.parametrize("role", ["hub_cashier", "0199aaaa-0000-7000-8000-000000000001"])
    def test_a_role_that_is_not_in_the_business_is_not_copied(self, client, olga, role):
        client.force_login(olga)

        response = post(client, "/roles", {"based_on": role, "name": "Cashier"})

        assert (response.status_code, code(response)) == (404, "base.role_not_found")


class TestUpdate:
    def test_only_what_is_sent_changes(self, client, olga):
        role = a_role(sale__view_sale=ON, sale__void_sale=ON, sale__take_payment=ON)
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.void_sale": "off"}})

        assert response.status_code == 200, response.content
        role.refresh_from_db()
        assert role.states == {"sale.view_sale": ON, "sale.void_sale": OFF, "sale.take_payment": ON}
        assert (role.name, role.description) == ("Cashier", "")
        assert response.json()["key"] == str(role.pk)
        assert facts(events.ROLE_UPDATED) == [{"id": str(role.pk)}]

    def test_whoever_holds_it_gains_and_loses_it_at_once(self, client, olga, eva):
        role = a_role(sale__view_sale=ON, sale__void_sale=OFF)
        held_by(eva, role)
        client.force_login(olga)

        states = {"sale.void_sale": "on", "sale.view_sale": "off"}
        assert post(client, "/roles/update", {"role": str(role.pk), "states": states}).status_code == 200

        assert "sale.void_sale" in access_for(eva, A)
        assert "sale.view_sale" not in access_for(eva, A)

    def test_naming_one_permission_of_an_app_it_was_not_saved_with_keeps_what_the_others_gave(self, client, olga):
        role = a_role(base__view_home=ON)
        client.force_login(olga)
        before = detail(client, role)
        assert (before["sale.take_payment"], before["sale.void_sale"]) == (ON, APPROVAL)

        assert post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.take_payment": "off"}}).status_code == 200

        assert detail(client, role) == {**before, "sale.take_payment": OFF}

    def test_it_leaves_to_review_what_it_did_not_name(self, client, olga):
        role = a_role(sale__view_sale=ON)
        client.force_login(olga)

        answer = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.view_sale": "off"}}).json()

        assert answer["to_review"] is True

    def test_saving_all_it_shows_leaves_nothing_to_review(self, client, olga):
        role = a_role(sale__view_sale=ON)
        client.force_login(olga)

        answer = post(client, "/roles/update", {"role": str(role.pk), "states": detail(client, role)}).json()

        assert answer["to_review"] is False

    def test_its_name_and_description_change_alone(self, client, olga):
        role = a_role(sale__view_sale=ON)
        client.force_login(olga)

        post(client, "/roles/update", {"role": str(role.pk), "name": " Evening  till ", "description": "From six"})

        role.refresh_from_db()
        assert (role.name, role.description, role.states) == ("Evening till", "From six", {"sale.view_sale": ON})

    def test_it_may_keep_its_own_name_and_not_take_another_role_s(self, client, olga):
        role = a_role("Cashier")
        a_role("Cook")
        client.force_login(olga)

        assert post(client, "/roles/update", {"role": str(role.pk), "name": "CASHIER"}).status_code == 200
        response = post(client, "/roles/update", {"role": str(role.pk), "name": "cook"})

        assert (response.status_code, code(response)) == (409, "base.role_name_taken")

    def test_a_role_is_not_left_without_a_name(self, client, olga):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "name": " "})

        assert (response.status_code, code(response)) == (422, "base.role_name_required")

    def test_there_is_something_to_change(self, client, olga):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk)})

        assert (response.status_code, code(response)) == (422, "base.nothing_to_change")

    def test_a_basic_role_is_not_changed(self, client, olga):
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": "hub_employee", "states": {"sale.void_sale": "on"}})

        assert (response.status_code, code(response)) == (409, "base.role_basic")

    def test_a_role_that_is_not_there_is_not_found(self, client, olga):
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": "hub_cashier", "name": "Cashier"})

        assert (response.status_code, code(response)) == (404, "base.role_not_found")

    @pytest.mark.parametrize("state", ["on", "approval", "off"])
    def test_nobody_gives_owning_the_business_not_even_its_owner(self, client, olga, state):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"base.own_business": state}})

        assert (response.status_code, code(response)) == (403, "base.role_owner_only")
        role.refresh_from_db()
        assert role.states == {}

    def test_nobody_gives_what_they_do_not_hold(self, client, rosa):
        role = a_role(sale__view_sale=OFF, sale__void_sale=OFF)
        client.force_login(rosa)

        given = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.view_sale": "on"}})
        refused = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.void_sale": "on"}})

        assert given.status_code == 200, given.content
        assert (refused.status_code, code(refused)) == (403, "base.role_beyond_editor")
        role.refresh_from_db()
        assert role.states == {"sale.view_sale": ON, "sale.void_sale": OFF}

    def test_nor_what_the_role_it_came_from_gives_if_they_do_not_hold_it(self, client, rosa):
        """The employee's role takes payments; Rosa's own does not, so she cannot turn it back on in a copy of it."""
        role = a_role(sale__view_sale=ON, sale__take_payment=OFF)
        assert "sale.take_payment" in permissions_of_role(role.origin)
        client.force_login(rosa)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.take_payment": "on"}})

        assert (response.status_code, code(response)) == (403, "base.role_beyond_editor")
        role.refresh_from_db()
        assert role.states == {"sale.view_sale": ON, "sale.take_payment": OFF}

    def test_not_even_to_the_role_they_hold_themselves(self, client, rosa):
        mine = BusinessRole.objects.get(name="People")
        client.force_login(rosa)

        response = post(client, "/roles/update", {"role": str(mine.pk), "states": {"base.administer_hub": "on"}})

        assert (response.status_code, code(response)) == (403, "base.role_beyond_editor")

    def test_what_a_role_already_allows_does_not_stop_a_change_of_anything_else(self, client, rosa):
        role = a_role(sale__view_sale=OFF, sale__void_sale=ON, inventory__view_product=ON)
        client.force_login(rosa)

        response = post(
            client, "/roles/update", {"role": str(role.pk), "name": "Till", "states": {"inventory.view_product": "off"}}
        )

        assert response.status_code == 200, response.content

    def test_to_allow_it_with_approval_gives_nothing_by_itself(self, client, rosa):
        role = a_role(sale__void_sale=OFF)
        client.force_login(rosa)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.void_sale": "approval"}})

        assert response.status_code == 200, response.content

    def test_only_what_a_manager_can_approve_is_left_to_approval(self, client, olga):
        role = a_role(sale__view_sale=ON)
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.view_sale": "approval"}})

        assert (response.status_code, code(response)) == (422, "base.role_not_approvable")

    @pytest.mark.parametrize("permission", ["sale.fly", "sale.*", "*"])
    def test_a_permission_no_app_declares_is_not_saved(self, client, olga, permission):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {permission: "on"}})

        assert (response.status_code, code(response)) == (422, "base.role_permission_unknown")

    def test_nor_one_of_an_app_that_is_off(self, client, olga, monkeypatch):
        role = a_role()
        client.force_login(olga)
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: frozenset({"base", "sale"}))

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"inventory.view_product": "on"}})

        assert (response.status_code, code(response)) == (422, "base.role_permission_unknown")

    def test_a_state_is_one_of_the_three(self, client, olga):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/update", {"role": str(role.pk), "states": {"sale.view_sale": "maybe"}})

        assert response.status_code == 422


class TestDelete:
    def test_a_role_nobody_holds_is_deleted(self, client, olga):
        role = a_role()
        client.force_login(olga)

        response = post(client, "/roles/delete", {"role": str(role.pk)})

        assert (response.status_code, response.json()) == (200, {"key": str(role.pk)})
        assert not BusinessRole.objects.exists()
        assert facts(events.ROLE_DELETED) == [{"id": str(role.pk)}]

    def test_one_somebody_holds_is_not(self, client, olga, eva, make_user):
        role = a_role()
        held_by(eva, role)
        held_by(make_user("saas:7", host=A.key, role=EMPLOYEE), role)
        client.force_login(olga)

        response = post(client, "/roles/delete", {"role": str(role.pk)})

        assert (response.status_code, code(response)) == (409, "base.role_in_use")
        assert "2" in response.json()["error"]["message"]
        assert BusinessRole.objects.filter(pk=role.pk).exists()
        assert HubUser.objects.filter(business_role=role).count() == 2

    def test_whoever_left_the_business_does_not_stop_it(self, client, olga, eva):
        role = a_role()
        held_by(eva, role)
        Membership.objects.filter(user=eva).delete()
        client.force_login(olga)

        assert post(client, "/roles/delete", {"role": str(role.pk)}).status_code == 200

        assert HubUser.objects.get(username="saas:3").business_role is None

    def test_nor_does_the_owner_whom_a_role_never_rules(self, client, olga):
        role = a_role()
        held_by(olga, role)
        client.force_login(olga)

        assert post(client, "/roles/delete", {"role": str(role.pk)}).status_code == 200

        assert HubUser.objects.get(username="saas:1").business_role is None

    def test_a_basic_role_is_not_deleted(self, client, olga):
        client.force_login(olga)

        response = post(client, "/roles/delete", {"role": "hub_accountant"})

        assert (response.status_code, code(response)) == (409, "base.role_basic")


ASKS = (
    ("/roles", {"based_on": "hub_employee", "name": "Cashier"}),
    ("/roles/update", {"role": "{role}", "name": "Till"}),
    ("/roles/delete", {"role": "{role}"}),
)


class TestWhoMay:
    @pytest.mark.parametrize(("path", "body"), ASKS)
    def test_without_managing_roles_it_is_refused(self, client, make_user, path, body):
        role = a_role()
        client.force_login(make_user("saas:4", host=A.key, role=Membership.Role.MANAGER))

        response = post(client, path, {key: value.format(role=role.pk) for key, value in body.items()})

        assert (response.status_code, code(response)) == (403, "permission_denied")
        assert list(BusinessRole.objects.values_list("name", flat=True)) == ["Cashier"]

    @pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
    def test_the_owner_and_an_administrator_manage_them(self, role):
        assert "base.manage_roles" in permissions_of_role(role)

    @pytest.mark.parametrize("role", [Membership.Role.MANAGER, EMPLOYEE, Membership.Role.ACCOUNTANT])
    def test_nobody_else_does_unless_a_role_of_the_business_lets_them(self, role, client, rosa):
        assert "base.manage_roles" not in permissions_of_role(role)
        client.force_login(rosa)
        # What a copy of their own role allows, they hold.
        mine = BusinessRole.objects.get(name="People")
        mine.states |= {
            permission: OFF
            for permission in permissions_of_role(Membership.Role.OWNER) - OWNER_ONLY
            if permission not in mine.states
        }
        mine.save()

        assert post(client, "/roles", {"based_on": str(mine.pk), "name": "People too"}).status_code == 200

    @pytest.mark.parametrize(("path", "body"), ASKS)
    def test_nobody_comes_in_without_a_session(self, client, path, body):
        assert post(client, path, body).status_code == 401


class TestTwoBusinesses:
    def test_a_role_of_one_is_not_there_in_the_other(self, client, olga, hub_b):
        with use_hub(hub_b):
            theirs = a_role("Theirs")
        client.force_login(olga)

        listed = {role["label"] for role in get(client, "/roles").json()["roles"]}
        assert "Theirs" not in listed
        assert get(client, "/roles/detail", role=str(theirs.pk)).status_code == 404
        for path, body in (
            ("/roles", {"based_on": str(theirs.pk), "name": "Mine"}),
            ("/roles/update", {"role": str(theirs.pk), "name": "Mine"}),
            ("/roles/delete", {"role": str(theirs.pk)}),
        ):
            assert code(post(client, path, body)) == "base.role_not_found", path
        with use_hub(hub_b):
            assert BusinessRole.objects.get().name == "Theirs"

    def test_two_businesses_may_give_a_role_the_same_name(self, client, olga, hub_b):
        with use_hub(hub_b):
            a_role("Cashier")
        client.force_login(olga)

        assert post(client, "/roles", {"based_on": "hub_employee", "name": "Cashier"}).status_code == 200

    def test_the_people_of_another_business_do_not_hold_it(self, client, olga, make_user, hub_b):
        role = a_role()
        theirs = make_user("saas:9", host=B.key, role=EMPLOYEE)
        held_by(theirs, role)
        client.force_login(olga)

        assert post(client, "/roles/delete", {"role": str(role.pk)}).status_code == 200


class TestHowTheyAreReached:
    ROUTES = {
        ("POST", "/roles", "base.role.create"),
        ("POST", "/roles/update", "base.role.update"),
        ("POST", "/roles/delete", "base.role.delete"),
    }

    def test_their_routes_are_the_ones_the_spa_calls(self):
        from base.api.people import router

        assert self.ROUTES <= bound_routes(router)
        assert self.ROUTES <= spa_routes("base.role.")

    @pytest.mark.parametrize("name", ["base.role.create", "base.role.update", "base.role.delete"])
    def test_an_api_key_does_not_reach_them(self, name):
        op = get_operation(name)

        assert (op.kind, op.permission, op.expose_api) == ("command", "base.manage_roles", False)

    def test_a_role_may_be_created_twice_after_a_cut(self):
        """Only their own database, so a cut before the COMMIT runs them again."""
        assert all(get_operation(f"base.role.{action}").repeatable for action in ("create", "update", "delete"))

    def test_they_are_run_by_the_platform_as_an_operation_too(self, olga):
        op = get_operation("base.role.create")
        ctx = OperationContext(scope=A, actor=olga, permissions=access_for(olga, A))

        assert op(ctx, op.input(based_on="hub_employee", name="Cashier")).label == "Cashier"
