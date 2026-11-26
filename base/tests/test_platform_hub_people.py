"""The people of ERPlora's own hub: erplora.com's photo says who they are and nothing else of that hub, and they come in
at its address with the one-time code of the jump, as in any business.

Its photo is the one of any business (``PUT /internal/hubs/{id}/state``, signed, with its monotonic ``version``), but of
it only ``members`` applies. A business (``hub_a``) gets the same photo whole, beside it.
"""

import json

import pytest
from django.conf import settings
from django.utils import timezone
from live.context import Scope

from apps.verifactu.models import Config
from apps.whatsapp_inbox.models.channel import Channel
from base import registry
from base.models import Hub, HubUser, Membership
from base.permissions import permissions_of_role
from base.queries.apps import app_limit
from base.queries.people import people_of, seats_of
from base.services.photo import apply_kept_photo
from base.tenancy import limits
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, HUB_DB
from base.tests.test_auth_views import callback, me
from base.tests.test_internal import APPROVED, REGISTRY, code, signed
from base.tests.test_internal_whatsapp import channel_state
from base.tests.test_platform_hub_host import erp, named
from base.tests.test_session_revoke import ANA, OLGA, REVOKE, alive, login

__all__ = ["erp"]

pytestmark = HUB_DB

ERP = "erp.localhost:8000"
A_HOST = f"{A.key}.localhost:8000"
ROLES = ["hub_owner", "hub_admin", "hub_manager", "hub_employee", "hub_accountant"]


def member(saas_id: str, role: str, name: str = "Someone") -> dict:
    return {"user_id": saas_id, "email": f"{saas_id[-4:]}@example.com", "name": name, "role": role}


def photo(hub: Hub, version: int, *members: dict, **rest) -> dict:
    return {"hub_id": str(hub.pk), "slug": hub.slug, "version": version, "members": list(members), **rest}


def send(client, hub: Hub, version: int, *members: dict, **rest):
    path, secret = f"/internal/hubs/{hub.pk}/state", settings.INTERNAL_SHARED_SECRET
    return signed(client, "put", path, photo(hub, version, *members, **rest), secret=secret)


def row(hub: Hub) -> dict:
    return {**Hub.objects.filter(pk=hub.pk).values().get(), "updated_at": None}


def roles_at(hub: Hub) -> dict[str, str]:
    """Who has access to ``hub`` and with which role."""
    memberships = Membership.objects.filter(host=hub.slug).values_list("user__username", "role")
    return {username.removeprefix("saas:"): role for username, role in memberships}


def people_in(hub: Hub) -> dict[str, tuple[str, str, bool]]:
    """Who its own database says is in ``hub``: their name, their email and whether they are still in it."""
    with use_hub(hub):
        rows = HubUser.objects.values_list("username", "name", "email", "is_active")
        return {username.removeprefix("saas:"): (name, email, active) for username, name, email, active in rows}


def arrives(saas_id: str, role: str) -> dict:
    """What erplora.com answers of the person whose code it is."""
    return {"user_id": saas_id, "email": f"{saas_id[-4:]}@example.com", "name": "Ana", "locale": "en", "role": role}


# ── Its people, from the photo ────────────────────────────────────────────────────────────────────────────────────


