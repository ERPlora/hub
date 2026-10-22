"""/auth/login, /auth/callback and /auth/logout: the Hub's end of the login through the SaaS (PLAN-SAAS §3.1 steps 4–6).

The jump to the SaaS carries a ``state`` that the cookie ``hub_login_state`` binds to the browser
that started it; the callback refuses a code that comes back without it (login CSRF). The SaaS sends
``state`` back as it got it: ``callback`` plays its auto-submitted form.

On the platform host (``hubs.localhost``) the same jump is the staff's to the Hub admin of a hub, with
the ``hub-admin`` audience (round 13, PLAN §18.1): it starts on the Hub too
(``/auth/login?hub=<slug>&next=/admin/hub/<slug>/``, the SaaS admin's button) and needs its state.
"""

import datetime as dt
import hashlib
import json
import logging
import time
import types
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from live.context import system_context

from base.models import DemoCode, Hub, Membership
from base.registry import REGISTRY_SCOPE
from base.schemas import DemoCodeIn, DemoCreateIn
from base.services import demo_code_create, demo_create

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
SAAS_LOGIN = "http://localhost:8001/hub-login/"
PLATFORM = "hubs.localhost:8000"
SAAS_HUBS = "http://localhost:8001/admin/accounts/hubs/"
ROOT = {"user_id": "7", "email": "root@erplora.com", "name": "Root", "locale": "es", "role": "platform_admin"}
DEEP_LINK = "/admin/hub/a/"
STATE_COOKIE = "hub_login_state"


def state_of(response) -> str:
    """The ``state`` of a jump to the SaaS's login (its ``Location``)."""
    [state] = parse_qs(urlsplit(response["Location"]).query)["state"]
    return state


def start_login(client, next_path="/demo/items", host=HOST):
    """The shell's auth gate: ``/auth/login`` answers the jump to the SaaS's login."""
    return client.get("/auth/login", {"next": next_path}, HTTP_HOST=host)


def callback(client, data, host=HOST):
    """The SaaS's auto-submitted form, after this browser's jump from the Hub and with its ``state``.

    On the platform host the jump is the one of ``next`` (its deep link); with no hub in it there is no
    jump (the SaaS admin's Hubs page), so no state.
    """
    if "state" not in data:
        jump = parse_qs(urlsplit(start_login(client, data.get("next") or "/", host=host)["Location"]).query)
        data = {**data, **({"state": jump["state"][0]} if "state" in jump else {})}
    return client.post("/auth/callback", data, HTTP_HOST=host)


def me(client, host=HOST):
    return client.get("/api/me", HTTP_HOST=host).json()


