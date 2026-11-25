"""What a role of the business says of a command a manager may approve (BASE-F84): it does it, it does it with approval or
it does not.

With approval, whoever lacks the permission is asked for a manager's, as in a basic role. With a no there is no question:
the command's own refusal, whatever pass comes with it, and no pass is handed out for it. The role is read on every
request, so a change counts from the next one on. The owner is never asked.
"""

import pytest

from base.models import Membership
from base.models.access import AccessSettings
from base.models.approvals import Approval
from base.models.roles import BusinessRole
from base.permissions import ADMINISTER_HUB, permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests.roles import a_role, held_by
from base.tests.test_approvals import (
    APPROVABLE,
    B_HOST,
    CHANGE,
    SETTINGS,
    adam,
    approvable,
    approve,
    code,
    eva,
    get,
    granted,
    mario,
    post,
    refused,
    with_pass,
)

__all__ = ["adam", "approvable", "eva", "in_business_a", "mario"]

pytestmark = HUB_DB

EMPLOYEE = Membership.Role.EMPLOYEE


def given(user, state: str | None, origin=EMPLOYEE) -> BusinessRole:
    """A role of the business held by ``user``: what ``origin`` gives in base, with ``state`` for the approvable command
    (``None``: saved before base had that permission)."""
    states = {p.replace(".", "__"): ON for p in permissions_of_role(origin) if p.startswith("base.")}
    states.pop(ADMINISTER_HUB.replace(".", "__"), None)
    if state is not None:
        states[ADMINISTER_HUB.replace(".", "__")] = state
    role = a_role("Till", origin=origin, **states)
    held_by(user, role)
    return role


def change(role: BusinessRole, state: str) -> None:
    role.states = {**role.states, ADMINISTER_HUB: state}
    role.save()


def changed() -> bool:
    return AccessSettings.objects.filter(pin_policy="always").exists()


class TestTheDoor:
    @pytest.mark.parametrize(
        ("state", "status", "why"),
        [(ON, 200, None), (APPROVAL, 403, "requires_elevation"), (OFF, 403, "permission_denied")],
    )
    def test_does_what_the_role_says(self, client, adam, eva, state, status, why):
        given(eva, state)

        response = post(client, SETTINGS, CHANGE)

        assert response.status_code == status, response.content
        assert changed() is (state == ON)
        if why is not None:
            assert code(response) == why

    def test_a_no_tells_nothing_of_an_approval(self, client, adam, eva):
        given(eva, OFF)

        assert "approval" not in post(client, SETTINGS, CHANGE).json()["error"]

    def test_a_basic_role_never_says_no(self, client, adam, eva):
        refused(client)

    def test_an_app_the_role_was_not_saved_with_asks_as_the_role_it_came_from(self, client, adam, eva):
        held_by(eva, a_role("Till", sale__view_sale=ON))

        refused(client)

    def test_a_permission_an_app_added_after_it_was_saved_is_a_no(self, client, adam, eva):
        given(eva, None)

        assert code(post(client, SETTINGS, CHANGE)) == "permission_denied"

    def test_the_owner_is_never_asked_whatever_role_their_row_names(self, client, adam, make_user):
        olga = make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")
        given(olga, OFF)
        client.force_login(olga)

        assert post(client, SETTINGS, CHANGE).status_code == 200

    def test_whoever_left_the_business_is_refused_as_ever(self, client, adam, eva):
        given(eva, APPROVAL)
        Membership.objects.filter(user=eva).delete()

        assert code(post(client, SETTINGS, CHANGE)) == "permission_denied"

    def test_the_role_of_one_business_says_nothing_in_another(self, client, adam, eva, hub_b):
        Membership.objects.create(user=eva, host=B.key, role=EMPLOYEE)
        given(eva, OFF)

        assert code(post(client, SETTINGS, CHANGE)) == "permission_denied"
        refused(client, host=B_HOST)
        with use_hub(hub_b):
            given(eva, OFF)
        assert code(post(client, SETTINGS, CHANGE, host=B_HOST)) == "permission_denied"


class TestItFollowsTheRole:
    def test_from_one_request_to_the_next(self, client, adam, eva):
        role = given(eva, APPROVAL)
        refused(client)

        change(role, OFF)
        assert code(post(client, SETTINGS, CHANGE)) == "permission_denied"
        change(role, APPROVAL)
        refused(client)
        change(role, ON)
        assert post(client, SETTINGS, CHANGE).status_code == 200

    def test_a_pass_given_before_the_no_lets_nothing_through_and_is_not_spent(self, client, adam, eva):
        role = given(eva, APPROVAL)
        token = granted(client)

        change(role, OFF)

        assert code(post(client, SETTINGS, CHANGE, **with_pass(token))) == "permission_denied"
        assert not changed()
        assert Approval.objects.get().used_at is None

    def test_that_pass_goes_through_if_the_role_allows_it_again_in_time(self, client, adam, eva):
        role = given(eva, APPROVAL)
        token = granted(client)
        change(role, OFF)
        post(client, SETTINGS, CHANGE, **with_pass(token))

        change(role, APPROVAL)

        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200
        assert Approval.objects.get().used_at is not None


class TestThePass:
    def test_is_not_handed_out_to_whoever_the_role_says_no(self, client, adam, eva):
        role = given(eva, APPROVAL)
        asked = refused(client)
        change(role, OFF)

        response = approve(client, asked, "saas:2")

        assert (response.status_code, code(response)) == (409, "base.approval_not_offered")
        assert not Approval.objects.exists()

    def test_is_handed_out_to_whoever_the_role_lets_do_it_with_approval(self, client, adam, eva):
        given(eva, APPROVAL)

        token = granted(client)

        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200


class TestWhoApproves:
    @pytest.mark.parametrize("state", [APPROVAL, OFF])
    def test_is_not_whoever_needs_an_approval_for_it(self, client, adam, eva, mario, state):
        given(mario, state, origin=Membership.Role.MANAGER)

        response = approve(client, refused(client), "saas:4", pin="1357")

        assert (response.status_code, code(response)) == (403, "base.approver_cannot")
        people = get(client, "/approvals/approvers", operation=APPROVABLE).json()["people"]
        assert [person["name"] for person in people] == ["Adam"]

    def test_is_whoever_does_it_by_a_role_of_the_business(self, client, adam, eva, mario):
        given(eva, APPROVAL)
        lead = a_role("Lead", origin=Membership.Role.MANAGER, base__view_home=ON, base__administer_hub=ON)
        held_by(mario, lead)

        response = approve(client, refused(client), "saas:4", pin="1357")

        assert response.status_code == 200, response.content
        assert post(client, SETTINGS, CHANGE, **with_pass(response.json()["token"])).status_code == 200


@pytest.mark.parametrize("state", [ON, APPROVAL, OFF, None])
def test_the_session_says_what_the_door_does(client, adam, eva, state):
    given(eva, state)

    me = get(client, "/me").json()
    answer = post(client, SETTINGS, CHANGE)

    assert (ADMINISTER_HUB in me["permissions"]) is (answer.status_code == 200)
    asks = answer.status_code == 403 and code(answer) == "requires_elevation"
    assert (ADMINISTER_HUB in me["approvable"]) is asks


def test_the_permission_of_the_command_is_the_one_the_role_is_asked_about(client, adam, eva):
    """Another permission of the role at «no» does not close a command of this one."""
    role = given(eva, APPROVAL)
    role.states = {**role.states, "base.view_costs": OFF, "sale.void_sale": OFF}
    role.save()

    refused(client)