class TestItsPeople:
    def test_who_has_not_come_in_yet_is_in_it_by_the_name_and_the_role_the_photo_says(self, client, erp, hub_a):
        answer = send(client, erp, 1, member(OLGA, "hub_owner", "Olga"), member(ANA, "hub_employee", "Ana"))

        assert (answer.status_code, answer.json()) == (200, {"applied": True, "version": 1})
        assert people_in(erp) == {
            OLGA: ("Olga", f"{OLGA[-4:]}@example.com", True),
            ANA: ("Ana", f"{ANA[-4:]}@example.com", True),
        }
        with use_hub(erp):
            listed = [(person["name"], person["role"], person["entered"]) for person in people_of("erp")]
        assert listed == [("Olga", "hub_owner", False), ("Ana", "hub_employee", False)]
        assert people_in(hub_a) == {}

    def test_a_role_that_changed_is_theirs_at_once_and_their_session_goes_on(self, client, erp):
        ana = login(ANA, erp, "hub_employee")

        send(client, erp, 1, member(ANA, "hub_admin"))

        assert roles_at(erp) == {ANA: "hub_admin"}
        assert alive(ana)

    def test_who_is_no_longer_in_it_is_out(self, client, erp):
        ana, olga = login(ANA, erp, "hub_employee"), login(OLGA, erp, "hub_owner")
        send(client, erp, 1, member(OLGA, "hub_owner"), member(ANA, "hub_employee"))

        answer = send(client, erp, 2, member(OLGA, "hub_owner"))

        assert answer.json() == {"applied": True, "version": 2}
        assert roles_at(erp) == {OLGA: "hub_owner"}
        assert (alive(ana), alive(olga)) == (False, True)
        assert {saas_id: active for saas_id, (_, _, active) in people_in(erp).items()} == {ANA: False, OLGA: True}
        with use_hub(erp):
            assert [person["id"] for person in people_of("erp")] == [f"saas:{OLGA}"]

    @pytest.mark.parametrize("version", [1, 2], ids=["older", "the one it has"])
    def test_a_photo_no_newer_than_the_one_it_has_changes_nobody(self, client, erp, version):
        ana = login(ANA, erp, "hub_employee")
        send(client, erp, 2, member(ANA, "hub_employee"))
        before = row(erp)

        answer = send(client, erp, version, member(OLGA, "hub_owner"))

        assert (answer.status_code, answer.json()) == (200, {"applied": False, "version": 2})
        assert row(erp) == before
        assert (roles_at(erp), list(people_in(erp)), alive(ana)) == ({ANA: "hub_employee"}, [ANA], True)

    def test_a_photo_without_people_changes_nobody(self, client, erp):
        ana = login(ANA, erp, "hub_employee")

        body = {"hub_id": str(erp.pk), "version": 1}
        answer = signed(client, "put", f"/internal/hubs/{erp.pk}/state", body)

        assert answer.json() == {"applied": True, "version": 1}
        assert (roles_at(erp), alive(ana), row(erp)["state"]) == ({ANA: "hub_employee"}, True, {})

    def test_its_sessions_of_one_account_end_on_their_own(self, client, erp, hub_a):
        there, elsewhere, olga = login(ANA, erp), login(ANA, hub_a), login(OLGA, erp)

        answer = signed(client, "post", REVOKE, {"user_id": ANA, "hub_id": str(erp.pk)})

        assert answer.json() == {"ended": 1}
        assert (alive(there), alive(elsewhere), alive(olga)) == (False, True, True)

    def test_those_of_a_photo_that_came_while_it_was_being_made_are_in_it_once_it_is(self, client, erp):
        Hub.objects.filter(pk=erp.pk).update(status=Hub.Status.SEEDING, ready_at=None)
        send(client, erp, 1, member(ANA, "hub_owner"), **EVERYTHING_ELSE)
        assert people_in(erp) == {}

        with use_hub(erp):
            apply_kept_photo(Hub.objects.get(pk=erp.pk))

        assert list(people_in(erp)) == [ANA]
        with use_hub(erp):
            assert not Config.objects.exists() and not Channel.objects.exists()


# ── Nothing else of it, from the photo ────────────────────────────────────────────────────────────────────────────


#: What erplora.com's photo of a business carries besides its people.
EVERYTHING_ELSE = {
    "status": "suspended",
    "suspends_on": "2026-11-30T00:00:00+00:00",
    "plan": {
        "slug": "free",
        "included_level": 0,
        "max_devices": 1,
        "max_users": 1,
        "max_db_connections": 1,
        "statement_timeout_seconds": 5,
        "assistant_messages_per_month": 30,
        "whatsapp_messages_per_month": 0,
        "max_apps": 1,
        "max_storage_bytes": 1,
    },
    "modules": [{"id": "kitchen", "source": "purchase", "valid_until": None}],
    "verifactu": {"representation": APPROVED},
    "whatsapp": channel_state(),
    "custom_domain": "shop.example.com",
}