class TestCallback:
    def test_redeems_the_code_opens_the_session_and_goes_to_next(self, client, fake_saas, settings):
        fake = fake_saas()
        response = callback(client, {"code": "c1", "next": "/demo/items"})
        assert (response.status_code, response["Location"]) == (302, "/demo/items")
        assert json.loads(fake.calls[0]["body"]) == {"code": "c1", "hub": "a"}
        body = me(client)
        assert (body["user"]["label"], body["scope"]["key"]) == ("Ana", "a")
        assert "demo.view" in body["permissions"]
        assert Membership.objects.get().role == "hub_manager"
        assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "es"
        assert body["language"] == "es"

    def test_the_session_is_only_for_the_hub_of_the_code(self, client, fake_saas):
        fake_saas()
        callback(client, {"code": "c1", "next": "/"})
        assert me(client, "b.localhost:8000")["permissions"] == []

    def test_is_csrf_exempt_because_the_saas_posts_it_cross_site(self, fake_saas):
        fake_saas()
        response = callback(Client(enforce_csrf_checks=True), {"code": "c1", "next": "/"})
        assert (response.status_code, response["Location"]) == (302, "/")

    @pytest.mark.parametrize(
        "next_path", [None, "", "https://evil.example.com/x", "//evil.example.com", "/\\evil.example.com", "demo"]
    )
    def test_next_is_only_a_path_of_this_hub(self, client, fake_saas, next_path):
        fake_saas()
        data = {"code": "c1"} if next_path is None else {"code": "c1", "next": next_path}
        assert callback(client, data)["Location"] == "/"

    @pytest.mark.parametrize(("locale", "cookie"), [("es-ES", "es"), ("en", "en"), ("fr", None), ("", None)])
    def test_the_language_follows_the_saas_when_the_hub_has_it(self, client, fake_saas, settings, locale, cookie):
        fake_saas(body={"user_id": "42", "email": "ana@example.com", "name": "Ana", "locale": locale, "role": "hub_admin"})
        response = callback(client, {"code": "c1", "next": "/"})
        sent = response.cookies.get(settings.LANGUAGE_COOKIE_NAME)
        assert (sent.value if sent else None) == cookie

    @pytest.mark.parametrize(
        ("saas_answer", "error"),
        [
            ({"status": 400, "body": {"error": {"code": "invalid_code", "message": "Invalid"}}}, "invalid_code"),
            ({"status": 401, "body": {"error": {"code": "unauthorized"}}}, "hub_unauthorized"),
            ({"raises": urllib.error.URLError("refused")}, "saas_unavailable"),
            ({"status": 200, "body": {"user_id": "42", "role": "owner_of_everything"}}, "unknown_role"),
        ],
    )
    def test_a_failure_goes_back_to_the_saas_login_with_the_error(self, client, fake_saas, saas_answer, error):
        fake_saas(**saas_answer)
        response = callback(client, {"code": "c1", "next": "/demo/items"})
        assert (response.status_code, response["Location"]) == (
            302,
            f"{SAAS_LOGIN}?hub=a&next=/demo/items&error={error}&state={state_of(response)}",
        )
        assert me(client)["user"] is None

    def test_a_failure_starts_a_new_jump_whose_state_the_callback_takes(self, client, fake_saas):
        fake_saas(status=400, body={"error": {"code": "invalid_code", "message": "Used"}})
        first = start_login(client)
        retry = client.post("/auth/callback", {"code": "c1", "state": state_of(first)}, HTTP_HOST=HOST)
        assert state_of(retry) != state_of(first)
        assert STATE_COOKIE in retry.cookies
        fake_saas()
        response = client.post("/auth/callback", {"code": "c2", "next": "/", "state": state_of(retry)}, HTTP_HOST=HOST)
        assert (response.status_code, response["Location"]) == (302, "/")
        assert me(client)["user"]["label"] == "Ana"

    def test_a_missing_code_never_reaches_the_saas(self, client, fake_saas):
        fake = fake_saas()
        response = callback(client, {"next": "/"})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/&error=invalid_code&state={state_of(response)}"
        assert fake.calls == []

    def test_a_user_deactivated_on_the_hub_is_sent_back(self, client, fake_saas):
        fake_saas()
        get_user_model().objects.create_user("saas:42", is_active=False)
        response = callback(client, {"code": "c1", "next": "/"})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/&error=user_inactive&state={state_of(response)}"
        assert me(client)["user"] is None

    def test_only_post(self, client, saas):
        assert client.get("/auth/callback", HTTP_HOST=HOST).status_code == 405

    @pytest.mark.parametrize("role", ["platform_admin", "platform_support"])
    def test_a_platform_role_never_opens_a_customer_session(self, client, fake_saas, role):
        fake = fake_saas(body={**ROOT, "role": role})
        response = callback(client, {"code": "c1", "next": DEEP_LINK})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next={DEEP_LINK}&error=unknown_role&state={state_of(response)}"
        # A hub host always redeems as a customer (hub-session), whatever next says.
        assert json.loads(fake.calls[0]["body"]) == {"code": "c1", "hub": "a"}
        assert not get_user_model().objects.filter(is_staff=True).exists()


class TestLoginStart:
    """``/auth/login?next=<path>``: where the shell's auth gate sends (``spa-config.loginUrl``)."""

    def test_jumps_to_the_saas_login_with_a_fresh_state_kept_in_a_cookie(self, client, saas):
        response = start_login(client, "/demo/items?q=1")
        state = state_of(response)
        assert (response.status_code, response["Location"]) == (
            302,
            f"{SAAS_LOGIN}?hub=a&next=/demo/items%3Fq%3D1&state={state}",
        )
        assert len(state) >= 43  # secrets.token_urlsafe(32)
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie["httponly"], cookie["samesite"], cookie["secure"], cookie["max-age"], cookie["path"]) == (
            True,
            "Lax",
            True,
            600,
            "/auth/callback",
        )
        assert "no-store" in response["Cache-Control"]

    def test_every_jump_has_its_own_state(self, client, saas):
        assert state_of(start_login(client)) != state_of(start_login(client))

    def test_locally_the_cookie_reaches_the_saas_cross_site_post(self, client, saas, settings):
        # localhost:8001 → a.localhost:8000 are two sites: a Lax cookie never comes back on the SaaS's
        # POST (erplora.com → <slug>.erplora.com is one site). Chrome and Firefox take Secure on *.localhost.
        settings.DEBUG = True
        cookie = start_login(client).cookies[STATE_COOKIE]
        assert (cookie["samesite"], cookie["secure"]) == ("None", True)

    @pytest.mark.parametrize("next_path", ["", "https://evil.example.com/x", "//evil.example.com", "demo"])
    def test_next_is_only_a_path_of_this_hub(self, client, saas, next_path):
        assert start_login(client, next_path)["Location"].startswith(f"{SAAS_LOGIN}?hub=a&next=/&state=")

    def test_without_next_lands_on_the_home(self, client, saas):
        response = client.get("/auth/login", HTTP_HOST=HOST)
        assert response["Location"].startswith(f"{SAAS_LOGIN}?hub=a&next=/&state=")

    @pytest.mark.parametrize("host", ["www.localhost:8000", "hub.localhost:8000"])
    def test_a_host_that_is_no_hub_is_not_found(self, client, saas, host):
        response = start_login(client, host=host)
        assert (response.status_code, STATE_COOKIE in response.cookies) == (404, False)

    def test_only_get_and_head(self, client, saas):
        assert client.post("/auth/login", HTTP_HOST=HOST).status_code == 405


