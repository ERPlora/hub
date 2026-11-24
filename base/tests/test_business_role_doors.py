"""A role of the business reaches every door that reads what a person may do, as the role of the invitation does: a
request to the business's API, a live query re-run, who may approve a refused action with their PIN and the ceiling of
an API key its holder made."""

from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.operations import HubContextBuilder
from base.permissions import ADMINISTER_HUB, permissions_of_role
from base.roles import ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, in_business_a
from base.tests.test_api_key_owner import CONFIG, MAKER, made
from base.tests.test_api_keys import code as key_code, get as key_get, host as key_host
from base.tests.test_approvals import (
    APPROVABLE,
    adam,
    approvable,
    approve,
    eva,
    get,
    mario,
    refused,
)
from base.tests.test_operations import request_for

__all__ = ["adam", "approvable", "eva", "in_business_a", "made", "mario"]

pytestmark = HUB_DB


def given(username: str, origin: str, **states: str) -> BusinessRole:
    """A role of the business duplicated from ``origin``, saved with what that role gives in base plus ``states``
    (permission names with ``__`` for ``.``), held by ``username``."""
    saved = {permission: ON for permission in permissions_of_role(origin) if permission.startswith("base.")}
    saved |= {name.replace("__", "."): state for name, state in states.items()}
    role = BusinessRole.objects.create(name=f"Role of {username}", origin=origin, states=saved)
    HubUser.objects.update_or_create(username=username, defaults={"business_role": role})
    return role


class TestARequest:
    def test_opens_what_the_role_of_the_business_allows_beyond_the_invitation(self, client, adam, eva):
        assert get(client, "/approvals").status_code == 403

        given("saas:3", Membership.Role.EMPLOYEE, base__administer_hub=ON)

        assert get(client, "/approvals").status_code == 200

    def test_closes_what_the_invitation_allows_and_the_role_of_the_business_does_not(self, client, adam):
        client.force_login(adam)
        assert get(client, "/approvals").status_code == 200

        given("saas:2", Membership.Role.EMPLOYEE)

        assert get(client, "/approvals").status_code == 403


def test_a_live_query_re_run_reads_a_role_given_after_it_began(eva):
    builder = HubContextBuilder()
    ctx = builder.from_request(request_for(HOST, eva))
    assert not ctx.has(ADMINISTER_HUB)

    given("saas:3", Membership.Role.EMPLOYEE, base__administer_hub=ON)

    assert builder.refresh(ctx).has(ADMINISTER_HUB)


class TestWhoApproves:
    def test_is_offered_when_a_role_of_the_business_gives_the_permission(self, client, adam, eva, mario):
        given("saas:4", Membership.Role.MANAGER, base__administer_hub=ON)

        response = get(client, "/approvals/approvers", operation=APPROVABLE)

        assert response.status_code == 200, response.content
        assert sorted(person["name"] for person in response.json()["people"]) == ["Adam", "Mario"]

    def test_approves_with_their_pin_when_a_role_of_the_business_gives_the_permission(self, client, adam, eva, mario):
        given("saas:4", Membership.Role.MANAGER, base__administer_hub=ON)

        response = approve(client, refused(client), "saas:4", pin="1357")

        assert response.status_code == 200, response.content
        assert response.json()["approver"] == "Mario"


def test_an_api_key_holds_no_more_than_the_role_of_the_business_of_its_maker(made, client, hub_a):
    assert key_get(client, key_host(hub_a), CONFIG, **made).status_code == 200

    with use_hub(hub_a):
        given(MAKER, Membership.Role.EMPLOYEE)

    refused_by_the_ceiling = key_get(client, key_host(hub_a), CONFIG, **made)
    assert (refused_by_the_ceiling.status_code, key_code(refused_by_the_ceiling)) == (403, "permission_denied")

