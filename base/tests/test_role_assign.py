"""Giving a person a role of the business, or returning them to the one of their invitation (``base.role.assign``,
BASE-F130).

Whoever manages roles gives them to the people below them by their invitation: never to the owner, never to themselves,
and never a role that allows more than they may do themselves, of any app of the deployment.
"""

import json

import pytest
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import events
from base.apps_on import active_apps
from base.models import Hub, HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import access_for, permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HOST, HUB_DB, in_business_a
from base.tests.roles import a_role, held_by
from base.tests.test_services_roles import adam, eva, olga

__all__ = ["adam", "eva", "in_business_a", "olga"]

pytestmark = HUB_DB

OWNER, ADMIN, MANAGER, EMPLOYEE, ACCOUNTANT = (
    Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER, Membership.Role.EMPLOYEE,
    Membership.Role.ACCOUNTANT,
)


def assign(client, person: str, role, host=HOST):
    body = {"person": person, "role": str(getattr(role, "pk", role))}
    return client.post("/api/roles/assign", json.dumps(body), content_type="application/json", HTTP_HOST=host)


def refusal(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def role_of(username: str) -> BusinessRole | None:
    return HubUser.objects.get(username=username).business_role


def facts() -> list[dict]:
    return list(OutboxEvent.objects.filter(name=events.ROLE_ASSIGNED).values_list("payload", flat=True))


@pytest.fixture
def mario(make_user):
    return make_user("saas:4", host=A.key, role=MANAGER, first_name="Mario")


@pytest.fixture
def cashier():
    """An employee's role that does not void sales."""
    return a_role("Cashier without voids", sale__view_sale=ON, sale__void_sale=OFF)


class TestGivingARole:
    def test_the_person_may_do_what_it_allows_from_then_on(self, client, olga, eva, cashier):
        client.force_login(olga)
        assert access_for(eva, A) == permissions_of_role(EMPLOYEE)

        response = assign(client, "saas:3", cashier)

        assert response.status_code == 200, response.content
        assert response.json() == {
            "person": "saas:3", "name": "Eva", "role": str(cashier.pk), "label": "Cashier without voids",
        }
        assert role_of("saas:3") == cashier
        allowed = access_for(eva, A)
        assert "sale.view_sale" in allowed
        assert "sale.take_payment" in permissions_of_role(EMPLOYEE) - allowed
        assert facts() == [{"person": "saas:3", "id": str(cashier.pk)}]

    def test_a_role_may_allow_more_than_their_invitation(self, client, olga, eva):
        assert "base.view_costs" not in access_for(eva, A)
        client.force_login(olga)

        assert assign(client, "saas:3", a_role("Shift lead", base__view_costs=ON)).status_code == 200

        assert "base.view_costs" in access_for(eva, A)

    def test_another_one_takes_its_place(self, client, olga, eva, cashier):
        held_by(eva, cashier)
        evening = a_role("Evening", sale__view_sale=ON)
        client.force_login(olga)

        assert assign(client, "saas:3", evening).status_code == 200

        assert role_of("saas:3") == evening

    def test_the_roles_list_counts_them_in_it_at_once(self, client, olga, eva, cashier):
        client.force_login(olga)
        assign(client, "saas:3", cashier)

        roles = client.get("/api/roles", HTTP_HOST=HOST).json()["roles"]

        members = {role["key"]: role["members"] for role in roles}
        assert (members[str(cashier.pk)], members["hub_employee"]) == (1, 0)

    def test_somebody_erplora_com_names_who_has_not_entered_yet(self, client, olga, cashier):
        member = "019a0000-0000-7000-8000-000000000007"
        people = [{"user_id": member, "role": "hub_employee", "name": "Luis Gil", "email": "luis@example.com"}]
        Hub.objects.filter(slug=A.key).update(state={"members": people})
        client.force_login(olga)

        response = assign(client, f"saas:{member}", cashier)

        assert response.status_code == 200, response.content
        person = HubUser.objects.get(username=f"saas:{member}")
        assert (person.business_role, person.name, person.email) == (cashier, "Luis Gil", "luis@example.com")
        assert str(person.account_id) == member

    def test_an_administrator_gives_them_to_whoever_is_below(self, client, adam, mario, cashier):
        client.force_login(adam)

        assert assign(client, "saas:4", cashier).status_code == 200


class TestReturningToTheInvitation:
    def test_the_role_of_their_invitation_takes_the_other_away(self, client, olga, eva, cashier):
        held_by(eva, cashier)
        client.force_login(olga)

        response = assign(client, "saas:3", "hub_employee")

        assert response.status_code == 200, response.content
        assert response.json() == {"person": "saas:3", "name": "Eva", "role": "hub_employee", "label": "Employee"}
        assert role_of("saas:3") is None
        assert access_for(eva, A) == permissions_of_role(EMPLOYEE)
        assert facts() == [{"person": "saas:3", "id": None}]

    def test_it_is_named_in_the_readers_language(self, client, olga, eva, cashier):
        client.force_login(olga)

        answer = client.post(
            "/api/roles/assign", json.dumps({"person": "saas:3", "role": "hub_employee"}),
            content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es",
        ).json()

        assert answer["label"] == "Empleado"

    @pytest.mark.parametrize("basic", ["hub_manager", "hub_owner", "hub_accountant"])
    def test_another_basic_role_is_given_on_erplora_com(self, client, olga, eva, cashier, basic):
        held_by(eva, cashier)
        client.force_login(olga)

        response = assign(client, "saas:3", basic)

        assert refusal(response) == (409, "base.role_basic")
        assert "role" in response.json()["error"]["fields"]
        assert role_of("saas:3") == cashier


class TestWhom:
    def test_never_the_owner(self, client, adam, olga, cashier):
        client.force_login(adam)

        assert refusal(assign(client, "saas:1", cashier)) == (403, "base.role_of_owner")

    def test_not_even_the_owner_themselves(self, client, olga, cashier):
        client.force_login(olga)

        assert refusal(assign(client, "saas:1", cashier)) == (403, "base.role_of_owner")

    def test_never_oneself(self, client, adam, cashier):
        client.force_login(adam)

        assert refusal(assign(client, "saas:2", cashier)) == (403, "base.role_own")
        assert facts() == []

    def test_nor_to_take_away_ones_own(self, client, adam, cashier):
        held_by(adam, a_role("Boss", base__view_home=ON, base__manage_roles=ON))
        client.force_login(adam)

        assert refusal(assign(client, "saas:2", "hub_admin")) == (403, "base.role_own")

    def test_nor_somebody_of_the_same_rank(self, client, adam, make_user, cashier):
        make_user("saas:6", host=A.key, role=ADMIN)
        client.force_login(adam)

        assert refusal(assign(client, "saas:6", cashier)) == (403, "base.role_above")

    def test_nor_somebody_above_whatever_their_role_of_the_business_lets_them(self, client, eva, mario):
        held_by(eva, a_role("People", base__view_home=ON, base__manage_roles=ON))
        client.force_login(eva)

        assert refusal(assign(client, "saas:4", a_role("Nothing", base__view_home=ON))) == (403, "base.role_above")

    def test_the_rank_is_the_one_of_the_invitation_not_of_the_role_they_hold(self, client, adam, eva, cashier):
        """Eva holds a copy of the owner's; by her invitation she is still below the administrator."""
        held_by(eva, a_role("Partner", origin=OWNER, base__view_home=ON))
        client.force_login(adam)

        assert assign(client, "saas:3", cashier).status_code == 200

    def test_a_manager_whose_role_manages_roles_gives_one_to_an_employee(self, client, mario, eva):
        nothing = a_role("Nothing", base__view_home=ON, **all_off())
        held_by(mario, a_role("People", base__view_home=ON, base__manage_roles=ON, **all_off()))
        client.force_login(mario)

        assert assign(client, "saas:3", nothing).status_code == 200

    def test_somebody_who_is_not_of_the_business(self, client, olga, make_user, cashier):
        make_user("saas:9")
        client.force_login(olga)

        assert refusal(assign(client, "saas:9", cashier)) == (404, "base.person_not_found")

    def test_somebody_who_left(self, client, olga, eva, cashier):
        Membership.objects.filter(user=eva).delete()
        client.force_login(olga)

        assert refusal(assign(client, "saas:3", cashier)) == (404, "base.person_not_found")
        assert not HubUser.objects.filter(username="saas:3").exists()


def all_off(*but: str) -> dict[str, str]:
    """Every permission of the deployment off but those ``but`` names, for a role that gives nothing of any app."""
    return {
        permission.replace(".", "__"): OFF
        for permission in permissions_of_role(ADMIN)
        if permission not in {"base.view_home", "base.manage_roles", *but}
    }


class TestNeverMoreThanWhoGivesIt:
    @pytest.fixture
    def mara(self, make_user):
        """A manager whose role of the business lets her manage roles and view sales, and nothing else."""
        user = make_user("saas:5", host=A.key, role=MANAGER, first_name="Mara")
        held_by(
            user,
            a_role("People", base__view_home=ON, base__manage_roles=ON, sale__view_sale=ON, **all_off("sale.view_sale")),
        )
        return user

    def test_what_they_hold_they_may_give(self, client, mara, eva):
        seller = a_role("Seller", base__view_home=ON, sale__view_sale=ON, **all_off("sale.view_sale"))
        client.force_login(mara)

        assert assign(client, "saas:3", seller).status_code == 200

    def test_what_they_do_not_hold_they_may_not(self, client, mara, eva):
        lead = a_role("Shift lead", base__view_home=ON, sale__void_sale=ON, **all_off("sale.void_sale"))
        client.force_login(mara)

        response = assign(client, "saas:3", lead)

        assert refusal(response) == (403, "base.role_beyond_editor")
        assert "role" in response.json()["error"]["fields"]
        assert not HubUser.objects.filter(username="saas:3", business_role__isnull=False).exists()
        assert facts() == []

    def test_nor_what_it_gives_of_an_app_that_is_off(self, client, mara, eva, monkeypatch):
        lead = a_role("Shift lead", base__view_home=ON, sale__void_sale=ON, **all_off("sale.void_sale"))
        on = active_apps(A) - {"sale"}
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: on)
        client.force_login(mara)

        assert refusal(assign(client, "saas:3", lead)) == (403, "base.role_beyond_editor")

    def test_nor_what_the_role_it_came_from_gives_of_an_app_it_was_not_saved_with(self, client, mara, eva):
        copy_of_the_manager = a_role("Boss", origin=MANAGER, base__view_home=ON)
        client.force_login(mara)

        assert refusal(assign(client, "saas:3", copy_of_the_manager)) == (403, "base.role_beyond_editor")

    @pytest.mark.parametrize("sale_on", [True, False])
    @pytest.mark.parametrize(("mine", "given"), [(OFF, False), (APPROVAL, True), (ON, True)])
    def test_nor_one_that_does_with_approval_what_their_role_says_no_to(
        self, client, mara, eva, monkeypatch, sale_on, mine, given
    ):
        hers = BusinessRole.objects.get(name="People")
        hers.states = {**hers.states, "sale.void_sale": mine}
        hers.save()
        till = a_role("Till", base__view_home=ON, sale__void_sale=APPROVAL, **all_off("sale.void_sale"))
        on = active_apps(A) - (set() if sale_on else {"sale"})
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: on)
        client.force_login(mara)

        response = assign(client, "saas:3", till)

        if given:
            assert response.status_code == 200, response.content
        else:
            assert refusal(response) == (403, "base.role_beyond_editor")
            assert not HubUser.objects.filter(username="saas:3", business_role__isnull=False).exists()

    @pytest.mark.parametrize(("mine", "given"), [(OFF, False), (APPROVAL, True)])
    def test_nor_return_somebody_to_an_invitation_that_does_with_approval_what_their_role_says_no_to(
        self, client, mara, eva, mine, given
    ):
        """Mara may do all an employee does; an employee voids with approval."""
        hers = BusinessRole.objects.get(name="People")
        approvable = {
            get_operation(name).permission for config in all_live_app_configs() for name in getattr(config, "approvals", {})
        }
        hers.states |= dict.fromkeys(approvable, APPROVAL) | {"sale.void_sale": mine}
        hers.states |= dict.fromkeys(permissions_of_role(EMPLOYEE), ON)
        hers.save()
        held_by(eva, a_role("Nothing", base__view_home=ON, **all_off()))
        client.force_login(mara)

        response = assign(client, "saas:3", "hub_employee")

        if given:
            assert response.status_code == 200, response.content
        else:
            assert refusal(response) == (403, "base.role_beyond_editor")
            assert role_of("saas:3").name == "Nothing"

    def test_nor_return_somebody_to_an_invitation_that_allows_more(self, client, mara, eva):
        held_by(eva, a_role("Nothing", base__view_home=ON, **all_off()))
        client.force_login(mara)

        assert refusal(assign(client, "saas:3", "hub_employee")) == (403, "base.role_beyond_editor")
        assert role_of("saas:3").name == "Nothing"


