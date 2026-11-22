"""``base.access.grantors``: who can give a person a screen it may not open, by name and nothing else.

Roles are changed on erplora.com by someone who outranks the person and may give a role above theirs: an employee
asks the owner or an administrator, a manager only the owner. The screen «No access» names them; never their email.
"""

import pytest
from live.context import OperationContext
from live.live_registry import live_registry
from live.operations import get as get_operation

from base import events
from base.models import Membership
from base.permissions import VIEW_HOME, permissions_for
from base.tenancy.tests.business import A, B, HOST, HUB_DB, in_business_a
from base.tests.test_people import photo

__all__ = ["in_business_a"]

pytestmark = HUB_DB


@pytest.fixture
def people(make_user):
    return {
        "olga": make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga", email="olga@example.com"),
        "adam": make_user("saas:2", host=A.key, role=Membership.Role.ADMIN, first_name="Adam", email="adam@example.com"),
        "mario": make_user("saas:3", host=A.key, role=Membership.Role.MANAGER, first_name="Mario"),
        "eva": make_user("saas:4", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva"),
        "bea": make_user("saas:9", host=B.key, role=Membership.Role.ADMIN, first_name="Bea"),
    }


def grantors(user) -> list[dict]:
    ctx = OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="en")
    answer = get_operation("base.access.grantors")(ctx, get_operation("base.access.grantors").input())
    return answer.model_dump(mode="json")["grantors"]


def test_an_employee_asks_the_owner_or_an_administrator_by_name_only(people):
    assert grantors(people["eva"]) == [{"name": "Olga"}, {"name": "Adam"}]


def test_a_manager_asks_only_the_owner_who_alone_gives_a_role_above_it(people):
    assert grantors(people["mario"]) == [{"name": "Olga"}]


def test_an_administrator_invited_on_erplora_com_who_has_not_entered_yet_is_named_too(people):
    photo(members=[
        {"user_id": "1", "role": "hub_owner", "email": "olga@example.com", "name": "Olga"},
        {"user_id": "0199aaaa-0000-7000-8000-000000000002", "role": "hub_admin", "email": "ines@example.com", "name": "Inés"},
    ])
    assert grantors(people["eva"]) == [{"name": "Olga"}, {"name": "Adam"}, {"name": "Inés"}]


def test_it_follows_the_people_and_their_names_live_and_every_person_of_the_business_may_ask(people):
    assert live_registry.subscribable["base.access.grantors"] == sorted({events.HUB_STATE_APPLIED, events.PROFILE_UPDATED})
    assert get_operation("base.access.grantors").permission == VIEW_HOME
    assert VIEW_HOME in permissions_for(people["eva"], A)


def test_by_its_route_an_employee_reads_the_names_and_nobody_without_a_session_does(client, people):
    client.force_login(people["eva"])
    response = client.get("/api/access/grantors", HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    assert response.json() == {"grantors": [{"name": "Olga"}, {"name": "Adam"}]}
    client.logout()
    assert client.get("/api/access/grantors", HTTP_HOST=HOST).status_code in (401, 403)


def test_an_account_named_by_its_email_is_named_by_the_part_before_the_at_never_its_address(people, make_user):
    make_user("saas:5", host=A.key, role=Membership.Role.ADMIN, first_name="ines@example.com")
    assert grantors(people["eva"]) == [{"name": "Olga"}, {"name": "Adam"}, {"name": "ines"}]
