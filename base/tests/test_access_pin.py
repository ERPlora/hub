"""BASE-G54/G55 (and the server's side of G60): the PIN of a person and entering with it on a shared device.

On a device of the hub (one where someone entered with their account) that is shared, of a business that asks who is
at the till, the way in is the PIN pad: the people of this hub with a PIN (name and initials, never their email), and
their PIN, checked by the Hub. Wrong PINs are counted against the person (5 in 5 minutes) and against the address (20 in
15 minutes, whoever they tried); a right one opens the person's session for a shift and, over a session of someone else
(«Switch user»), ends that one only once the new one exists.
"""

import datetime as dt
import json
from uuid import uuid4

import pytest
from django.contrib.auth.hashers import identify_hasher, make_password
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent

from base import access
from base.models import AccessSettings, Credential, Membership, SessionOwner, TrustedDevice

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
B_HOST = "b.localhost:8000"


def a_device(client, mode=access.SHARED) -> TrustedDevice:
    token = access.new_device_token()
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), mode=mode, last_entry_at=timezone.now())
    client.cookies[access.DEVICE_COOKIE] = token
    return device


def with_pin(user, pin: str) -> Credential:
    return Credential.objects.create(username=user.username, pin_hash=make_password(pin, hasher="argon2"), pin_set_at=timezone.now())


def door(client, host=HOST):
    response = client.get("/api/access/door", HTTP_HOST=host)
    assert response.status_code == 200, response.content
    return response.json()


def pin(client, person, digits, next_path="/sale/pos", host=HOST, **extra):
    body = {"person": str(person), "pin": digits, "next": next_path}
    return client.post("/auth/pin", json.dumps(body), content_type="application/json", HTTP_HOST=host, **extra)


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def ana(make_user):
    return make_user("saas:1", host="a", role=Membership.Role.EMPLOYEE, first_name="Ana", last_name="López", email="ana@example.com")


@pytest.fixture
def bea(make_user):
    return make_user("saas:2", host="a", role=Membership.Role.MANAGER, first_name="Bea", email="bea@example.com")


class TestTheDoor:
    def test_a_shared_device_of_the_hub_lists_its_people_with_a_pin_by_name_and_initials(self, client, ana, bea, make_user):
        a_device(client)
        with_pin(ana, "4826")
        with_pin(bea, "9071")
        make_user("saas:3", host="a", first_name="Carla")  # no PIN: not on the grid
        answer = door(client)
        assert (answer["pin"], answer["pin_length"], answer["wait"]) == (True, 4, 0)
        assert [(p["name"], p["initials"]) for p in answer["people"]] == [("Ana López", "AL"), ("Bea", "B")]
        assert {p["id"] for p in answer["people"]} == {str(c.pk) for c in Credential.objects.all()}
        assert "example.com" not in json.dumps(answer) and "saas:" not in json.dumps(answer)

    def test_an_account_without_a_name_is_on_the_grid_without_its_email(self, client, make_user):
        # The SaaS names a person without a name by their email (`full_name or email`); the grid is seen by anyone at
        # the till, so it shows the part before the «@», never the address (gh:hub#2536).
        a_device(client)
        with_pin(make_user("saas:5", host="a", first_name="carla.ruiz@example.com", email="carla.ruiz@example.com"), "4826")
        faces = door(client)["people"]
        assert [(p["name"], p["initials"]) for p in faces] == [("carla.ruiz", "C")]
        assert "example.com" not in json.dumps(faces)

    def test_only_the_active_people_of_this_hub(self, client, ana, make_user):
        a_device(client)
        with_pin(ana, "4826")
        with_pin(make_user("saas:7", host="b", first_name="Bruno"), "1357")
        with_pin(make_user("saas:8", host="a", first_name="Gone", is_active=False), "2468")
        assert [p["name"] for p in door(client)["people"]] == ["Ana López"]

    @pytest.mark.parametrize("how", ["no_cookie", "unknown_device", "personal", "never"])
    def test_anywhere_else_there_is_no_pin_pad_and_nobody_is_named(self, client, ana, how):
        with_pin(ana, "4826")
        if how == "unknown_device":
            client.cookies[access.DEVICE_COOKIE] = access.new_device_token()
        elif how != "no_cookie":
            a_device(client, mode=access.PERSONAL if how == "personal" else access.SHARED)
        if how == "never":
            AccessSettings.objects.create(pin_policy=access.NEVER)
        answer = door(client)
        assert (answer["pin"], answer["people"]) == (False, [])

    def test_the_door_carries_erplora_com_s_plans_without_naming_the_business(self, client, ana, settings):
        # BASE-G57: «Upgrade plan» after another device's entry ended this one; nobody is signed in, so the link is
        # the Store's plans of erplora.com (which asks who it is), never this hub's id.
        settings.SAAS_URL = "https://erplora.example"
        answer = door(client)
        assert answer["plan_url"] == "https://erplora.example/store/plans"

    def test_a_business_of_six_digit_pins_says_so(self, client, ana):
        a_device(client)
        with_pin(ana, "482613")
        AccessSettings.objects.create(pin_length=6)
        assert door(client)["pin_length"] == 6

    def test_an_address_that_tried_too_many_pins_hears_how_long_to_wait_and_nobody_is_named(self, client, ana):
        a_device(client)
        with_pin(ana, "4826")
        for _ in range(20):
            pin(client, uuid4(), "0000")  # 20 names: each one's own count stays under its 5
        answer = door(client)
        assert answer["people"] == [] and answer["wait"] > 0


