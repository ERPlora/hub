"""The appointment app's routes: each bound to its operation, and the flows over HTTP.

Requests go to business A's host (``HOST``, scope ``A``) with Django's sync test client, which sees the test's
transaction. The platform's reactions have no route.
"""

import pytest
from live.ninja import ensure_api_parity

from apps.appointment.api import router
from apps.flow.tests.test_api import get, post
from base.tests.routes import spa_routes
from config.api import api

from .conftest import HOST, HUB_DB, MONDAY, A, at, make_appointment, wall

ROUTES = {
    ("GET", "/appointment/appointments", "appointment.appointment.list"),
    ("GET", "/appointment/appointments/detail", "appointment.appointment.get"),
    ("GET", "/appointment/appointments/history", "appointment.appointment.history"),
    (
        "GET",
        "/appointment/appointments/for_customer",
        "appointment.appointment.list_for_customer",
    ),
    (
        "GET",
        "/appointment/appointments/count_for_service",
        "appointment.appointment.count_active_for_service",
    ),
    (
        "GET",
        "/appointment/appointments/count_to_confirm",
        "appointment.appointment.count_to_confirm",
    ),
    ("GET", "/appointment/appointments/notices", "appointment.appointment.notices"),
    ("POST", "/appointment/appointments", "appointment.appointment.create"),
    (
        "POST",
        "/appointment/appointments/bulk_create",
        "appointment.appointment.bulk_create",
    ),
    (
        "POST",
        "/appointment/appointments/reschedule",
        "appointment.appointment.reschedule",
    ),
    ("POST", "/appointment/appointments/update", "appointment.appointment.update"),
    ("POST", "/appointment/appointments/confirm", "appointment.appointment.confirm"),
    ("POST", "/appointment/appointments/start", "appointment.appointment.start"),
    ("POST", "/appointment/appointments/complete", "appointment.appointment.complete"),
    (
        "POST",
        "/appointment/appointments/mark_no_show",
        "appointment.appointment.mark_no_show",
    ),
    ("POST", "/appointment/appointments/cancel", "appointment.appointment.cancel"),
    ("POST", "/appointment/appointments/delete", "appointment.appointment.delete"),
    (
        "POST",
        "/appointment/appointments/bulk_delete",
        "appointment.appointment.bulk_delete",
    ),
    ("POST", "/appointment/appointments/charge", "appointment.appointment.charge"),
    ("GET", "/appointment/lanes", "appointment.agenda.lanes"),
    ("GET", "/appointment/availability/slots", "appointment.availability.slots"),
    ("GET", "/appointment/availability/check", "appointment.availability.check"),
    ("GET", "/appointment/blocked_times", "appointment.blocked_time.list"),
    ("POST", "/appointment/blocked_times", "appointment.blocked_time.create"),
    ("POST", "/appointment/blocked_times/delete", "appointment.blocked_time.delete"),
    ("GET", "/appointment/recurring", "appointment.recurring.list"),
    ("GET", "/appointment/recurring/detail", "appointment.recurring.get"),
    ("POST", "/appointment/recurring", "appointment.recurring.create"),
    ("POST", "/appointment/recurring/materialize", "appointment.recurring.materialize"),
    ("POST", "/appointment/recurring/update", "appointment.recurring.update"),
    ("POST", "/appointment/recurring/activate", "appointment.recurring.activate"),
    ("POST", "/appointment/recurring/deactivate", "appointment.recurring.deactivate"),
    ("POST", "/appointment/recurring/delete", "appointment.recurring.delete"),
    ("GET", "/appointment/settings", "appointment.settings.get"),
    ("POST", "/appointment/settings", "appointment.settings.update"),
}


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host=A.key, role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("bea", host=A.key, role="hub_employee"))
    return client


# Binding


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


@HUB_DB
def test_the_openapi_describes_the_appointment_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("appointment.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_appointment_route():
    assert spa_routes("appointment.") == ROUTES


# Authentication and permissions


@HUB_DB
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/appointment/appointments", date_from=MONDAY.isoformat()),
        post(client, "/appointment/appointments/confirm", {"number": "APT-1"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@HUB_DB
def test_an_employee_without_a_record_reads_an_empty_agenda_and_deletes_nothing(
    employee_client,
):
    assert (
        get(
            employee_client, "/appointment/appointments", date_from=MONDAY.isoformat()
        ).json()["total"]
        == 0
    )
    refused = post(
        employee_client, "/appointment/appointments/delete", {"number": "APT-1"}
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        403,
        "permission_denied",
    )
    settings_write = post(
        employee_client, "/appointment/settings", {"slot_interval": 30}
    )
    assert settings_write.status_code == 403


# The flows over HTTP


@HUB_DB
@pytest.mark.usefixtures("anytime")
def test_book_list_move_and_cancel_over_http(admin_client, salon):
    booked = post(
        admin_client,
        "/appointment/appointments",
        {
            "customer": "Lucía Pérez",
            "services": [{"service": "Haircut"}],
            "staff": "Ana",
            "start": wall(MONDAY, "10:00"),
        },
    )
    assert booked.status_code == 201, booked.json()
    number = booked.json()["number"]
    page = get(
        admin_client, "/appointment/appointments", date_from=MONDAY.isoformat()
    ).json()
    assert [row["number"] for row in page["rows"]] == [number]
    slots = get(
        admin_client,
        "/appointment/availability/slots",
        date=MONDAY.isoformat(),
        services="Haircut",
        staff="Ana",
    )
    assert slots.status_code == 200 and slots.json()["slots"]
    # The spans travel as the free times do: the business's wall clock with its offset.
    offset = slots.json()["slots"][0]["start"][-6:]
    assert slots.json()["windows"] == [
        {"start": f"{MONDAY.isoformat()}T08:00:00{offset}", "end": f"{MONDAY.isoformat()}T20:00:00{offset}"}
    ]
    moved = post(
        admin_client,
        "/appointment/appointments/reschedule",
        {"number": number, "start": wall(MONDAY, "11:00")},
    )
    assert moved.json()["start"].startswith(f"{MONDAY.isoformat()}T11:00")
    cancelled = post(
        admin_client,
        "/appointment/appointments/cancel",
        {"number": number, "reason": "Ill"},
    )
    assert cancelled.json()["status"] == "cancelled"


@HUB_DB
@pytest.mark.usefixtures("anytime")
def test_a_refusal_is_a_409_and_a_bad_field_a_422_on_that_field(admin_client, salon):
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    clash = post(
        admin_client,
        "/appointment/appointments",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service": "Haircut"}],
            "staff": "Ana",
            "start": wall(MONDAY, "10:00"),
        },
    )
    assert (clash.status_code, clash.json()["error"]["code"]) == (
        409,
        "appointment.overlap_needs_confirmation",
    )
    bad = post(
        admin_client,
        "/appointment/appointments",
        {
            "customer_id": str(salon.lucia.id),
            "services": [],
            "staff": "Ana",
            "start": "soon",
        },
    )
    assert bad.status_code == 422
    assert {"services", "start"} <= set(bad.json()["error"]["fields"])


@HUB_DB
@pytest.mark.parametrize(
    "path",
    [
        "/appointment/settings",
        "/appointment/appointments/count_to_confirm",
    ],
)
def test_a_read_without_parameters_answers_over_http(admin_client, path):
    answer = get(admin_client, path)
    assert answer.status_code == 200, answer.content
