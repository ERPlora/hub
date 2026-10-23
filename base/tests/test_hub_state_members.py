"""The SaaS's photo applies its members in the Hub (``PUT /internal/hubs/{id}/state``, its ``members``; HUBS-F26,
HUBS-F27 and HUBS-F28 of the SaaS).

The photo lists who is in the business and with which role. In this business only: a person whose role changed gets
it at once (``Membership.role``) and their sessions here end, so the new permission is the one they work with from
now on; a person who is no longer in it loses their membership and their sessions here; a handover is both at once
(the new owner ``hub_owner``, the former one with the role the photo says). Nobody is created: a person the Hub has
not seen yet gets their role when they first enter. All of it in the photo's transaction (a photo out of contract
changes nothing); the open apps hear it after its COMMIT. A photo older than the one kept, or one without
``members``, changes no one.
"""

import json

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from live.context import Scope
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base.models import Hub, Membership
from base.tests.test_internal import HUB_ID, PATH, code, signed
from base.tests.test_session_revoke import alive, login

ANA = "0199c4b0-0000-7000-8000-00000000a0a0"
OLGA = "0199c4b0-0000-7000-8000-00000000b0b0"
BETA_ID = "0199c4b0-0000-7000-8000-0000000000a2"


@pytest.fixture
def acme(db):
    return Hub.objects.create(id=HUB_ID, slug="acme", status="ready")


@pytest.fixture
def beta(db):
    return Hub.objects.create(id=BETA_ID, slug="beta", status="ready")


def member(saas_id: str, role: str) -> dict:
    return {"user_id": saas_id, "email": f"{saas_id[-4:]}@example.com", "name": "Someone", "role": role}


def photo(version: int, *members: dict) -> dict:
    return {"hub_id": HUB_ID, "slug": "acme", "version": version, "members": list(members)}


def role_of(saas_id: str, slug: str = "acme") -> str | None:
    return (
        Membership.objects.filter(user__username=f"saas:{saas_id}", host=slug).values_list("role", flat=True).first()
    )


