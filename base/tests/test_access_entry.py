"""The way in of a browser without a session (BASE-G54, G55, G57, G58, G61): the PIN pad or erplora.com's sign-in.

A page of the hub loaded without a session goes to the hub's «Access» (``/login``) when this browser is a shared device
of the hub, of a business that asks, with somebody to choose on its grid (saying, if so, that the session ended:
«ended»), or when another device's entry ended it («device_limit», the plan covers fewer devices). Anywhere else it
goes, as before, straight to erplora.com's sign-in for this hub, which brings the person back while its own session
lives. After an entry with the account on a device that asks,
in a business that already enters by PIN, a person without one is asked to choose it first (``/pin/setup``), and may
leave it for later.
"""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from base import access
from base.models import AccessSettings, Credential, Hub, Membership, TrustedDevice
from base.tests.test_access_account import enter
from base.tests.test_middleware import through_the_jump

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
SAAS_LOGIN = "http://localhost:8001/hub-login/"


def a_device(client, mode=access.SHARED, **fields) -> TrustedDevice:
    token = access.new_device_token()
    device = TrustedDevice.objects.create(
        token_digest=access.token_digest(token), mode=mode, last_entry_at=timezone.now(), **fields
    )
    client.cookies[access.DEVICE_COOKIE] = token
    return device


def with_pin(user, digits="4826"):
    return Credential.objects.create(username=user.username, pin_hash=make_password(digits, hasher="argon2"))


def page(client, path="/sale/pos"):
    return client.get(path, HTTP_HOST=HOST, HTTP_ACCEPT="text/html")


def query(response) -> dict:
    return {key: values[0] for key, values in parse_qs(urlsplit(response["Location"]).query).items()}


@pytest.fixture
def ana(make_user, saas):
    return make_user("saas:1", host="a", first_name="Ana")


class TestThePinPadOrTheSaas:
    def test_a_shared_device_with_somebody_to_choose_goes_to_the_hub_s_access(self, client, ana):
        a_device(client)
        with_pin(ana)
        response = page(client)
        assert response.status_code == 302
        assert response["Location"].startswith("/login?")
        assert query(response) == {"next": "/sale/pos"}

    @pytest.mark.parametrize("how", ["no_device", "personal", "never", "nobody_with_a_pin"])
    def test_anywhere_else_straight_to_the_saas_sign_in_as_before(self, client, ana, how):
        if how != "no_device":
            a_device(client, mode=access.PERSONAL if how == "personal" else access.SHARED)
        if how == "never":
            AccessSettings.objects.create(pin_policy=access.NEVER)
        if how != "nobody_with_a_pin":
            with_pin(ana)
        response = through_the_jump(client, page(client))
        assert response["Location"].startswith(f"{SAAS_LOGIN}?hub=a&next=/sale/pos&state=")

    def test_the_access_page_itself_is_the_spa_without_a_session(self, client, ana, spa_manifest):
        a_device(client)
        with_pin(ana)
        response = page(client, "/login?next=/sale/pos")
        assert response.status_code == 200
        assert b'id="session-me"' in response.content

    def test_the_shell_s_gate_takes_the_same_way(self, client, ana):
        a_device(client)
        with_pin(ana)
        response = client.get("/auth/login", {"next": "/sale/pos"}, HTTP_HOST=HOST)
        assert response["Location"].startswith("/login?")

    def test_enter_with_the_account_from_the_access_page_jumps_to_the_saas(self, client, ana):
        a_device(client)
        with_pin(ana)
        response = client.get("/auth/login", {"next": "/sale/pos", "account": "1"}, HTTP_HOST=HOST)
        assert response["Location"].startswith(f"{SAAS_LOGIN}?hub=a&next=/sale/pos&state=")

    def test_a_demo_still_jumps_to_its_own_door(self, client, ana):
        from base.tests.test_auth_views import host_of, new_demo

        slug = new_demo()
        response = client.get("/demo/items", HTTP_HOST=host_of(slug), HTTP_ACCEPT="text/html")
        assert "/demo/enter/" in through_the_jump(client, response, host_of(slug))["Location"]


