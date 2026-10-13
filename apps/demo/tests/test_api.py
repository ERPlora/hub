"""The demo app's routes: each bound to its operation, and the whole CRUD over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.demo.api import router
from config.api import api

ROUTES = {
    ("GET", "/demo/items", "demo.item.list"),
    ("GET", "/demo/items/detail", "demo.item.detail"),
    ("GET", "/demo/items/stats", "demo.item.stats"),
    ("POST", "/demo/items", "demo.item.create"),
    ("POST", "/demo/items/update", "demo.item.update"),
    ("POST", "/demo/items/delete", "demo.item.delete"),
    ("POST", "/demo/items/add_line", "demo.item.add_line"),
}
# The SPA's op → route map (hand-written for the PoC until V3 generates it from the OpenAPI).
SPA_ROUTES = settings.BASE_DIR / "frontend" / "generated" / "operations.json"


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    return client


# Binding


def test_seven_routes_each_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_openapi_matches_the_spa_route_map(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        op["operationId"]: {"method": method, "path": path}
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("demo.")
    }
    expected = {name: route for name, route in json.loads(Path(SPA_ROUTES).read_text()).items() if name.startswith("demo.")}
    assert served == expected


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/demo/items"), post(client, "/demo/items", {"name": "x"})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_but_does_not_write(employee_client):
    assert get(employee_client, "/demo/items").status_code == 200
    for response in (get(employee_client, "/demo/items/stats"), post(employee_client, "/demo/items", {"name": "x"})):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    response = get(admin_client, "/demo/items", host="b.localhost")
    assert response.status_code == 403


# Validation


@pytest.mark.django_db
def test_an_invalid_item_is_422_per_field(admin_client):
    response = post(admin_client, "/demo/items", {"name": "", "status": "closed"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {"name", "status"}


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/demo/items", limit=101)
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"limit"}


@pytest.mark.django_db
def test_a_missing_or_malformed_id(admin_client):
    missing = get(admin_client, "/demo/items/detail", id=str(uuid.uuid7()))
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    malformed = get(admin_client, "/demo/items/detail", id="nope")
    assert (malformed.status_code, set(malformed.json()["error"]["fields"])) == (422, {"id"})


# The whole CRUD


@pytest.mark.django_db
def test_crud_round_trip(admin_client):
    created = post(admin_client, "/demo/items", {"name": "Table 1"})
    assert created.status_code == 201
    item = created.json()
    assert (item["name"], item["status"], item["note"], item["line_count"], item["lines"]) == ("Table 1", "open", "", 0, [])
    item_id = item["id"]

    page = get(admin_client, "/demo/items", search="table").json()
    assert ([row["id"] for row in page["rows"]], page["total"], page["limit"], page["offset"]) == ([item_id], 1, 50, 0)
    assert get(admin_client, "/demo/items/detail", id=item_id).json() == item

    updated = post(admin_client, "/demo/items/update", {"id": item_id, "note": "by the window"})
    assert (updated.status_code, updated.json()["note"]) == (200, "by the window")

    line = {"id": item_id, "text": "Coffee", "qty": 1.5, "client_line_id": str(uuid.uuid7())}
    added = post(admin_client, "/demo/items/add_line", line)
    assert added.status_code == 200
    [added_line] = added.json()["lines"]
    assert (added_line["text"], added_line["qty"], added_line["position"]) == ("Coffee", "1.500", 1)
    assert added_line["client_line_id"] == line["client_line_id"]
    assert post(admin_client, "/demo/items/add_line", line).json() == added.json()  # repeated: same item, one line

    assert get(admin_client, "/demo/items/stats").json() == {"total": 1, "open": 1, "done": 0, "lines": 1}

    post(admin_client, "/demo/items/update", {"id": item_id, "status": "done"})
    closed = post(admin_client, "/demo/items/add_line", {"id": item_id, "text": "Tea", "qty": 1})
    assert (closed.status_code, closed.json()["error"]["code"]) == (409, "demo.item_done")

    deleted = post(admin_client, "/demo/items/delete", {"id": item_id})
    assert (deleted.status_code, deleted.json()) == (200, {"id": item_id})
    assert get(admin_client, "/demo/items/detail", id=item_id).status_code == 404