class TestWhoMay:
    @pytest.mark.parametrize("role", [MANAGER, EMPLOYEE, ACCOUNTANT])
    def test_without_managing_roles_it_is_refused(self, client, make_user, eva, cashier, role):
        client.force_login(make_user("saas:8", host=A.key, role=role))

        assert refusal(assign(client, "saas:3", cashier)) == (403, "permission_denied")
        assert not HubUser.objects.filter(business_role__isnull=False).exists()

    def test_nobody_comes_in_without_a_session(self, client, eva, cashier):
        assert assign(client, "saas:3", cashier).status_code == 401

    def test_a_role_that_does_not_exist(self, client, olga, eva):
        client.force_login(olga)

        assert refusal(assign(client, "saas:3", "019a0000-0000-7000-8000-000000000000")) == (404, "base.role_not_found")
        assert refusal(assign(client, "saas:3", "nonsense")) == (404, "base.role_not_found")

    def test_both_the_person_and_the_role_are_needed(self, client, olga):
        client.force_login(olga)

        response = client.post(
            "/api/roles/assign", json.dumps({"person": "saas:3"}), content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 422


class TestTwoBusinesses:
    def test_a_role_of_one_is_not_given_in_the_other(self, client, olga, eva, hub_b):
        with use_hub(hub_b):
            theirs = a_role("Theirs")
        client.force_login(olga)

        assert refusal(assign(client, "saas:3", theirs)) == (404, "base.role_not_found")

    def test_nor_to_the_people_of_the_other(self, client, olga, make_user, cashier, hub_b):
        make_user("saas:7", host=B.key, role=EMPLOYEE)
        client.force_login(olga)

        assert refusal(assign(client, "saas:7", cashier)) == (404, "base.person_not_found")
        with use_hub(hub_b):
            assert not HubUser.objects.filter(business_role__isnull=False).exists()

    def test_the_same_person_in_both_keeps_in_one_what_they_were_given_in_the_other(self, client, olga, eva, hub_b):
        cashier = a_role()
        Membership.objects.create(user=eva, host=B.key, role=EMPLOYEE)
        with use_hub(hub_b):
            theirs = a_role("Theirs", sale__view_sale=ON)
            held_by(eva, theirs)
        client.force_login(olga)

        assert assign(client, "saas:3", cashier).status_code == 200

        assert role_of("saas:3") == cashier
        with use_hub(hub_b):
            assert role_of("saas:3") == theirs
