"""What the SPA's HTML tells the shell about the way in of this session (``hub-home``'s ``access``; APP-BASE-3).

- «Switch user» (BASE-G60) only on a shared device of the hub of a business that asks, with somebody on its grid.
- The lock after inactivity (BASE-G59) only there and when the business always asks: its minutes, served with the
  session itself, so a till never has to read them on its own and fall back to anything (gh:hub#2537, hub#2677).
- erplora.com's pages (account, report, plan, the bar's «erplora.com») only for a session opened with the account: a
  session opened with a PIN or a badge on a shared till is not that browser's erplora.com account (gh:hub#2506).
"""

import json
import re

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from base import access
from base.models import AccessSettings, Credential, Membership, Profile, TrustedDevice

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def hub_home(client) -> dict:
    html = client.get("/", HTTP_HOST=HOST, HTTP_ACCEPT="text/html").content.decode()
    match = re.search(r'<script id="hub-home" type="application/json"[^>]*>(.*?)</script>', html, re.S)
    assert match, html[:400]
    return json.loads(match.group(1))


def a_device(client, mode=access.SHARED) -> TrustedDevice:
    token = access.new_device_token()
    device = TrustedDevice.objects.create(token_digest=access.token_digest(token), mode=mode, last_entry_at=timezone.now())
    client.cookies[access.DEVICE_COOKIE] = token
    return device


def with_pin(user, digits) -> Credential:
    return Credential.objects.create(username=user.username, pin_hash=make_password(digits, hasher="argon2"))


def enter_with_pin(client, credential, digits):
    body = json.dumps({"person": str(credential.pk), "pin": digits, "next": "/"})
    assert client.post("/auth/pin", body, content_type="application/json", HTTP_HOST=HOST).status_code == 200


@pytest.fixture
def people(make_user, saas, spa_manifest):
    ana = make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Ana")
    bea = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Bea")
    return ana, bea


def test_an_account_s_session_keeps_erplora_com_s_pages_and_no_switch_off_a_till(client, people):
    ana, _ = people
    client.force_login(ana)
    home = hub_home(client)
    assert home["account_url"] and home["report_url"] and home["plan_url"] and home["members_url"] and home["manage_url"]
    assert home["access"] == {"credential": "account", "switch_user": False, "idle_minutes": None}


def test_a_pin_session_on_a_till_switches_user_and_never_names_erplora_com(client, people):
    ana, bea = people
    a_device(client)
    with_pin(ana, "4826")
    enter_with_pin(client, with_pin(bea, "9071"), "9071")
    home = hub_home(client)
    assert (home["account_url"], home["report_url"], home["plan_url"], home["members_url"]) == ("", "", "", "")
    assert home["access"] == {"credential": "pin", "switch_user": True, "idle_minutes": None}


def test_the_owner_entering_with_her_pin_gets_no_way_to_erplora_com_in_the_bar(client, people):
    # BASE-F11, gh:hub#2506: the owner may open erplora.com's panel, but a PIN on a shared till is a credential of the
    # shift, not her account: the bar's «erplora.com» is empty, as every other erplora.com page.
    ana, _ = people
    a_device(client)
    enter_with_pin(client, with_pin(ana, "4826"), "4826")
    home = hub_home(client)
    assert (home["access"]["credential"], home["manage_url"]) == ("pin", "")


def test_a_till_of_a_business_that_always_asks_locks_after_its_minutes(client, people):
    ana, _ = people
    AccessSettings.objects.create(pin_policy=access.ALWAYS, pin_inactivity_minutes=10)
    a_device(client)
    enter_with_pin(client, with_pin(ana, "4826"), "4826")
    assert hub_home(client)["access"]["idle_minutes"] == 10


def test_a_personal_device_never_locks_nor_switches(client, people):
    ana, _ = people
    AccessSettings.objects.create(pin_policy=access.ALWAYS)
    a_device(client, mode=access.PERSONAL)
    with_pin(ana, "4826")
    client.force_login(ana)
    assert hub_home(client)["access"] == {"credential": "account", "switch_user": False, "idle_minutes": None}


def test_the_person_s_own_appearance_comes_with_the_html_on_any_device(client, people):
    # BASE-G125: the mode and palette chosen in «My profile» follow the person to every device they enter; empty, the
    # business's (and the browser's own toggle).
    ana, bea = people
    Profile.objects.create(username=ana.username, theme_mode="dark", palette="forest")
    client.force_login(ana)
    assert hub_home(client)["preferences"] == {"theme_mode": "dark", "palette": "forest"}
    client.force_login(bea)
    assert hub_home(client)["preferences"] == {"theme_mode": "", "palette": ""}
