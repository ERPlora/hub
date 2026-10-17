"""base.auth: the SaaS's login URL and redeeming its one-time code (PLAN-SAAS §2.1, §3.1 step 6)."""

import hashlib
import hmac
import json
import logging
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from base import auth, signing
from base.auth import RedeemedUser
from base.tests.conftest import ANA, SECRET

pytestmark = pytest.mark.usefixtures("saas")


class TestLoginUrl:
    def test_carries_the_hub_a_readable_next_and_the_state(self):
        url = auth.login_url("a", "/demo/items", state="s1")
        assert url == "http://localhost:8001/hub-login/?hub=a&next=/demo/items&state=s1"

    def test_encodes_the_query_of_next_and_adds_the_error(self):
        url = auth.login_url("a", "/demo/items?q=1&x=2", state="s1", error="invalid_code")
        assert url == "http://localhost:8001/hub-login/?hub=a&next=/demo/items%3Fq%3D1%26x%3D2&error=invalid_code&state=s1"

    def test_follows_the_setting_with_or_without_a_trailing_slash(self, settings):
        settings.SAAS_URL = "https://erplora.com/"
        assert auth.login_url("bar", "/", state="s1") == "https://erplora.com/hub-login/?hub=bar&next=/&state=s1"

    def test_the_staff_s_jump_asks_for_the_hub_admin_audience(self):
        url = auth.login_url("a", "/admin/hub/a/", state="s1", audience="hub-admin")
        assert url == "http://localhost:8001/hub-login/?hub=a&audience=hub-admin&next=/admin/hub/a/&state=s1"

    def test_an_unknown_audience_is_a_programming_error(self):
        with pytest.raises(ValueError):
            auth.login_url("a", "/", state="s1", audience="everything")

    def test_never_leaves_without_a_next_and_a_state(self):
        # The callback refuses a code that comes back without the state of this browser's jump.
        with pytest.raises(TypeError):
            auth.login_url("a", "/demo/items")
        with pytest.raises(TypeError):
            auth.login_url("a", state="s1")


class TestAdminHubsUrl:
    def test_is_the_hubs_page_of_the_saas_admin(self):
        # Where the staff start (PLAN §18.1, point 6): every hub with «Open in the Hub admin».
        assert auth.admin_hubs_url() == "http://localhost:8001/admin/accounts/hubs/"

    def test_carries_the_error(self, settings):
        settings.SAAS_URL = "https://erplora.com/"
        assert auth.admin_hubs_url("invalid_code") == "https://erplora.com/admin/accounts/hubs/?error=invalid_code"


def test_signature_is_hex_hmac_sha256_of_timestamp_dot_body():
    body = b'{"code": "c1", "hub": "a"}'
    expected = hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert auth.sign(SECRET, "1700000000", body) == expected


