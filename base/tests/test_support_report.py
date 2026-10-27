"""BASE-F108 · «Report a problem» from the user menu, without leaving the hub (FIX-HUB-BASE-REPORT-PROBLEM-MODAL).

``base.support.report`` sends erplora.com what the person wrote, signed v1 + v2 like ``/internal/auth/redeem``
(``POST {SAAS_INTERNAL_URL}/internal/support/report``), with who and where they are: the SaaS account of the session,
the business (its slug and id), the screen and the browser. erplora.com mails its support mailbox «Reply-To» that
account (ACCOUNTS-F38), so only a session opened with the account may report: a PIN on a shared till has nobody to
answer to (gh:hub#2506). Its limit is erplora.com's, per account (``SUPPORT_REPORT_RATELIMIT``): the hub keeps none.
A refusal of erplora.com, or erplora.com out of reach, is said with the address to write to; never a silent failure.
"""

import json

import pytest

from base import access, registry, signing
from base.models import Membership, SessionOwner, TrustedDevice
from base.services import CREDENTIAL_SESSION_KEY
from base.tests.conftest import ANA, SECRET
from base.tests.test_access_account import enter
from base.tests.test_access_badge import badge, with_badge
from base.tests.test_access_spa import a_device, enter_with_pin, with_pin

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
URL = "/api/support/report"
SAAS_PATH = "/internal/support/report"
BROWSER = "Mozilla/5.0 (iPad; CPU OS 18_0) ERPlora/1.4"
SENT = {"reply_to": "ana@example.com"}


@pytest.fixture(autouse=True)
def _support(settings):
    settings.SUPPORT_EMAIL = "support@example.com"


ACCOUNT_ID = "019a2b3c-0000-7000-8000-000000000042"


@pytest.fixture
def ana(make_user, saas, spa_manifest):
    return make_user(f"saas:{ACCOUNT_ID}", host="a", role=Membership.Role.MANAGER, first_name="Ana")


@pytest.fixture
def account(client, ana, fake_saas):
    """Ana enters with her erplora.com account the real way, the SaaS's jump and its one-time code, on a tablet (which
    makes it a shared device of the hub): ``_log_in`` keeps the session's credential in it. A test's own
    ``fake_saas`` then answers the report."""
    fake_saas(body={**ANA, "user_id": ACCOUNT_ID, "locale": "en"})
    assert enter(client).status_code == 302
    return ana


def load_the_shell(client) -> None:
    """The SPA's HTML, which the user menu (and its «Report a problem») comes from."""
    assert client.get("/", HTTP_HOST=HOST, HTTP_ACCEPT="text/html").status_code == 200


def forget_the_credential(client) -> None:
    """The session as one opened before ``_log_in`` kept its credential in it."""
    session = client.session
    del session[CREDENTIAL_SESSION_KEY]
    session.save()


def report(client, **body):
    payload = {"subject": "The printer stops", "description": "It prints half a ticket.", "page": "/sales/pos", **body}
    return client.post(URL, json.dumps(payload), content_type="application/json", HTTP_HOST=HOST, HTTP_USER_AGENT=BROWSER)


class TestSent:
    def test_it_reaches_erplora_com_signed_with_the_account_the_business_the_screen_and_the_browser(
        self, client, account, fake_saas
    ):
        saas = fake_saas(body=SENT)

        response = report(client, subject="  The printer stops  ", description=" It prints half a ticket.\n")

        assert response.status_code == 200, response.content
        assert response.json() == {"reply_to": "ana@example.com"}
        [call] = saas.calls
        assert call["url"] == f"http://localhost:8001{SAAS_PATH}"
        assert json.loads(call["body"]) == {
            "account": "019a2b3c-0000-7000-8000-000000000042",
            "hub": "a",
            "hub_id": str(registry.hub_id("a")),
            "page": "/sales/pos",
            "browser": BROWSER,
            "subject": "The printer stops",
            "description": "It prints half a ticket.",
        }

    def test_the_call_is_signed_v1_and_v2_with_the_shared_secret(self, client, account, fake_saas):
        saas = fake_saas(body=SENT)

        report(client)

        [call] = saas.calls
        headers, body = call["headers"], call["body"]
        timestamp = int(headers[signing.TIMESTAMP_HEADER])
        assert headers["Content-Type"] == "application/json"
        assert headers[signing.SIGNATURE_HEADER] == signing.sign(body, timestamp, SECRET)
        assert headers[signing.SIGNATURE_V2_HEADER] == signing.sign_v2("POST", SAAS_PATH, body, timestamp, SECRET)

    def test_without_a_screen_it_says_none(self, client, account, fake_saas):
        saas = fake_saas(body=SENT)

        report(client, page=None)

        assert json.loads(saas.calls[0]["body"])["page"] is None


