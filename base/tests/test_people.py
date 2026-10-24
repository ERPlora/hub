"""BASE-G138…G144, G10, G11 and G26: the people of the business and their roles, in Employees (APP-BASE-5).

Who is in the business, and with which role, is erplora.com's (HUBS-F24…F29: inviting, changing the role, removing,
the plan's places): the Hub lists them — those who already entered and those the SaaS's photo names that have not yet
— with how each one gets in (the account, and here a PIN and a badge), and lets whoever runs the business take away a
PIN or give and take away a badge. A person removed on erplora.com and invited again comes back with what the hub kept
of them. The roles are the four of erplora.com, with how many people and permissions each has.
"""

import json

import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import access, services
from base import people as people_rules
from base.permissions import permissions_for
from base.models import Credential, Hub, Membership
from base.tests.test_access_pin import a_device, door

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
B_HOST = "b.localhost:8000"


def get(client, path, host=HOST, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, body=None, host=HOST):
    return client.post(f"/api{path}", json.dumps(body or {}), content_type="application/json", HTTP_HOST=host)


def code(response) -> str:
    return response.json()["error"]["code"]


def with_pin(username: str, pin: str = "2580") -> Credential:
    credential, _ = Credential.objects.get_or_create(username=username)
    credential.pin_hash, credential.pin_set_at = make_password(pin, hasher="argon2"), timezone.now()
    credential.save()
    return credential


def with_badge(username: str, card: str) -> Credential:
    credential, _ = Credential.objects.get_or_create(username=username)
    credential.badge_digest = access.badge_digest(access.clean_badge(card), key=services.badge_key())
    credential.badge_set_at = timezone.now()
    credential.save()
    return credential


def photo(slug="a", *, members=(), max_users=None):
    """The SaaS's photo of ``slug``, as ``base.hub.state_apply`` keeps it."""
    state = {"version": 1, "members": list(members)}
    if max_users is not None:
        state["plan"] = {"max_users": max_users, "max_devices": 0}
    Hub.objects.filter(slug=slug).update(state=state, state_version=1)


@pytest.fixture(autouse=True)
def no_attempts_left_from_another_test():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Olga", email="olga@example.com")


@pytest.fixture
def adam(make_user):
    return make_user("saas:2", host="a", role=Membership.Role.ADMIN, first_name="Adam", email="adam@example.com")


@pytest.fixture
def eva(make_user):
    return make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva", email="eva@example.com")


@pytest.fixture
def mario(make_user):
    return make_user("saas:4", host="a", role=Membership.Role.MANAGER, first_name="Mario", email="mario@example.com")


def people(client, host=HOST) -> dict:
    response = get(client, "/people", host=host)
    assert response.status_code == 200, response.content
    return response.json()


def row(answer: dict, person: str) -> dict:
    return next(entry for entry in answer["people"] if entry["id"] == person)


class TestWhoIsInTheBusiness:
    """BASE-G11 (Employees › Personal) and BASE-G142 (how each person gets in)."""

    def test_every_person_of_this_business_once_from_the_top_role(self, client, olga, eva, mario, make_user):
        make_user("saas:9", host="b", role=Membership.Role.ADMIN, first_name="Bea")
        client.force_login(olga)
        answer = people(client)
        assert [entry["id"] for entry in answer["people"]] == ["saas:1", "saas:4", "saas:3"]
        assert row(answer, "saas:4")["role"] == "hub_manager"
        assert row(answer, "saas:1")["me"] is True and row(answer, "saas:3")["me"] is False

    def test_how_each_person_gets_in_the_account_always_then_pin_and_badge(self, client, olga, eva, mario):
        with_pin("saas:3")
        with_badge("saas:4", "CARD-0004")
        client.force_login(olga)
        answer = people(client)
        assert row(answer, "saas:1")["ways"] == {"account": True, "pin": False, "badge": False}
        assert row(answer, "saas:3")["ways"] == {"account": True, "pin": True, "badge": False}
        assert row(answer, "saas:4")["ways"] == {"account": True, "pin": False, "badge": True}

    def test_who_the_photo_names_and_has_not_entered_yet_is_listed_too(self, client, olga):
        photo(members=[
            {"user_id": "1", "role": "hub_owner", "email": "olga@example.com", "name": "Olga"},
            {"user_id": "0199aaaa-0000-7000-8000-000000000001", "role": "hub_employee", "email": "nuria@example.com", "name": "Nuria"},
        ])
        client.force_login(olga)
        nuria = row(people(client), "saas:0199aaaa-0000-7000-8000-000000000001")
        assert (nuria["name"], nuria["role"], nuria["entered"]) == ("Nuria", "hub_employee", False)
        assert nuria["ways"] == {"account": True, "pin": False, "badge": False}
        assert row(people(client), "saas:1")["entered"] is True

    def test_the_email_only_for_who_runs_the_business(self, client, olga, eva):
        client.force_login(olga)
        assert row(people(client), "saas:3")["email"] == "eva@example.com"
        client.force_login(eva)
        assert row(people(client), "saas:1")["email"] == ""
        assert row(people(client), "saas:3")["email"] == "eva@example.com"

    def test_the_name_is_the_one_of_my_profile_in_this_business(self, client, olga, eva):
        from base.models import Profile

        Profile.objects.create(username="saas:3", first_name="Eva María", last_name="Ruiz")
        client.force_login(olga)
        assert row(people(client), "saas:3")["name"] == "Eva María Ruiz"

    def test_nobody_without_a_session(self, client, olga):
        assert get(client, "/people").status_code in (401, 403)


