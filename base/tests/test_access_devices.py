"""BASE-G57, G63–G66 and G72: the devices of the hub.

- G72: from the device itself, an administrator decides whether it is shared (a till: PIN, a shift) or personal (no
  PIN, 30 days); the sessions open from now on follow it, the open one keeps its end.
- G63–G66: the administrators see the devices someone entered from (never their token), name them, remove a lost one
  (its sessions end at once and the PIN stops working on it) and remove at once those nobody used in 30 days.
- G57: a plan that covers N devices (``plan.max_devices`` of the SaaS's photo) ends, at each entry, the sessions of
  the other devices past the N - 1 most recent; each of them says why at its next way in.
"""

import datetime as dt
import json

import pytest
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent

from base import access
from base.models import Hub, Membership, SessionOwner, TrustedDevice
from base.tests.test_access_account import enter

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def a_device(client, mode=access.SHARED, **fields) -> TrustedDevice:
    token = access.new_device_token()
    fields.setdefault("last_entry_at", timezone.now())
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), mode=mode, **fields)
    client.cookies[access.DEVICE_COOKIE] = token
    return device


def get(client, path):
    return client.get(f"/api{path}", HTTP_HOST=HOST)


def post(client, path, body=None):
    return client.post(f"/api{path}", json.dumps(body or {}), content_type="application/json", HTTP_HOST=HOST)


def code(response):
    return response.json()["error"]["code"]


@pytest.fixture
def owner(client, make_user):
    user = make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Olga")
    client.force_login(user)
    return user


@pytest.fixture
def employee(client, make_user):
    user = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva")
    client.force_login(user)
    return user


class TestThisDevice:
    def test_it_says_its_mode_and_whether_the_hub_knows_it(self, client, owner):
        assert get(client, "/device").json() == {"known": False, "mode": "shared", "mode_set_by": "", "mode_set_at": None}
        a_device(client, mode=access.PERSONAL)
        answer = get(client, "/device").json()
        assert (answer["known"], answer["mode"]) == (True, "personal")

    def test_an_administrator_makes_it_personal_from_the_device_itself(self, client, owner):
        device = a_device(client)
        response = post(client, "/device/mode", {"mode": "personal"})
        assert response.status_code == 200 and response.json()["mode"] == "personal"
        device.refresh_from_db()
        assert (device.mode, device.mode_set_by) == ("personal", "Olga")
        assert device.mode_set_at is not None
        assert OutboxEvent.objects.filter(name="base.device.mode_changed").count() == 1

    def test_a_device_nobody_entered_with_an_account_cannot_be_set(self, client, owner):
        response = post(client, "/device/mode", {"mode": "personal"})
        assert (response.status_code, code(response)) == (404, "base.device_unknown")
        assert "account" in response.json()["error"]["message"]

    def test_only_an_administrator(self, client, employee):
        a_device(client)
        assert post(client, "/device/mode", {"mode": "personal"}).status_code == 403

    def test_a_mode_it_does_not_know_is_refused(self, client, owner):
        a_device(client)
        assert post(client, "/device/mode", {"mode": "kiosk"}).status_code == 422

    def test_the_sessions_open_from_now_on_follow_it_and_the_open_one_keeps_its_end(self, client, fake_saas):
        fake_saas()
        enter(client)
        Membership.objects.filter(host="a").update(role=Membership.Role.OWNER)
        until = client.session.get_expiry_date()
        post(client, "/device/mode", {"mode": "personal"})
        assert client.session.get_expiry_date() == until
        enter(client)
        assert client.session.get_expiry_date() - timezone.now() > dt.timedelta(days=29)