class TestOnlyWithTheAccount:
    def test_a_pin_session_on_a_till_cannot_report_and_nothing_leaves(self, client, ana, make_user, fake_saas):
        saas = fake_saas(body=SENT)
        bea = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Bea")
        a_device(client)
        with_pin(ana, "4826")
        enter_with_pin(client, with_pin(bea, "9071"), "9071")

        response = report(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert saas.calls == []

    def test_a_pin_session_opened_before_the_session_kept_its_credential_cannot_report(
        self, client, ana, make_user, fake_saas
    ):
        # A PIN session of a shift opened before the deploy has no credential in the session; its SessionOwner says PIN.
        # Without the key it is no account's: never the account's by default.
        saas = fake_saas(body=SENT)
        bea = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Bea")
        a_device(client)
        enter_with_pin(client, with_pin(bea, "9071"), "9071")
        forget_the_credential(client)
        assert SessionOwner.objects.get(session_id=client.session.session_key).credential == SessionOwner.Credential.PIN

        response = report(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert saas.calls == []

    def test_a_session_opened_with_the_account_on_a_till_can(self, client, account, fake_saas):
        # The way in, not the device: she entered with her erplora.com account on a shared device of the hub.
        saas = fake_saas(body=SENT)
        owner = SessionOwner.objects.get(session_id=client.session.session_key)
        assert owner.credential == SessionOwner.Credential.ACCOUNT
        assert TrustedDevice.objects.get(pk=owner.device_id).mode == access.SHARED

        assert report(client).status_code == 200
        assert len(saas.calls) == 1

    def test_an_account_session_from_before_gets_its_credential_back_once_the_shell_loads(self, client, account, fake_saas):
        # The user menu only exists once the shell loaded: the shell writes in the session what SessionOwner says, so
        # the menu and the operation say the same.
        saas = fake_saas(body=SENT)
        forget_the_credential(client)
        assert report(client).status_code == 403

        load_the_shell(client)

        assert client.session[CREDENTIAL_SESSION_KEY] == SessionOwner.Credential.ACCOUNT
        assert report(client).status_code == 200
        assert len(saas.calls) == 1

    def test_a_pin_session_from_before_stays_refused_once_the_shell_loads(self, client, ana, make_user, fake_saas):
        saas = fake_saas(body=SENT)
        bea = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Bea")
        a_device(client)
        enter_with_pin(client, with_pin(bea, "9071"), "9071")
        forget_the_credential(client)

        load_the_shell(client)

        assert client.session[CREDENTIAL_SESSION_KEY] == SessionOwner.Credential.PIN
        response = report(client)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert saas.calls == []

    def test_a_person_who_is_no_erplora_com_account_cannot(self, client, make_user, saas, spa_manifest, fake_saas):
        # A demo's visitor (``demo:<slug>``) or any local copy without an account behind it.
        fake = fake_saas(body=SENT)
        client.force_login(make_user("demo:a", host="a", role=Membership.Role.OWNER))
        # Its shell says it entered with no PIN (a demo has no SessionOwner): only the missing account stops it.
        load_the_shell(client)
        assert client.session[CREDENTIAL_SESSION_KEY] == SessionOwner.Credential.ACCOUNT

        response = report(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert fake.calls == []

    def test_a_badge_session_on_a_till_cannot_report_and_nothing_leaves(self, client, ana, make_user, fake_saas):
        # A card on a shared till is the device's way in, like a PIN: the browser's erplora.com account is whoever
        # made it a device of the hub, never the person who swiped (gh:hub#2506).
        saas = fake_saas(body=SENT)
        bea = make_user("saas:2", host="a", role=Membership.Role.EMPLOYEE, first_name="Bea")
        a_device(client)
        with_badge(bea, "04a1b2c3")
        assert badge(client, "04a1b2c3").status_code == 200
        assert SessionOwner.objects.get(session_id=client.session.session_key).credential == SessionOwner.Credential.BADGE

        response = report(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert saas.calls == []

    def test_the_platform_s_staff_on_hubs_erplora_com_cannot_report_and_nothing_leaves(
        self, client, saas, spa_manifest, fake_saas
    ):
        # The staff's session on hubs.erplora.com is opened with their account too, but it is no customer's: no
        # report leaves it, with or without a hub chosen for the admin.
        from base.tests.test_auth_views import DEEP_LINK, PLATFORM, ROOT, callback

        fake_saas(body=ROOT)
        assert callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM).status_code == 302
        assert client.session[CREDENTIAL_SESSION_KEY] == SessionOwner.Credential.ACCOUNT
        fake = fake_saas(body=SENT)
        for chosen in (False, True):
            if chosen:
                assert client.get(DEEP_LINK, HTTP_HOST=PLATFORM).status_code == 302
            payload = {"subject": "The printer stops", "description": "It prints half a ticket."}
            response = client.post(URL, json.dumps(payload), content_type="application/json", HTTP_HOST=PLATFORM)
            # Without a hub chosen, the platform host sends everything to the admin; with one, the operation refuses.
            assert response.status_code in (302, 401, 403, 404), (chosen, response.status_code, response.content[:200])
            assert fake.calls == [], chosen

    def test_without_a_session_it_is_refused(self, client, saas, fake_saas):
        fake = fake_saas(body=SENT)

        assert report(client).status_code in (401, 403)
        assert fake.calls == []


class TestRefused:
    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({"subject": "   "}, "subject"),
            ({"description": "  "}, "description"),
            ({"subject": "x" * 151}, "subject"),
            ({"description": "x" * 5001}, "description"),
        ],
    )
    def test_what_is_missing_or_too_long_is_a_422_on_its_field_and_nothing_leaves(self, client, account, fake_saas, body, field):
        saas = fake_saas(body=SENT)

        response = report(client, **body)

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert saas.calls == []

    def test_erplora_com_s_limit_is_said_as_too_many_attempts(self, client, account, fake_saas):
        fake_saas(status=429, body={"error": {"code": "accounts.too_many_attempts", "message": "Too many attempts."}})

        response = report(client)

        assert response.status_code == 429
        error = response.json()["error"]
        assert error["code"] == "base.too_many_attempts"
        assert error["message"] == "Too many attempts. Please try again in a few minutes."

    @pytest.mark.parametrize(
        "answer",
        [
            {"raises": ConnectionRefusedError("refused")},
            {"raises": TimeoutError("timed out")},
            {"status": 503, "body": {"error": {"code": "accounts.report_not_sent", "message": "Mail is down."}}},
            {"status": 500, "body": b"<html>Server Error</html>"},
            {"status": 401, "body": {"error": {"code": "unauthorized", "message": "Bad signature."}}},
            {"status": 403, "body": {"error": {"code": "accounts.not_a_member", "message": "Not a member."}}},
            {"status": 200, "body": {"unexpected": True}},
        ],
    )
    def test_erplora_com_out_of_reach_or_refusing_is_said_with_the_address_to_write_to(
        self, client, account, fake_saas, caplog, answer
    ):
        fake_saas(**answer)

        response = report(client)

        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "base.report_not_sent"
        assert "support@example.com" in error["message"]
        assert "base.support_report_not_sent" in caplog.text

    def test_the_text_is_never_logged(self, client, account, fake_saas, caplog):
        fake_saas(raises=ConnectionRefusedError("refused"))
        caplog.set_level("INFO")

        report(client, description="My card is 4242 4242 4242 4242")

        assert "4242" not in caplog.text

    def test_the_messages_speak_spanish_to_a_spanish_person(self, client, account, fake_saas, settings):
        fake_saas(raises=ConnectionRefusedError("refused"))
        # Her language in this browser (the cookie entering left, here in English, as she would change it).
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

        response = client.post(URL, json.dumps({"subject": "S", "description": "D"}), content_type="application/json", HTTP_HOST=HOST)

        assert response.json()["error"]["message"] == (
            "No hemos podido enviar tu informe. Escríbenos directamente a support@example.com."
        )
