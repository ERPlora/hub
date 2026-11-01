"""SaasLoginRequiredMiddleware: a browser without a session on a SPA route goes to the SaaS's login.

The Hub has no login of its own (Ioan, 2026-10-13; PLAN-SAAS §2.1). The API keeps answering 401,
and every path with a URL of its own in Django (health, callback…) is left alone.

PlatformHostMiddleware: the platform host (``hubs.localhost``, ``hubs.erplora.com``) is only the Hub
admin for the staff (round 13, PLAN §18.1); on any other host, ``/admin/`` is not found (PLAN §18.1.3).
"""

import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.urls import clear_script_prefix, set_script_prefix

from base import health

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


def state_of(response) -> str:
    """The ``state`` of a jump to the SaaS's login (its ``Location``)."""
    [state] = parse_qs(urlsplit(response["Location"]).query)["state"]
    return state


def jump_target(response) -> str:
    """Where the hub's jump page sends (``base/jump.html``): ``/auth/login?next=<path>``, before its script adds the
    fragment the browser never sends to the server."""
    assert response.status_code == 200, f"{response.status_code} is no jump page"
    match = re.search(r'<script id="hub-jump" type="application/json">(.*?)</script>', response.content.decode(), re.S)
    assert match is not None, "no jump page"
    return json.loads(match.group(1))


def through_the_jump(client, response, host="a.localhost:8000"):
    """The jump page followed as a browser does without a fragment: ``/auth/login``'s answer."""
    return client.get(jump_target(response), HTTP_HOST=host, HTTP_ACCEPT=HTML)


@pytest.mark.parametrize(
    ("path", "host", "location"),
    [
        ("/demo/items", "a.localhost:8000", f"{SAAS_LOGIN}?hub=a&next=/demo/items"),
        ("/", "a.localhost:8000", f"{SAAS_LOGIN}?hub=a&next=/"),
        ("/demo/items?q=1&page=2", "b.localhost:8000", f"{SAAS_LOGIN}?hub=b&next=/demo/items%3Fq%3D1%26page%3D2"),
    ],
)
def test_an_anonymous_browser_goes_to_the_saas_login_of_its_hub(client, path, host, location):
    page = browse(client, path, host)
    assert jump_target(page) == f"/auth/login?{urlencode({'next': path})}"
    response = through_the_jump(client, page, host)
    assert (response.status_code, response["Location"]) == (302, f"{location}&state={state_of(response)}")


def test_the_jump_page_carries_the_fragment_the_browser_never_sends(client):
    # «/settings#data» reaches the server as «/settings»: only the page's script knows the «#data» it adds to
    # ``next``, so the person lands on the tab the link named after erplora.com (BASE-G52).
    page = browse(client, "/settings")
    html = page.content.decode()
    nonce = re.search(r"'nonce-([^']+)'", page["Content-Security-Policy"]).group(1)
    assert f'<script nonce="{nonce}">' in html
    assert "encodeURIComponent(location.hash)" in html
    assert '<meta http-equiv="refresh" content="0;url=/auth/login?next=%2Fsettings">' in html
    assert "no-store" in page["Cache-Control"]


def test_the_jump_page_speaks_the_language_of_the_browser_without_scripts(client):
    page = client.get("/settings", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE="es")
    assert '<html lang="es">' in page.content.decode()
    assert '<a href="/auth/login?next=%2Fsettings">Continuar para entrar</a>' in page.content.decode()


def test_the_jump_page_leaves_the_state_to_the_login_it_sends_to(client):
    # The page is not the jump to erplora.com: /auth/login is, with its own fresh state (no page replays one).
    assert not browse(client, "/demo/items").cookies


def test_the_jump_binds_its_state_to_this_browser_with_a_cookie(client):
    # Only the callback reads it (PLAN-SAAS §3.1): /auth/callback refuses a code without this state.
    response = through_the_jump(client, browse(client, "/demo/items"))
    cookie = response.cookies["hub_login_state"]
    assert (cookie["httponly"], cookie["samesite"], cookie["secure"], cookie["max-age"], cookie["path"]) == (
        True,
        "Lax",
        True,
        600,
        "/auth/callback",
    )
    assert state_of(response) != state_of(through_the_jump(client, browse(client, "/demo/items")))