class TestTheDevicesOfTheHub:
    def test_an_administrator_sees_each_device_without_its_token(self, client, owner):
        here = a_device(client, name="Bar", agent="Chrome · Android", last_user_label="Olga")
        token = client.cookies[access.DEVICE_COOKIE].value
        other = TrustedDevice.objects.create(
            token_digest="0" * 64, agent="Safari · iPad", last_entry_at=timezone.now() - dt.timedelta(days=40)
        )
        answer = get(client, "/devices").json()
        rows = {row["id"]: row for row in answer["devices"]}
        assert set(rows) == {str(here.pk), str(other.pk)}
        assert (rows[str(here.pk)]["name"], rows[str(here.pk)]["current"], rows[str(here.pk)]["last_user"]) == ("Bar", True, "Olga")
        assert (rows[str(other.pk)]["current"], rows[str(other.pk)]["unused"]) == (False, True)
        assert answer["unused"] == 1
        assert token not in json.dumps(answer) and "token" not in json.dumps(answer)

    def test_the_one_in_hand_is_never_unused_however_old(self, client, owner):
        here = a_device(client, last_entry_at=timezone.now() - dt.timedelta(days=40))
        answer = get(client, "/devices").json()
        [row] = [row for row in answer["devices"] if row["id"] == str(here.pk)]
        assert (row["current"], row["unused"], answer["unused"]) == (True, False, 0)

    def test_it_says_which_one_has_a_session_open_and_until_when(self, client, fake_saas):
        fake_saas()
        enter(client)
        Membership.objects.filter(host="a").update(role=Membership.Role.OWNER)
        [row] = get(client, "/devices").json()["devices"]
        assert row["in_use"] is True
        assert row["session_until"] is not None

    def test_only_an_administrator_sees_them(self, client, employee):
        assert get(client, "/devices").status_code == 403

    def test_naming_one(self, client, owner):
        device = a_device(client)
        assert post(client, "/devices/rename", {"id": str(device.pk), "name": "  Kitchen  "}).status_code == 200
        device.refresh_from_db()
        assert device.name == "Kitchen"
        assert OutboxEvent.objects.filter(name="base.device.renamed").count() == 1
        too_long = post(client, "/devices/rename", {"id": str(device.pk), "name": "x" * 61})
        assert too_long.status_code == 422

    def test_removing_a_lost_one_ends_its_sessions_at_once_and_the_pin_with_it(self, client, owner, fake_saas):
        fake_saas()
        lost = Client()
        enter(lost)
        lost_device = TrustedDevice.objects.get()
        a_device(client)
        response = post(client, "/devices/remove", {"id": str(lost_device.pk)})
        assert (response.status_code, response.json()) == (200, {"removed": 1, "yours": False})
        assert not TrustedDevice.objects.filter(pk=lost_device.pk).exists()
        assert lost.get("/api/me", HTTP_HOST=HOST).json()["user"] is None
        assert OutboxEvent.objects.filter(name="base.device.removed").count() == 1

    def test_removing_the_one_in_your_hand_ends_your_session(self, client, fake_saas):
        fake_saas()
        enter(client)
        Membership.objects.filter(host="a").update(role=Membership.Role.OWNER)
        device = TrustedDevice.objects.get()
        assert post(client, "/devices/remove", {"id": str(device.pk)}).json() == {"removed": 1, "yours": True}
        assert client.get("/api/me", HTTP_HOST=HOST).json()["user"] is None

    def test_removing_one_that_is_gone_says_so(self, client, owner):
        response = post(client, "/devices/remove", {"id": "01a16b35-d6b9-71ea-84a7-7880b22e3139"})
        assert (response.status_code, code(response)) == (404, "base.device_unknown")

    def test_removing_those_nobody_used_in_thirty_days_keeps_the_rest_and_the_one_in_hand(self, client, owner):
        old = timezone.now() - dt.timedelta(days=31)
        here = a_device(client, last_entry_at=old)
        unused = TrustedDevice.objects.create(token_digest="1" * 64, last_entry_at=old)
        recent = TrustedDevice.objects.create(token_digest="2" * 64, last_entry_at=timezone.now() - dt.timedelta(days=29))
        assert post(client, "/devices/prune").json() == {"removed": 1}
        assert set(TrustedDevice.objects.values_list("pk", flat=True)) == {here.pk, recent.pk}
        assert not TrustedDevice.objects.filter(pk=unused.pk).exists()
        assert OutboxEvent.objects.filter(name="base.device.pruned").count() == 1


class TestThePlanCoversOneDevice:
    @pytest.fixture
    def one_device(self, db):
        Hub.objects.filter(slug="a").update(state={"plan": {"max_devices": 1}})

    def test_entering_on_another_device_ends_this_one_s_session_and_says_why(self, fake_saas, one_device):
        fake_saas()
        first, second = Client(), Client()
        enter(first)
        enter(second)
        assert first.get("/api/me", HTTP_HOST=HOST).json()["user"] is None
        assert second.get("/api/me", HTTP_HOST=HOST).json()["user"] is not None
        evicted = TrustedDevice.objects.get(token_digest=access.token_digest(first.cookies[access.DEVICE_COOKIE].value))
        assert evicted.ended_reason == "device_limit"
        response = first.get("/sale/pos", HTTP_HOST=HOST, HTTP_ACCEPT="text/html")
        assert "notice=device_limit" in response["Location"]

    def test_entering_again_on_the_same_device_ends_nothing(self, client, fake_saas, one_device):
        fake_saas()
        enter(client)
        other = Client()
        enter(other)
        enter(other)
        assert other.get("/api/me", HTTP_HOST=HOST).json()["user"] is not None
        assert Session.objects.count() == 1

    def test_a_plan_without_a_cap_ends_nothing(self, fake_saas):
        fake_saas()
        first, second = Client(), Client()
        enter(first)
        enter(second)
        assert first.get("/api/me", HTTP_HOST=HOST).json()["user"] is not None

    def test_two_devices_keep_the_most_recent_other_one(self, fake_saas):
        Hub.objects.filter(slug="a").update(state={"plan": {"max_devices": 2}})
        fake_saas()
        oldest, newer, entering = Client(), Client(), Client()
        enter(oldest)
        enter(newer)
        enter(entering)
        assert oldest.get("/api/me", HTTP_HOST=HOST).json()["user"] is None
        assert newer.get("/api/me", HTTP_HOST=HOST).json()["user"] is not None

    def test_the_next_entry_on_the_evicted_device_forgets_why(self, fake_saas, one_device):
        fake_saas()
        first, second = Client(), Client()
        enter(first)
        enter(second)
        enter(first)
        token = first.cookies[access.DEVICE_COOKIE].value
        assert TrustedDevice.objects.get(token_digest=access.token_digest(token)).ended_reason == ""

    def test_the_session_s_note_names_the_device_it_was_on(self, fake_saas, one_device):
        fake_saas()
        first = Client()
        enter(first)
        assert SessionOwner.objects.get().device_id == TrustedDevice.objects.get().pk
