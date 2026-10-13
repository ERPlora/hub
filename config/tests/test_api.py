"""The hub's API at /api/: routes bound to operations, OpenAPI, session auth with CSRF, Swagger with nonce.

This module is also the URLconf of its own tests that need a probe API (``ROOT_URLCONF = __name__``
via the ``probe_urls`` fixture).
"""

import re

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


@pytest.mark.django_db
def test_swagger_scripts_carry_the_csp_nonce(probe_urls, client):
    response = client.get("/probe/docs", HTTP_HOST="a.localhost")
    assert response.status_code == 200
    [nonce] = re.findall(r"'nonce-([^']+)'", response["Content-Security-Policy"])
    scripts = re.findall(r"<script\b[^>]*>", response.content.decode())
    assert len(scripts) == 3  # settings JSON, bundle, init
    assert all(f'nonce="{nonce}"' in tag for tag in scripts)
    assert "cdn" not in response.content.decode().lower()


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
