"""The roles of the business (``base.role.list``) and «What it allows» of one (``base.role.detail``, BASE-F82): app by app,
each permission with its phrase in the reader's language and what the role does with it: ``on``, ``approval`` (a manager
approves it there and then) or ``off``, the words a role of the business keeps its own states in."""

import json

import pytest
from live.assistant import description
from live.context import OperationContext
from live.errors import OperationError
from live.operations import get as get_operation

from base import events, queries
from base.models import Membership
from base.models.roles import BusinessRole
from base.permissions import OWNER_ONLY, permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.sensitive import DATA_PERMISSIONS
from base.tenancy.tests.business import A, HOST, HUB_DB, in_business_a
from base.tests.roles import a_role, held_by
from base.tests.routes import bound_routes, spa_routes

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def detail(client, role: str, host=HOST):
    return client.get("/api/roles/detail", {"role": role}, HTTP_HOST=host)


def read(role: str, language: str = "en") -> dict:
    op = get_operation("base.role.detail")
    ctx = OperationContext(scope=A, actor="ana", permissions=permissions_of_role(Membership.Role.EMPLOYEE), language=language)
    return op(ctx, op.input(role=role)).model_dump()


def group(answer: dict, key: str) -> dict:
    return next(app for app in answer["apps"] if app["app"] == key)


def states(answer: dict) -> dict[str, str]:
    return {line["permission"]: line["state"] for app in answer["apps"] for line in app["permissions"]}


@pytest.fixture
def eva(make_user):
    return make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva")


