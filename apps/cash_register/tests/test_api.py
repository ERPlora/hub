"""The cash register app's routes: each bound to its operation, and the main flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.cash_register.api import router
from config.api import api

ROUTES = {
    ("GET", "/cash_register/settings", "cash_register.settings.get"),
    ("POST", "/cash_register/settings", "cash_register.settings.update"),
    ("GET", "/cash_register/registers", "cash_register.register.list"),
    ("POST", "/cash_register/registers", "cash_register.register.create"),
    ("POST", "/cash_register/registers/update", "cash_register.register.update"),
    ("GET", "/cash_register/sessions", "cash_register.session.list"),
    ("GET", "/cash_register/sessions/current", "cash_register.session.current"),
    ("GET", "/cash_register/sessions/detail", "cash_register.session.get"),
    ("GET", "/cash_register/sessions/closing_summary", "cash_register.session.closing_summary"),
    ("POST", "/cash_register/sessions/open", "cash_register.session.open"),
    ("POST", "/cash_register/sessions/close", "cash_register.session.close"),
    ("POST", "/cash_register/sessions/auto_close", "cash_register.session.auto_close"),
    ("POST", "/cash_register/sessions/print", "cash_register.session.print"),
    ("GET", "/cash_register/movements", "cash_register.movement.list"),
    ("POST", "/cash_register/movements", "cash_register.movement.add"),
    ("GET", "/cash_register/counts", "cash_register.count.list"),
    ("POST", "/cash_register/counts", "cash_register.count.add"),
    ("GET", "/cash_register/currency", "cash_register.currency.get"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    return client


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_spas_route_map_names_every_cash_register_route():
    from django.conf import settings

    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("cash_register.")
    }
    assert mine == ROUTES


def test_every_operation_has_a_route_and_is_open_to_api_keys():
    from live.operations import registry

    ops = {name for name in registry if name.startswith("cash_register.")}
    assert ops == {operation for _m, _p, operation in ROUTES}
    assert all(registry[name].expose_api for name in ops)


@pytest.mark.django_db
def test_an_employee_opens_records_counts_and_closes_over_http(employee_client):
    opened = post(
        employee_client, "/cash_register/sessions/open", {"opening_balance": 10000}
    )
    assert opened.status_code == 201
    session = opened.json()
    assert session["status"] == "open"
    moved = post(
        employee_client,
        "/cash_register/movements",
        {"type": "out", "amount": 500, "description": "Bread"},
    )
    assert moved.status_code == 201 and moved.json()["signed_amount"] == -500
    counted = post(
        employee_client,
        "/cash_register/counts",
        {"denominations": {"bills": {"50": 1}, "coins": {"2": 20}}},
    )
    assert counted.status_code == 201 and counted.json()["total"] == 9000
    closed = post(
        employee_client,
        "/cash_register/sessions/close",
        {"session_id": session["id"], "closing_balance": 9000},
    )
    assert closed.status_code == 200
    assert (closed.json()["expected_balance"], closed.json()["difference"]) == (
        9500,
        -500,
    )
    detail = get(
        employee_client, "/cash_register/sessions/detail", session=session["number"]
    )
    assert detail.json()["summary"]["total_cash_out"] == 500
    assert (
        get(
            employee_client, "/cash_register/movements", session_id=session["id"]
        ).json()["total"]
        == 1
    )
    assert (
        get(employee_client, "/cash_register/counts", session_id=session["id"]).json()[
            "total"
        ]
        == 1
    )
    assert get(employee_client, "/cash_register/sessions").json()["total"] == 1


@pytest.mark.django_db
def test_the_close_summary_is_read_over_http_before_closing(employee_client):
    session = post(employee_client, "/cash_register/sessions/open", {"opening_balance": 10000}).json()
    seen = get(employee_client, "/cash_register/sessions/closing_summary", closing_balance=9500)
    assert seen.status_code == 200
    assert (seen.json()["number"], seen.json()["closing_balance"], seen.json()["difference"]) == (session["number"], 9500, -500)
    asked = get(employee_client, "/cash_register/sessions/closing_summary")
    assert asked.status_code == 409
    assert asked.json()["error"]["code"] == "cash_register.closing_balance_required"
    assert get(employee_client, "/cash_register/sessions/current").json()["session"]["status"] == "open"


@pytest.mark.django_db
def test_a_refusal_is_the_error_envelope(employee_client):
    post(employee_client, "/cash_register/sessions/open", {"opening_balance": 100})
    response = post(
        employee_client, "/cash_register/sessions/open", {"opening_balance": 100}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cash_register.session_already_open"
    response = post(
        employee_client, "/cash_register/movements", {"type": "out", "amount": 101}
    )
    assert (
        response.json()["error"]["code"] == "cash_register.negative_balance_not_allowed"
    )


@pytest.mark.django_db
def test_a_bad_payload_is_a_422_by_field(employee_client):
    response = post(
        employee_client, "/cash_register/movements", {"type": "in", "amount": 0}
    )
    assert response.status_code == 422
    assert "amount" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_the_employee_neither_changes_the_settings_nor_creates_drawers(employee_client):
    assert (
        post(
            employee_client, "/cash_register/settings", {"require_blind_count": True}
        ).status_code
        == 403
    )
    assert (
        post(employee_client, "/cash_register/registers", {"name": "Bar"}).status_code
        == 403
    )
    assert get(employee_client, "/cash_register/settings").status_code == 200


@pytest.mark.django_db
def test_the_admin_sets_up_the_drawer_over_http(admin_client):
    assert (
        post(
            admin_client, "/cash_register/settings", {"auto_close_time": "23:00"}
        ).json()["auto_close_time"]
        == "23:00"
    )
    created = post(admin_client, "/cash_register/registers", {"name": "Bar"})
    assert created.status_code == 201
    renamed = post(
        admin_client,
        "/cash_register/registers/update",
        {"register_id": created.json()["id"], "name": "Terrace"},
    )
    assert renamed.json()["name"] == "Terrace"
    assert [
        r["name"] for r in get(admin_client, "/cash_register/registers").json()["rows"]
    ] == ["Terrace"]
    assert get(admin_client, "/cash_register/currency").json()["currency"] == "EUR"
    assert post(admin_client, "/cash_register/sessions/auto_close", {}).json() == {
        "closed": []
    }
    assert (
        get(admin_client, "/cash_register/sessions/current").json()["session"] is None
    )


@pytest.mark.django_db
def test_without_a_session_nothing_is_read(client):
    assert get(client, "/cash_register/sessions").status_code == 401