class TestNothingElseOfIt:
    @pytest.fixture
    def both(self, client, erp, hub_a):
        """ERPlora's own hub and a business, each with the same whole photo, and what its row said before."""
        before = row(erp)
        people = [member(OLGA, "hub_owner"), member(ANA, "hub_employee")]
        for hub in (erp, hub_a):
            assert send(client, hub, 1, *people, **EVERYTHING_ELSE).json() == {"applied": True, "version": 1}
        return Hub.objects.get(pk=erp.pk), Hub.objects.get(pk=hub_a.pk), before

    def test_its_row_keeps_its_people_and_a_business_s_the_whole_photo(self, both):
        own, business, before = both
        people = [member(OLGA, "hub_owner"), member(ANA, "hub_employee")]

        assert row(own) == {**before, "state": {"members": people}, "state_version": 1}
        assert business.state == photo(business, 1, *people, **EVERYTHING_ELSE)
        assert business.custom_domain == "shop.example.com"

    def test_its_limits_stay_the_platform_s_and_a_business_s_are_its_plan_s(self, both):
        own, business, _ = both

        assert limits.hub_limits(own) == limits.PLATFORM
        assert limits.hub_limits(business) == limits.PlanLimits(max_transactions=1, statement_timeout_seconds=5)
        assert (app_limit(own), app_limit(business)) == (None, 1)
        for hub, known in ((own, False), (business, True)):
            assert seats_of(hub.slug, 2)["known"] is known
        # A photo newer than the one its limiter follows resizes it: to the platform's again.
        with use_hub(own) as tenancy:
            assert limits.limiter_for(tenancy.alias).limits == limits.PLATFORM

    def test_no_plan_ends_the_sessions_of_its_devices(self, both):
        own, business, _ = both

        ours = [login(OLGA, own, "hub_owner"), login(ANA, own, "hub_employee")]
        theirs = [login(OLGA, business, "hub_owner"), login(ANA, business, "hub_employee")]

        assert [alive(key) for key in ours] == [True, True]
        assert [alive(key) for key in theirs] == [False, True]

    def test_it_is_never_suspended(self, client, both):
        own, business, _ = both

        assert (registry.refusal(own), registry.refusal(business).status) == (None, 402)
        assert client.get("/api/me", HTTP_HOST=ERP).status_code == 200
        assert client.get("/api/me", HTTP_HOST=A_HOST).status_code == 402

    def test_nothing_is_told_to_its_apps(self, both):
        own, business, _ = both

        told = []
        for hub in (own, business):
            with use_hub(hub):
                told.append((Config.objects.count(), Channel.objects.count()))
        assert told == [(0, 0), (1, 1)]

    def test_no_domain_is_its_website_s(self, both):
        _, business, _ = both

        assert registry.custom_domains() == [("shop.example.com", business.pk)]

    def test_what_a_photo_said_of_it_before_stays_out_with_the_next_one(self, client, both):
        own, _, before = both

        answer = send(client, own, 2, member(OLGA, "hub_owner"), **{**EVERYTHING_ELSE, "status": "past_due"})

        assert answer.json() == {"applied": True, "version": 2}
        assert row(own) == {**before, "state": {"members": [member(OLGA, "hub_owner")]}, "state_version": 2}

    def test_a_block_a_business_would_refuse_never_keeps_its_people_out(self, client, erp, hub_a):
        unread = {"verifactu": {"representation": {"status": "maybe"}}, "whatsapp": {"status": "maybe"}}

        ours = send(client, erp, 1, member(ANA, "hub_employee"), **unread)
        theirs = send(client, hub_a, 1, member(ANA, "hub_employee"), **unread)

        assert (ours.status_code, theirs.status_code) == (200, 422)
        assert (list(people_in(erp)), people_in(hub_a)) == ([ANA], {})


# ── What erplora.com never does to it ─────────────────────────────────────────────────────────────────────────────