def test_head_is_a_navigation_too(client):
    response = browse(client, "/demo/items", method="head")
    assert (response.status_code, response.has_header("Location")) == (200, False)


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


@pytest.mark.parametrize(("language", "message"), [("en", "Not found"), ("es", "No encontrado.")])
def test_the_404_envelope_of_a_host_that_is_no_hub_is_the_api_s_own_in_the_request_s_language(client, language, message):
    # The same envelope as an unknown API path (live.api_errors), in the language the browser asks for.
    no_hub = client.get("/api/me", HTTP_HOST="www.localhost:8000", HTTP_ACCEPT_LANGUAGE=language)
    unknown = client.get("/api/nope", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT_LANGUAGE=language)
    assert no_hub.json() == unknown.json() == {"error": {"code": "not_found", "message": message}}


def test_the_login_callback_of_a_host_that_is_no_hub_is_not_found(client):
    response = client.post("/auth/callback", {"code": "c1", "next": "/"}, HTTP_HOST="hub.localhost:8000")
    assert response.status_code == 404


def test_health_still_answers_on_a_reserved_host(client):
    # hub.localhost is reserved, not the platform host (hubs.localhost, PLAN §18.1).
    assert browse(client, "/healthz", "hub.localhost:8000").status_code == 200


# HUB_BASE_DOMAIN (plan 2026-10-14-entorno-pre, H-2): prod's Hub (erplora.com) never serves a host of
# pre (x.pre.erplora.com), which the ALB's wildcard *.erplora.com would also match; /readyz still
# answers on every host Django accepts, the private name included.
PROD_HOSTS = [".erplora.com", "hub.erplora.internal"]


@pytest.fixture
def prod_domain(settings):
    settings.ALLOWED_HOSTS = PROD_HOSTS
    settings.HUB_BASE_DOMAIN = "erplora.com"
    settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}


@pytest.mark.usefixtures("prod_domain")
def test_with_a_base_domain_the_pages_of_another_domain_are_not_found(client, superuser):
    from base.models import Hub

    Hub.objects.create(slug="acme", status="ready")  # the registry's, as the SaaS's sign-up leaves it
    page = browse(client, "/demo/items", "acme.erplora.com")
    assert through_the_jump(client, page, "acme.erplora.com")["Location"].startswith(SAAS_LOGIN)
    for host in ("acme.pre.erplora.com", "pre.erplora.com", "erplora.com"):
        assert browse(client, "/demo/items", host).status_code == 404
        api = client.get("/api/me", HTTP_HOST=host)
        assert (api.status_code, api.json()["error"]["code"]) == (404, "not_found")
    # pre's platform host is no platform host of prod: its admin is not found, even for the staff.
    client.force_login(superuser)
    assert browse(client, "/admin/", "hubs.pre.erplora.com").status_code == 404
    assert browse(client, "/admin/", "hubs.erplora.com").status_code == 200


@pytest.mark.usefixtures("prod_domain")
@pytest.mark.parametrize("host", ["hub.erplora.internal:8000", "hubs.erplora.com", "acme.erplora.com"])
def test_readyz_still_answers_on_the_private_name(client, host):
    health.forget_readiness()
    response = client.get("/readyz", HTTP_HOST=host)
    assert (response.status_code, response.json()) == (200, {"status": "ok"})
    health.forget_readiness()


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

    def test_a_module_s_documentation_image_is_served_without_a_session(self, client, settings):
        # Round 16 (spec §4.4): the SaaS's store links /static/catalog/<id>/img/ on this host; WhiteNoise
        # serves what AppImagesFinder publishes (from the finders here, from STATIC_ROOT once collected).
        settings.WHITENOISE_USE_FINDERS = True
        response = browse(client, "/static/catalog/demo/img/items-list.png", PLATFORM)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert not response.has_header("Location")
        assert b"".join(response.streaming_content).startswith(b"\x89PNG")

    def test_csp_reports_are_left_alone(self, client):
        response = client.post("/csp-report/", "{}", content_type="application/csp-report", HTTP_HOST=PLATFORM)
        assert response.status_code == 204

    def test_logout_is_left_alone(self, client, superuser):
        client.force_login(superuser)
        response = client.post("/auth/logout", HTTP_HOST=PLATFORM)
        assert (response.status_code, response["Location"]) == (302, "http://localhost:8001/logout")
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
        response = through_the_jump(client, browse(client, "/demo/items"))
        assert response["Location"] == f"{SAAS_LOGIN}?hub=a&next=/demo/items&state={state_of(response)}"


