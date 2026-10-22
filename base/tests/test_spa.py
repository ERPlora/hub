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
