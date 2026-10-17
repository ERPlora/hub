"""The hub's API at /api/: routes bound to operations, OpenAPI, session auth with CSRF, Swagger with nonce.

This module is also the URLconf of its own tests that need a probe API (``ROOT_URLCONF = __name__``
via the ``probe_urls`` fixture).
"""

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client
from django.urls import path
from live.ninja import ensure_api_parity, operation_ids
from live.operations import registry
from ninja import Router

from config.api import api, build_api

probe_router = Router()


@probe_router.post("/echo")
def echo(request):
    return {"user": request.user.get_username()}


@probe_router.get("/open", auth=None)
def open_route(request):
    return {"ok": True}


probe_api = build_api(urls_namespace="config-test-probe", docs=True)
probe_api.add_router("", probe_router)
urlpatterns = [path("probe/", probe_api.urls)]


@pytest.fixture
def probe_urls(settings):
    settings.ROOT_URLCONF = __name__


# --- The real API ------------------------------------------------------------------------------


def test_every_route_is_bound_to_its_operation():
    assert ensure_api_parity(api) == []
    assert "base.session.me" in operation_ids(api)


def test_openapi_is_served_with_operation_names_as_ids(client):
    response = client.get("/api/openapi.json", HTTP_HOST="a.localhost")
    assert response.status_code == 200
    schema = response.json()
    assert (schema["info"]["title"], schema["info"]["version"]) == ("ERPlora Hub API", "1")
    assert schema["paths"]["/api/me"]["get"]["operationId"] == "base.session.me"
    ids = [op["operationId"] for methods in schema["paths"].values() for op in methods.values()]
    assert ids and all(op_id in registry for op_id in ids)


def test_docs_follow_debug(settings):
    settings.DEBUG = True
    assert build_api(urls_namespace="config-test-debug").docs_url == "/docs"
    settings.DEBUG = False
    assert build_api(urls_namespace="config-test-prod").docs_url is None


# --- Session auth and CSRF -----------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_write_is_401_envelope(probe_urls, client):
    response = client.post("/probe/echo", HTTP_HOST="a.localhost")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_session_write_without_csrf_token_is_refused(probe_urls):
    client = Client(enforce_csrf_checks=True)
    client.force_login(get_user_model().objects.create_user("ana", password="pw"))
    response = client.post("/probe/echo", HTTP_HOST="a.localhost")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_session_write_with_csrf_token_passes(probe_urls, settings):
    client = Client(enforce_csrf_checks=True)
    client.force_login(get_user_model().objects.create_user("ana", password="pw"))
    token = _get_new_csrf_string()
    client.cookies[settings.CSRF_COOKIE_NAME] = token
    response = client.post("/probe/echo", HTTP_HOST="a.localhost", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.json() == {"user": "ana"}


@pytest.mark.django_db
def test_route_without_auth_is_open(probe_urls, client):
    assert client.get("/probe/open", HTTP_HOST="a.localhost").json() == {"ok": True}


# --- Swagger -------------------------------------------------------------------------------------


class AssetTags(HTMLParser):
    """The <script> and <link> start tags of a page, with their attributes."""

    def __init__(self, html: str):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "link"):
            self.tags.append((tag, dict(attrs)))

    def scripts(self) -> list[dict[str, str | None]]:
        return [attrs for tag, attrs in self.tags if tag == "script"]

    def external_urls(self) -> list[str]:
        """Every src/href that does not stay on the page's origin: it has a scheme (https:) or a host (//cdn…)."""
        urls = [attrs.get("src") or attrs.get("href") for _, attrs in self.tags]
        return [url for url in urls if url and (urlsplit(url).scheme or urlsplit(url).netloc)]


def assert_swagger_is_self_hosted_with_nonce(response) -> None:
    """Swagger UI comes from ninja's own static files, never a CDN, and every script carries the CSP nonce.

    No <script>/<link> leaves the origin, and no "cdn" anywhere else (an @import, an <img>, an inline import)
    once the CSRF token and the nonce are taken out: they are random and can spell "cdn".
    """
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    html = response.content.decode()
    [csrf_token] = re.findall(r'data-csrf-token="([^"]*)"', html)
    page = AssetTags(html)
    assert len(page.scripts()) == 3  # settings JSON, bundle, init
    assert all(attrs.get("nonce") == nonce for attrs in page.scripts())
    assert page.external_urls() == []
    assert "cdn" not in html.replace(nonce, "").replace(csrf_token, "").lower()


@pytest.mark.django_db
def test_swagger_scripts_carry_the_csp_nonce(probe_urls, client):
    response = client.get("/probe/docs", HTTP_HOST="a.localhost")
    assert response.status_code == 200
    assert_swagger_is_self_hosted_with_nonce(response)


# Random parts of the page pinned to values that spell "cdn" (seen in CI: a CSRF token "…swcdnuv…").
CDN_NONCE = "cdnCDNcdn".ljust(22, "0")
CDN_CSRF_TOKEN = "swcdnuv".ljust(64, "0")


@pytest.mark.django_db
def test_swagger_check_holds_when_the_nonce_and_csrf_token_spell_cdn(probe_urls, client, monkeypatch):
    monkeypatch.setattr("django.utils.csp.generate_nonce", lambda: CDN_NONCE)
    monkeypatch.setattr("django.template.context_processors.get_token", lambda request: CDN_CSRF_TOKEN)
    response = client.get("/probe/docs", HTTP_HOST="a.localhost")
    assert response.status_code == 200
    assert CDN_CSRF_TOKEN in response.content.decode()
    assert f"'nonce-{CDN_NONCE}'" in response["Content-Security-Policy"]
    assert_swagger_is_self_hosted_with_nonce(response)


@pytest.mark.django_db
def test_swagger_check_catches_a_script_or_stylesheet_from_a_cdn(probe_urls, client):
    html = client.get("/probe/docs", HTTP_HOST="a.localhost").content.decode()
    bundle = AssetTags(html).scripts()[1]["src"]
    cdn_script = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
    cdn_style = "//cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
    planted = html.replace(f'src="{bundle}"', f'src="{cdn_script}"').replace(
        "</head>", f'<link rel="stylesheet" href="{cdn_style}"></head>'
    )
    assert AssetTags(html).external_urls() == []
    assert AssetTags(planted).external_urls() == [cdn_style, cdn_script]


# --- Mounting the routers of the apps ------------------------------------------------------------
# mount_app_routers itself lives in live.ninja and is tested there (packages/live/tests/test_ninja.py).


def test_base_and_every_module_are_mounted_by_live_mount_app_routers():
    """base is a platform LiveAppConfig (round 15), so the loop mounts it: no explicit add_router."""
    ids = operation_ids(api)
    assert "base.session.me" in ids
    assert {f"demo.item.{action}" for action in ("list", "detail", "stats", "create", "update", "delete", "add_line")} <= ids


def test_every_route_is_mounted_once():
    schema = api.get_openapi_schema()
    ids = [op["operationId"] for methods in schema["paths"].values() for op in methods.values()]
    assert len(ids) == len(set(ids))
    assert list(schema["paths"]).count("/api/me") == 1