class TestThePlansPlaces:
    """BASE-G138: the places of the plan the photo carries; every one taken says so."""

    def test_the_places_used_against_the_plans_limit(self, client, olga, eva):
        photo(max_users=3)
        client.force_login(olga)
        assert people(client)["seats"] == {"known": True, "used": 2, "limit": 3, "full": False}

    def test_every_place_taken_is_full(self, client, olga, eva, mario):
        photo(max_users=3)
        client.force_login(olga)
        assert people(client)["seats"]["full"] is True

    def test_no_limit_and_no_photo_never_full(self, client, olga, eva):
        photo(max_users=0)
        client.force_login(olga)
        assert people(client)["seats"] == {"known": True, "used": 2, "limit": None, "full": False}
        Hub.objects.filter(slug="a").update(state={})
        assert people(client)["seats"] == {"known": False, "used": 2, "limit": None, "full": False}


class TestOnePerson:
    """BASE-G10: a person's page, for whoever runs the business."""

    def test_what_the_hub_keeps_of_a_person_and_what_this_admin_may_do(self, client, adam, eva, olga):
        with_pin("saas:3")
        client.force_login(adam)
        answer = get(client, "/people/detail", person="saas:3").json()
        assert answer["id"] == "saas:3" and answer["ways"] == {"account": True, "pin": True, "badge": False}
        assert answer["pin_set_at"] is not None and answer["badge_set_at"] is None
        assert answer["may"] == {"remove_pin": True, "set_badge": True}
        owner = get(client, "/people/detail", person="saas:1").json()
        assert owner["may"] == {"remove_pin": False, "set_badge": False}
        mine = get(client, "/people/detail", person="saas:2").json()
        assert mine["may"] == {"remove_pin": True, "set_badge": False}

    def test_a_person_of_another_business_or_nobody_is_not_found(self, client, adam, make_user):
        make_user("saas:9", host="b", role=Membership.Role.EMPLOYEE)
        client.force_login(adam)
        assert code(get(client, "/people/detail", person="saas:9")) == "base.person_not_found"
        assert code(get(client, "/people/detail", person="saas:404")) == "base.person_not_found"

    def test_an_employee_cannot_open_it(self, client, eva):
        client.force_login(eva)
        assert code(get(client, "/people/detail", person="saas:3")) == "permission_denied"


class TestRemoveAPin:
    """BASE-G139: whoever runs the business takes a person's PIN away; their account still gets them in."""

    def test_the_pin_goes_and_the_person_leaves_the_pin_pad(self, client, adam, eva):
        with_pin("saas:3")
        a_device(client)
        client.force_login(adam)
        assert [face["name"] for face in door(client)["people"]] == ["Eva"]
        response = post(client, "/people/pin/remove", {"person": "saas:3"})
        assert response.status_code == 200, response.content
        assert response.json()["ways"] == {"account": True, "pin": False, "badge": False}
        assert Credential.objects.get(username="saas:3").pin_hash == ""
        assert door(client)["people"] == []
        assert OutboxEvent.objects.filter(name="base.person.pin_removed").count() == 1

    def test_the_badge_stays(self, client, adam, eva):
        with_pin("saas:3")
        with_badge("saas:3", "CARD-0003")
        client.force_login(adam)
        assert post(client, "/people/pin/remove", {"person": "saas:3"}).json()["ways"]["badge"] is True

    def test_without_a_pin_there_is_nothing_to_remove(self, client, adam, eva):
        client.force_login(adam)
        assert code(post(client, "/people/pin/remove", {"person": "saas:3"})) == "base.person_no_pin"

    def test_the_owners_only_by_the_owner(self, client, adam, olga):
        with_pin("saas:1")
        client.force_login(adam)
        response = post(client, "/people/pin/remove", {"person": "saas:1"})
        assert (response.status_code, code(response)) == (403, "base.person_owner_only")
        client.force_login(olga)
        assert post(client, "/people/pin/remove", {"person": "saas:1"}).status_code == 200

    def test_a_manager_or_an_employee_cannot(self, client, mario, eva):
        with_pin("saas:3")
        client.force_login(mario)
        assert code(post(client, "/people/pin/remove", {"person": "saas:3"})) == "permission_denied"
        assert Credential.objects.get(username="saas:3").pin_hash != ""


