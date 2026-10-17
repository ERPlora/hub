"""GET /api/me: base.session.me over HTTP, open to anonymous visitors."""

import pytest
from django.urls import resolve

pytestmark = pytest.mark.django_db


def test_me_is_bound_to_session_me():
    from base.api import router

    [(path, view)] = router.path_operations.items()
    [route] = view.operations
    assert (path, route.methods, route.operation_id) == ("/me", ["GET"], "base.session.me")
    assert route.auth_param is None  # anonymous visitors get user: null, not a 401
    assert resolve("/api/me").url_name


def test_anonymous(client):
    response = client.get("/api/me", HTTP_HOST="a.localhost:8000")
    assert response.status_code == 200
    body = response.json()
    assert (body["user"], body["permissions"], body["scope"]) == (None, [], {"kind": "host", "key": "a"})
    assert body["demo"] is None


def test_employee_on_its_host_and_elsewhere(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    on_a = client.get("/api/me", HTTP_HOST="a.localhost:8000").json()
    on_b = client.get("/api/me", HTTP_HOST="b.localhost:8000").json()
    # demo is the reference app; the other modules' grants and menus are pinned by their own tests.
    demo_permissions = [permission for permission in on_a["permissions"] if permission.startswith("demo.")]
    assert (on_a["user"]["label"], demo_permissions) == ("ana", ["demo.view"])
    assert "demo" in [g["id"] for g in on_a["menu"]]
    assert (on_b["permissions"], on_b["menu"]) == ([], [])


def test_language_follows_the_request(client):
    body = client.get("/api/me", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es").json()
    assert body["language"] == "es"