class TestRedeemCode:
    def test_posts_the_signed_code_and_returns_the_user(self, fake_saas):
        fake = fake_saas()
        result = auth.redeem_code("c1", "a")
        assert (result.ok, result.error) == (True, None)
        assert result.user == RedeemedUser(user_id="42", email="ana@example.com", name="Ana", locale="es", role="hub_manager")
        [call] = fake.calls
        assert call["url"] == "http://localhost:8001/internal/auth/redeem"
        assert json.loads(call["body"]) == {"code": "c1", "hub": "a"}
        assert call["timeout"] == 5
        headers = call["headers"]
        assert headers["Content-Type"] == "application/json"
        timestamp = headers["X-Erplora-Timestamp"]
        assert timestamp.isdigit()
        assert headers["X-Erplora-Signature"] == auth.sign(SECRET, timestamp, call["body"])

    def test_signs_the_call_with_v2_too(self, fake_saas):
        # v2 also covers the method and the route (base.signing): the SaaS judges a call that carries it by v2.
        fake = fake_saas()
        auth.redeem_code("c1", "a")
        [call] = fake.calls
        headers = call["headers"]
        timestamp = int(headers["X-Erplora-Timestamp"])
        assert headers["X-Erplora-Signature-V2"] == signing.sign_v2(
            "POST", "/internal/auth/redeem", call["body"], timestamp, SECRET
        )
        assert headers["X-Erplora-Signature"] == signing.sign(call["body"], timestamp, SECRET)

    def test_a_numeric_user_id_becomes_text_and_missing_optionals_are_empty(self, fake_saas):
        fake_saas(body={"user_id": 7, "email": "bo@example.com", "role": "hub_employee"})
        user = auth.redeem_code("c1", "a").user
        assert (user.user_id, user.name, user.locale) == ("7", "", "")

    @pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
    def test_the_role_from_the_saas_is_kept_as_it_is(self, fake_saas, role):
        fake_saas(body={**ANA, "role": role})
        assert auth.redeem_code("c1", "a").user.role == role

    @pytest.mark.parametrize(
        "role",
        [
            "owner", "admin", "manager", "employee", "superuser", "support", "superhero", "hub_", None, ["hub_admin"],
            # A platform role never opens a customer's session (round 13: only with the hub-admin audience).
            "platform_admin", "platform_support",
        ],
    )  # fmt: skip
    def test_an_unknown_role_is_refused(self, fake_saas, role):
        fake_saas(body={**ANA, "role": role})
        result = auth.redeem_code("c1", "a")
        assert (result.ok, result.user, result.error) == (False, None, "unknown_role")

    @pytest.mark.parametrize("code", ["", "   ", None])
    def test_a_blank_code_is_invalid_without_calling_the_saas(self, fake_saas, code):
        fake = fake_saas()
        assert auth.redeem_code(code, "a").error == "invalid_code"
        assert fake.calls == []

    def test_a_400_carries_the_saas_error_code(self, fake_saas):
        fake_saas(status=400, body={"error": {"code": "code_expired", "message": "Expired"}})
        assert auth.redeem_code("c1", "a").error == "code_expired"

    @pytest.mark.parametrize("body", [b"not json", {"error": "flat"}, {"error": {"code": "Bad Code!"}}])
    def test_a_400_without_a_clean_code_is_invalid_code(self, fake_saas, body):
        fake_saas(status=400, body=body)
        assert auth.redeem_code("c1", "a").error == "invalid_code"

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_rejected_signature_is_hub_unauthorized(self, fake_saas, status):
        fake_saas(status=status, body={"error": {"code": "unauthorized"}})
        assert auth.redeem_code("c1", "a").error == "hub_unauthorized"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"raises": urllib.error.URLError("connection refused")},
            {"raises": TimeoutError("timed out")},
            {"status": 502, "body": b"Bad gateway"},
            {"status": 200, "body": b"not json"},
            {"status": 200, "body": {"email": "ana@example.com", "role": "hub_admin"}},
            {"status": 200, "body": ["not", "an", "object"]},
        ],
    )
    def test_anything_else_is_saas_unavailable_and_logged(self, fake_saas, caplog, kwargs):
        fake_saas(**kwargs)
        with caplog.at_level(logging.WARNING, logger="base.auth"):
            assert auth.redeem_code("c1", "a").error == "saas_unavailable"
        assert caplog.records, "a failed redeem must leave a warning"


class TestRedeemCodeForTheHubAdmin:
    """Audience ``hub-admin``: the staff's jump from the SaaS admin to hubs.erplora.com (PLAN §18.1)."""

    @pytest.mark.parametrize("role", ["platform_admin", "platform_support"])
    def test_sends_the_audience_and_keeps_the_platform_role(self, fake_saas, role):
        fake = fake_saas(body={**ANA, "role": role})
        result = auth.redeem_code("c1", "a", audience=auth.HUB_ADMIN_AUDIENCE)
        assert (result.ok, result.user.role) == (True, role)
        [call] = fake.calls
        assert json.loads(call["body"]) == {"code": "c1", "hub": "a", "audience": "hub-admin"}
        assert call["headers"]["X-Erplora-Signature"] == auth.sign(SECRET, call["headers"]["X-Erplora-Timestamp"], call["body"])

    @pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager", "hub_employee"])
    def test_a_customer_role_is_not_platform_staff(self, fake_saas, role):
        fake_saas(body={**ANA, "role": role})
        result = auth.redeem_code("c1", "a", audience=auth.HUB_ADMIN_AUDIENCE)
        assert (result.ok, result.user, result.error) == (False, None, "not_platform_staff")

    @pytest.mark.parametrize("role", ["superuser", "support", "platform_", "platform_owner", None, ["hub_admin"]])
    def test_an_unknown_role_is_refused(self, fake_saas, role):
        fake_saas(body={**ANA, "role": role})
        assert auth.redeem_code("c1", "a", audience=auth.HUB_ADMIN_AUDIENCE).error == "unknown_role"

    def test_the_saas_errors_are_the_same_as_for_a_customer(self, fake_saas):
        fake_saas(status=400, body={"error": {"code": "invalid_code", "message": "Used"}})
        assert auth.redeem_code("c1", "a", audience=auth.HUB_ADMIN_AUDIENCE).error == "invalid_code"

    def test_an_unknown_audience_is_a_programming_error(self, fake_saas):
        fake = fake_saas()
        with pytest.raises(ValueError, match="audience"):
            auth.redeem_code("c1", "a", audience="hub-everything")
        assert fake.calls == []


