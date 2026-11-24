"""The assistant's cards of the roles a business makes (BASE-F127 to BASE-F129): a role by its name, each permission in
the words of «What it allows» with what it becomes, and how many people have the role. Never a key, a permission's name
nor a state as it is kept."""

import pytest
from live.context import OperationContext
from live.operations import get

from base import assistant
from base.models import HubUser, Membership
from base.permissions import access_for
from base.roles import OFF, ON
from base.tenancy.tests.business import A, HUB_DB, in_business_a
from base.tests import card_turn
from base.tests.roles import a_role, held_by

__all__ = ["in_business_a"]

pytestmark = HUB_DB

LANGUAGES = pytest.mark.parametrize("language", ["en", "es"])


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")


@pytest.fixture
def cashier(make_user):
    role = a_role(sale__view_sale=ON, sale__void_sale=ON)
    for username in ("saas:3", "saas:4"):
        held_by(make_user(username, host=A.key, role=Membership.Role.EMPLOYEE), role)
    return role


def asking(user, language: str) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=access_for(user, A), language=language)


def turn(user, language: str, name: str, arguments: dict) -> dict:
    return card_turn.turn(asking(user, language), card_turn.call(name, arguments), said="the roles")


def lines(fields: list[dict]) -> list[tuple]:
    return [(field["label"], field["value"]) for field in fields]


@LANGUAGES
def test_creating_one_says_the_role_it_comes_from_by_its_name(olga, language):
    card = turn(olga, language, "base.role.create", {"based_on": "hub_employee", "name": "Cashier"})["confirm"]

    assert lines(card["fields"]) == {
        "en": [("Based on", "Employee"), ("Name", "Cashier")],
        "es": [("A partir de", "Empleado"), ("Nombre", "Cashier")],
    }[language]
    assert card["risk"] == "normal"


@LANGUAGES
def test_creating_one_from_another_of_the_business_says_its_name(olga, cashier, language):
    card = turn(olga, language, "base.role.create", {"based_on": str(cashier.pk), "name": "Evening"})["confirm"]

    assert [value for _, value in lines(card["fields"])] == ["Cashier", "Evening"]


@LANGUAGES
def test_changing_one_says_each_permission_in_words_and_what_it_becomes(olga, cashier, language):
    states = {"sale.void_sale": "approval", "base.view_costs": "on", "sale.take_payment": "off"}

    card = turn(olga, language, "base.role.update", {"role": str(cashier.pk), "states": states})["confirm"]

    assert lines(card["fields"]) == {
        "en": [
            ("Role", "Cashier"), ("Void a sale", "With approval"), ("View costs", "Allowed"),
            ("Take payments", "No"),
        ],
        "es": [
            ("Rol", "Cashier"), ("Anular una venta", "Con aprobación"), ("Ver costes", "Permitido"),
            ("Cobrar", "No"),
        ],
    }[language]
    assert lines(card["preview"]) == {
        "en": [("People with this role", 2)], "es": [("Personas con este rol", 2)],
    }[language]
    assert card["risk"] == "high"


@LANGUAGES
def test_renaming_one_says_its_name_of_now_and_the_new_one(olga, cashier, language):
    card = turn(olga, language, "base.role.update", {"role": str(cashier.pk), "name": "Till"})["confirm"]

    assert [value for _, value in lines(card["fields"])] == ["Cashier", "Till"]


def test_a_permission_no_app_declares_is_not_said_as_it_was_sent(olga, cashier):
    fields = assistant.cards.card(
        get("base.role.update"),
        {"role": str(cashier.pk), "states": {"sale.fly": "on", "sale.void_sale": "maybe"}},
        "en",
        asking(olga, "en"),
    )["fields"]

    assert lines(fields) == [("Role", "Cashier")]


@LANGUAGES
def test_deleting_one_says_its_name_and_how_many_have_it(olga, cashier, language):
    card = turn(olga, language, "base.role.delete", {"role": str(cashier.pk)})["confirm"]

    assert [value for _, value in lines(card["fields"])] == ["Cashier"]
    assert [value for _, value in lines(card["preview"])] == [2]
    assert card["risk"] == "high"


def test_the_yes_changes_the_role(olga, cashier):
    drawn = turn(olga, "es", "base.role.update", {"role": str(cashier.pk), "states": {"sale.void_sale": "off"}})

    plan = card_turn.turn(
        asking(olga, "es"), drawn["pending"][0], said="the roles",
        decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"},
    )

    assert [row["outcome"] for row in plan["executed"]] == ["ok"]
    cashier.refresh_from_db()
    assert cashier.states == {"sale.view_sale": ON, "sale.void_sale": OFF}


@pytest.mark.parametrize("name", ["base.role.create", "base.role.update", "base.role.delete", "base.role.assign"])
@pytest.mark.parametrize("role", list(Membership.Role))
def test_the_assistant_offers_them_to_who_manages_roles(make_user, name, role):
    tools = assistant.tools.catalog(asking(make_user("saas:9", host=A.key, role=role), "es"))

    assert (name in tools) == (role in {Membership.Role.OWNER, Membership.Role.ADMIN})


@pytest.fixture
def luis(make_user):
    return make_user("saas:6", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Luis")


@LANGUAGES
def test_giving_one_says_the_person_and_the_role_by_their_names(olga, cashier, luis, language):
    card = turn(olga, language, "base.role.assign", {"person": "saas:6", "role": str(cashier.pk)})["confirm"]

    assert lines(card["fields"]) == {
        "en": [("Person", "Luis"), ("Role", "Cashier")], "es": [("Persona", "Luis"), ("Rol", "Cashier")],
    }[language]
    assert lines(card["preview"]) == {
        "en": [("People with this role", 2)], "es": [("Personas con este rol", 2)],
    }[language]
    assert card["risk"] == "high"


@LANGUAGES
def test_returning_somebody_to_their_invitation_says_its_role_in_words(olga, cashier, luis, language):
    card = turn(olga, language, "base.role.assign", {"person": "saas:6", "role": "hub_employee"})["confirm"]

    assert [value for _, value in lines(card["fields"])] == ["Luis", {"en": "Employee", "es": "Empleado"}[language]]


def test_whoever_manages_roles_and_does_not_run_the_business_sees_the_person_by_name_too(make_user, cashier, luis):
    mara = make_user("saas:5", host=A.key, role=Membership.Role.MANAGER)
    held_by(mara, a_role("People", base__view_home=ON, base__manage_roles=ON))

    card = turn(mara, "en", "base.role.assign", {"person": "saas:6", "role": str(cashier.pk)})["confirm"]

    assert lines(card["fields"]) == [("Person", "Luis"), ("Role", "Cashier")]


def test_somebody_who_is_not_of_the_business_is_not_said_by_their_id(olga, cashier):
    fields = assistant.cards.card(
        get("base.role.assign"), {"person": "saas:99", "role": str(cashier.pk)}, "en", asking(olga, "en")
    )["fields"]

    assert lines(fields) == [("Role", "Cashier")]


def test_the_yes_gives_the_role(olga, cashier, luis):
    drawn = turn(olga, "es", "base.role.assign", {"person": "saas:6", "role": str(cashier.pk)})

    plan = card_turn.turn(
        asking(olga, "es"), drawn["pending"][0], said="the roles",
        decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"},
    )

    assert [row["outcome"] for row in plan["executed"]] == ["ok"]
    assert HubUser.objects.get(username="saas:6").business_role == cashier
