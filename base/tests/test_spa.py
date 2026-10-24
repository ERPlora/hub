"""The SPA's HTML embeds base.session.me as JSON with the CSP nonce, next to spa-config."""

import json
import re
from urllib.parse import urlsplit

import pytest
from django.utils.csp import CSP
from live.csp import base_policy, debug_policy

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]


def json_block(response, block_id: str) -> tuple[str, dict]:
    match = re.search(
        rf'<script id="{block_id}" type="application/json" nonce="([^"]+)">(.*?)</script>',
        response.content.decode(),
        re.S,
    )
    assert match, f"no {block_id} block"
    return match.group(1), json.loads(match.group(2))


def csp_nonce(response) -> str:
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    return nonce


def csp_directives(response) -> dict[str, str]:
    return dict(
        directive.strip().split(" ", 1) for directive in response["Content-Security-Policy"].split(";") if directive.strip()
    )


def test_anonymous_shell_embeds_an_empty_session(client):
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    assert response.status_code == 200
    nonce, me = json_block(response, "session-me")
    assert nonce == csp_nonce(response)
    assert (me["user"], me["permissions"], me["menu"], me["scope"]) == (None, [], [], {"kind": "host", "key": "a"})
    config_nonce, config = json_block(response, "spa-config")
    assert config_nonce == nonce
    assert config["liveUrl"] == "/api/live"