class TestWhatIsNeverDoneToIt:
    @pytest.mark.parametrize(
        ("method", "path", "body", "refused"),
        [
            ("delete", "", {}, (409, "base.platform_hub_kept")),
            ("post", "/restore", {}, (409, "base.platform_hub_kept")),
            ("put", "", {**REGISTRY, "slug": "acme"}, (409, "base.platform_hub_kept")),
            ("put", "", {**REGISTRY, "slug": "erp"}, (422, "base.slug_invalid")),
        ],
        ids=["deleted", "restored", "registered under another name", "registered under its own"],
    )
    def test_it_is_never_registered_closed_nor_restored(self, client, erp, method, path, body, refused):
        before = row(erp)

        answer = signed(client, method, f"/internal/hubs/{erp.pk}{path}", {**body, "id": str(erp.pk)})

        assert (answer.status_code, code(answer)) == refused
        assert row(erp) == before

    def test_a_business_is_still_closed_and_restored(self, client, hub_a):
        path = f"/internal/hubs/{hub_a.pk}"
        Hub.objects.filter(pk=hub_a.pk).update(ready_at=timezone.now())

        closed = signed(client, "delete", path, {"id": str(hub_a.pk)})
        restored = signed(client, "post", f"{path}/restore", {"id": str(hub_a.pk)})

        assert (closed.status_code, closed.json()["status"]) == (202, "cancelled")
        assert (restored.status_code, restored.json()["status"]) == (200, "ready")

    @pytest.mark.parametrize(
        ("method", "path"), [("put", "/state"), ("delete", ""), ("post", "/restore"), ("put", "")]
    )
    @pytest.mark.parametrize("signature", [{"with_v1": False}, {"secret": "another"}], ids=["none", "another secret"])
    def test_a_call_without_a_good_signature_does_nothing(self, client, erp, method, path, signature):
        ana, before = login(ANA, erp, "hub_employee"), row(erp)

        answer = signed(client, method, f"/internal/hubs/{erp.pk}{path}", photo(erp, 1), **signature)

        assert (answer.status_code, code(answer)) == (401, "internal.unsigned")
        assert (row(erp), roles_at(erp), alive(ana)) == (before, {ANA: "hub_employee"}, True)


# ── The other businesses ──────────────────────────────────────────────────────────────────────────────────────────


class TestTheOtherBusinesses:
    @pytest.fixture
    def in_both(self, erp, hub_a):
        """Ana, an employee of a business and the owner of ERPlora's own hub, with a session in each."""
        return login(ANA, erp, "hub_owner"), login(ANA, hub_a, "hub_employee")

    def test_its_photo_changes_nobody_of_a_business(self, client, erp, hub_a, in_both):
        here, there = in_both
        before = row(hub_a)

        send(client, erp, 1, member(OLGA, "hub_owner"))

        assert (roles_at(erp), roles_at(hub_a)) == ({}, {ANA: "hub_employee"})
        assert (alive(here), alive(there)) == (False, True)
        assert (row(hub_a), list(people_in(hub_a))) == (before, [ANA])

    def test_a_business_s_photo_changes_nobody_of_it(self, client, erp, hub_a, in_both):
        here, there = in_both
        before = row(erp)

        send(client, hub_a, 1, member(OLGA, "hub_owner"))

        assert (roles_at(erp), roles_at(hub_a)) == ({ANA: "hub_owner"}, {})
        assert (alive(here), alive(there)) == (True, False)
        assert (row(erp), list(people_in(erp))) == (before, [ANA])


# ── They come in ──────────────────────────────────────────────────────────────────────────────────────────────────


