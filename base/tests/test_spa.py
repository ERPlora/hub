"""The SPA's HTML embeds base.session.me as JSON with the CSP nonce, next to spa-config."""

import json
import re

import pytest

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
    assert (on_a["user"]["label"], on_a["permissions"], [g["id"] for g in on_a["menu"]]) == ("ana", ["demo.view"], ["demo"])
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


@pytest.mark.parametrize(("host", "hub"), [("a.localhost:8000", "a"), ("b.localhost", "b")])
def test_spa_config_points_the_auth_gate_at_the_saas_login_of_its_hub(client, settings, host, hub):
    settings.SAAS_URL = "http://localhost:8001"
    _, config = json_block(client.get("/demo/items", HTTP_HOST=host), "spa-config")
    # Without next: the SPA's auth gate appends `&next=` itself.
    assert config["loginUrl"] == f"http://localhost:8001/hub-login/?hub={hub}"


def test_the_csp_header_lets_the_logout_form_go_on_to_the_saas(client, settings):
    # /auth/logout answers 302 to the SaaS's logout; form-action filters that redirect too.
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    directives = dict(
        directive.strip().split(" ", 1) for directive in response["Content-Security-Policy"].split(";") if directive.strip()
    )
    assert directives["form-action"] == f"'self' {settings.SAAS_URL.rstrip('/')}"


@pytest.mark.parametrize(
    ("cookie", "painted"),
    [*[(p, p) for p in ("erplora", "terracotta", "corporate", "minimal", "forest", "ocean", "violet")], ("neon", "erplora")],
)
def test_the_shell_paints_every_palette_of_the_ui_and_the_default_for_any_other(client, cookie, painted):
    client.cookies["ep_palette"] = cookie
    response = client.get("/demo/items", HTTP_HOST="a.localhost:8000")
    assert f'data-ep-palette="{painted}"' in response.content.decode()
