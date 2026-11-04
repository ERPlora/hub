"""BASE-F11 · the pass to erplora.com: «Upgrade plan» and «Manage on erplora.com» arrive already signed in (saas#190).

``base.saas_pass.create`` signs, at the click, what erplora.com's ``GET /hub-pass/`` reads (ACCOUNTS-F29 of the SaaS,
``accounts/hub_pass.py``): the Hub never asks the SaaS anything per request (PLAN-SAAS §2). These tests read the pass
as the SaaS does, ``django.core.signing`` with ``INTERNAL_SHARED_SECRET``, its salt and its minute. A pass opens a
session on erplora.com, so it goes only to a session opened with the account: a PIN or a badge on a shared till is
not the browser's erplora.com account (gh:hub#2506).
"""

import json
import logging
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.core import signing
from django.test import Client
from live.operations import INTERNAL
from live.operations import get as get_operation

from base import services
from base.models import Membership
from base.tests.conftest import ANA, SECRET
from base.tests.test_access_account import enter
from base.tests.test_access_badge import badge, with_badge
from base.tests.test_access_spa import a_device, enter_with_pin, with_pin
from base.tests.test_auth_views import DEEP_LINK, PLATFORM, ROOT, callback

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
URL = "/api/saas-pass"
#: What erplora.com's ``accounts/hub_pass.py`` reads: its salt, its minute and the shape of a nonce.
SALT = "erplora.hub-pass.v1"
MAX_AGE = 60
NONCE = re.compile(r"[A-Za-z0-9_-]{16,128}")
ACCOUNT_ID = "019a2b3c-0000-7000-8000-000000000042"


def ask(client, next_="plan", host=HOST):
    return client.post(URL, json.dumps({"next": next_}), content_type="application/json", HTTP_HOST=host)


def a_person(make_user, role):
    return make_user(f"saas:{ACCOUNT_ID}", host="a", role=role, first_name="Ana")


@pytest.fixture
def account(client, make_user, fake_saas, spa_manifest):
    """Ana, who runs the shift, enters with her erplora.com account the real way: the SaaS's jump and its code."""
    fake_saas(body={**ANA, "user_id": ACCOUNT_ID, "locale": "en"})
    person = a_person(make_user, Membership.Role.MANAGER)
    assert enter(client).status_code == 302
    return person


def the_pass(response) -> str:
    assert response.status_code == 200, response.content[:300]
    address = urlsplit(response.json()["url"])
    [token] = parse_qs(address.query, strict_parsing=True)["pass"]
    return token


def read_as_the_saas(token: str) -> dict:
    return signing.loads(token, key=SECRET, salt=SALT, max_age=MAX_AGE)


