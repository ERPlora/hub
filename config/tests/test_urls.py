"""URLconf of hub-next: Django's own prefixes first, the SPA shell for every other path."""

import json

import pytest
from django.urls import resolve
from live.live_view import live_stream

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"
SHELL_MARK = '<div id="app"></div>'


def is_shell(response) -> bool:
    return SHELL_MARK in response.content.decode(errors="replace")


def test_healthz(client):
    response = client.get("/healthz", HTTP_HOST=HOST)
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_readyz(client):
    response = client.get("/readyz", HTTP_HOST=HOST)
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_openapi(client):
    assert client.get("/api/openapi.json", HTTP_HOST=HOST).status_code == 200


@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("path", ["/", "/demo/items", "/demo/items/0192f0c4-7a1e-7000-8000-000000000000", "/apiary"])
def test_spa_paths_get_the_shell(client, path):
    response = client.get(path, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert is_shell(response)


@pytest.mark.parametrize("path", ["/api/nope", "/internal/hubs", "/ws/print", "/p/abc", "/static/nope.js", "/csp-report/x", "/auth/nope"])
def test_django_prefixes_never_get_the_shell(client, path):
    response = client.get(path, HTTP_HOST=HOST)
    assert response.status_code == 404
    assert not is_shell(response)


@pytest.mark.parametrize(
    "path",
    ["/internal/hubs/0199c4b0-0000-7000-8000-000000000001", "/internal/hubs/0199c4b0-0000-7000-8000-000000000001/restore"],
)
def test_the_registry_door_is_routed_and_refuses_an_unsigned_call(client, path):
    # The SaaS's PUT/GET/DELETE /internal/hubs/{id} and POST …/restore (base.internal), never the shell.
    response = client.put(path, b"{}", content_type="application/json", HTTP_HOST=HOST)
    assert (response.status_code, response.json()["error"]["code"]) == (401, "internal.unsigned")
    assert not is_shell(response)


def test_the_registry_routes_resolve_to_their_views():
    assert resolve("/internal/hubs/0199c4b0-0000-7000-8000-000000000001").url_name == "internal-hub"
    assert resolve("/internal/hubs/0199c4b0-0000-7000-8000-000000000001/restore").url_name == "internal-hub-restore"


def test_unknown_api_path_is_the_json_error_envelope(client):
    response = client.get("/api/nope", HTTP_HOST=HOST)
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not found"}}


def test_wrong_method_on_an_api_route_is_the_json_405_envelope(client):
    response = client.delete("/api/me", HTTP_HOST=HOST)
    assert response.status_code == 405
    assert response.json() == {"error": {"code": "method_not_allowed", "message": "Method not allowed"}}
    assert response["Allow"] == "GET"


@pytest.mark.usefixtures("spa_manifest")
def test_built_shell_links_the_vite_build_with_nonces(client):
    response = client.get("/demo/items", HTTP_HOST=HOST)
    html = response.content.decode()
    csp = response["Content-Security-Policy"]
    nonce = csp.split("'nonce-", 1)[1].split("'", 1)[0]
    assert f'<script type="module" src="/static/spa/assets/main-abc123.js" nonce="{nonce}">' in html
    assert f'<link rel="modulepreload" href="/static/spa/assets/vendor-789.js" nonce="{nonce}">' in html
    assert '<link rel="stylesheet" href="/static/spa/assets/main-def456.css">' in html
    assert 'id="spa-config"' in html and 'id="session-me"' in html
    for directive in ("'strict-dynamic'", "ipc:", "http://ipc.localhost"):
        assert directive in csp


def test_debug_shell_loads_from_the_vite_dev_server(client, settings):
    settings.DEBUG = True
    html = client.get("/demo/items", HTTP_HOST=HOST).content.decode()
    assert 'src="http://localhost:5173/static/spa/@vite/client"' in html
    assert 'src="http://localhost:5173/static/spa/frontend/main.ts"' in html


@pytest.mark.parametrize("path", ["/admin/", "/admin/login/", "/admin/hub/a/"])
def test_the_admin_is_not_found_on_a_hub_host(client, admin_user, path):
    # The Hub admin lives only on the platform host hubs.<domain> (PLAN §18.1.3), also for a superuser.
    for response in (client.get(path, HTTP_HOST=HOST), client.post(path, HTTP_HOST=HOST)):
        assert (response.status_code, response.has_header("Location"), is_shell(response)) == (404, False, False)
    client.force_login(admin_user)
    response = client.get(path, HTTP_HOST=HOST)
    assert (response.status_code, response.has_header("Location"), is_shell(response)) == (404, False, False)


def test_the_admin_deep_link_wins_over_the_admin_s_own_urls():
    # Otherwise admin/<app_label>/ would take /admin/hub/ (round 13, PLAN §18.1).
    assert resolve("/admin/hub/a/").url_name == "admin-hub"


def test_csp_report(client):
    response = client.post(
        "/csp-report/", json.dumps({"csp-report": {"violated-directive": "script-src"}}), content_type="application/json"
    )
    assert response.status_code == 204


def test_api_live_is_the_live_stream_and_wins_over_the_api():
    assert resolve("/api/live").func is live_stream


def test_api_live_without_a_session_is_401_envelope(client):
    response = client.get("/api/live", HTTP_HOST=HOST)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
