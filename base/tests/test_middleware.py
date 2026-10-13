"""SaasLoginRequiredMiddleware: a browser without a session on a SPA route goes to the SaaS's login.

The Hub has no login of its own (Ioan, 2026-10-13; PLAN-SAAS §2.1). The API keeps answering 401,
and every path with a URL of its own in Django (health, callback…) is left alone.

PlatformHostMiddleware: the platform host (``hubs.localhost``, ``hubs.erplora.com``) is only the Hub
admin for the staff (round 13, PLAN §18.1); on any other host, ``/admin/`` is not found (PLAN §18.1.3).
"""

import pytest
from django.urls import clear_script_prefix, set_script_prefix

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
SAAS_LOGIN = "http://localhost:8001/hub-login/"


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_URL = "http://localhost:8001"


@pytest.fixture
def script_prefix():
    """The prefix Django's real handlers set from SCRIPT_NAME or root_path (its test client sets none)."""
    set_script_prefix("/x/")
    yield
    clear_script_prefix()


def browse(client, path, host="a.localhost:8000", method="get"):
    return getattr(client, method)(path, HTTP_HOST=host, HTTP_ACCEPT=HTML)


@pytest.mark.parametrize(
    ("path", "host", "location"),
    [
        ("/demo/items", "a.localhost:8000", f"{SAAS_LOGIN}?hub=a&next=/demo/items"),
        ("/", "a.localhost:8000", f"{SAAS_LOGIN}?hub=a&next=/"),
        ("/demo/items?q=1&page=2", "b.localhost:8000", f"{SAAS_LOGIN}?hub=b&next=/demo/items%3Fq%3D1%26page%3D2"),
    ],
)
def test_an_anonymous_browser_goes_to_the_saas_login_of_its_hub(client, path, host, location):
    response = browse(client, path, host)
    assert (response.status_code, response["Location"]) == (302, location)


def test_head_is_a_navigation_too(client):
    assert browse(client, "/demo/items", method="head").status_code == 302


def test_a_signed_in_person_gets_the_shell(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = browse(client, "/demo/items")
    assert response.status_code == 200
    assert '<div id="app"></div>' in response.content.decode()


def test_a_request_that_is_not_a_page_load_still_gets_the_shell(client):
    # No text/html in Accept: not a browser navigation; the SPA's own auth gate decides.
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT="application/json")
    assert response.status_code == 200


def test_an_anonymous_post_to_a_spa_route_is_not_redirected(client):
    assert browse(client, "/demo/items", method="post").status_code == 405


def test_the_api_keeps_its_answers(client):
    me = browse(client, "/api/me")
    assert (me.status_code, me.json()["user"]) == (200, None)
    items = browse(client, "/api/demo/items")
    assert items.status_code == 401
    assert items.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("path", "status"), [("/healthz", 200), ("/auth/callback", 405)])
def test_paths_of_django_are_never_redirected(client, path, status):
    assert browse(client, path).status_code == status


# Hosts that are no hub (live.slugs: reserved or invalid first label): 404, never the SaaS's login.
NO_HUB_HOSTS = ["www.localhost:8000", "hub.localhost:8000", "localhost:8000", "ab.localhost:8000"]


@pytest.mark.parametrize("host", NO_HUB_HOSTS)
def test_a_page_of_a_host_that_is_no_hub_is_not_found(client, host):
    assert browse(client, "/demo/items", host).status_code == 404
    assert client.get("/demo/items", HTTP_HOST=host, HTTP_ACCEPT="application/json").status_code == 404


def test_a_signed_in_person_gets_no_shell_on_a_host_that_is_no_hub(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    assert browse(client, "/demo/items", "www.localhost:8000").status_code == 404


@pytest.mark.parametrize("path", ["/api/me", "/api/demo/items", "/api/live"])
def test_the_api_of_a_host_that_is_no_hub_is_a_404_envelope(client, path):
    response = client.get(path, HTTP_HOST="www.localhost:8000")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "not_found")


def test_the_login_callback_of_a_host_that_is_no_hub_is_not_found(client):
    response = client.post("/auth/callback", {"code": "c1", "next": "/"}, HTTP_HOST="hub.localhost:8000")
    assert response.status_code == 404


def test_health_still_answers_on_a_reserved_host(client):
    # hub.localhost is reserved, not the platform host (hubs.localhost, PLAN §18.1).
    assert browse(client, "/healthz", "hub.localhost:8000").status_code == 200


# The Hub admin lives only on the platform host (PLAN §18.1.3): on a hub host and on a host that is no
# hub, every admin path is not found, never the admin's own login, also for a superuser.
NOT_THE_PLATFORM_HOSTS = ["a.localhost:8000", *NO_HUB_HOSTS]
ADMIN_PATHS = ["/admin/", "/admin/login/", "/admin/hub/a/", "/admin/base/membership/"]


@pytest.mark.parametrize("host", NOT_THE_PLATFORM_HOSTS)
@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_the_admin_is_not_found_outside_the_platform_host(client, superuser, host, path):
    for method in ("get", "post"):
        anonymous = browse(client, path, host, method=method)
        assert (anonymous.status_code, anonymous.has_header("Location")) == (404, False)
    client.force_login(superuser)
    for method in ("get", "post"):
        staff = browse(client, path, host, method=method)
        assert (staff.status_code, staff.has_header("Location")) == (404, False)


