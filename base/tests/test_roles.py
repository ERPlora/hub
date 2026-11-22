"""«What it allows» of a basic role (``base.role.detail``, BASE-F82): app by app, each permission with its phrase in the
reader's language and what the role does with it: ``yes``, ``approval`` (a manager approves it there and then) or
``no``."""

import json

import pytest
from live.assistant import description
from live.context import OperationContext
from live.errors import OperationError
from live.operations import get as get_operation

from base import events
from base.models import Membership
from base.permissions import OWNER_ONLY, permissions_of_role
from base.sensitive import DATA_PERMISSIONS
from base.tenancy.tests.business import A, HOST, HUB_DB, in_business_a
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

    def test_what_the_role_holds_is_yes_and_what_nobody_approves_for_it_is_no(self):
        employee = states(read("hub_employee"))

        assert employee["sale.take_payment"] == "yes"
        assert employee["sale.view_all_sales"] == "no"
        assert employee["base.view_customer_contact"] == "yes"
        assert employee["base.view_costs"] == "no"

    def test_the_states_follow_what_each_role_is_given(self):
        for role in Membership.Role.values:
            given = permissions_of_role(role)
            for permission, state in states(read(role)).items():
                assert (state == "yes") == (permission in given), (role, permission, state)

    def test_the_owner_holds_everything_and_the_administrator_all_but_owning_the_business(self):
        owner = states(read("hub_owner"))
        admin = states(read("hub_admin"))

        assert set(owner.values()) == {"yes"}
        assert {permission for permission, state in admin.items() if state != "yes"} == set(OWNER_ONLY)

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


class TestHowItIsReached:
    def test_its_route_is_the_one_the_spa_calls(self):
        from base.api.people import router

        route = ("GET", "/roles/detail", "base.role.detail")
        assert route in bound_routes(router)
        assert route in spa_routes("base.")

    def test_it_follows_the_photo_and_the_apps_turned_on_or_off(self):
        from live.live_registry import live_registry

        assert live_registry.subscribable["base.role.detail"] == sorted({events.HUB_STATE_APPLIED, *events.APP_EVENTS})

    def test_anyone_of_the_business_reads_it_and_the_assistant_knows_it(self):
        op = get_operation("base.role.detail")

        assert op.permission == "base.view_home"
        assert description(op)