class TestTheContract:
    def test_it_says_what_erplora_com_reads_for_the_plan(self, client, account):
        said = read_as_the_saas(the_pass(ask(client, "plan")))

        assert set(said) == {"user", "hub", "next", "nonce"}
        assert (said["user"], said["hub"], said["next"]) == (ACCOUNT_ID, "a", "plan")
        assert NONCE.fullmatch(said["nonce"])

    def test_it_says_what_erplora_com_reads_for_the_business(self, client, account):
        said = read_as_the_saas(the_pass(ask(client, "business")))

        assert (said["user"], said["hub"], said["next"]) == (ACCOUNT_ID, "a", "business")

    def test_the_address_is_erplora_com_s_door_with_the_pass_encoded(self, client, account):
        response = ask(client)
        token = the_pass(response)

        assert response.json() == {"url": f"http://localhost:8001/hub-pass/?{urlencode({'pass': token})}"}

    def test_a_saas_url_with_a_final_slash_makes_no_double_slash(self, client, account, settings):
        settings.SAAS_URL = "https://erplora.com/"

        assert ask(client).json()["url"].startswith("https://erplora.com/hub-pass/?pass=")

    def test_every_pass_has_its_own_nonce(self, client, account):
        nonces = {read_as_the_saas(the_pass(ask(client)))["nonce"] for _ in range(3)}

        assert len(nonces) == 3

    def test_it_goes_uncompressed_as_the_contract_says(self, client, account):
        # ``signing.dumps(..., compress=True)`` starts with a dot: the contract signs it without.
        assert not the_pass(ask(client)).startswith(".")

    def test_only_the_shared_secret_and_its_salt_read_it(self, client, account, settings):
        token = the_pass(ask(client))

        for key, salt in ((settings.SECRET_KEY, SALT), ("another-secret", SALT), (SECRET, "erplora.hub-pass.v2")):
            with pytest.raises(signing.BadSignature):
                signing.loads(token, key=key, salt=salt)

    def test_during_a_rotation_it_signs_with_the_current_secret(self, client, account, settings):
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = "the-old-one"
        settings.INTERNAL_SHARED_SECRET = "the-new-one"

        token = the_pass(ask(client))

        assert signing.loads(token, key="the-new-one", salt=SALT, max_age=MAX_AGE)["next"] == "plan"
        with pytest.raises(signing.BadSignature):
            signing.loads(token, key="the-old-one", salt=SALT)

    def test_without_the_shared_secret_it_signs_nothing_never_with_the_secret_key(self, client, account, settings):
        # Django's signer falls back on SECRET_KEY when the key is empty; erplora.com would refuse that pass anyway.
        settings.INTERNAL_SHARED_SECRET = ""

        response = ask(client)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "base.saas_pass_unavailable"

    @pytest.mark.parametrize("next_", ["account", "", "PLAN", None])
    def test_it_only_leads_to_the_plan_or_the_business(self, client, account, next_):
        response = client.post(URL, json.dumps({"next": next_}), content_type="application/json", HTTP_HOST=HOST)

        assert response.status_code == 422

    def test_it_needs_to_be_told_where_it_leads(self, client, account):
        assert client.post(URL, "{}", content_type="application/json", HTTP_HOST=HOST).status_code == 422

    def test_the_pass_is_never_logged(self, client, account, caplog):
        with caplog.at_level(logging.DEBUG):
            token = the_pass(ask(client))

        signature = token.rsplit(":", 1)[-1]
        assert signature not in caplog.text
        assert token not in caplog.text

    def test_it_is_a_door_of_the_screen_never_a_tool_of_the_assistant_and_keeps_nothing(self):
        # A pass in a chat would stay in its history and in the model's context for a minute.
        operation = get_operation("base.saas_pass.create")

        assert operation.ai is INTERNAL
        assert operation.database is False


class TestOnlyWithTheAccount:
    def refused(self, response):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.saas_pass_needs_account"
        assert "url" not in response.json()

    def test_a_pin_session_on_a_till_gets_no_pass(self, client, make_user, spa_manifest, saas):
        bea = make_user("saas:2", host="a", role=Membership.Role.OWNER, first_name="Bea")
        a_device(client)
        enter_with_pin(client, with_pin(bea, "9071"), "9071")

        self.refused(ask(client))
        self.refused(ask(client, "business"))

    def test_a_badge_session_on_a_till_gets_no_pass(self, client, make_user, spa_manifest, saas):
        bea = make_user("saas:2", host="a", role=Membership.Role.OWNER, first_name="Bea")
        a_device(client)
        with_badge(bea, "04a1b2c3")
        assert badge(client, "04a1b2c3").status_code == 200

        self.refused(ask(client))

    def test_a_session_that_does_not_say_how_it_was_opened_gets_no_pass(self, client, account):
        session = client.session
        del session[services.CREDENTIAL_SESSION_KEY]
        session.save()

        self.refused(ask(client))

    def test_a_person_who_is_no_erplora_com_account_gets_no_pass(self, client, make_user, spa_manifest, saas):
        # A demo's visitor: its shell says it entered with no PIN, only the missing account stops it.
        client.force_login(make_user("demo:a", host="a", role=Membership.Role.OWNER))
        assert client.get("/", HTTP_HOST=HOST, HTTP_ACCEPT="text/html").status_code == 200

        self.refused(ask(client))

    def test_without_a_session_it_is_refused(self, client, saas):
        assert ask(client).status_code in (401, 403)

    def test_the_platform_s_staff_on_hubs_erplora_com_get_no_pass(self, client, saas, spa_manifest, fake_saas):
        fake_saas(body=ROOT)
        assert callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM).status_code == 302

        # The platform's host has no business: everything but the admin goes back to the admin, nothing is signed.
        response = ask(client, host=PLATFORM)

        assert response.status_code == 302
        assert "hub-pass" not in response["Location"]