@pytest.mark.django_db
class TestTheMembersOfThePhoto:
    def test_a_new_role_applies_now_and_ends_that_person_s_sessions_in_this_business_only(self, client, acme, beta):
        ana_here, ana_on_beta = login(ANA, acme, "hub_employee"), login(ANA, beta, "hub_employee")
        olga_here = login(OLGA, acme, "hub_owner")

        answer = signed(client, "put", PATH, photo(1, member(OLGA, "hub_owner"), member(ANA, "hub_manager")))

        assert answer.json() == {"applied": True, "version": 1}
        assert (role_of(ANA), role_of(ANA, "beta"), role_of(OLGA)) == ("hub_manager", "hub_employee", "hub_owner")
        assert not alive(ana_here)
        assert alive(ana_on_beta) and alive(olga_here)

    def test_whoever_is_no_longer_in_it_loses_the_membership_and_the_sessions_here(self, client, acme, beta):
        ana_here, ana_on_beta = login(ANA, acme, "hub_employee"), login(ANA, beta, "hub_employee")
        olga_here = login(OLGA, acme, "hub_owner")

        signed(client, "put", PATH, photo(1, member(OLGA, "hub_owner")))

        assert role_of(ANA) is None and not alive(ana_here)
        assert role_of(ANA, "beta") == "hub_employee" and alive(ana_on_beta)
        assert role_of(OLGA) == "hub_owner" and alive(olga_here)

    def test_a_handover_makes_the_new_owner_and_gives_the_former_one_the_photo_s_role(self, client, acme):
        ana_here, olga_here = login(ANA, acme, "hub_owner"), login(OLGA, acme, "hub_admin")

        signed(client, "put", PATH, photo(1, member(OLGA, "hub_owner"), member(ANA, "hub_admin")))

        assert (role_of(OLGA), role_of(ANA)) == ("hub_owner", "hub_admin")
        assert not alive(ana_here) and not alive(olga_here)

    def test_someone_the_hub_has_not_seen_yet_is_not_created(self, client, acme):
        login(OLGA, acme, "hub_owner")

        signed(client, "put", PATH, photo(1, member(OLGA, "hub_owner"), member(ANA, "hub_employee")))

        assert role_of(ANA) is None
        assert not get_user_model().objects.filter(username=f"saas:{ANA}").exists()

    def test_a_person_whose_role_is_the_same_keeps_their_sessions(self, client, acme):
        ana_here = login(ANA, acme, "hub_employee")

        signed(client, "put", PATH, photo(1, member(ANA, "hub_employee")))

        assert role_of(ANA) == "hub_employee" and alive(ana_here)

    def test_a_photo_without_members_changes_no_one(self, client, acme):
        ana_here = login(ANA, acme, "hub_employee")

        answer = signed(client, "put", PATH, {"hub_id": HUB_ID, "slug": "acme", "version": 1})

        assert answer.json() == {"applied": True, "version": 1}
        assert role_of(ANA) == "hub_employee" and alive(ana_here)

    def test_an_older_photo_changes_no_one(self, client, acme):
        signed(client, "put", PATH, photo(2, member(ANA, "hub_employee")))
        ana_here = login(ANA, acme, "hub_employee")

        answer = signed(client, "put", PATH, photo(1))

        assert answer.json() == {"applied": False, "version": 2}
        assert role_of(ANA) == "hub_employee" and alive(ana_here)

    def test_a_photo_with_nobody_removes_the_saas_s_members_but_not_the_demo_s_owner(self, client, acme):
        demo = get_user_model().objects.create(username="demo:acme")
        Membership.objects.create(user=demo, host="acme", role="hub_owner")
        ana_here = login(ANA, acme, "hub_employee")

        signed(client, "put", PATH, photo(1))

        assert Membership.objects.filter(user=demo, host="acme").exists()
        assert role_of(ANA) is None and not alive(ana_here)

    @pytest.mark.parametrize(
        "members",
        [
            "everyone",
            [{"user_id": "not-an-id", "role": "hub_employee"}],
            [{"user_id": ANA, "role": "superuser"}],
            [{"user_id": ANA}],
        ],
        ids=["not-a-list", "bad-id", "bad-role", "no-role"],
    )
    def test_members_out_of_contract_are_422_and_change_nothing(self, client, acme, members):
        ana_here = login(ANA, acme, "hub_employee")

        answer = signed(client, "put", PATH, {"hub_id": HUB_ID, "slug": "acme", "version": 1, "members": members})

        assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
        assert role_of(ANA) == "hub_employee" and alive(ana_here)
        acme.refresh_from_db()
        assert acme.state_version == 0

    def test_a_photo_refused_further_on_keeps_everyone_as_they_were(self, client, acme):
        """The members apply in the photo's transaction: a VeriFactu block out of contract undoes them too."""
        ana_here = login(ANA, acme, "hub_employee")

        answer = signed(
            client,
            "put",
            PATH,
            {**photo(1, member(ANA, "hub_manager")), "verifactu": {"representation": {"status": "maybe"}}},
        )

        assert answer.status_code == 422 and code(answer) == "internal.payload_invalid"
        assert role_of(ANA) == "hub_employee" and alive(ana_here)


@pytest.mark.django_db(transaction=True)
def test_the_open_apps_of_the_business_hear_it_after_the_commit(client):
    hub = Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
    login(ANA, hub, "hub_employee")
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    with psycopg.connect(dsn, autocommit=True) as listener:
        listener.execute(f"LISTEN {channel_for(Scope('host', 'acme'))}")

        signed(client, "put", PATH, photo(1, member(ANA, "hub_manager")))

        heard = {name for note in listener.notifies(timeout=1.0) for name in json.loads(note.payload)["events"]}
    assert "*" in heard