class TestABadge:
    """BASE-G140: whoever runs the business gives a person a badge, or takes it away; never their own."""

    def test_the_card_is_kept_as_its_digest_never_its_number(self, client, adam, eva):
        client.force_login(adam)
        response = post(client, "/people/badge", {"person": "saas:3", "badge": " card-0003 "})
        assert response.status_code == 200, response.content
        assert response.json()["ways"]["badge"] is True
        kept = Credential.objects.get(username="saas:3")
        assert kept.badge_digest == access.badge_digest("CARD-0003", key=services.badge_key())
        assert "0003" not in kept.badge_digest and kept.badge_set_at is not None
        assert OutboxEvent.objects.filter(name="base.person.badge_set").count() == 1

    def test_and_then_the_card_opens_the_way_in_as_that_person(self, client, adam, eva):
        client.force_login(adam)
        post(client, "/people/badge", {"person": "saas:3", "badge": "CARD-0003"})
        user, _ = services.badge_owner("a", "card-0003")
        assert user is not None and user.username == "saas:3"

    @pytest.mark.parametrize("card", ["abc", "x" * 65, "CARD 0003", "CARD/0003", ""])
    def test_a_card_that_is_no_badge_is_refused_on_its_field(self, client, adam, eva, card):
        client.force_login(adam)
        response = post(client, "/people/badge", {"person": "saas:3", "badge": card})
        assert (response.status_code, code(response)) == (422, "base.badge_invalid")
        assert response.json()["error"]["fields"] == {"badge": "invalid"}

    def test_nobody_gives_themselves_a_badge(self, client, adam):
        client.force_login(adam)
        response = post(client, "/people/badge", {"person": "saas:2", "badge": "CARD-0002"})
        assert (response.status_code, code(response)) == (403, "base.badge_own")

    def test_the_owner_may_give_their_own(self, client, olga):
        client.force_login(olga)
        assert post(client, "/people/badge", {"person": "saas:1", "badge": "CARD-0001"}).status_code == 200

    def test_the_owners_only_by_the_owner(self, client, adam, olga):
        client.force_login(adam)
        assert code(post(client, "/people/badge", {"person": "saas:1", "badge": "CARD-0001"})) == "base.person_owner_only"

    def test_a_card_someone_else_carries_is_refused(self, client, adam, eva, mario):
        with_badge("saas:4", "CARD-0004")
        client.force_login(adam)
        response = post(client, "/people/badge", {"person": "saas:3", "badge": "card-0004"})
        assert (response.status_code, code(response)) == (409, "base.badge_taken")
        assert Credential.objects.filter(username="saas:3").exclude(badge_digest="").count() == 0

    def test_trying_cards_is_braked_and_then_says_nothing_about_them(self, client, adam, eva, mario):
        """gh:hub#2560: «already taken» tells that a number is someone's card, so every try counts (30 an hour)."""
        with_badge("saas:4", "CARD-0004")
        client.force_login(adam)
        for attempt in range(people_rules.BADGE_CHANGE_LIMIT.attempts):
            post(client, "/people/badge", {"person": "saas:3", "badge": f"TRY-{attempt:04d}"})
        response = post(client, "/people/badge", {"person": "saas:3", "badge": "CARD-0004"})
        assert (response.status_code, code(response)) == (429, "base.too_many_badge_changes")
        assert "minute" in response.json()["error"]["message"]

    def test_the_limit_is_this_editors_on_this_business(self, client, adam, olga, eva):
        client.force_login(adam)
        for attempt in range(people_rules.BADGE_CHANGE_LIMIT.attempts):
            post(client, "/people/badge", {"person": "saas:3", "badge": f"TRY-{attempt:04d}"})
        client.force_login(olga)
        assert post(client, "/people/badge", {"person": "saas:3", "badge": "CARD-0003"}).status_code == 200

    def test_taking_it_away_leaves_the_pin(self, client, adam, eva):
        with_pin("saas:3")
        with_badge("saas:3", "CARD-0003")
        client.force_login(adam)
        response = post(client, "/people/badge/remove", {"person": "saas:3"})
        assert response.json()["ways"] == {"account": True, "pin": True, "badge": False}
        assert services.badge_owner("a", "CARD-0003")[0] is None
        assert OutboxEvent.objects.filter(name="base.person.badge_removed").count() == 1

    def test_without_a_badge_there_is_nothing_to_take_away(self, client, adam, eva):
        client.force_login(adam)
        assert code(post(client, "/people/badge/remove", {"person": "saas:3"})) == "base.person_no_badge"

    def test_a_person_the_photo_names_gets_one_before_entering(self, client, adam):
        photo(members=[{"user_id": "0199aaaa-0000-7000-8000-000000000002", "role": "hub_employee", "name": "Nuria"}])
        client.force_login(adam)
        person = "saas:0199aaaa-0000-7000-8000-000000000002"
        assert post(client, "/people/badge", {"person": person, "badge": "CARD-0099"}).status_code == 200
        assert Credential.objects.get(username=person).badge_digest != ""