class TestWhatTheAccessPageSays:
    def test_a_session_that_ended_on_a_till_says_so_on_its_pin_pad(self, client, ana):
        a_device(client)
        with_pin(ana)
        client.force_login(ana)
        Session.objects.all().delete()
        response = page(client)
        assert response["Location"].startswith("/login?")
        assert query(response) == {"next": "/sale/pos", "notice": "ended"}

    @pytest.mark.parametrize("device", ["none", "personal"])
    def test_a_session_that_ended_where_the_pin_is_not_offered_goes_on_to_erplora_com(self, client, ana, device):
        # erplora.com's sign-in brings the person straight back when its own session is alive (BASE-F13), as before.
        if device == "personal":
            a_device(client, mode=access.PERSONAL)
        client.force_login(ana)
        Session.objects.all().delete()
        assert through_the_jump(client, page(client))["Location"].startswith(SAAS_LOGIN)

    def test_another_device_s_entry_says_the_plan_covers_fewer_devices(self, client, ana):
        a_device(client, mode=access.PERSONAL, ended_reason=TrustedDevice.EndedReason.DEVICE_LIMIT)
        response = page(client)
        assert query(response) == {"next": "/sale/pos", "notice": "device_limit"}

    def test_a_browser_that_never_had_a_session_hears_nothing(self, client, ana):
        a_device(client)
        with_pin(ana)
        assert "notice" not in query(page(client))


class TestChoosingAPinAfterTheAccount:
    """``fake_saas`` vouches for Ana (``saas:42``); Bea already enters this hub's tills with her PIN."""

    @pytest.fixture
    def bea_has_a_pin(self, make_user):
        with_pin(make_user("saas:2", host="a", first_name="Bea"), "9071")

    def test_a_person_without_a_pin_on_a_device_that_asks_is_asked_to_choose_one_first(self, client, fake_saas, bea_has_a_pin):
        fake_saas()
        response = enter(client, "/sale/pos")
        assert response["Location"] == "/pin/setup?next=%2Fsale%2Fpos"

    def test_a_business_nobody_of_which_has_a_pin_is_never_asked(self, client, fake_saas, make_user):
        fake_saas()
        with_pin(make_user("saas:7", host="b"), "9071")  # another hub's PIN says nothing of this one
        assert enter(client, "/sale/pos")["Location"] == "/sale/pos"

    def test_a_person_with_a_pin_goes_on_to_next(self, client, fake_saas, bea_has_a_pin):
        fake_saas()
        enter(client, "/sale/pos")
        Credential.objects.create(username="saas:42", pin_hash=make_password("4826", hasher="argon2"))
        assert enter(client, "/sale/pos")["Location"] == "/sale/pos"

    @pytest.mark.parametrize("how", ["personal", "never"])
    def test_where_the_pin_is_not_offered_it_goes_on_to_next(self, client, fake_saas, bea_has_a_pin, how):
        fake_saas()
        enter(client, "/sale/pos")
        if how == "personal":
            TrustedDevice.objects.update(mode=access.PERSONAL)
        else:
            AccessSettings.objects.create(pin_policy=access.NEVER)
        assert enter(client, "/sale/pos")["Location"] == "/sale/pos"


class TestSigningOut:
    def test_on_a_device_with_the_pin_pad_it_goes_back_to_the_pin_pad(self, client, ana):
        a_device(client)
        with_pin(ana)
        client.force_login(ana)
        response = client.post("/auth/logout", HTTP_HOST=HOST)
        assert (response.status_code, response["Location"]) == (302, "/login")
        assert not Session.objects.exists()

    def test_anywhere_else_it_goes_on_to_erplora_com_s_sign_out_as_before(self, client, ana):
        client.force_login(ana)
        response = client.post("/auth/logout", HTTP_HOST=HOST)
        assert response["Location"] == "http://localhost:8001/accounts/logout/"
