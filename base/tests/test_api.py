"""base over HTTP: GET /api/me (base.session.me, open to anonymous visitors) and the Home's three queries."""

import pytest
from django.urls import resolve

pytestmark = pytest.mark.django_db


def test_me_is_bound_to_session_me():
    from base.api import router

    [route] = router.path_operations["/me"].operations
    assert (route.methods, route.operation_id) == (["GET"], "base.session.me")
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


# The Home (PLAN-HUB round 2026-10-21): base.setup.status, base.widget.list and base.bell.counters


@pytest.mark.parametrize(
    ("path", "operation"),
    [("/home/setup", "base.setup.status"), ("/home/widgets", "base.widget.list"), ("/home/bell", "base.bell.counters")],
)
def test_the_homes_routes_are_bound_to_its_queries(path, operation):
    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == (["GET"], operation)
    assert resolve(f"/api{path}").url_name


def test_the_list_of_an_owner_over_http(client, make_user, settings):
    settings.SHOW_UNLISTED_MODULES = False
    client.force_login(make_user("ana", host="a", role="hub_owner"))

    response = client.get("/api/home/setup", HTTP_HOST="a.localhost:8000")

    assert response.status_code == 200
    body = response.json()
    assert [item["key"] for item in body["items"]] == ["base.apps", "base.team"]
    assert body["blocking_pending"] == 0


def test_an_anonymous_visitor_gets_no_home(client):
    for path in ("/api/home/setup", "/api/home/widgets", "/api/home/bell"):
        response = client.get(path, HTTP_HOST="a.localhost:8000")
        assert response.status_code in (401, 403), path


def test_the_spas_route_map_names_every_base_route(settings):
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    import json

    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {(route["method"].upper(), route["path"], op) for op, route in spa.items() if op.startswith("base.")}
    assert mine == {
        ("GET", "/api/me", "base.session.me"),
        ("GET", "/api/home/setup", "base.setup.status"),
        ("GET", "/api/home/widgets", "base.widget.list"),
        ("GET", "/api/home/bell", "base.bell.counters"),
    }
