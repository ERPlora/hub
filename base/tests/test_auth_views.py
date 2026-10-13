"""/auth/callback and /auth/logout: the Hub's end of the login through the SaaS (PLAN-SAAS §3.1 steps 5–6).

On the platform host (``hubs.localhost``) the callback is the end of the staff's jump from the SaaS
admin to the Hub admin, with the ``hub-admin`` audience (round 13, PLAN §18.1).
"""

import json
import urllib.error

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from base.models import Membership

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
SAAS_LOGIN = "http://localhost:8001/hub-login/"
PLATFORM = "hubs.localhost:8000"
SAAS_HUBS = "http://localhost:8001/admin/accounts/hubs/"
ROOT = {"user_id": "7", "email": "root@erplora.com", "name": "Root", "locale": "es", "role": "platform_admin"}
DEEP_LINK = "/admin/hub/a/"


def callback(client, data, host=HOST):
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
            f"{SAAS_LOGIN}?hub=a&next=/demo/items&error={error}",
        )
        assert me(client)["user"] is None

    def test_a_missing_code_never_reaches_the_saas(self, client, fake_saas):
        fake = fake_saas()
        response = callback(client, {"next": "/"})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/&error=invalid_code"
        assert fake.calls == []

    def test_a_user_deactivated_on_the_hub_is_sent_back(self, client, fake_saas):
        fake_saas()
        get_user_model().objects.create_user("saas:42", is_active=False)
        response = callback(client, {"code": "c1", "next": "/"})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/&error=user_inactive"
        assert me(client)["user"] is None

    def test_only_post(self, client, saas):
        assert client.get("/auth/callback", HTTP_HOST=HOST).status_code == 405

    @pytest.mark.parametrize("role", ["platform_admin", "platform_support"])
    def test_a_platform_role_never_opens_a_customer_session(self, client, fake_saas, role):
        fake = fake_saas(body={**ROOT, "role": role})
        response = callback(client, {"code": "c1", "next": DEEP_LINK})
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next={DEEP_LINK}&error=unknown_role"
        # A hub host always redeems as a customer (hub-session), whatever next says.
        assert json.loads(fake.calls[0]["body"]) == {"code": "c1", "hub": "a"}
        assert not get_user_model().objects.filter(is_staff=True).exists()


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