class TestTheBusinessNeedsItsPermission:
    def enter_as(self, client, make_user, fake_saas, role):
        # The role is the one erplora.com says at the jump, which overwrites the one kept here.
        fake_saas(body={**ANA, "user_id": ACCOUNT_ID, "locale": "en", "role": str(role)})
        a_person(make_user, role)
        assert enter(client).status_code == 302

    def test_an_employee_with_the_account_goes_to_the_plan_but_not_to_the_business(
        self, client, make_user, fake_saas, spa_manifest
    ):
        self.enter_as(client, make_user, fake_saas, Membership.Role.EMPLOYEE)

        assert read_as_the_saas(the_pass(ask(client, "plan")))["next"] == "plan"
        response = ask(client, "business")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.saas_pass_needs_management"

    @pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER])
    def test_who_runs_the_business_goes_to_the_business(self, client, make_user, fake_saas, spa_manifest, role):
        self.enter_as(client, make_user, fake_saas, role)

        assert read_as_the_saas(the_pass(ask(client, "business")))["next"] == "business"


class TestItsBusiness:
    def test_a_pass_names_the_business_of_the_address_it_was_asked_on(self, fake_saas, make_user, spa_manifest):
        # One account and two businesses: a session belongs to the host it was opened on, so each has its own browser
        # cookie, and each pass opens the door of the business it was asked on.
        fake_saas(body={**ANA, "user_id": ACCOUNT_ID, "locale": "en"})
        person = a_person(make_user, Membership.Role.MANAGER)
        Membership.objects.create(user=person, host="b", role=Membership.Role.MANAGER)
        on_a, on_b = Client(), Client()
        assert enter(on_a).status_code == 302
        assert enter(on_b, host="b.localhost:8000").status_code == 302

        assert read_as_the_saas(the_pass(ask(on_a)))["hub"] == "a"
        assert read_as_the_saas(the_pass(ask(on_b, host="b.localhost:8000")))["hub"] == "b"


class TestItsWords:
    def said_to_a_person_who_speaks(self, language, fake_saas, role, next_) -> dict:
        """What the operation answers a person of this role whom erplora.com says speaks this language."""
        fake_saas(body={**ANA, "user_id": ACCOUNT_ID, "locale": language, "role": str(role)})
        browser = Client()
        assert enter(browser).status_code == 302
        return ask(browser, next_).json()["error"]

    def test_no_permission_for_the_business_speaks_the_person_s_language(self, make_user, fake_saas, spa_manifest):
        a_person(make_user, Membership.Role.EMPLOYEE)

        english, spanish = (
            self.said_to_a_person_who_speaks(language, fake_saas, Membership.Role.EMPLOYEE, "business")
            for language in ("en", "es")
        )

        assert english["code"] == spanish["code"] == "base.saas_pass_needs_management"
        assert english["message"] != spanish["message"]

    def test_the_door_out_of_order_speaks_the_person_s_language(self, make_user, fake_saas, spa_manifest, settings):
        a_person(make_user, Membership.Role.MANAGER)
        settings.INTERNAL_SHARED_SECRET = ""

        english, spanish = (
            self.said_to_a_person_who_speaks(language, fake_saas, Membership.Role.MANAGER, "plan")
            for language in ("en", "es")
        )

        assert english["code"] == spanish["code"] == "base.saas_pass_unavailable"
        assert english["message"] != spanish["message"]

    def test_a_pin_s_refusal_speaks_the_browser_s_language(self, client, make_user, spa_manifest, saas):
        bea = make_user("saas:2", host="a", role=Membership.Role.OWNER, first_name="Bea")
        a_device(client)
        enter_with_pin(client, with_pin(bea, "9071"), "9071")

        english, spanish = (
            client.post(
                URL,
                json.dumps({"next": "plan"}),
                content_type="application/json",
                HTTP_HOST=HOST,
                HTTP_ACCEPT_LANGUAGE=language,
            ).json()["error"]
            for language in ("en", "es")
        )

        assert english["code"] == spanish["code"] == "base.saas_pass_needs_account"
        assert english["message"] != spanish["message"]