def test_logged_in_shell_embeds_its_session_on_that_host(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    _, on_a = json_block(client.get("/demo/items", HTTP_HOST="a.localhost:8000"), "session-me")
    _, on_b = json_block(client.get("/demo/items", HTTP_HOST="b.localhost:8000"), "session-me")
    # demo is the reference app; the other modules' grants and menus are pinned by their own tests.
    demo_permissions = [permission for permission in on_a["permissions"] if permission.startswith("demo.")]
    assert (on_a["user"]["label"], demo_permissions) == ("ana", ["demo.view"])
    assert "demo" in [g["id"] for g in on_a["menu"]]
    assert (on_b["permissions"], on_b["menu"]) == ([], [])


def test_embedded_json_cannot_close_the_script(client, make_user):
    client.force_login(make_user("eve", host="a", first_name="</script><script>alert(1)//"))
    response = client.get("/demo/items", HTTP_HOST="a.localhost")
    assert "</script><script>alert(1)" not in response.content.decode()
    _, me = json_block(response, "session-me")
    assert me["user"]["label"].startswith("</script>")


def test_shell_is_never_cached_and_sets_the_csrf_cookie(client, settings):
    response = client.get("/demo/items", HTTP_HOST="a.localhost")
    assert "no-store" in response["Cache-Control"]
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_only_get_and_head(client):
    assert client.post("/demo/items", HTTP_HOST="a.localhost").status_code == 405
    assert client.head("/demo/items", HTTP_HOST="a.localhost").status_code == 200


@pytest.mark.parametrize("host", ["a.localhost:8000", "b.localhost"])
def test_spa_config_points_the_auth_gate_at_the_hub_s_own_jump_to_the_saas_login(client, host):
    # /auth/login gives the jump its state (and this browser its cookie); the gate appends `?next=`.
    _, config = json_block(client.get("/demo/items", HTTP_HOST=host), "spa-config")
    assert config["loginUrl"] == "/auth/login"


def test_the_csp_header_lets_the_logout_form_go_on_to_the_saas(client, settings):
    # /auth/logout answers 302 to the SaaS's logout; form-action filters that redirect too.
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    assert csp_directives(response)["form-action"] == f"'self' {settings.SAAS_URL.rstrip('/')}"


def test_the_csp_header_lets_the_thread_show_the_saas_s_attachments_and_widens_nothing_else(client, settings):
    # WHATSAPP_INBOX-F06: the SaaS serves a conversation's photos and voice notes (/whatsapp/media/<id>); the
    # thread shows and plays them from its origin only. default-src, script-src and connect-src (Tauri's ipc:
    # bridge) stay as live.csp gives them.
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    directives = csp_directives(response)
    saas = "{0.scheme}://{0.netloc}".format(urlsplit(settings.SAAS_URL))
    # The policy was built at import, with the DEBUG of the checkout (the test run turns DEBUG off later).
    dev_server = settings.LIVE["spa"]["dev_server"]
    policy = debug_policy(dev_server) if dev_server else base_policy()
    nonce = f"'nonce-{csp_nonce(response)}'"
    assert directives["img-src"] == " ".join([*policy["img-src"], saas])
    assert directives["media-src"] == f"'self' {saas}"
    for name in ("default-src", "script-src", "connect-src"):
        assert directives[name] == " ".join(nonce if value == CSP.NONCE else value for value in policy[name])


@pytest.mark.parametrize(
    ("cookie", "painted"),
    [*[(p, p) for p in ("erplora", "terracotta", "corporate", "minimal", "forest", "ocean", "violet")], ("neon", "erplora")],
)
def test_the_shell_paints_every_palette_of_the_ui_and_the_default_for_any_other(client, cookie, painted):
    client.cookies["ep_palette"] = cookie
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    assert f'data-ep-palette="{painted}"' in response.content.decode()


@pytest.mark.parametrize("slug", ["a", "b"])
def test_the_shell_embeds_this_hub_s_name_and_where_its_plan_is_changed_on_the_saas(client, settings, make_user, slug):
    # BASE-G127: the Home is headed by the business's name; BASE-G169: «Upgrade plan» opens its plan on erplora.com.
    # APP-BASE-1 (PLAN-SAAS §1.1): the user menu's «My account» and «Report a problem» open the SaaS's own pages.
    from base.models import Hub

    Hub.objects.filter(slug=slug).update(name=f"Bar {slug.upper()}")
    hub = Hub.objects.get(slug=slug)
    saas = settings.SAAS_URL.rstrip("/")
    client.force_login(make_user("ana", host=slug, role="hub_employee"))
    _, home = json_block(client.get("/demo/items", HTTP_HOST=f"{slug}.localhost:8000"), "hub-home")
    assert home == {
        "name": f"Bar {slug.upper()}",
        "plan_url": f"{saas}/store/plans?business={hub.id}",
        "account_url": f"{saas}/account",
        "report_url": f"{saas}/report-a-problem",
        # APP-BASE-3: the session's way in (base/tests/test_access_spa.py).
        "access": {"credential": "account", "switch_user": False, "idle_minutes": None},
    }


def test_a_visitor_without_a_session_learns_nothing_of_the_hub(client):
    # The shell's auth gate sends a visitor without a session to the login, so the HTML carries no `hub-home`:
    # neither the business's name nor the hub's id (the one in the plan's address on erplora.com).
    from base.models import Hub

    Hub.objects.filter(slug="a").update(name="Bar Secreto")
    hub = Hub.objects.get(slug="a")
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="hub-home"' not in html
    assert "Bar Secreto" not in html
    assert str(hub.id) not in html


# flow: ninguno — the SPA's answer to a path without a URL of its own (file probes: /robots.txt, /favicon.ico).
# A path whose last segment has an extension names a file; the SPA has no route like it. A probe for a file Django
# does not serve (a crawler's robots.txt, a browser's favicon, a scanner's wp-login.php) gets a plain 404: no shell
# and no cookie, so the website's «no cookies» holds and a crawler reads no HTML as its robots.txt.
BROWSER_PAGE = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
BROWSER_IMAGE = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
FILE_PROBES = [
    "/robots.txt",
    "/favicon.ico",
    "/sitemap.xml",
    "/apple-touch-icon.png",
    "/wp-login.php",
    "/demo/items/main.js.map",
    "/.env",
]
DEEP_LINK = "/demo/items/0192f0c4-7d2e-7c4a-9b1e-2f6a8d3c5e10"


def is_the_shell(response) -> bool:
    return 'id="spa-config"' in response.content.decode()


@pytest.mark.parametrize("path", FILE_PROBES)
@pytest.mark.parametrize("accept", ["*/*", BROWSER_PAGE, BROWSER_IMAGE])
def test_a_probe_for_a_file_without_a_session_gets_a_plain_404_with_no_cookie(client, path, accept):
    response = client.get(path, HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=accept)
    assert (response.status_code, dict(response.cookies)) == (404, {})
    assert not is_the_shell(response)


def test_a_head_of_robots_txt_is_the_same_404(client):
    response = client.head("/robots.txt", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT="*/*")
    assert (response.status_code, dict(response.cookies)) == (404, {})


def test_a_signed_in_browser_asking_for_the_favicon_gets_the_404_and_no_csrf_cookie(client, settings, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = client.get("/favicon.ico", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=BROWSER_IMAGE)
    assert response.status_code == 404
    assert settings.CSRF_COOKIE_NAME not in response.cookies
    assert not is_the_shell(response)


@pytest.mark.parametrize("path", ["/", "/demo/items", DEEP_LINK, "/demo/items/new"])
def test_a_signed_in_navigation_still_gets_the_shell_and_its_csrf_cookie(client, settings, make_user, path):
    # Without the cookie the SDK's first write is refused (403): every page load of the SPA sets it.
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = client.get(path, HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=BROWSER_PAGE)
    assert response.status_code == 200 and is_the_shell(response)
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_a_deep_link_without_a_session_still_jumps_to_the_saas_login(client, settings):
    response = client.get(DEEP_LINK, HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=BROWSER_PAGE)
    location = urlsplit(response["Location"]) if response.status_code == 302 else None
    assert location is not None
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{settings.SAAS_URL.rstrip('/')}/hub-login/"


def test_a_call_without_a_session_that_does_not_ask_for_a_page_still_gets_the_shell_and_its_cookie(client, settings):
    response = client.get(DEEP_LINK, HTTP_HOST="a.localhost:8000", HTTP_ACCEPT="*/*")
    assert response.status_code == 200 and is_the_shell(response)
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_the_home_page_of_a_published_website_is_still_the_website_with_no_cookie(client, monkeypatch):
    from django.apps import apps
    from django.http import HttpResponse

    from base import public_home

    class Published:
        def is_published(self, hub) -> bool:
            return True

        def respond(self, request) -> HttpResponse:
            return HttpResponse("<!doctype html><title>Bar A</title>", content_type="text/html; charset=utf-8")

    real = apps.is_installed
    monkeypatch.setattr(apps, "is_installed", lambda name: True if name == public_home.WEBSITE_APP else real(name))
    monkeypatch.setattr(public_home, "_provider", Published)
    response = client.get("/", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=BROWSER_PAGE)
    assert (response.status_code, dict(response.cookies)) == (200, {})
    assert "<title>Bar A</title>" in response.content.decode() and not is_the_shell(response)


def test_a_file_s_path_with_a_trailing_slash_is_the_same_404_and_no_redirect_to_the_shell(client):
    # APPEND_SLASH sends a path without a route to the one with a slash when that one resolves: it must not.
    for path in ("/robots.txt", "/robots.txt/"):
        response = client.get(path, HTTP_HOST="a.localhost:8000", HTTP_ACCEPT="*/*")
        assert (response.status_code, dict(response.cookies)) == (404, {}), path


# The old hub's <head> (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE): with /favicon.ico a 404, the shell declares its
# tab and home-screen icons, static files of the Hub (live.spa, LIVE["spa"]["icons"]), never a CDN.
HUB_ICONS = [
    ("icon", "base/icons/favicon.ico", ' sizes="any"'),
    ("apple-touch-icon", "base/icons/apple-touch-icon.png", ""),
]


@pytest.mark.parametrize("signed_in", [False, True])
def test_the_shell_declares_the_old_hub_s_icons_from_its_static_files(client, make_user, signed_in):
    from django.contrib.staticfiles import finders

    if signed_in:
        client.force_login(make_user("ana", host="a", role="hub_employee"))
    html = client.get("/demo/items", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT="*/*").content.decode()
    head = html[: html.index("</head>")]
    for rel, path, sizes in HUB_ICONS:
        assert f'<link rel="{rel}" href="/static/{path}"{sizes}>' in head
        assert finders.find(path), f"{path} is no static file of the Hub"