class TestWhatABasicRoleAllows:
    def test_the_employee_voids_a_sale_with_approval(self, client, eva):
        client.force_login(eva)

        response = detail(client, "hub_employee")

        assert response.status_code == 200, response.content
        sale = group(response.json(), "sale")
        void = next(line for line in sale["permissions"] if line["permission"] == "sale.void_sale")
        assert (void["phrase"], void["state"]) == ("Void a sale", "approval")

    def test_in_spanish_the_phrases_and_the_apps_are_spanish(self):
        answer = read("hub_employee", language="es")

        sale = group(answer, "sale")
        assert sale["name"] == "Ventas / TPV"
        void = next(line for line in sale["permissions"] if line["permission"] == "sale.void_sale")
        assert (void["phrase"], void["state"]) == ("Anular una venta", "approval")
        assert group(answer, "base")["name"] == "El negocio"
        assert group(answer, "sensitive")["name"] == "Datos sensibles"
        assert answer["label"] == "Empleado"

    def test_what_the_role_holds_is_on_and_what_nobody_approves_for_it_is_off(self):
        employee = states(read("hub_employee"))

        assert employee["sale.take_payment"] == "on"
        assert employee["sale.view_all_sales"] == "off"
        assert employee["base.view_customer_contact"] == "on"
        assert employee["base.view_costs"] == "off"

    def test_the_states_follow_what_each_role_is_given(self):
        for role in Membership.Role.values:
            given = permissions_of_role(role)
            for permission, state in states(read(role)).items():
                assert (state == "on") == (permission in given), (role, permission, state)

    def test_the_owner_holds_everything_and_the_administrator_all_but_owning_the_business(self):
        owner = states(read("hub_owner"))
        admin = states(read("hub_admin"))

        assert set(owner.values()) == {"on"}
        assert {permission for permission, state in admin.items() if state != "on"} == set(OWNER_ONLY)

    def test_the_business_comes_first_and_the_sensitive_data_last_each_with_its_own(self):
        answer = read("hub_manager")

        keys = [app["app"] for app in answer["apps"]]
        assert (keys[0], keys[-1]) == ("base", "sensitive")
        assert {line["permission"] for line in group(answer, "sensitive")["permissions"]} == set(DATA_PERMISSIONS)
        assert not DATA_PERMISSIONS & {line["permission"] for line in group(answer, "base")["permissions"]}
        assert keys[1:-1] == sorted(keys[1:-1], key=lambda key: group(answer, key)["name"].casefold())

    def test_an_app_that_is_off_does_not_show(self, monkeypatch):
        on = {"base", "sale", "inventory"}
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: frozenset(on))

        answer = read("hub_employee")

        assert {app["app"] for app in answer["apps"]} == {"base", "sale", "inventory", "sensitive"}

    def test_it_says_how_many_people_have_the_role(self, client, eva, make_user):
        make_user("saas:7", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Javi")
        make_user("saas:8", host=A.key, role=Membership.Role.MANAGER, first_name="Marta")
        client.force_login(eva)

        answer = detail(client, "hub_employee").json()

        assert (answer["key"], answer["origin"], answer["members"]) == ("hub_employee", "basic", 2)

    def test_a_role_that_is_not_one_of_the_five_is_not_found(self, client, eva):
        client.force_login(eva)

        response = detail(client, "hub_cashier")

        assert response.status_code == 404
        assert json.loads(response.content)["error"]["code"] == "base.role_not_found"

    def test_the_refusal_is_said_in_spanish(self):
        with pytest.raises(OperationError) as refused:
            read("hub_cashier", language="es")
        assert refused.value.code == "base.role_not_found"
        assert str(refused.value.message) == "Este rol no existe en este negocio."


def listed(client, host=HOST) -> list[dict]:
    return client.get("/api/roles", HTTP_HOST=host).json()["roles"]


class TestTheRolesOfTheBusiness:
    """A role the business made (BASE-F127): listed after the basic ones, with what was saved in it."""

    def test_it_is_listed_after_the_basic_ones_by_its_name(self, client, eva):
        late, early = a_role("waiter"), a_role("Cashier", base__view_home=ON)
        client.force_login(eva)

        rows = listed(client)

        assert [row["origin"] for row in rows] == ["basic"] * 5 + ["own"] * 2
        assert [(row["key"], row["label"]) for row in rows[5:]] == [
            (str(early.pk), "Cashier"), (str(late.pk), "waiter"),
        ]

    def test_which_apps_are_on_is_read_once_whatever_the_roles(self, client, eva, monkeypatch):
        for number in range(3):
            a_role(f"Role {number}")
        client.force_login(eva)
        read = []
        real = queries.roles.active_apps
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: read.append(scope) or real(scope))

        assert len(listed(client)) == 8
        assert read == [A]

    def test_it_says_how_many_permissions_it_gives(self, client, eva):
        saved = {permission: OFF for permission in permissions_of_role(Membership.Role.OWNER) - OWNER_ONLY}
        saved |= {"sale.view_sale": ON, "sale.void_sale": APPROVAL}
        BusinessRole.objects.create(name="Cashier", origin=Membership.Role.ADMIN, states=saved)
        client.force_login(eva)

        assert listed(client)[-1]["permissions"] == 1

    def test_whoever_holds_it_counts_in_it_and_not_in_the_role_of_their_invitation(self, client, eva, make_user):
        role = a_role()
        held_by(eva, role)
        make_user("saas:7", host=A.key, role=Membership.Role.EMPLOYEE)
        client.force_login(eva)

        members = {row["label"]: row["members"] for row in listed(client)}

        assert (members["Cashier"], members["Employee"]) == (1, 1)
        assert detail(client, str(role.pk)).json()["members"] == 1
        assert detail(client, "hub_employee").json()["members"] == 1

    def test_the_owner_counts_as_the_owner_whatever_role_their_row_names(self, client, make_user):
        role = a_role()
        olga = make_user("saas:1", host=A.key, role=Membership.Role.OWNER)
        held_by(olga, role)
        client.force_login(olga)

        members = {row["label"]: row["members"] for row in listed(client)}

        assert (members["Owner"], members["Cashier"]) == (1, 0)

    def test_whoever_left_the_business_does_not_count(self, client, eva, make_user):
        role = a_role()
        gone = make_user("saas:7", host=A.key, role=Membership.Role.EMPLOYEE)
        held_by(gone, role)
        Membership.objects.filter(user=gone).delete()
        client.force_login(eva)

        assert listed(client)[-1]["members"] == 0

    def test_it_is_to_review_while_an_app_that_is_on_has_something_it_was_not_saved_with(self, client, eva, monkeypatch):
        a_role("Cashier", sale__view_sale=ON)
        saved = {permission: ON for permission in permissions_of_role(Membership.Role.ADMIN)}
        BusinessRole.objects.create(name="Manager two", origin=Membership.Role.MANAGER, states=saved)
        client.force_login(eva)
        assert {row["label"]: row["to_review"] for row in listed(client)[5:]} == {"Cashier": True, "Manager two": False}
        assert not any(row["to_review"] for row in listed(client)[:5])

        # Only the apps that are on are left to review.
        del saved["inventory.view_product"]
        BusinessRole.objects.filter(name="Manager two").update(states=saved)
        assert listed(client)[-1]["to_review"] is True
        monkeypatch.setattr("base.queries.roles.active_apps", lambda scope: frozenset({"base", "sale"}))
        assert listed(client)[-1]["to_review"] is False

    def test_what_it_allows_is_what_was_saved_in_it(self, client, eva):
        role = a_role(sale__view_sale=OFF, sale__void_sale=ON, sale__take_payment=ON)
        BusinessRole.objects.filter(pk=role.pk).update(description="The till")
        client.force_login(eva)

        answer = detail(client, str(role.pk)).json()

        assert (answer["key"], answer["label"], answer["description"], answer["origin"], answer["to_review"]) == (
            str(role.pk), "Cashier", "The till", "own", True,
        )
        sale = {line["permission"]: line["state"] for line in group(answer, "sale")["permissions"]}
        assert (sale["sale.view_sale"], sale["sale.void_sale"], sale["sale.take_payment"]) == ("off", "on", "on")
        # An app's permission it was not saved with is off.
        assert sale["sale.view_all_sales"] == "off"

    def test_an_app_it_was_not_saved_with_allows_what_it_allows_the_role_it_came_from(self, client, eva):
        role = a_role(base__view_home=ON)
        client.force_login(eva)

        own, basic = detail(client, str(role.pk)).json(), detail(client, "hub_employee").json()

        assert group(own, "sale") == group(basic, "sale")

    def test_owning_the_business_is_not_among_what_it_may_allow(self, client, eva):
        role = a_role(origin=Membership.Role.ADMIN)
        client.force_login(eva)

        answer = detail(client, str(role.pk)).json()

        assert not OWNER_ONLY & {line["permission"] for app in answer["apps"] for line in app["permissions"]}
        assert "base.manage_roles" in {line["permission"] for line in group(answer, "base")["permissions"]}

    def test_the_sensitive_data_come_last_as_in_a_basic_role(self, client, eva):
        role = a_role(base__view_home=ON, base__view_costs=ON)
        client.force_login(eva)

        answer = detail(client, str(role.pk)).json()

        assert answer["apps"][-1]["app"] == "sensitive"
        assert {line["permission"] for line in group(answer, "sensitive")["permissions"]} == set(DATA_PERMISSIONS)
        assert "base.view_costs" not in {line["permission"] for line in group(answer, "base")["permissions"]}

    @pytest.mark.parametrize("key", ["0199aaaa-0000-7000-8000-000000000001", "", "not-a-role"])
    def test_one_that_is_not_there_is_not_found(self, client, eva, key):
        client.force_login(eva)

        assert json.loads(detail(client, key).content)["error"]["code"] == "base.role_not_found"


class TestHowItIsReached:
    def test_its_route_is_the_one_the_spa_calls(self):
        from base.api.people import router

        route = ("GET", "/roles/detail", "base.role.detail")
        assert route in bound_routes(router)
        assert route in spa_routes("base.")

    def test_it_follows_the_photo_the_apps_turned_on_or_off_and_the_roles_of_the_business(self):
        from live.live_registry import live_registry

        followed = sorted({events.HUB_STATE_APPLIED, *events.APP_EVENTS, *events.ROLE_EVENTS})
        assert live_registry.subscribable["base.role.detail"] == followed
        # The list says which are left to review, which an app turned on changes.
        assert live_registry.subscribable["base.role.list"] == followed

    def test_anyone_of_the_business_reads_it_and_the_assistant_knows_it(self):
        op = get_operation("base.role.detail")

        assert op.permission == "base.view_home"
        assert description(op)
