"""The table app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to business A's host (``HOST``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST), by
its id or as a person says it.
"""

import json
import uuid

import pytest
from django.test import Client
from live.ninja import ensure_api_parity

from apps.flow.tests.test_api import get, post
from apps.table.api import router
from base.tests.routes import spa_routes
from config.api import api

from .conftest import HOST, HUB_DB, A, B, make_hold, make_session, make_table, make_zone

ROUTES = {
    ("GET", "/table/zones", "table.zone.list"),
    ("GET", "/table/zones/detail", "table.zone.get"),
    ("POST", "/table/zones", "table.zone.create"),
    ("POST", "/table/zones/update", "table.zone.update"),
    ("POST", "/table/zones/delete", "table.zone.delete"),
    ("GET", "/table/tables", "table.table.list"),
    ("GET", "/table/tables/detail", "table.table.get"),
    ("POST", "/table/tables", "table.table.create"),
    ("POST", "/table/tables/bulk_create", "table.table.bulk_create"),
    ("POST", "/table/tables/update", "table.table.update"),
    ("POST", "/table/tables/move", "table.table.move"),
    ("POST", "/table/tables/delete", "table.table.delete"),
    ("GET", "/table/sessions", "table.session.list"),
    ("GET", "/table/sessions/detail", "table.session.get"),
    ("GET", "/table/sessions/by_order", "table.session.by_order"),
    ("GET", "/table/sessions/line", "table.session.line"),
    ("POST", "/table/sessions/open", "table.session.open"),
    ("POST", "/table/sessions/close", "table.session.close"),
    ("POST", "/table/sessions/transfer", "table.session.transfer"),
    ("POST", "/table/sessions/merge", "table.session.merge"),
    ("POST", "/table/sessions/split", "table.session.split"),
    ("POST", "/table/sessions/set_guests", "table.session.set_guests"),
    ("POST", "/table/sessions/park", "table.session.park"),
    ("POST", "/table/sessions/restore", "table.session.restore"),
    ("POST", "/table/sessions/link_order", "table.session.link_order"),
    ("POST", "/table/sessions/delete", "table.session.delete"),
    ("GET", "/table/waiters", "table.waiter.list"),
    ("GET", "/table/floor/status", "table.floor.status"),
    ("GET", "/table/settings", "table.settings.get"),
    ("POST", "/table/settings", "table.settings.update"),
    ("POST", "/table/holds", "table.hold.place"),
    ("GET", "/table/holds/by_reservation", "table.hold.by_reservation"),
    ("POST", "/table/holds/release", "table.hold.release"),
}


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host=A.key, role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("luis", host=A.key, role="hub_employee"))
    return client


# ── Binding ──────────────────────────────────────────────────────────────────────────────────────


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_platforms_writes_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {
        "table.session.close_by_order",
        "table.hold.expire",
        "table.hold.sync_reservation",
        "table.hold.move_reservation",
        "table.hold.forget_customer",
    }


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


# ── Authentication and permissions ───────────────────────────────────────────────────────────────


