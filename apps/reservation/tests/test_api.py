"""The reservation app's routes: each bound to its operation, and the whole book over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST), by
its id or as a person says it.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.reservation.api import router
from config.api import api

from .conftest import make_reservation, make_table, open_week

ROUTES = {
    ("GET", "/reservation/reservations", "reservation.reservation.list"),
    ("GET", "/reservation/reservations/detail", "reservation.reservation.get"),
    ("POST", "/reservation/reservations", "reservation.reservation.create"),
    ("POST", "/reservation/reservations/update", "reservation.reservation.update"),
    ("POST", "/reservation/reservations/confirm", "reservation.reservation.confirm"),
    ("POST", "/reservation/reservations/seat", "reservation.reservation.seat"),
    ("POST", "/reservation/reservations/complete", "reservation.reservation.complete"),
    ("POST", "/reservation/reservations/cancel", "reservation.reservation.cancel"),
    ("POST", "/reservation/reservations/no_show", "reservation.reservation.no_show"),
    ("POST", "/reservation/reservations/delete", "reservation.reservation.delete"),
    (
        "POST",
        "/reservation/reservations/release_unconfirmed",
        "reservation.reservation.release_unconfirmed",
    ),
    ("GET", "/reservation/availability/day", "reservation.availability.day"),
    ("GET", "/reservation/availability/tables", "reservation.availability.tables"),
    ("GET", "/reservation/time_slots", "reservation.time_slot.list"),
    ("POST", "/reservation/time_slots", "reservation.time_slot.create"),
    ("POST", "/reservation/time_slots/delete", "reservation.time_slot.delete"),
    ("GET", "/reservation/blocked_dates", "reservation.blocked_date.list"),
    ("POST", "/reservation/blocked_dates", "reservation.blocked_date.create"),
    ("POST", "/reservation/blocked_dates/delete", "reservation.blocked_date.delete"),
    ("GET", "/reservation/waitlist", "reservation.waitlist.list"),
    ("POST", "/reservation/waitlist", "reservation.waitlist.create"),
    ("POST", "/reservation/waitlist/update", "reservation.waitlist.update"),
    ("POST", "/reservation/waitlist/convert", "reservation.waitlist.convert"),
    ("POST", "/reservation/waitlist/delete", "reservation.waitlist.delete"),
    ("GET", "/reservation/settings", "reservation.settings.get"),
    ("POST", "/reservation/settings", "reservation.settings.update"),
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


def test_the_platforms_writes_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {"reservation.customer.reassign", "reservation.customer.erase"}


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_spas_route_map_names_every_reservation_route(settings):
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("reservation.")
    }
    assert mine == ROUTES


# ── Authentication and permissions ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/reservation/reservations"),
        post(client, "/reservation/time_slots", {}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_the_host_runs_the_book_but_not_its_rules(employee_client):
    open_week()
    for path in (
        "/reservation/reservations",
        "/reservation/waitlist",
        "/reservation/time_slots",
        "/reservation/blocked_dates",
        "/reservation/settings",
        "/reservation/availability/day",
    ):
        assert get(employee_client, path).status_code == 200, path
    booked = post(
        employee_client,
        "/reservation/reservations",
        {
            "guest_name": "Ana",
            "guest_phone": "600111222",
            "date": "2026-10-15",
            "time": "21:00",
            "party_size": 2,
        },
    )
    assert booked.status_code == 201
    assert (
        post(
            employee_client,
            "/reservation/reservations/confirm",
            {"id": booked.json()["id"]},
        ).status_code
        == 200
    )
    for response in (
        post(
            employee_client,
            "/reservation/time_slots",
            {"day_of_week": 1, "start_time": "08:00", "end_time": "09:00"},
        ),
        post(employee_client, "/reservation/settings", {"auto_confirm": True}),
        post(
            employee_client,
            "/reservation/reservations/delete",
            {"id": booked.json()["id"]},
        ),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert (
        get(admin_client, "/reservation/reservations", host="b.localhost").status_code
        == 403
    )


# ── Validation and refusals ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_an_invalid_booking_is_422_per_field(admin_client):
    response = post(
        admin_client,
        "/reservation/reservations",
        {"guest_name": "Ana", "date": "x", "party_size": 0},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], {"date", "time", "party_size"} <= set(error["fields"])) == (
        "invalid_payload",
        True,
    )


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/reservation/reservations", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_a_full_slot_is_a_409_with_its_code_and_field_in_the_readers_language(
    admin_client,
):
    from .conftest import THURSDAY, make_slot

    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    make_reservation()
    response = post(
        admin_client,
        "/reservation/reservations",
        {
            "guest_name": "Luis",
            "guest_phone": "600333444",
            "date": "2026-10-15",
            "time": "21:00",
            "party_size": 2,
        },
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "reservation.no_capacity"
    assert error["message"] == "Esa franja ya está completa para ese día."
    assert error["fields"] == {
        "time": error["message"],
        "overbook": "Envía overbook como true para reservar igualmente esta franja llena.",
    }


@pytest.mark.django_db
def test_a_change_on_behalf_of_another_guest_is_a_409_that_says_nothing_of_the_booking(admin_client):
    other = make_reservation()
    response = post(
        admin_client,
        "/reservation/reservations/cancel",
        {"id": str(other.id), "on_behalf_of": "01a15d83-0000-7000-8000-000000000000"},
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "reservation.customer_mismatch",
        "message": "Esa reserva es de otro comensal, así que no se puede gestionar en su nombre.",
    }


# ── The whole flow over HTTP ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_booking_confirming_seating_and_completing_over_http(admin_client):
    open_week()
    table = make_table("5")
    booked = post(
        admin_client,
        "/reservation/reservations",
        {
            "guest_name": "Ana García",
            "guest_phone": "600111222",
            "date": "2026-10-15",
            "time": "21:00",
            "party_size": 4,
            "table": "5",
        },
    )
    assert (booked.status_code, booked.json()["status"], booked.json()["table_id"]) == (
        201,
        "pending",
        str(table.id),
    )
    ref = {"guest": "Ana", "day": "2026-10-15"}
    assert (
        post(admin_client, "/reservation/reservations/confirm", ref).json()["status"]
        == "confirmed"
    )
    day = get(
        admin_client,
        "/reservation/reservations",
        date_from="2026-10-15",
        date_to="2026-10-15",
    ).json()
    assert [
        (row["guest_name"], row["status"], row["table_label"]) for row in day["rows"]
    ] == [("Ana García", "confirmed", "5 (no zone)")]
    seated = post(admin_client, "/reservation/reservations/seat", ref).json()
    assert (seated["status"], seated["table_session_id"] is not None) == (
        "seated",
        True,
    )
    assert (
        post(admin_client, "/reservation/reservations/complete", ref).json()["status"]
        == "completed"
    )
    figures = get(
        admin_client, "/reservation/availability/day", date="2026-10-15"
    ).json()
    assert (figures["reservations"], figures["covers"]) == (1, 4)