# A script prefix (SCRIPT_NAME; behind Daphne, the client's own Daphne-Root-Path header) is not part of
# the path Django resolves (``path_info``): the gates must look at that one, or a prefix walks past them.
@pytest.mark.parametrize(
    ("host", "script_name"),
    [("a.localhost:8000", "/x"), ("www.localhost:8000", "/x"), ("www.localhost:8000", "/static")],
)
def test_a_script_prefix_does_not_open_the_admin_outside_the_platform_host(client, superuser, host, script_name):
    for user in (None, superuser):
        if user is not None:
            client.force_login(user)
        response = client.get("/admin/login/", HTTP_HOST=host, HTTP_ACCEPT=HTML, SCRIPT_NAME=script_name)
        assert (response.status_code, response.has_header("Location")) == (404, False)


def test_a_script_prefix_keeps_the_api_404_envelope_of_a_host_that_is_no_hub(client):
    response = client.get("/api/me", HTTP_HOST="www.localhost:8000", SCRIPT_NAME="/x")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "not_found")


@pytest.mark.parametrize("host", NOT_THE_PLATFORM_HOSTS)
def test_static_files_and_csp_reports_are_left_alone_outside_the_platform_host(client, host):
    # Django's plain 404 for a missing static file, never the SPA's shell nor the SaaS's login.
    missing = browse(client, "/static/nope.js", host)
    assert (missing.status_code, missing.has_header("Location")) == (404, False)
    assert '<div id="app"></div>' not in missing.content.decode()
    response = client.post("/csp-report/", "{}", content_type="application/csp-report", HTTP_HOST=host)
    assert response.status_code == 204


PLATFORM = "hubs.localhost:8000"
SAAS_HUBS = "http://localhost:8001/admin/accounts/hubs/"
# Every path that is not the admin: the SPA, the API (also /api/live) and unknown ones.
OUTSIDE_THE_ADMIN = ["/", "/demo/items", "/api/me", "/api/live", "/api/demo/items", "/api/nope", "/nowhere?x=1"]


class TestPlatformHost:
    @pytest.mark.parametrize("path", [*OUTSIDE_THE_ADMIN, "/admin/", "/admin/login/", "/admin/hub/a/", "/admin/base/"])
    def test_without_a_session_goes_to_the_saas_admin_hubs_page(self, client, path):
        # No login of its own and no code without a hub: the staff start on the SaaS admin.
        response = browse(client, path, PLATFORM)
        assert (response.status_code, response["Location"]) == (302, SAAS_HUBS)
        api_call = client.get(path, HTTP_HOST=PLATFORM, HTTP_ACCEPT="application/json")
        assert (api_call.status_code, api_call["Location"]) == (302, SAAS_HUBS)

    @pytest.mark.parametrize("path", [*OUTSIDE_THE_ADMIN, "/admin/", "/admin/login/", "/admin/base/membership/"])
    def test_a_session_without_staff_is_forbidden_never_the_login(self, client, make_user, path):
        client.force_login(make_user("ana", host="a", role="hub_owner"))
        response = browse(client, path, PLATFORM)
        assert response.status_code == 403
        assert not response.has_header("Location")

    @pytest.mark.parametrize("path", OUTSIDE_THE_ADMIN)
    def test_staff_outside_the_admin_go_to_the_admin(self, client, superuser, path):
        client.force_login(superuser)
        for method in ("get", "post"):
            response = browse(client, path, PLATFORM, method=method)
            assert (response.status_code, response["Location"]) == (302, "/admin/")

    def test_staff_get_the_admin(self, client, superuser):
        client.force_login(superuser)
        assert browse(client, "/admin/", PLATFORM).status_code == 200
        assert browse(client, "/admin/base/membership/", PLATFORM).status_code == 200

    def test_staff_never_get_the_admin_s_own_login(self, client, superuser):
        client.force_login(superuser)
        response = browse(client, "/admin/login/", PLATFORM)
        assert (response.status_code, response["Location"]) == (302, SAAS_HUBS)

    @pytest.mark.parametrize(("path", "method", "status"), [
        ("/healthz", "get", 200),
        ("/static/nope.js", "get", 404),
        ("/auth/callback", "get", 405),
        ("/auth/nope", "get", 404),
    ])  # fmt: skip
    def test_health_static_and_auth_are_left_alone(self, client, path, method, status):
        assert browse(client, path, PLATFORM, method=method).status_code == status

    def test_csp_reports_are_left_alone(self, client):
        response = client.post("/csp-report/", "{}", content_type="application/csp-report", HTTP_HOST=PLATFORM)
        assert response.status_code == 204

    def test_logout_is_left_alone(self, client, superuser):
        client.force_login(superuser)
        response = client.post("/auth/logout", HTTP_HOST=PLATFORM)
        assert (response.status_code, response["Location"]) == (302, "http://localhost:8001/accounts/logout/")
        assert browse(client, "/admin/", PLATFORM)["Location"] == SAAS_HUBS

    # With the URL prefixed (SCRIPT_NAME) or not (Daphne's root_path only): reverse() carries the
    # prefix and path_info does not, so compared as they are, the admin's index redirected to itself.
    @pytest.mark.parametrize("environ", [{"SCRIPT_NAME": "/x"}, {}])
    def test_a_script_prefix_keeps_the_admin_and_its_disabled_login(self, client, superuser, script_prefix, environ):
        client.force_login(superuser)
        prefixed = {"HTTP_HOST": PLATFORM, "HTTP_ACCEPT": HTML, **environ}
        assert client.get("/admin/", **prefixed).status_code == 200
        assert client.get("/admin/base/membership/", **prefixed).status_code == 200
        login = client.get("/admin/login/", **prefixed)
        assert (login.status_code, login["Location"]) == (302, SAAS_HUBS)
        outside = client.get("/demo/items", **prefixed)
        assert (outside.status_code, outside["Location"]) == (302, "/x/admin/")

    def test_a_hub_host_keeps_the_saas_login_of_its_hub(self, client):
        response = browse(client, "/demo/items")
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/demo/items"