@HUB_DB
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/table/tables"),
        post(client, "/table/zones", {"name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@HUB_DB
def test_a_waiter_serves_the_room_but_does_not_draw_it(employee_client):
    table = make_table("4", zone=make_zone())
    for path in (
        "/table/zones",
        "/table/tables",
        "/table/sessions",
        "/table/settings",
        "/table/waiters",
    ):
        assert get(employee_client, path).status_code == 200, path
    seated = post(
        employee_client, "/table/sessions/open", {"table": "4", "guests_count": 2}
    )
    assert seated.status_code == 201
    assert seated.json()["waiter_name"] == "luis"
    for response in (
        post(employee_client, "/table/zones", {"name": "Bar"}),
        post(
            employee_client,
            "/table/tables/move",
            {"id": str(table.id), "position_x": 1, "position_y": 1},
        ),
        post(employee_client, "/table/settings", {"prompt_guests_on_seat": False}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@HUB_DB
def test_a_role_on_a_is_no_role_on_b(admin_client, hub_b):
    assert get(admin_client, "/table/tables", host=f"{B.key}.localhost").status_code == 403


# ── Validation and refusals ──────────────────────────────────────────────────────────────────────


@HUB_DB
def test_an_invalid_table_is_422_per_field(admin_client):
    zone = make_zone()
    response = post(
        admin_client,
        "/table/tables",
        {"zone_id": str(zone.id), "capacity": 0, "shape": "oval"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], set(error["fields"])) == (
        "invalid_payload",
        {"capacity", "shape"},
    )


@HUB_DB
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/table/tables", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@HUB_DB
def test_a_taken_table_is_a_409_with_its_own_code_in_the_readers_language(admin_client):
    table = make_table("4", zone=make_zone())
    make_session(table)
    response = admin_client.post(
        "/api/table/sessions/open",
        json.dumps({"table_id": str(table.id)}),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "table.table_not_available"
    assert error["message"].startswith("Esa mesa no se puede sentar")


@HUB_DB
def test_seating_a_reservations_party_over_http_spends_only_its_hold(admin_client):
    table = make_table("4", zone=make_zone())
    ana, bea = str(uuid.uuid7()), str(uuid.uuid7())
    make_hold(table, starts_in=-50, ref=ana, source="reservation", party_size=2)
    later = make_hold(table, starts_in=50, ref=bea, source="reservation", party_size=4)
    response = post(admin_client, "/table/sessions/open", {"table_id": str(table.id), "reservation_id": ana})
    assert (response.status_code, response.json()["guests_count"]) == (201, 2)
    later.refresh_from_db()
    assert later.status == "held"


# ── The whole flow over HTTP ─────────────────────────────────────────────────────────────────────


@HUB_DB
def test_drawing_seating_and_closing_a_table_over_http(admin_client):
    zone = post(admin_client, "/table/zones", {"name": "Terrace"})
    assert zone.status_code == 201
    table = post(admin_client, "/table/tables", {"zone": "Terrace"})
    assert (table.status_code, table.json()["number"]) == (201, "1")
    moved = post(
        admin_client,
        "/table/tables/move",
        {"id": table.json()["id"], "position_x": 200, "position_y": 100},
    )
    assert moved.json()["position_x"] == 200
    seated = post(
        admin_client, "/table/sessions/open", {"table": "1", "guests_count": 3}
    )
    assert seated.status_code == 201
    plan = get(admin_client, "/table/tables", zone_id=zone.json()["id"]).json()
    assert [(row["number"], row["status"], row["guests"]) for row in plan["rows"]] == [
        ("1", "occupied", 3)
    ]
    closed = post(admin_client, "/table/sessions/close", {"id": seated.json()["id"]})
    assert closed.json()["status"] == "closed"
    assert (
        get(admin_client, "/table/tables/detail", id=table.json()["id"]).json()[
            "status"
        ]
        == "available"
    )


@HUB_DB
def test_many_tables_are_made_at_once_over_http_or_none_with_the_taken_numbers(admin_client, make_user):
    # TABLE-F07 (assistant and API: the old module had no screen for it either).
    post(admin_client, "/table/zones", {"name": "Terrace"})
    made = post(
        admin_client,
        "/table/tables/bulk_create",
        {"zone": "Terrace", "count": 3, "prefix": "T", "start_number": 11, "capacity": 2},
    )
    assert made.status_code == 201
    assert [(row["number"], row["capacity"]) for row in made.json()["rows"]] == [
        ("T11", 2),
        ("T12", 2),
        ("T13", 2),
    ]
    again = post(admin_client, "/table/tables/bulk_create", {"zone": "Terrace", "count": 2, "prefix": "T", "start_number": 12})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "table.number_taken")
    assert "T12" in again.json()["error"]["message"]
    assert len(get(admin_client, "/table/tables").json()["rows"]) == 3
    waiter = Client()
    waiter.force_login(make_user("luis", host=A.key, role="hub_employee"))
    refused = post(waiter, "/table/tables/bulk_create", {"zone": "Terrace", "count": 1})
    assert refused.status_code == 403


@HUB_DB
def test_a_table_has_asked_for_the_bill_once_printed_until_it_is_paid_over_http(admin_client, product):
    product("Coffee", "COF", 150, "restaurant.drink")
    check = post(admin_client, "/sale/orders", {"label": "Table 4", "lines": [{"product": "COF"}]})
    assert check.status_code == 201
    table = make_table("4")
    post(admin_client, "/table/sessions/open", {"table_id": str(table.id), "order_id": check.json()["id"]})
    assert get(admin_client, "/table/tables/detail", id=str(table.id)).json()["bill_requested"] is False
    assert post(admin_client, "/sale/orders/print_bill", {"order_id": check.json()["id"]}).status_code == 200
    [row] = get(admin_client, "/table/tables").json()["rows"]
    assert (row["status"], row["bill_requested"]) == ("occupied", True)
    paid = post(
        admin_client,
        "/sale/sales",
        {"idempotency_key": "table-api-bill", "order_id": check.json()["id"], "payments": [{"method": "card"}]},
    )
    assert paid.status_code == 201
    after = get(admin_client, "/table/tables/detail", id=str(table.id)).json()
    assert (after["status"], after["bill_requested"]) == ("available", False)


def test_the_spas_route_map_names_every_table_route():
    assert spa_routes("table.") == ROUTES
