"""What a role of the business says of a write a manager may approve, to the assistant (BASE-F100): it runs it, it asks for
the approval as the screen does, or the tool is not theirs: not offered, not found and not run, whatever pass comes with
its yes."""

import dataclasses

import pytest
from live.context import OperationContext
from live.operations import get

from base import activation, assistant
from base.models import Membership
from base.models.approvals import Approval
from base.models.access import Credential
from base.models.roles import BusinessRole
from base.permissions import access_for
from base.roles import APPROVAL, OFF, ON
from base.services.assistant import _assistant_approved
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests.fake_gateway import gateway, signed
from base.tests.roles import a_role, held_by
from base.tests.test_api_assistant import (
    _answering_its_card,
    _create_turn,
    _instructions_sent,
    _items,
    approvable_create,
    frames,
    post,
)
from base.tests.test_people import with_pin

__all__ = ["approvable_create", "gateway", "in_business_a", "signed"]

pytestmark = HUB_DB

ADD_LINE = "demo.item.add_line"
MANAGE = "demo.manage"


@pytest.fixture
def eva(make_user, client):
    """An employee at the device, with a manager in the business who may approve."""
    make_user("saas:4", host=A.key, role=Membership.Role.MANAGER, first_name="Mario")
    with_pin("saas:4", "1357")
    user = make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva")
    client.force_login(user)
    return user


def given(user, state: str | None) -> BusinessRole:
    """A role held by ``user`` that sees the items, with ``state`` for what the write asks (``None``: not saved)."""
    role = a_role("Counter", base__view_home=ON, demo__view=ON, **({} if state is None else {"demo__manage": state}))
    held_by(user, role)
    return role


def change(role: BusinessRole, state: str) -> None:
    role.states = {**role.states, MANAGE: state}
    role.save()


def asks(user, scope=A) -> OperationContext:
    return OperationContext(scope=scope, actor=user, permissions=access_for(user, scope), language="en")


def answered(client, gateway, body: dict, **headers) -> dict:
    """What the turn did with its one call, as the panel hears it first."""
    gateway.turn({"type": "text_delta", "text": "No."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    return frames(post(client, "/assistant/turn", body, **headers))[0]


def approved(client, body: dict) -> str:
    """The manager approves the very request of ``body``: the pass of one use."""
    question = post(client, "/assistant/turn", body).json()["error"]["approval"]
    asked = {"operation": question["operation"], "fingerprint": question["fingerprint"], "pin": "1357"}
    answer = post(client, "/approvals", {**asked, "person": str(Credential.objects.get(username="saas:4").pk)})
    assert answer.status_code == 200, answer.content
    return answer.json()["token"]


class TestTheTools:
    @pytest.mark.parametrize(("state", "offered"), [(ON, True), (APPROVAL, True), (OFF, False), (None, False)])
    def test_are_the_ones_the_role_lets_also_with_approval(self, eva, state, offered):
        given(eva, state)

        assert (ADD_LINE in assistant.tools.catalog(asks(eva))) is offered

    def test_of_an_app_the_role_was_not_saved_with_are_those_of_the_role_it_came_from(self, eva):
        held_by(eva, a_role("Counter", base__view_home=ON, sale__view_sale=ON))

        assert ADD_LINE in assistant.tools.catalog(asks(eva))

    def test_of_an_app_that_is_off_are_none_and_come_back_as_the_role_says(self, eva, monkeypatch):
        role = given(eva, APPROVAL)
        monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}))
        assert ADD_LINE not in assistant.tools.catalog(asks(eva))
        change(role, OFF)
        monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset())

        assert ADD_LINE not in assistant.tools.catalog(asks(eva))

    def test_of_the_owner_are_every_one_whatever_role_their_row_names(self, make_user):
        olga = make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")
        given(olga, OFF)

        assert ADD_LINE in assistant.tools.catalog(asks(olga))

    def test_a_no_to_one_permission_takes_no_other_tool_away(self, eva):
        given(eva, OFF)
        basic = {name for name in assistant.tools.catalog(asks(eva)) if name.startswith("sale.")}

        held_by(eva, a_role("Counter too", base__view_home=ON, demo__view=ON, demo__manage=APPROVAL))

        assert basic == {name for name in assistant.tools.catalog(asks(eva)) if name.startswith("sale.")}
        assert "sale.sale.void" in basic

    def test_the_search_of_the_rest_does_not_find_what_the_role_says_no_to(self, eva):
        find = get(assistant.relevance.FIND_TOOLS)
        role = given(eva, APPROVAL)

        def found() -> str:
            return find(asks(eva), find.input(query="add a line to an item")).model_dump_json()

        assert "demo__item__add_line" in found()
        change(role, OFF)
        assert "demo__item__add_line" not in found()

    def test_the_role_of_one_business_says_nothing_in_another(self, eva, hub_b):
        Membership.objects.create(user=eva, host=B.key, role=Membership.Role.EMPLOYEE)
        given(eva, OFF)

        assert ADD_LINE not in assistant.tools.catalog(asks(eva))
        with use_hub(hub_b):
            assert ADD_LINE in assistant.tools.catalog(asks(eva, B))


