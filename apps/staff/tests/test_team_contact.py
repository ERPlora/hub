"""A colleague's email and phone reach only whoever sees the team's contact details (``base.view_team_contact``): the
owner, an administrator and a manager; an employee gets the team without them, on every door (the API, the assistant),
and cannot find, filter or sort the team by them. Their own record keeps their own contact details."""

import json

import pytest
from live.assistant.running import run_tool
from live.operations import get as operation

from apps.flow.tests.test_api import get
from apps.staff.schemas.members import CompensationListIn
from base.sensitive import VIEW_TEAM_CONTACT

from .conftest import HUB_DB, A, ctx_for, make_member

pytestmark = HUB_DB

ANA = {"email": "ana@salon.example", "phone": "+34 600 111 222"}


@pytest.fixture
def ana(db):
    return make_member("Ana", "López", **ANA)


@pytest.fixture
def as_role(client, make_user):
    def sign_in(role: str):
        user = make_user(role, host=A.key, role=role)
        client.force_login(user)
        return user

    return sign_in


def contact(rows: list[dict]) -> list[tuple]:
    return [(row["full_name"], row["email"], row["phone"]) for row in rows]


@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager"])
def test_who_runs_the_business_gets_the_team_with_its_email_and_phone(ana, as_role, client, role):
    as_role(role)
    assert contact(get(client, "/staff/members").json()["rows"]) == [("Ana López", *ANA.values())]
    assert contact([get(client, "/staff/members/detail", id=str(ana.id)).json()]) == [("Ana López", *ANA.values())]


def test_an_employee_gets_the_team_without_its_email_or_phone(ana, as_role, client):
    as_role("hub_employee")
    assert contact(get(client, "/staff/members").json()["rows"]) == [("Ana López", None, None)]
    assert contact([get(client, "/staff/members/detail", id=str(ana.id)).json()]) == [("Ana López", None, None)]


def test_an_employee_keeps_their_own_email_and_phone_in_my_record(as_role, client):
    me = as_role("hub_employee")
    make_member("Eva", "Ruiz", user=me.person, email="eva@salon.example", phone="+34 600 333 444")
    mine = get(client, "/staff/members/mine").json()["member"]
    assert (mine["email"], mine["phone"]) == ("eva@salon.example", "+34 600 333 444")


def test_the_assistant_tool_gives_an_employee_the_team_without_its_contact_and_a_manager_with_it(ana):
    def rows(role: str) -> list[dict]:
        outcome = run_tool(ctx_for(role), operation("staff.member.list"), "{}")
        assert outcome.outcome == "ok", outcome.content
        return json.loads(outcome.content)["rows"]

    assert contact(rows("hub_employee")) == [("Ana López", None, None)]
    assert contact(rows("hub_manager")) == [("Ana López", *ANA.values())]


@pytest.mark.parametrize("text", ["600 111", "salon.example"])
def test_an_employee_s_search_does_not_look_into_the_team_s_contact(ana, as_role, client, text):
    as_role("hub_manager")
    assert get(client, "/staff/members", search=text).json()["total"] == 1
    as_role("hub_employee")
    assert get(client, "/staff/members", search=text).json()["total"] == 0
    assert get(client, "/staff/members", search="Ana").json()["total"] == 1


def test_the_pay_sheet_s_search_looks_into_the_contact_only_for_whoever_sees_it(ana):
    def found(permissions: set[str]) -> int:
        params = CompensationListIn(search="600 111")
        return operation("staff.member.compensation")(ctx_for(permissions=permissions), params).total

    pay = {"staff.view", "staff.view_compensation"}
    assert (found(pay), found(pay | {VIEW_TEAM_CONTACT})) == (0, 1)


@pytest.mark.parametrize("field", ["email", "phone"])
def test_filtering_the_team_by_its_contact_is_refused_to_an_employee(ana, as_role, client, field):
    as_role("hub_manager")
    assert get(client, "/staff/members", **{field: ANA[field][:6]}).json()["total"] == 1
    as_role("hub_employee")
    refused = get(client, "/staff/members", **{field: ANA[field][:6]})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("sort", ["email", "-email", "phone", "-phone"])
def test_the_team_is_not_sorted_by_its_contact(ana, as_role, client, sort):
    as_role("hub_manager")
    assert get(client, "/staff/members", sort=sort).status_code == 422


def test_an_employee_still_sorts_the_team_by_the_other_columns(ana, as_role, client):
    make_member("Bea", "Soto")
    as_role("hub_employee")
    answer = get(client, "/staff/members", sort="-name")
    assert answer.status_code == 200
    assert [row["full_name"] for row in answer.json()["rows"]] == ["Bea Soto", "Ana López"]