class TestEnteringWithThePin:
    def test_the_right_pin_opens_the_person_s_session_on_this_device_for_a_shift(self, client, ana):
        device = a_device(client)
        cred = with_pin(ana, "4826")
        response = pin(client, cred.pk, "4826")
        assert (response.status_code, response.json()) == (200, {"next": "/sale/pos"})
        me = client.get("/api/me", HTTP_HOST=HOST).json()
        assert me["user"]["label"] == "Ana López"
        owner = SessionOwner.objects.get()
        assert (owner.saas_user_id, owner.host, owner.device_id, owner.credential) == ("1", "a", device.pk, "pin")
        lasts = client.session.get_expiry_date() - timezone.now()
        assert dt.timedelta(hours=11, minutes=59) < lasts <= dt.timedelta(hours=12)
        device.refresh_from_db()
        assert (device.last_username, device.last_user_label) == ("saas:1", "Ana López")

    @pytest.mark.parametrize(("own", "business", "cookie"), [("en", "es", "en"), ("", "es", "es")])
    def test_the_entry_leaves_the_person_s_language_so_a_reload_speaks_it_at_once(self, client, ana, own, business, cookie):
        # gh:hub#2639: the page Django serves after the entry, and every reload, is in the person's language from the
        # first paint (their «My profile» choice, else the business's): never a moment in the business's.
        from django.conf import settings

        from base.models import Hub, Profile

        Hub.objects.filter(slug="a").update(language=business)
        Profile.objects.create(username=ana.username, first_name="Ana", language=own)
        a_device(client)
        response = pin(client, with_pin(ana, "4826").pk, "4826")
        assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == cookie

    def test_a_wrong_pin_says_so_and_opens_nothing(self, client, ana):
        a_device(client)
        cred = with_pin(ana, "4826")
        response = pin(client, cred.pk, "4827")
        assert (response.status_code, code(response)) == (401, "base.pin_incorrect")
        assert client.get("/api/me", HTTP_HOST=HOST).json()["user"] is None

    def test_the_pin_pad_s_refusals_speak_the_till_s_language(self, client, ana):
        # The pad paints the Hub's sentence as it comes: a Spanish till reads it in Spanish (base/locale, en + es).
        a_device(client)
        cred = with_pin(ana, "4826")
        response = pin(client, cred.pk, "4827", HTTP_ACCEPT_LANGUAGE="es")
        assert response.json()["error"]["message"] == "PIN incorrecto."
        client.cookies.pop(access.DEVICE_COOKIE)
        refused = pin(client, cred.pk, "4826", HTTP_ACCEPT_LANGUAGE="es")
        assert refused.json()["error"]["message"].startswith("En este dispositivo todavía no funciona el PIN.")

    @pytest.mark.parametrize("who", ["another_hubs", "deactivated", "unknown", "not_an_id", "no_pin"])
    def test_whoever_is_not_a_person_of_this_hub_with_that_pin_hears_the_same(self, client, make_user, who):
        a_device(client)
        if who == "another_hubs":
            person = with_pin(make_user("saas:7", host="b"), "4826").pk
        elif who == "deactivated":
            person = with_pin(make_user("saas:8", host="a", is_active=False), "4826").pk
        elif who == "no_pin":
            person = Credential.objects.create(username=make_user("saas:9", host="a").username).pk
        else:
            person = uuid4() if who == "unknown" else "x"
        response = pin(client, person, "4826")
        assert (response.status_code, code(response)) == (401, "base.pin_incorrect")

    def test_five_wrong_pins_for_one_person_make_it_wait_and_a_right_one_before_starts_again(self, client, ana, bea):
        a_device(client)
        cred = with_pin(ana, "4826")
        for _ in range(4):
            pin(client, cred.pk, "1111")
        assert pin(client, cred.pk, "4826").status_code == 200
        client.post("/auth/logout", HTTP_HOST=HOST)
        for _ in range(5):
            assert pin(client, cred.pk, "1111").status_code == 401
        refused = pin(client, cred.pk, "4826")
        assert (refused.status_code, code(refused)) == (429, "base.too_many_attempts")
        assert 0 < int(refused["Retry-After"]) <= 300
        other = with_pin(bea, "9071")
        assert pin(client, other.pk, "9071").status_code == 200

    def test_twenty_wrong_pins_from_one_address_close_the_pin_to_it_for_everyone_else_s_name(self, client, ana, bea):
        a_device(client)
        with_pin(ana, "4826")
        second = with_pin(bea, "9071")
        for _ in range(20):
            assert pin(client, uuid4(), "0000").status_code == 401
        refused = pin(client, second.pk, "9071")
        assert (refused.status_code, code(refused)) == (429, "base.too_many_attempts")
        elsewhere = Client(REMOTE_ADDR="10.0.0.9")
        a_device(elsewhere)
        assert pin(elsewhere, second.pk, "9071").status_code == 200

    def test_a_browser_that_is_no_device_of_the_hub_cannot_use_the_pin(self, client, ana):
        cred = with_pin(ana, "4826")
        response = pin(client, cred.pk, "4826")
        assert (response.status_code, code(response)) == (403, "base.device_not_trusted")
        client.cookies[access.DEVICE_COOKIE] = access.new_device_token()
        assert code(pin(client, cred.pk, "4826")) == "base.device_not_trusted"

    @pytest.mark.parametrize("how", ["personal", "never"])
    def test_where_the_pin_is_not_offered_it_does_not_open(self, client, ana, how):
        a_device(client, mode=access.PERSONAL if how == "personal" else access.SHARED)
        if how == "never":
            AccessSettings.objects.create(pin_policy=access.NEVER)
        response = pin(client, with_pin(ana, "4826").pk, "4826")
        assert (response.status_code, code(response)) == (403, "base.pin_not_offered")

    def test_a_pin_needs_this_hub_s_csrf_token(self, ana):
        strict = Client(enforce_csrf_checks=True)
        a_device(strict)
        assert pin(strict, with_pin(ana, "4826").pk, "4826").status_code == 403
        assert not SessionOwner.objects.exists()

    def test_next_is_a_path_of_this_hub_or_home(self, client, ana):
        a_device(client)
        response = pin(client, with_pin(ana, "4826").pk, "4826", next_path="https://evil.example/")
        assert response.json() == {"next": "/"}