class TestCallbackState:
    """The callback redeems a code only with the ``state`` of this browser's jump (login CSRF)."""

    def test_the_state_of_this_browser_s_jump_opens_the_session(self, client, fake_saas):
        fake = fake_saas()
        state = state_of(start_login(client))
        response = client.post("/auth/callback", {"code": "c1", "next": "/demo/items", "state": state}, HTTP_HOST=HOST)
        assert (response.status_code, response["Location"]) == (302, "/demo/items")
        assert len(fake.calls) == 1
        assert me(client)["user"]["label"] == "Ana"

    def test_without_the_cookie_is_forbidden_and_never_reaches_the_saas(self, fake_saas, caplog):
        # The attacker's own jump and code, posted from the victim's browser (which has no cookie).
        fake = fake_saas()
        attacker, victim = Client(), Client()
        state = state_of(start_login(attacker))
        with caplog.at_level(logging.WARNING, logger="base.auth_views"):
            response = victim.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        assert (response.status_code, response.has_header("Location")) == (403, False)
        assert fake.calls == []
        assert me(victim)["user"] is None
        assert any(r.name == "base.auth_views" and r.levelno == logging.WARNING and "'a'" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("posted", [{"state": "not-the-one"}, {"state": ""}, {}])
    def test_a_state_that_is_not_this_browser_s_is_forbidden(self, client, fake_saas, caplog, posted):
        fake = fake_saas()
        start_login(client)
        with caplog.at_level(logging.WARNING, logger="base.auth_views"):
            response = client.post("/auth/callback", {"code": "c1", "next": "/", **posted}, HTTP_HOST=HOST)
        assert response.status_code == 403
        assert fake.calls == []
        assert me(client)["user"] is None
        assert any(r.name == "base.auth_views" and r.levelno == logging.WARNING for r in caplog.records)

    def test_a_forged_post_does_not_spoil_this_browser_s_own_login(self, client, fake_saas):
        fake_saas()
        state = state_of(start_login(client))
        forged = client.post("/auth/callback", {"code": "evil", "state": "forged"}, HTTP_HOST=HOST)
        assert forged.status_code == 403
        response = client.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        assert (response.status_code, response["Location"]) == (302, "/")

    @pytest.mark.parametrize(("age", "status"), [(590, 302), (601, 403)])
    def test_the_cookie_lasts_ten_minutes(self, client, fake_saas, monkeypatch, age, status):
        fake = fake_saas()
        # The jump happened `age` seconds ago: its cookie was signed then.
        with monkeypatch.context() as past:
            past.setattr(signing, "time", types.SimpleNamespace(time=lambda: time.time() - age))
            state = state_of(start_login(client))
        response = client.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        assert response.status_code == status
        assert len(fake.calls) == (1 if status == 302 else 0)

    def test_a_tampered_cookie_is_forbidden(self, client, fake_saas):
        fake = fake_saas()
        state = state_of(start_login(client))
        client.cookies[STATE_COOKIE] = state  # the raw state, without the Hub's signature
        response = client.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        assert (response.status_code, fake.calls) == (403, [])

    @pytest.mark.parametrize(
        ("language", "heading", "link"),
        [
            ("en", "We could not finish signing you in", "Sign in again"),
            ("es", "No hemos podido terminar de iniciar tu sesión", "Volver a entrar"),
        ],
    )
    def test_the_403_is_a_page_of_the_hub_that_signs_in_again(
        self, client, fake_saas, django_assert_num_queries, language, heading, link
    ):
        fake_saas()
        start_login(client)
        data = {"code": "c1", "next": "/demo/items?q=1", "state": "forged"}
        # One read, the host gate's row of the hub (base.registry); the page itself reads nothing.
        with django_assert_num_queries(1):
            response = client.post("/auth/callback", data, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE=language)
        assert response.status_code == 403
        assert response["Content-Type"].startswith("text/html")
        html = response.content.decode()
        assert f'<html lang="{language}">' in html
        assert heading in html
        assert f'<a href="/auth/login?next=%2Fdemo%2Fitems%3Fq%3D1">{link}</a>' in html

    @pytest.mark.parametrize("next_path", [None, "https://evil.example.com/x", "//evil.example.com"])
    def test_the_link_of_the_403_never_leaves_the_hub(self, client, fake_saas, next_path):
        fake_saas()
        data = {"code": "c1", "state": "forged"} if next_path is None else {"code": "c1", "state": "forged", "next": next_path}
        response = client.post("/auth/callback", data, HTTP_HOST=HOST)
        assert response.status_code == 403
        assert 'href="/auth/login?next=%2F"' in response.content.decode()

    def test_the_cookie_is_deleted_once_the_code_is_redeemed(self, client, fake_saas):
        fake = fake_saas()
        state = state_of(start_login(client))
        response = client.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie.value, cookie["max-age"], cookie["path"]) == ("", 0, "/auth/callback")
        # A state serves one login: the same one again is refused before reaching the SaaS.
        replay = client.post("/auth/callback", {"code": "c1", "next": "/", "state": state}, HTTP_HOST=HOST)
        assert (replay.status_code, len(fake.calls)) == (403, 1)


