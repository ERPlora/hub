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
    [
        ("/home/setup", "base.setup.status"),
        ("/home/widgets", "base.widget.list"),
        ("/home/bell", "base.bell.counters"),
        ("/home/notices", "base.notice.list"),
    ],
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
    # Base's own steps; the modules of the store bring theirs too (VeriFactu's, FIX-VERIFACTU-SETUP-HOOKS).
    assert [item["key"] for item in body["items"] if item["app"] == "base"] == ["base.apps", "base.team"]
    assert body["blocking_pending"] == 0


def test_an_anonymous_visitor_gets_no_home(client):
    for path in ("/api/home/setup", "/api/home/widgets", "/api/home/bell", "/api/home/notices"):
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
        ("GET", "/api/home/notices", "base.notice.list"),
        ("GET", "/api/apps", "base.app.list"),
        ("GET", "/api/system/plan", "base.plan.usage"),
        *DATA_ROUTES,
    }


# Settings › Data (APP-BASE-2): the blueprints, the loads, the export and the reset. Reading what a file brings goes by
# POST (a command that writes nothing: its body, the file, does not fit in a query string); the export by GET.
DATA_ROUTES = {
    ("GET", "/api/settings/data/blueprints", "base.blueprint.list"),
    ("POST", "/api/settings/data/blueprints/inspect", "base.blueprint.inspect"),
    ("POST", "/api/settings/data/blueprints/import", "base.blueprint.import"),
    ("GET", "/api/settings/data/export", "base.blueprint.export"),
    ("GET", "/api/settings/data/imports", "base.import.list"),
    ("POST", "/api/settings/data/imports/undo", "base.import.undo"),
    ("GET", "/api/settings/data/datasets", "base.dataset.list"),
    ("POST", "/api/settings/data/reset", "base.hub.reset"),
}


@pytest.mark.parametrize(("method", "path", "operation"), sorted(DATA_ROUTES))
def test_the_data_routes_are_bound_to_their_operations(method, path, operation):
    from base.api import router

    [route] = router.path_operations[path.removeprefix("/api")].operations
    assert (route.methods, route.operation_id) == ([method], operation)
    assert resolve(path).url_name


def test_an_owner_loads_a_file_over_http_bigger_than_any_other_body(client, make_user, settings):
    import base64

    from base import blueprint

    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
    client.force_login(make_user("ana", host="a", role="hub_owner"))
    zone = {"name": "Patio", "description": "", "color": "warning", "sort_order": 1}
    bundle = blueprint.Bundle(
        manifest=blueprint.manifest(
            name="Patio", language="es", country="ES", purpose="template", created_at="", vertical="", apps=["table"]
        ),
        data={"table.zone": [zone]},
    )
    # Beyond Django's ceiling for any other view (1 KB here): a field the schema ignores makes the body weigh more.
    padded = {"file_base64": base64.b64encode(blueprint.write_zip(bundle)).decode(), "apps": ["table"], "note": "x" * 2048}

    response = client.post(
        "/api/settings/data/blueprints/import", padded, content_type="application/json", HTTP_HOST="a.localhost:8000"
    )

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "complete"


def test_an_employee_gets_no_data_over_http(client, make_user):
    client.force_login(make_user("eva", host="a", role="hub_employee"))

    response = client.get("/api/settings/data/blueprints", HTTP_HOST="a.localhost:8000")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