# The registry decides (plan 2026-10-17, §1.2): a slug without a row is 404, a hub that is gone 410, one still being
# prepared 503. `a` and `b` are in it (the autouse fixture `local_hubs`, as `seed_local_hubs` leaves them).


class TestTheRegistryGate:
    @pytest.fixture
    def hub(self):
        from base.models import Hub

        def make(slug, **fields):
            return Hub.objects.create(slug=slug, **{"status": "ready", **fields})

        return make

    def test_a_slug_without_a_row_is_not_found(self, client):
        assert browse(client, "/demo/items", "zzz.localhost:8000").status_code == 404
        api = client.get("/api/me", HTTP_HOST="zzz.localhost:8000")
        assert (api.status_code, api.json()["error"]["code"]) == (404, "not_found")

    def test_a_ready_hub_serves_its_pages_and_names_itself_on_the_request(self, client, hub, rf):
        from base.middleware import HubHostRequiredMiddleware

        acme = hub("acme")
        assert jump_target(browse(client, "/demo/items", "acme.localhost:8000"))  # on to the SaaS's login
        request = rf.get("/demo/items", HTTP_HOST="acme.localhost:8000")
        assert HubHostRequiredMiddleware(lambda r: None).process_request(request) is None
        assert request.hub == acme

    def test_the_local_hubs_are_registered(self, client, make_user):
        client.force_login(make_user("ana", host="a", role="hub_employee"))
        assert browse(client, "/demo/items").status_code == 200
        assert browse(client, "/demo/items", "b.localhost:8000").status_code == 200

    @pytest.mark.parametrize("status", ["cancelled", "purged"])
    def test_a_business_that_is_gone_is_410_with_the_way_back_to_erplora(self, client, hub, status):
        hub("acme", status=status)
        response = browse(client, "/", "acme.localhost:8000")
        assert response.status_code == 410
        html = response.content.decode()
        assert "This business is no longer available" in html
        assert 'href="http://localhost:8001/launch"' in html

    def test_a_demo_is_gone_from_its_expiry_even_before_the_reaper(self, client, hub):
        import datetime as dt

        from django.utils import timezone

        hub("demo-0000beef", is_demo=True, expires_at=timezone.now() - dt.timedelta(seconds=1))
        response = browse(client, "/demo/items", "demo-0000beef.localhost:8000")
        assert response.status_code == 410
        html = response.content.decode()
        assert "This demo has ended" in html
        # ``state=expired``: the SaaS's /demo/ forgets the demo its session still holds and says it ended.
        assert 'href="http://localhost:8001/demo/?state=expired"' in html

    @pytest.mark.parametrize("ended", ["by_time", "expired", "purged"])
    def test_the_login_of_a_demo_that_ended_still_jumps_to_the_saas_door(self, client, hub, ended):
        # The SaaS's «Back to my demo» starts here: its /demo/enter/ asks for a code, hears 410 and says «expired»
        # (plan 2026-10-17, §1.7); a 410 page here would leave the SaaS believing the demo is still on.
        import datetime as dt

        from django.utils import timezone

        past = timezone.now() - dt.timedelta(seconds=1)
        fields = {"by_time": {}, "expired": {"status": "expired"}, "purged": {"status": "purged"}}[ended]
        hub("demo-0000beef", is_demo=True, expires_at=past, **fields)
        response = client.get("/auth/login", {"next": "/"}, HTTP_HOST="demo-0000beef.localhost:8000", HTTP_ACCEPT=HTML)
        assert response.status_code == 302
        assert response["Location"].startswith("http://localhost:8001/demo/enter/?hub=demo-0000beef&next=/&state=")

    def test_the_login_of_a_business_that_is_gone_is_still_410(self, client, hub):
        hub("acme", status="cancelled")
        response = client.get("/auth/login", {"next": "/"}, HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML)
        assert response.status_code == 410

    def test_a_demo_on_time_is_served(self, client, hub):
        import datetime as dt

        from django.utils import timezone

        hub("demo-0000beef", is_demo=True, expires_at=timezone.now() + dt.timedelta(minutes=5))
        assert jump_target(browse(client, "/", "demo-0000beef.localhost:8000"))  # on to its door

    def test_the_gone_page_is_translated(self, client, hub):
        hub("acme", status="cancelled")
        response = client.get("/", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE="es")
        assert "Este negocio ya no está disponible" in response.content.decode()

    @pytest.mark.parametrize("path", ["/api/me", "/api/live", "/api/demo/items"])
    def test_the_api_of_a_hub_that_is_gone_is_the_410_envelope(self, client, hub, path):
        hub("acme", status="cancelled")
        response = client.get(path, HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML)
        assert response.status_code == 410
        assert response.json() == {"error": {"code": "base.hub_gone", "message": "This hub is no longer available."}}

    def test_a_call_that_does_not_ask_for_a_page_gets_the_envelope(self, client, hub):
        hub("acme", status="cancelled")
        response = client.post("/auth/callback", {"code": "c1"}, HTTP_HOST="acme.localhost:8000")
        assert (response.status_code, response.json()["error"]["code"]) == (410, "base.hub_gone")

    @pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding", "failed"])
    def test_a_hub_being_prepared_is_503_and_asks_to_come_back(self, client, hub, status):
        hub("acme", status=status)
        response = browse(client, "/", "acme.localhost:8000")
        assert (response.status_code, response["Retry-After"]) == (503, "30")
        html = response.content.decode()
        assert '<meta http-equiv="refresh" content="10">' in html
        assert "Your business is being prepared" in html

    @pytest.mark.parametrize(
        ("fields", "status"),
        [({"status": "cancelled"}, 410), ({"state": {"status": "suspended"}}, 402)],
        ids=["gone", "suspended"],
    )
    def test_only_a_hub_being_prepared_asks_to_come_back(self, client, hub, fields, status):
        # Retry-After says «try again soon»: true while it is being prepared, never for a hub gone or suspended.
        hub("acme", **fields)
        page = browse(client, "/", "acme.localhost:8000")
        api = client.get("/api/me", HTTP_HOST="acme.localhost:8000")
        assert (page.status_code, api.status_code) == (status, status)
        assert not page.has_header("Retry-After") and not api.has_header("Retry-After")

    # A hub moving to another cluster (round 2026-10-30b of PLAN-DB, decision 3; control.hub.move): closed for the few
    # seconds its database is copied, then back on its new cluster.
    def test_a_hub_moving_to_another_cluster_is_503_under_maintenance_and_asks_to_come_back(self, client, hub):
        from control.models import Cluster

        hub("acme", moving_to=Cluster.objects.create(name="next", host="writer-next.example"))
        page = browse(client, "/", "acme.localhost:8000")
        api = client.get("/api/me", HTTP_HOST="acme.localhost:8000")
        assert (page.status_code, page["Retry-After"]) == (503, "30")
        html = page.content.decode()
        assert '<meta http-equiv="refresh" content="10">' in html
        assert "This business is under maintenance" in html and "It takes a few minutes." in html
        assert (api.status_code, api["Retry-After"], api.json()["error"]["code"]) == (503, "30", "base.hub_maintenance")
        assert "for a few minutes" in api.json()["error"]["message"]

    def test_a_hub_under_maintenance_says_so_in_spanish(self, client, hub):
        from control.models import Cluster

        hub("acme", moving_to=Cluster.objects.create(name="next", host="writer-next.example"))
        page = client.get("/", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE="es")
        api = client.get("/api/me", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT_LANGUAGE="es")
        assert "Este negocio está en mantenimiento" in page.content.decode()
        assert "Tarda unos minutos." in page.content.decode()
        assert api.json()["error"]["message"] == (
            "Este hub está en mantenimiento unos minutos; vuelve a intentarlo enseguida."
        )

    def test_the_api_of_a_hub_being_prepared_is_the_503_envelope(self, client, hub):
        hub("acme", status="failed")
        response = client.get("/api/me", HTTP_HOST="acme.localhost:8000")
        assert (response.status_code, response["Retry-After"]) == (503, "30")
        assert response.json()["error"]["code"] == "base.hub_preparing"

    # BILLING-F16 of the SaaS: a business suspended for an unpaid invoice (the SaaS's photo, ``status``) does not
    # open, with a session or without, until it is paid; in its 7 days of grace (``past_due``) it works.
    def test_a_suspended_business_is_402_with_the_way_back_to_erplora(self, client, hub):
        hub("acme", state={"status": "suspended"})
        response = browse(client, "/", "acme.localhost:8000")
        assert response.status_code == 402
        html = response.content.decode()
        assert "This business is suspended" in html
        assert 'href="http://localhost:8001/launch"' in html

    def test_a_signed_in_person_of_a_suspended_business_is_stopped_too(self, client, hub, make_user):
        hub("acme", state={"status": "suspended"})
        client.force_login(make_user("ana", host="acme", role="hub_employee"))
        assert browse(client, "/demo/items", "acme.localhost:8000").status_code == 402

    @pytest.mark.parametrize("path", ["/api/me", "/api/live", "/api/demo/items"])
    def test_the_api_of_a_suspended_business_is_the_402_envelope(self, client, hub, path):
        hub("acme", state={"status": "suspended"})
        response = client.get(path, HTTP_HOST="acme.localhost:8000")
        assert response.status_code == 402
        assert response.json()["error"]["code"] == "base.hub_suspended"

    def test_the_login_of_a_suspended_business_lets_nobody_in(self, client, hub):
        hub("acme", state={"status": "suspended"})
        response = client.post("/auth/callback", {"code": "c1"}, HTTP_HOST="acme.localhost:8000")
        assert (response.status_code, response.json()["error"]["code"]) == (402, "base.hub_suspended")

    @pytest.mark.parametrize("status", ["active", "past_due"])
    def test_a_business_in_its_grace_or_paid_up_is_served(self, client, hub, status):
        hub("acme", state={"status": status})
        assert jump_target(browse(client, "/demo/items", "acme.localhost:8000"))  # on to the SaaS's login

    def test_the_suspended_page_is_translated(self, client, hub):
        hub("acme", state={"status": "suspended"})
        response = client.get("/", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE="es")
        assert "Este negocio está suspendido" in response.content.decode()

    def test_the_saas_still_reaches_a_suspended_business(self, client, hub):
        acme = hub("acme", state={"status": "suspended"})
        response = client.get(f"/internal/hubs/{acme.id}", HTTP_HOST="hub.localhost:8000")
        assert response.json()["error"]["code"] == "internal.unsigned"

    def test_the_probes_and_static_files_of_a_suspended_business_still_answer(self, client, hub):
        # The deploy's probe, the static files and the CSP reports are no business of the 402: they answer first.
        hub("acme", state={"status": "suspended"})
        host = "acme.localhost:8000"
        assert client.get("/readyz", HTTP_HOST=host).status_code == 200
        missing = browse(client, "/static/nope.js", host)
        assert (missing.status_code, missing.has_header("Location")) == (404, False)
        report = client.post("/csp-report/", "{}", content_type="application/csp-report", HTTP_HOST=host)
        assert report.status_code == 204

    @pytest.mark.parametrize("host", ["localhost:8000", "hub.localhost:8000", "hub.erplora.internal", "zzz.localhost"])
    def test_the_internal_door_is_never_the_hosts_404(self, client, settings, host):
        # The SaaS's calls go to the private name (`hub`, reserved): its signature is the door (base.internal).
        settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "hub.erplora.internal"]
        response = client.get("/internal/hubs/0199c4b0-0000-7000-8000-000000000001", HTTP_HOST=host)
        assert (response.status_code, response.json()["error"]["code"]) == (401, "internal.unsigned")