class TestAdminLoginStart:
    """``hubs.<domain>/auth/login``: the staff's jump to the Hub admin, from the SaaS admin's button."""

    @pytest.mark.parametrize(
        "query",
        [
            {"hub": "a", "next": DEEP_LINK},
            {"hub": "a"},
            # The hub of the deep link when hub is missing; hub wins over another deep link.
            {"next": DEEP_LINK},
            {"hub": "a", "next": "/admin/hub/b/"},
            {"hub": "a", "next": "https://evil.example.com/"},
        ],
    )
    def test_jumps_to_the_saas_login_with_the_hub_admin_audience_and_a_state(self, client, saas, query):
        response = client.get("/auth/login", query, HTTP_HOST=PLATFORM)
        state = state_of(response)
        assert (response.status_code, response["Location"]) == (
            302,
            f"{SAAS_LOGIN}?hub=a&audience=hub-admin&next={DEEP_LINK}&state={state}",
        )
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie["httponly"], cookie["samesite"], cookie["secure"], cookie["max-age"], cookie["path"]) == (
            True,
            "Lax",
            True,
            600,
            "/auth/callback",
        )
        assert "no-store" in response["Cache-Control"]

    @pytest.mark.parametrize(
        "query",
        [{"next": "/admin/"}, {}, {"hub": "hubs"}, {"hub": "hub"}, {"hub": "A"}, {"next": "/admin/hub/../"}],
    )
    def test_without_a_hub_goes_to_the_saas_admin_hubs_page(self, client, saas, query):
        # A hub-admin code is always for a hub (PLAN §18.1.3): the staff choose it there.
        response = client.get("/auth/login", query, HTTP_HOST=PLATFORM)
        assert (response.status_code, response["Location"]) == (302, SAAS_HUBS)
        assert STATE_COOKIE not in response.cookies

    def test_a_hub_host_never_asks_for_the_hub_admin_audience(self, client, saas):
        response = client.get("/auth/login", {"hub": "b", "next": DEEP_LINK}, HTTP_HOST=HOST)
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next={DEEP_LINK}&state={state_of(response)}"


def staff_session(client) -> int:
    """Status of the Hub admin's index on the platform host for this client."""
    return client.get("/admin/", HTTP_HOST=PLATFORM).status_code