class TestTheyComeIn:
    @pytest.mark.parametrize("role", ROLES)
    def test_with_the_code_of_the_jump_and_their_role(self, client, fake_saas, erp, role):
        fake = fake_saas(body=arrives(ANA, role))

        answer = callback(client, {"code": "c1", "next": "/system"}, host=ERP)

        assert (answer.status_code, answer["Location"]) == (302, "/system")
        assert json.loads(fake.calls[0]["body"]) == {"code": "c1", "hub": "erp"}
        session = me(client, ERP)
        assert (session["user"]["label"], session["scope"]["key"]) == ("Ana", "erp")
        assert set(session["permissions"]) == permissions_of_role(role)
        assert (roles_at(erp), list(people_in(erp))) == ({ANA: role}, [ANA])

    def test_that_session_is_no_session_of_a_business(self, client, fake_saas, erp, hub_a):
        fake_saas(body=arrives(ANA, "hub_owner"))

        callback(client, {"code": "c1", "next": "/"}, host=ERP)

        assert me(client, A_HOST)["permissions"] == []
        assert (roles_at(hub_a), people_in(hub_a)) == ({}, {})

    def test_until_the_photo_leaves_them_out(self, client, fake_saas, erp):
        fake_saas(body=arrives(ANA, "hub_owner"))
        callback(client, {"code": "c1", "next": "/"}, host=ERP)
        send(client, erp, 1, member(ANA, "hub_employee"))
        assert set(me(client, ERP)["permissions"]) == permissions_of_role("hub_employee")

        send(client, erp, 2, member(OLGA, "hub_owner"))

        assert (me(client, ERP)["user"], me(client, ERP)["permissions"]) == (None, [])

    def test_never_with_a_code_erplora_com_refuses(self, client, fake_saas, erp):
        fake_saas(status=400, body={"error": {"code": "invalid_code"}})

        answer = callback(client, {"code": "c1", "next": "/"}, host=ERP)

        assert answer["Location"].startswith("http://localhost:8001/hub-login/?hub=erp&next=/&error=invalid_code")
        assert (me(client, ERP)["user"], roles_at(erp)) == (None, {})

    @pytest.mark.parametrize("role", ["platform_admin", "platform_support", "owner", None])
    def test_never_with_a_role_no_business_has(self, client, fake_saas, erp, role):
        fake_saas(body=arrives(ANA, role))

        callback(client, {"code": "c1", "next": "/"}, host=ERP)

        assert (me(client, ERP)["user"], roles_at(erp)) == (None, {})

    def test_nor_does_support_while_it_does_not_let_support_in(self, client, fake_saas, erp):
        fake_saas(body=arrives(ANA, Membership.SUPPORT))

        answer = callback(client, {"code": "c1", "next": "/"}, host=ERP)

        assert answer.status_code == 403
        assert (me(client, ERP)["user"], roles_at(erp), people_in(erp)) == (None, {}, {})

    @pytest.mark.parametrize(
        ("slug", "is_platform"),
        [("erplora", True), ("test", False), ("hub", False), ("www", False), ("erp", False)],
        ids=["the name it had", "test", "hub", "www", "its name on another row"],
    )
    def test_at_no_other_reserved_name(self, client, fake_saas, hub_b, slug, is_platform):
        hub = named(hub_b, slug, is_platform=is_platform)
        fake = fake_saas(body=arrives(ANA, "hub_owner"))

        answer = client.post(
            "/auth/callback", {"code": "c1", "next": "/", "state": "s"}, HTTP_HOST=f"{slug}.localhost:8000"
        )

        assert answer.status_code == 404
        assert (fake.calls, roles_at(hub), people_in(hub)) == ([], {}, {})


def test_the_photo_reaches_it_by_its_id_whatever_its_name(client, hub_b):
    """Its row may still have the name it had before: its people are its own, and go with it when it is renamed."""
    hub = named(hub_b, "erplora", is_platform=True)

    send(client, hub, 1, member(ANA, "hub_owner"), **EVERYTHING_ELSE)

    assert row(hub)["state"] == {"members": [member(ANA, "hub_owner")]}
    assert list(people_in(hub)) == [ANA]


def test_the_photo_of_it_is_told_to_whoever_has_it_open(client, erp, monkeypatch, django_capture_on_commit_callbacks):
    from base.services import hub_registry

    told = []
    monkeypatch.setattr(hub_registry, "notify", lambda scope, names: told.append((scope, names)))

    with django_capture_on_commit_callbacks(execute=True):
        send(client, erp, 1, member(ANA, "hub_owner"))

    assert told == [(Scope("host", "erp"), ["base.hub.state_applied"])]