class TestSwitchingUser:
    def test_a_right_pin_over_someone_s_session_ends_that_one_and_opens_the_new_one(self, client, ana, bea):
        a_device(client)
        pin(client, with_pin(ana, "4826").pk, "4826")
        before = client.session.session_key
        assert pin(client, with_pin(bea, "9071").pk, "9071").status_code == 200
        assert not Session.objects.filter(session_key=before).exists()
        assert client.get("/api/me", HTTP_HOST=HOST).json()["user"]["label"] == "Bea"
        assert list(SessionOwner.objects.values_list("saas_user_id", flat=True)) == ["2"]

    def test_a_wrong_pin_leaves_whoever_was_in_inside(self, client, ana, bea):
        a_device(client)
        pin(client, with_pin(ana, "4826").pk, "4826")
        with_pin(bea, "9071")
        assert pin(client, Credential.objects.get(username="saas:2").pk, "1111").status_code == 401
        assert client.get("/api/me", HTTP_HOST=HOST).json()["user"]["label"] == "Ana López"


def set_pin(client, digits, current="", host=HOST):
    return client.post(
        "/api/me/pin", json.dumps({"pin": digits, "current": current}), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def ana_in(client, ana):
    client.force_login(ana)
    return ana


class TestChoosingMyPin:
    def test_a_first_pin_is_kept_as_an_argon2id_hash_and_says_so_to_the_live_queries(self, client, ana_in):
        response = set_pin(client, "4826")
        assert (response.status_code, response.json()) == (200, {"set": True})
        cred = Credential.objects.get(username="saas:1")
        assert identify_hasher(cred.pin_hash).algorithm == "argon2" and "4826" not in cred.pin_hash
        assert cred.pin_hash.startswith("argon2$argon2id$")
        assert OutboxEvent.objects.filter(name="base.pin.set").count() == 1

    @pytest.mark.parametrize(("digits", "expected"), [("482", "base.pin_length"), ("48261", "base.pin_length"), ("48a6", "base.pin_digits"), ("1234", "base.pin_guessable"), ("7777", "base.pin_guessable")])
    def test_a_pin_the_business_would_not_take_is_refused_with_its_reason(self, client, ana_in, digits, expected):
        response = set_pin(client, digits)
        assert (response.status_code, code(response)) == (422, expected)
        assert not Credential.objects.exists()

    def test_six_digits_when_the_business_says_six(self, client, ana_in):
        AccessSettings.objects.create(pin_length=6)
        assert code(set_pin(client, "4826")) == "base.pin_length"
        assert set_pin(client, "482613").status_code == 200

    def test_changing_it_asks_for_the_current_one(self, client, ana_in):
        set_pin(client, "4826")
        wrong = set_pin(client, "9071", current="1111")
        assert (wrong.status_code, code(wrong)) == (403, "base.pin_current_wrong")
        assert set_pin(client, "9071", current="4826").status_code == 200
        assert pin_matches("saas:1", "9071")

    def test_a_pin_another_active_person_of_this_hub_has_is_refused(self, client, ana_in, bea, make_user):
        with_pin(bea, "9071")
        taken = set_pin(client, "9071")
        assert (taken.status_code, code(taken)) == (409, "base.pin_taken")
        with_pin(make_user("saas:7", host="b"), "1357")
        assert set_pin(client, "1357").status_code == 200

    def test_thirty_tries_in_an_hour_make_it_wait_whether_they_were_taken_or_not(self, client, ana_in):
        for attempt in range(30):
            set_pin(client, "4826" if attempt == 0 else "1111", current="4826")
        refused = set_pin(client, "9071", current="4826")
        assert (refused.status_code, code(refused)) == (429, "base.too_many_pin_changes")

    def test_without_a_session_nobody_sets_a_pin(self, client, ana):
        assert set_pin(client, "4826").status_code == 401


def pin_matches(username, digits):
    from django.contrib.auth.hashers import check_password

    return check_password(digits, Credential.objects.get(username=username).pin_hash)