class TestAdminCallback:
    def test_platform_admin_opens_a_staff_session_and_lands_on_the_deep_link(self, client, fake_saas, settings):
        fake = fake_saas(body=ROOT)
        response = callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        assert (response.status_code, response["Location"]) == (302, DEEP_LINK)
        [call] = fake.calls
        assert json.loads(call["body"]) == {"code": "c1", "hub": "a", "audience": "hub-admin"}
        user = get_user_model().objects.get(username="saas-staff:7")
        assert (user.is_staff, user.is_superuser, user.email) == (True, True, "root@erplora.com")
        assert client.session["saas_user_id"] == "7"
        assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "es"
        chosen = client.get(DEEP_LINK, HTTP_HOST=PLATFORM)
        assert (chosen.status_code, chosen["Location"]) == (302, "/admin/")
        index = client.get("/admin/", HTTP_HOST=PLATFORM)
        assert index.status_code == 200
        assert "Hub: a" in index.content.decode()

    def test_the_state_of_this_browser_s_jump_opens_the_staff_session(self, client, fake_saas):
        fake = fake_saas(body=ROOT)
        state = state_of(client.get("/auth/login", {"hub": "a", "next": DEEP_LINK}, HTTP_HOST=PLATFORM))
        response = client.post("/auth/callback", {"code": "c1", "next": DEEP_LINK, "state": state}, HTTP_HOST=PLATFORM)
        assert (response.status_code, response["Location"]) == (302, DEEP_LINK)
        assert len(fake.calls) == 1
        assert staff_session(client) == 200
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie.value, cookie["max-age"], cookie["path"]) == ("", 0, "/auth/callback")

    @pytest.mark.parametrize("posted", [{"state": "not-the-one"}, {}])
    def test_without_this_browser_s_state_the_staff_get_a_403_that_signs_in_again(self, fake_saas, caplog, posted):
        # A hub-admin code posted from a browser that did not start the jump (login CSRF into the Hub admin).
        fake = fake_saas(body=ROOT)
        attacker, victim = Client(), Client()
        callback(attacker, {"code": "c0", "next": DEEP_LINK}, PLATFORM)
        victim.get("/auth/login", {"hub": "a"}, HTTP_HOST=PLATFORM)
        with caplog.at_level(logging.WARNING, logger="base.auth_views"):
            response = victim.post("/auth/callback", {"code": "c1", "next": DEEP_LINK, **posted}, HTTP_HOST=PLATFORM)
        assert response.status_code == 403
        assert 'href="/auth/login?next=%2Fadmin%2Fhub%2Fa%2F"' in response.content.decode()
        assert len(fake.calls) == 1  # the attacker's own, never the victim's
        assert victim.get("/admin/", HTTP_HOST=PLATFORM)["Location"] == SAAS_HUBS
        assert any(r.name == "base.auth_views" and r.levelno == logging.WARNING for r in caplog.records)

    def test_platform_support_is_read_only_staff(self, client, fake_saas):
        fake_saas(body={**ROOT, "role": "platform_support"})
        assert callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)["Location"] == DEEP_LINK
        user = get_user_model().objects.get(username="saas-staff:7")
        assert (user.is_staff, user.is_superuser) == (True, False)
        assert list(user.groups.values_list("name", flat=True)) == ["support"]
        assert staff_session(client) == 200
        assert client.get("/admin/base/membership/", HTTP_HOST=PLATFORM).status_code == 200
        assert client.get("/admin/base/membership/add/", HTTP_HOST=PLATFORM).status_code == 403

    def test_is_csrf_exempt_because_the_saas_posts_it_cross_site(self, fake_saas):
        fake_saas(body=ROOT)
        response = callback(Client(enforce_csrf_checks=True), {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        assert (response.status_code, response["Location"]) == (302, DEEP_LINK)

    @pytest.mark.parametrize(
        "next_path",
        [
            None,
            "",
            "/",
            "/admin/",
            "/admin/hub/../",
            "/admin/hub/hubs/",
            "/admin/hub/hub/",
            "/admin/hub/A/",
            "/admin/hub/a",
            "/admin/hub/a/base/",
            "/admin/hub/a/\n",
            "https://evil.example.com/admin/hub/a/",
            "//evil.example.com/admin/hub/a/",
        ],
    )
    def test_a_next_that_is_no_deep_link_is_a_400_and_never_reaches_the_saas(self, client, fake_saas, next_path):
        fake = fake_saas(body=ROOT)
        data = {"code": "c1"} if next_path is None else {"code": "c1", "next": next_path}
        response = callback(client, data, PLATFORM)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_next"
        assert fake.calls == []
        assert not get_user_model().objects.exists()

    def test_a_next_that_is_no_deep_link_is_explained_in_the_request_s_language(self, client, fake_saas):
        fake_saas(body=ROOT)
        response = client.post("/auth/callback", {"code": "c1", "next": "/"}, HTTP_HOST=PLATFORM, HTTP_ACCEPT_LANGUAGE="es")
        assert response.json()["error"] == {
            "code": "invalid_next",
            "message": "next debe ser el enlace directo /admin/hub/<slug>/ de un hub.",
        }

    @pytest.mark.parametrize(
        ("saas_answer", "error"),
        [
            ({"status": 200, "body": {**ROOT, "role": "hub_owner"}}, "not_platform_staff"),
            ({"status": 200, "body": {**ROOT, "role": "superhero"}}, "unknown_role"),
            ({"status": 400, "body": {"error": {"code": "invalid_code", "message": "Used"}}}, "invalid_code"),
            ({"status": 401, "body": {"error": {"code": "unauthorized"}}}, "hub_unauthorized"),
            ({"raises": urllib.error.URLError("refused")}, "saas_unavailable"),
            ({"status": 200, "body": b"not json"}, "saas_unavailable"),
        ],
    )
    def test_a_failure_goes_back_to_the_saas_hubs_page_with_the_error(self, client, fake_saas, saas_answer, error):
        fake_saas(**saas_answer)
        response = callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        assert (response.status_code, response["Location"]) == (302, f"{SAAS_HUBS}?error={error}")
        assert not get_user_model().objects.filter(is_staff=True).exists()
        assert client.get("/admin/", HTTP_HOST=PLATFORM)["Location"] == SAAS_HUBS

    def test_a_missing_code_never_reaches_the_saas(self, client, fake_saas):
        fake = fake_saas(body=ROOT)
        response = callback(client, {"next": DEEP_LINK}, PLATFORM)
        assert response["Location"] == f"{SAAS_HUBS}?error=invalid_code"
        assert fake.calls == []

    def test_the_same_code_twice_is_refused_by_the_saas_the_second_time(self, client, fake_saas):
        fake_saas(body=ROOT)
        assert callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)["Location"] == DEEP_LINK
        fake_saas(status=400, body={"error": {"code": "invalid_code", "message": "Used"}})
        replay = Client()
        response = callback(replay, {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        assert response["Location"] == f"{SAAS_HUBS}?error=invalid_code"
        assert replay.get("/admin/", HTTP_HOST=PLATFORM)["Location"] == SAAS_HUBS

    def test_a_staff_copy_deactivated_on_the_hub_is_sent_back(self, client, fake_saas):
        fake_saas(body=ROOT)
        get_user_model().objects.create_user("saas-staff:7", is_active=False)
        response = callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        assert response["Location"] == f"{SAAS_HUBS}?error=user_inactive"
        assert client.get("/admin/", HTTP_HOST=PLATFORM)["Location"] == SAAS_HUBS

    def test_only_post(self, client, saas):
        assert client.get("/auth/callback", HTTP_HOST=PLATFORM).status_code == 405

    def test_one_account_at_both_doors_keeps_each_session_as_it_entered(self, fake_saas):
        # Ioan is platform_admin and owner of hub a: entering his hub must not lock him out of the
        # Hub admin, and entering the admin must not make him a superuser on his hub.
        staff, customer = Client(), Client()
        fake_saas(body=ROOT)
        callback(staff, {"code": "c1", "next": DEEP_LINK}, PLATFORM)
        fake_saas(body={**ROOT, "role": "hub_owner"})
        callback(customer, {"code": "c2", "next": "/"})
        assert staff_session(staff) == 200
        fake_saas(body=ROOT)
        callback(staff, {"code": "c3", "next": DEEP_LINK}, PLATFORM)
        permissions = me(customer)["permissions"]
        assert "*" not in permissions
        assert "demo.view" in permissions
        assert staff_session(staff) == 200


class TestLogout:
    def test_closes_the_session_and_goes_to_the_saas_logout(self, client, fake_saas):
        fake_saas()
        callback(client, {"code": "c1", "next": "/"})
        response = client.post("/auth/logout", HTTP_HOST=HOST)
        assert (response.status_code, response["Location"]) == (302, "http://localhost:8001/accounts/logout/")
        assert me(client)["user"] is None

    def test_needs_the_csrf_token(self, saas):
        assert Client(enforce_csrf_checks=True).post("/auth/logout", HTTP_HOST=HOST).status_code == 403

    def test_only_post(self, client, saas):
        assert client.get("/auth/logout", HTTP_HOST=HOST).status_code == 405


# A demo hub (plan 2026-10-17, §1.6): no account behind it. Its jump goes to the SaaS's /demo/enter/ with the same
# state; the SaaS posts back a code the Hub made for the browser that owns the demo, redeemed here without the SaaS.

DEMO_OWNER = hashlib.sha256(b"ana's browser").hexdigest()
SAAS_DEMO_ENTER = "http://localhost:8001/demo/enter/"
SAAS_DEMO_FAILED = "http://localhost:8001/demo/?state=failed"


def new_demo(session_key: str = DEMO_OWNER) -> str:
    """A demo of the browser ``session_key``, as ``POST /internal/demos`` leaves it; its slug."""
    return demo_create(system_context(REGISTRY_SCOPE), DemoCreateIn(session_key=session_key, language="es")).slug


def a_code(slug: str, session_key: str = DEMO_OWNER, language: str = "es") -> str:
    """What the SaaS's /demo/enter/ asks for (``POST /internal/demos/{slug}/codes``) and posts to the callback."""
    data = DemoCodeIn(slug=slug, session_key=session_key, language=language)
    return demo_code_create(system_context(REGISTRY_SCOPE), data).code


def host_of(slug: str) -> str:
    return f"{slug}.localhost:8000"


@pytest.fixture
def demo(saas) -> str:
    return new_demo()


class TestDemoLoginStart:
    def test_a_demo_jumps_to_the_saas_demo_enter_with_a_fresh_state(self, client, demo):
        response = start_login(client, "/demo/items", host=host_of(demo))
        state = state_of(response)
        assert (response.status_code, response["Location"]) == (
            302,
            f"{SAAS_DEMO_ENTER}?hub={demo}&next=/demo/items&state={state}",
        )
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie["path"], cookie["max-age"], cookie["httponly"]) == ("/auth/callback", 600, True)

    def test_a_page_of_the_demo_without_a_session_jumps_there_too(self, client, demo):
        response = client.get("/demo/items", HTTP_HOST=host_of(demo), HTTP_ACCEPT="text/html")
        assert response.status_code == 302
        assert response["Location"].startswith(f"{SAAS_DEMO_ENTER}?hub={demo}&next=/demo/items&state=")
        assert STATE_COOKIE in response.cookies

    def test_a_business_still_jumps_to_the_saas_login(self, client, demo):
        assert start_login(client, "/", host=HOST)["Location"].startswith(f"{SAAS_LOGIN}?hub=a&")


class TestDemoCallback:
    def test_a_code_of_this_browser_opens_the_owner_s_session_without_the_saas(self, client, fake_saas, demo, settings):
        fake = fake_saas()
        response = callback(client, {"code": a_code(demo), "next": "/demo/items"}, host=host_of(demo))
        assert (response.status_code, response["Location"]) == (302, "/demo/items")
        assert fake.calls == []
        body = me(client, host_of(demo))
        assert (body["user"]["label"], body["scope"]["key"]) == ("Demo", demo)
        # The API's JSON keeps milliseconds.
        ends = parse_datetime(body["demo"]["expires_at"])
        assert abs(ends - Hub.objects.get(slug=demo).expires_at) < dt.timedelta(milliseconds=1)
        assert Membership.objects.get(host=demo).role == "hub_owner"
        # The code's language (the visitor's on the SaaS) is the session's.
        assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "es"
        assert body["language"] == "es"
        cookie = response.cookies[STATE_COOKIE]
        assert (cookie.value, cookie["max-age"]) == ("", 0)

    def test_the_session_is_only_for_this_demo(self, client, fake_saas, demo):
        fake_saas()
        callback(client, {"code": a_code(demo), "next": "/"}, host=host_of(demo))
        assert me(client, HOST)["permissions"] == []

    def test_without_this_browser_s_state_it_is_403_and_the_code_stays_unspent(self, fake_saas, demo):
        fake = fake_saas()
        code = a_code(demo)
        response = Client().post("/auth/callback", {"code": code, "next": "/", "state": "x"}, HTTP_HOST=host_of(demo))
        assert response.status_code == 403
        assert "/auth/login" in response.content.decode()
        assert DemoCode.objects.get().used_at is None and fake.calls == []

    @pytest.mark.parametrize("how", ["spent", "expired", "another_demo_s", "missing", "unknown"])
    def test_a_code_that_opens_nothing_goes_back_to_the_saas_demo_door(self, client, fake_saas, demo, how, caplog):
        fake = fake_saas()
        code = {"missing": "", "unknown": "not-a-code"}[how] if how in ("missing", "unknown") else a_code(demo)
        if how == "spent":
            callback(Client(), {"code": code, "next": "/"}, host=host_of(demo))
        elif how == "expired":
            DemoCode.objects.update(expires_at=timezone.now() - dt.timedelta(seconds=1))
        elif how == "another_demo_s":
            other_owner = hashlib.sha256(b"bea's browser").hexdigest()
            code = a_code(new_demo(other_owner), other_owner)
        with caplog.at_level(logging.WARNING, logger="base.auth_views"):
            response = callback(client, {"code": code, "next": "/"}, host=host_of(demo))
        assert (response.status_code, response["Location"]) == (302, SAAS_DEMO_FAILED)
        assert me(client, host_of(demo))["user"] is None and fake.calls == []
        assert demo in caplog.text

    def test_a_demo_owner_deactivated_in_the_admin_goes_back_to_the_door(self, client, fake_saas, demo):
        fake_saas()
        callback(Client(), {"code": a_code(demo), "next": "/"}, host=host_of(demo))
        get_user_model().objects.filter(username=f"demo:{demo}").update(is_active=False)
        response = callback(client, {"code": a_code(demo), "next": "/"}, host=host_of(demo))
        assert (response.status_code, response["Location"]) == (302, SAAS_DEMO_FAILED)

    def test_the_callback_of_a_demo_that_ended_is_410(self, client, fake_saas, demo):
        fake_saas()
        code = a_code(demo)
        Hub.objects.filter(slug=demo).update(expires_at=timezone.now())
        response = client.post("/auth/callback", {"code": code, "next": "/", "state": "x"}, HTTP_HOST=host_of(demo))
        assert (response.status_code, response.json()["error"]["code"]) == (410, "base.hub_gone")
        assert DemoCode.objects.get().used_at is None


class TestDemoLogout:
    def test_leaving_a_demo_goes_back_to_the_saas_demo_door(self, client, fake_saas, demo):
        fake_saas()
        callback(client, {"code": a_code(demo), "next": "/"}, host=host_of(demo))
        response = client.post("/auth/logout", HTTP_HOST=host_of(demo))
        assert (response.status_code, response["Location"]) == (302, "http://localhost:8001/demo/")
        assert me(client, host_of(demo))["user"] is None


# Attempts: past 10 refused callbacks of an address in 5 minutes, its next refused one is 429 until the window of the
# first one ends; a good code always redeems (people behind the same address are never locked out)


ATTEMPTS = 10
INVALID = {"status": 400, "body": {"error": {"code": "invalid_code", "message": "Invalid"}}}


def refused(client, times: int = 1, host: str = HOST, **meta):
    """``times`` callbacks of this browser whose code the SaaS refuses (``invalid_code``); the last answer."""
    for _ in range(times):
        response = callback_from(client, {"code": "guess", "next": "/"}, host, **meta)
    return response


def callback_from(client, data, host=HOST, **meta):
    """The callback (with this browser's state) from the address of ``meta`` (``REMOTE_ADDR``…)."""
    jump = parse_qs(urlsplit(client.get("/auth/login", {"next": data.get("next") or "/"}, HTTP_HOST=host, **meta)["Location"]).query)
    data = {**data, **({"state": jump["state"][0]} if "state" in jump and "state" not in data else {})}
    return client.post("/auth/callback", data, HTTP_HOST=host, **meta)


class TestCallbackAttempts:
    def test_past_ten_refused_codes_the_next_refused_one_is_429_with_retry_after(self, client, fake_saas):
        fake_saas(**INVALID)
        assert refused(client, ATTEMPTS).status_code == 302
        answer = refused(client)
        assert answer.status_code == 429
        assert 290 <= int(answer["Retry-After"]) <= 300
        assert STATE_COOKIE not in answer.cookies, "no new jump while the address waits"
        assert me(client)["user"] is None

    def test_a_good_code_redeems_while_the_address_is_past_the_limit(self, client, fake_saas):
        # The tablet next to it guessed (or kept an expired code): the waiter with a good one still gets in.
        fake_saas(**INVALID)
        refused(client, ATTEMPTS + 1)
        fake_saas()
        waiter = Client()
        response = callback(waiter, {"code": "c1", "next": "/demo/items"})
        assert (response.status_code, response["Location"]) == (302, "/demo/items")
        assert me(waiter)["user"]["label"] == "Ana"

    def test_the_429_is_a_page_of_the_hub_in_the_browser_s_language(self, client, fake_saas):
        fake_saas(**INVALID)
        refused(client, ATTEMPTS)
        answer = refused(client, HTTP_ACCEPT_LANGUAGE="es")
        page = answer.content.decode()
        assert answer.status_code == 429 and answer["Content-Type"].startswith("text/html")
        assert "Demasiados intentos de entrar" in page and "Vuelve a intentarlo en 5 minutos." in page
        assert answer["Cache-Control"].startswith("max-age=0")

    def test_a_callback_without_a_code_counts(self, client, fake_saas):
        fake = fake_saas()
        for _ in range(ATTEMPTS):
            assert "error=invalid_code" in callback(client, {"next": "/"})["Location"]
        assert callback(client, {"next": "/"}).status_code == 429
        assert fake.calls == []

    def test_a_good_redemption_is_not_counted(self, client, fake_saas):
        fake_saas(**INVALID)
        refused(client, ATTEMPTS - 1)
        fake_saas()
        for _ in range(5):
            assert callback(client, {"code": "c1", "next": "/"})["Location"] == "/"
        fake_saas(**INVALID)
        assert refused(client).status_code == 302
        assert refused(client).status_code == 429

    def test_a_callback_without_this_browser_s_state_counts(self, client, fake_saas):
        fake = fake_saas()
        for _ in range(ATTEMPTS):
            assert client.post("/auth/callback", {"code": "c1", "state": "forged"}, HTTP_HOST=HOST).status_code == 403
        assert client.post("/auth/callback", {"code": "c1", "state": "forged"}, HTTP_HOST=HOST).status_code == 429
        assert fake.calls == []
        assert callback(client, {"code": "c1", "next": "/"})["Location"] == "/", "with its state, the code redeems"

    @pytest.mark.parametrize(
        "saas_answer",
        [
            {"raises": urllib.error.URLError("refused")},
            {"status": 503, "body": {}},
            {"status": 401, "body": {"error": {"code": "unauthorized"}}},
            {"status": 200, "body": {"user_id": "42", "role": "owner_of_everything"}},
        ],
    )
    def test_what_fails_on_the_hub_s_side_or_after_a_good_code_is_not_counted(self, client, fake_saas, saas_answer):
        # The SaaS away, the hub's own signature refused, a code that was good but opens no session here: nobody
        # guessed anything, and counting it would lock people out for the platform's fault.
        fake_saas(**saas_answer)
        for _ in range(ATTEMPTS + 2):
            assert callback(client, {"code": "c1", "next": "/"}).status_code == 302
        fake_saas(**INVALID)
        assert refused(client).status_code == 302

    def test_a_deactivated_user_s_good_code_is_not_counted(self, client, fake_saas):
        fake_saas()
        get_user_model().objects.create_user("saas:42", is_active=False)
        for _ in range(ATTEMPTS + 1):
            assert "error=user_inactive" in callback(client, {"code": "c1", "next": "/"})["Location"]

    @pytest.mark.parametrize(
        ("caller", "same", "neighbour"),
        [
            ("203.0.113.7", "203.0.113.7", "203.0.113.8"),
            # IPv6: one subscriber holds a whole /64; its other addresses are the same caller.
            ("2001:db8:1:2::7", "2001:db8:1:2:ffff::1", "2001:db8:1:3::7"),
        ],
    )
    def test_the_count_is_per_address_as_the_proxies_saw_it(self, client, fake_saas, settings, caller, same, neighbour):
        settings.TRUSTED_PROXY_HOPS = 1
        fake_saas(**INVALID)
        refused(client, ATTEMPTS, HTTP_X_FORWARDED_FOR=f"198.51.100.1, {caller}")
        # The entry the client wrote is not who it is: changing it does not open a new count.
        assert refused(client, HTTP_X_FORWARDED_FOR=f"198.51.100.2, {same}").status_code == 429
        assert refused(Client(), HTTP_X_FORWARDED_FOR=neighbour).status_code == 302

    def test_a_demo_s_refused_codes_count_and_its_good_code_still_opens_it(self, client, fake_saas, demo):
        fake_saas()
        for _ in range(ATTEMPTS):
            assert callback(client, {"code": "guess", "next": "/"}, host=host_of(demo))["Location"] == SAAS_DEMO_FAILED
        assert callback(client, {"code": "guess", "next": "/"}, host=host_of(demo)).status_code == 429
        assert callback(client, {"code": a_code(demo), "next": "/demo/items"}, host=host_of(demo))["Location"] == "/demo/items"

    def test_the_staff_s_refused_codes_count_on_the_platform_host_and_on_the_hub_s(self, client, fake_saas):
        fake_saas(**INVALID)
        for _ in range(ATTEMPTS):
            assert callback(client, {"code": "guess", "next": DEEP_LINK}, PLATFORM).status_code == 302
        assert callback(client, {"code": "guess", "next": DEEP_LINK}, PLATFORM).status_code == 429
        assert refused(client).status_code == 429
        fake_saas(body=ROOT)
        assert callback(client, {"code": "c1", "next": DEEP_LINK}, PLATFORM)["Location"] == DEEP_LINK

    def test_a_staff_callback_without_this_browser_s_state_counts(self, client, fake_saas):
        fake = fake_saas(body=ROOT)

        def forged():
            return client.post("/auth/callback", {"code": "c1", "next": DEEP_LINK, "state": "forged"}, HTTP_HOST=PLATFORM)

        for _ in range(ATTEMPTS):
            assert forged().status_code == 403
        assert forged().status_code == 429
        assert fake.calls == []
