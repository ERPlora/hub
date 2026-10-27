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

from base import registry, signing
from base.models import Membership
from base.tests.conftest import SECRET
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


@pytest.fixture
def ana(make_user, saas, spa_manifest):
    return make_user("saas:019a2b3c-0000-7000-8000-000000000042", host="a", role=Membership.Role.MANAGER, first_name="Ana")


def report(client, **body):
    payload = {"subject": "The printer stops", "description": "It prints half a ticket.", "page": "/sales/pos", **body}
    return client.post(URL, json.dumps(payload), content_type="application/json", HTTP_HOST=HOST, HTTP_USER_AGENT=BROWSER)


class TestSent:
    def test_it_reaches_erplora_com_signed_with_the_account_the_business_the_screen_and_the_browser(
        self, client, ana, fake_saas
    ):
        saas = fake_saas(body=SENT)
        client.force_login(ana)

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

    def test_the_call_is_signed_v1_and_v2_with_the_shared_secret(self, client, ana, fake_saas):
        saas = fake_saas(body=SENT)
        client.force_login(ana)

        report(client)

        [call] = saas.calls
        headers, body = call["headers"], call["body"]
        timestamp = int(headers[signing.TIMESTAMP_HEADER])
        assert headers["Content-Type"] == "application/json"
        assert headers[signing.SIGNATURE_HEADER] == signing.sign(body, timestamp, SECRET)
        assert headers[signing.SIGNATURE_V2_HEADER] == signing.sign_v2("POST", SAAS_PATH, body, timestamp, SECRET)

    def test_without_a_screen_it_says_none(self, client, ana, fake_saas):
        saas = fake_saas(body=SENT)
        client.force_login(ana)

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

    def test_a_session_opened_with_the_account_on_a_till_can(self, client, ana, fake_saas):
        # The way in, not the device: the owner who entered with her erplora.com account on a shared till.
        saas = fake_saas(body=SENT)
        a_device(client)
        client.force_login(ana)

        assert report(client).status_code == 200
        assert len(saas.calls) == 1

    def test_a_person_who_is_no_erplora_com_account_cannot(self, client, make_user, saas, spa_manifest, fake_saas):
        # A demo's visitor (``demo:<slug>``) or any local copy without an account behind it.
        fake = fake_saas(body=SENT)
        client.force_login(make_user("demo:a", host="a", role=Membership.Role.OWNER))

        response = report(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "base.support_needs_account"
        assert fake.calls == []

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
    def test_what_is_missing_or_too_long_is_a_422_on_its_field_and_nothing_leaves(self, client, ana, fake_saas, body, field):
        saas = fake_saas(body=SENT)
        client.force_login(ana)

        response = report(client, **body)

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert saas.calls == []

    def test_erplora_com_s_limit_is_said_as_too_many_attempts(self, client, ana, fake_saas):
        fake_saas(status=429, body={"error": {"code": "accounts.too_many_attempts", "message": "Too many attempts."}})
        client.force_login(ana)

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
        self, client, ana, fake_saas, caplog, answer
    ):
        fake_saas(**answer)
        client.force_login(ana)

        response = report(client)

        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "base.report_not_sent"
        assert "support@example.com" in error["message"]
        assert "base.support_report_not_sent" in caplog.text

    def test_the_text_is_never_logged(self, client, ana, fake_saas, caplog):
        fake_saas(raises=ConnectionRefusedError("refused"))
        client.force_login(ana)
        caplog.set_level("INFO")

        report(client, description="My card is 4242 4242 4242 4242")

        assert "4242" not in caplog.text

    def test_the_messages_speak_spanish_to_a_spanish_person(self, client, ana, fake_saas):
        fake_saas(raises=ConnectionRefusedError("refused"))
        client.force_login(ana)

        response = client.post(
            URL,
            json.dumps({"subject": "S", "description": "D"}),
            content_type="application/json",
            HTTP_HOST=HOST,
            HTTP_ACCEPT_LANGUAGE="es",
        )

        assert response.json()["error"]["message"] == (
            "No hemos podido enviar tu informe. Escríbenos directamente a support@example.com."
        )