class TestWhatTheModelHears:
    ASK = {"role": "user", "content": "add a line of 2 coffees to the item Mesa 4"}

    @pytest.mark.parametrize(("state", "said"), [(ON, False), (APPROVAL, True), (OFF, False)])
    def test_of_an_approval_is_only_what_the_role_leaves_to_it(self, client, eva, gateway, state, said):
        given(eva, state)
        gateway.turn({"type": "response", "output": [], "usage": {}, "continuation": None})

        frames(post(client, "/assistant/turn", {"messages": [self.ASK]}, HTTP_ACCEPT_LANGUAGE="en"))

        asked = _instructions_sent(gateway).partition("This person needs a manager's approval to run ")[2]
        assert ("`demo__item__add_line`" in asked.partition(": before you call one")[0]) is said
        tools = [tool["name"] for tool in gateway.sent("/internal/assistant/chat/stream")[0].body["tools"]]
        assert ("demo__item__add_line" in tools) is (state != OFF)


class TestItsYes:
    def test_runs_what_the_role_allows_with_no_question(self, client, eva, gateway, approvable_create):
        given(eva, ON)

        got = answered(client, gateway, _answering_its_card(client, _create_turn()))

        assert (got["name"], got["outcome"]) == ("demo.item.create", "ok")
        assert _items() == 1

    def test_asks_for_the_approval_the_role_leaves_it_to(self, client, eva, gateway, approvable_create):
        given(eva, APPROVAL)
        body = _answering_its_card(client, _create_turn())

        response = post(client, "/assistant/turn", body)

        assert (response.status_code, response.json()["error"]["code"]) == (403, "requires_elevation")
        assert answered(client, gateway, body, HTTP_X_ELEVATION_TOKEN=approved(client, body))["outcome"] == "ok"
        assert _items() == 1

    @pytest.mark.parametrize(("state", "asked"), [(ON, False), (APPROVAL, True), (OFF, False), (None, False)])
    def test_is_put_to_a_manager_only_as_the_role_says(self, rf, eva, approvable_create, state, asked):
        """The yes of a tool the role says no to never carries a pass, were the model to reach it."""
        given(eva, state)
        ctx = dataclasses.replace(asks(eva), request=rf.post("/api/assistant/turn", HTTP_X_ELEVATION_TOKEN="elev_x"))

        run_as = _assistant_approved(ctx, get("demo.item.create"), '{"name": "Mesa 4"}')

        assert hasattr(ctx.request, "approved") is asked
        assert (run_as is not ctx) is asked

    def test_runs_nothing_the_role_says_no_to_and_asks_nobody(self, client, eva, gateway, approvable_create):
        given(eva, OFF)

        got = answered(client, gateway, _create_turn())

        assert (got["outcome"], got["code"]) == ("refused", "not_available")
        assert _items() == 0

    def test_for_a_card_drawn_before_the_no_runs_nothing_with_a_pass_or_without(
        self, client, eva, gateway, approvable_create
    ):
        role = given(eva, APPROVAL)
        body = _answering_its_card(client, _create_turn())
        token = approved(client, body)

        change(role, OFF)

        assert answered(client, gateway, body)["outcome"] == "refused"
        assert answered(client, gateway, body, HTTP_X_ELEVATION_TOKEN=token)["outcome"] == "refused"
        assert _items() == 0
        assert Approval.objects.get().used_at is None
