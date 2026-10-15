"""The kitchen app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST), by its
id or as a person says it.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.kitchen.api import router
from config.api import api

from .conftest import add_line, open_check

ROUTES = {
    ("GET", "/kitchen/board", "kitchen.ticket.board"),
    ("GET", "/kitchen/all_day", "kitchen.ticket.all_day"),
    ("GET", "/kitchen/tickets", "kitchen.ticket.list"),
    ("GET", "/kitchen/tickets/detail", "kitchen.ticket.get"),
    ("GET", "/kitchen/tickets/by_order", "kitchen.ticket.by_order"),
    ("POST", "/kitchen/tickets", "kitchen.ticket.create"),
    ("POST", "/kitchen/tickets/send", "kitchen.ticket.send"),
    ("POST", "/kitchen/tickets/start", "kitchen.ticket.start"),
    ("POST", "/kitchen/tickets/ready", "kitchen.ticket.ready"),
    ("POST", "/kitchen/tickets/serve", "kitchen.ticket.serve"),
    ("POST", "/kitchen/tickets/recall", "kitchen.ticket.recall"),
    ("POST", "/kitchen/tickets/cancel", "kitchen.ticket.cancel"),
    ("POST", "/kitchen/tickets/delete", "kitchen.ticket.delete"),
    ("POST", "/kitchen/tickets/set_rush", "kitchen.ticket.set_rush"),
    ("POST", "/kitchen/tickets/reprint", "kitchen.ticket.reprint"),
    ("POST", "/kitchen/items/bump", "kitchen.item.bump"),
    ("POST", "/kitchen/items/recall", "kitchen.item.recall"),
    ("GET", "/kitchen/stations", "kitchen.station.list"),
    ("POST", "/kitchen/stations", "kitchen.station.create"),
    ("POST", "/kitchen/stations/update", "kitchen.station.update"),
    ("POST", "/kitchen/stations/delete", "kitchen.station.delete"),
    ("GET", "/kitchen/routing", "kitchen.routing.list"),
    ("POST", "/kitchen/routing", "kitchen.routing.set"),
    ("POST", "/kitchen/routing/clear", "kitchen.routing.clear"),
    ("GET", "/kitchen/settings", "kitchen.settings.get"),
    ("POST", "/kitchen/settings", "kitchen.settings.update"),
    ("GET", "/kitchen/log", "kitchen.log.list"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost", **headers):
    return client.post(
        f"/api{path}",
        json.dumps(data),
        content_type="application/json",
        HTTP_HOST=host,
        **headers,
    )


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("luis", host="a", role="hub_employee"))
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


def test_the_systems_writes_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {"kitchen.ticket.receive", "kitchen.ticket.sync"}


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_spas_route_map_names_every_kitchen_route(settings):
    # frontend/generated/operations.json: the op → route map the SDK's client uses.
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("kitchen.")
    }
    assert mine == ROUTES


# ── Authentication and permissions ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/kitchen/board"),
        post(client, "/kitchen/stations", {"name": "Grill"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_a_cook_moves_tickets_but_does_not_run_the_kitchen(employee_client):
    for path in (
        "/kitchen/board",
        "/kitchen/all_day",
        "/kitchen/tickets",
        "/kitchen/stations",
        "/kitchen/log",
    ):
        assert get(employee_client, path).status_code == 200, path
    made = post(
        employee_client, "/kitchen/tickets", {"items": [{"name": "Staff meal"}]}
    )
    assert made.status_code == 201 and made.json()["waiter"] == "luis"
    bumped = post(
        employee_client, "/kitchen/items/bump", {"ticket_id": made.json()["id"]}
    )
    assert bumped.json()["status"] == "ready"
    for response in (
        post(employee_client, "/kitchen/stations", {"name": "Bar"}),
        post(employee_client, "/kitchen/settings", {"print_pass": True}),
        post(
            employee_client, "/kitchen/tickets/cancel", {"ticket_id": made.json()["id"]}
        ),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/kitchen/board", host="b.localhost").status_code == 403


# ── Validation and refusals ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_invalid_station_is_422_per_field(admin_client):
    response = post(admin_client, "/kitchen/stations", {"name": "", "color": "orange"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], set(error["fields"])) == (
        "invalid_payload",
        {"name", "color"},
    )


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/kitchen/tickets", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_a_step_off_the_path_is_a_409_in_the_readers_language(admin_client):
    made = post(admin_client, "/kitchen/tickets", {"items": [{"name": "Soup"}]}).json()
    response = post(
        admin_client,
        "/kitchen/tickets/serve",
        {"ticket_id": made["id"]},
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "kitchen.invalid_transition"
    assert error["message"].startswith("Esa comanda ya no está en el estado")


# ── The whole flow over HTTP ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sending_a_check_and_taking_it_to_the_pass_over_http(admin_client, product):
    station = post(admin_client, "/kitchen/stations", {"name": "Grill"})
    assert station.status_code == 201
    burger = product("Burger")
    routed = post(
        admin_client, "/kitchen/routing", {"station": "Grill", "product": "Burger"}
    )
    assert routed.json()["station_name"] == "Grill"
    order = open_check("Table 4")
    add_line(order.id, burger)
    sent = post(
        admin_client,
        "/kitchen/tickets/send",
        {"order_id": str(order.id), "priority": "rush"},
    )
    assert sent.status_code == 201
    assert (sent.json()["priority"], sent.json()["items"][0]["station_name"]) == (
        "rush",
        "Grill",
    )
    on_grill = get(admin_client, "/kitchen/board", station="grill").json()
    assert [t["label"] for t in on_grill["cooking"]] == ["Table 4"]
    post(admin_client, "/kitchen/items/bump", {"ticket": "table 4", "station": "grill"})
    board = get(admin_client, "/kitchen/board").json()
    assert (board["cooking_count"], board["ready_count"]) == (0, 1)
    served = post(admin_client, "/kitchen/tickets/serve", {"ticket": "table 4"})
    assert served.json()["status"] == "served"
    history = get(admin_client, "/kitchen/log").json()
    assert history["rows"][0]["action"] == "served"