class TestComingBack:
    """BASE-G141: removed on erplora.com and invited again, a person comes back with their PIN and badge."""

    def test_what_the_hub_kept_of_them_is_theirs_again(self, client, olga, eva):
        with_pin("saas:3")
        with_badge("saas:3", "CARD-0003")
        Membership.objects.filter(user=eva, host="a").delete()
        client.force_login(olga)
        assert [entry["id"] for entry in people(client)["people"]] == ["saas:1"]
        assert services.badge_owner("a", "CARD-0003")[0] is None
        Membership.objects.create(user=eva, host="a", role=Membership.Role.EMPLOYEE)
        assert row(people(client), "saas:3")["ways"] == {"account": True, "pin": True, "badge": True}
        assert services.badge_owner("a", "CARD-0003")[0] == eva


class TestTheRoles:
    """BASE-G143 and G144: the roles of the business, who has each one and how many permissions it gives."""

    def test_the_four_roles_of_erplora_com_with_their_people_and_permissions(self, client, olga, adam, eva):
        client.force_login(eva)
        response = get(client, "/roles")
        assert response.status_code == 200, response.content
        roles = {role["key"]: role for role in response.json()["roles"]}
        assert list(roles) == ["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
        assert {key: role["members"] for key, role in roles.items()} == {
            "hub_owner": 1, "hub_admin": 1, "hub_manager": 0, "hub_employee": 1,
        }
        assert roles["hub_owner"]["permissions"] == roles["hub_admin"]["permissions"]
        assert roles["hub_admin"]["permissions"] > roles["hub_manager"]["permissions"] > roles["hub_employee"]["permissions"] > 0
        assert all(role["origin"] == "basic" for role in roles.values())
        assert roles["hub_manager"]["label"] == "Manager"


class TestPermissions:
    """BASE-G26: what each role may do is checked on every operation (``@operation``), whatever the caller."""

    def test_an_operation_refuses_whom_its_permission_is_not_given(self, eva, olga):
        op = get_operation("base.person.pin_remove")
        employee = OperationContext(scope=Scope("host", "a"), actor=eva, permissions=permissions_for(eva, Scope("host", "a")))
        with pytest.raises(OperationError) as refused:
            op(employee, op.input(person="saas:1"))
        assert refused.value.code == "permission_denied"


class TestFollowedLive:
    """Employees follows, without reloading, what changes the people and their ways in."""

    def test_what_re_runs_the_people_and_the_roles(self):
        from live.live_registry import live_registry

        from base import events

        on = live_registry.subscribable
        people_events = sorted(
            {events.PIN_SET, events.PROFILE_UPDATED, events.HUB_STATE_APPLIED, *events.PERSON_EVENTS}
        )
        assert on["base.person.list"] == people_events
        assert on["base.person.detail"] == people_events
        assert on["base.role.list"] == [events.HUB_STATE_APPLIED]

    def test_the_prefix_of_a_person_is_the_one_of_their_account(self):
        assert people_rules.SAAS_PREFIX == services.SAAS_USERNAME_PREFIX


PEOPLE_ROUTES = {
    ("GET", "/people", "base.person.list"),
    ("GET", "/people/detail", "base.person.detail"),
    ("POST", "/people/pin/remove", "base.person.pin_remove"),
    ("POST", "/people/badge", "base.person.badge_set"),
    ("POST", "/people/badge/remove", "base.person.badge_remove"),
    ("GET", "/roles", "base.role.list"),
}


class TestTheRoutes:
    """The SPA calls each operation by its name: the hand-written map names the route ``base/api.py`` binds."""

    def test_the_spas_route_map_names_every_route_of_people_and_roles(self, settings):
        from base.tests.test_access_routes import bound_routes

        assert PEOPLE_ROUTES <= bound_routes()
        spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
        mine = {op for _, _, op in PEOPLE_ROUTES}
        named = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op in mine}
        assert named == PEOPLE_ROUTES

    @pytest.mark.parametrize("name", sorted(op for _, _, op in PEOPLE_ROUTES))
    def test_each_tells_the_assistant_what_it_does(self, name):
        op = get_operation(name)
        assert isinstance(op.ai, dict) and op.ai["description"].strip()
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}