# In production the ALB answers 404 to /internal/* (aws-next/stacks/shared/alb.tf): the Hub reaches the
# SaaS's /internal over the private name (SAAS_INTERNAL_URL), the browser over the public one (SAAS_URL).
PUBLIC = "https://erplora.com"
INTERNAL = "http://saas.erplora.internal:8000"


class TestInternalUrl:
    def test_the_redeem_goes_to_the_internal_url_with_the_same_signature(self, fake_saas, settings):
        fake = fake_saas()
        settings.SAAS_URL, settings.SAAS_INTERNAL_URL = PUBLIC, f"{INTERNAL}/"
        assert auth.redeem_code("c1", "a").ok
        [call] = fake.calls
        assert call["url"] == f"{INTERNAL}/internal/auth/redeem"
        timestamp = call["headers"]["X-Erplora-Timestamp"]
        assert call["headers"]["X-Erplora-Signature"] == auth.sign(SECRET, timestamp, call["body"])

    def test_the_browser_redirects_keep_the_public_url(self, settings):
        settings.SAAS_URL, settings.SAAS_INTERNAL_URL = PUBLIC, f"{INTERNAL}/"
        assert auth.login_url("a", "/demo/items", state="s1") == f"{PUBLIC}/hub-login/?hub=a&next=/demo/items&state=s1"
        assert auth.admin_hubs_url("invalid_code") == f"{PUBLIC}/admin/accounts/hubs/?error=invalid_code"
        assert auth.saas_url("/accounts/logout/") == f"{PUBLIC}/accounts/logout/"


class _SaasHandler(BaseHTTPRequestHandler):
    answer: tuple[int, bytes] = (200, json.dumps(ANA).encode())
    received: list[dict] = []

    def do_POST(self):  # noqa: N802 (http.server's naming)
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append({"path": self.path, "headers": dict(self.headers), "body": body})
        status, payload = type(self).answer
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def local_saas(settings):
    """A real HTTP server on a free port, answering ``_SaasHandler.answer``."""
    _SaasHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _SaasHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The redeem is server-to-server: it goes to the internal URL, never to the public one.
    settings.SAAS_URL = "https://erplora.com"
    settings.SAAS_INTERNAL_URL = f"http://127.0.0.1:{server.server_port}"
    yield _SaasHandler
    server.shutdown()
    server.server_close()


class TestOverHttp:
    def test_redeems_against_a_real_server_with_a_verifiable_signature(self, local_saas):
        local_saas.answer = (200, json.dumps(ANA).encode())
        assert auth.redeem_code("c1", "a").user.email == "ana@example.com"
        [request] = local_saas.received
        assert request["path"] == "/internal/auth/redeem"
        timestamp = request["headers"]["X-Erplora-Timestamp"]
        assert request["headers"]["X-Erplora-Signature"] == auth.sign(SECRET, timestamp, request["body"])

    def test_an_error_status_is_an_answer_not_an_exception(self, local_saas):
        local_saas.answer = (400, json.dumps({"error": {"code": "invalid_code"}}).encode())
        assert auth.redeem_code("c1", "a").error == "invalid_code"

    def test_a_closed_port_is_saas_unavailable(self, local_saas, settings):
        settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
        assert auth.redeem_code("c1", "a").error == "saas_unavailable"
