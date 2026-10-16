"""The online booking app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. The public operations have session routes too (the owner's and the admin's preview); the page
without a session calls them in-process from base. The platform's reaction has no route.
"""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.appointment.models import Appointment
from apps.online_booking.api import router
from config.api import api

from .conftest import TUESDAY, at, booking_data, make_appointment

ROUTES = {
    ("GET", "/online_booking/bookings", "online_booking.booking.list"),
    ("GET", "/online_booking/bookings/detail", "online_booking.booking.get"),
    ("POST", "/online_booking/bookings/confirm", "online_booking.booking.confirm"),
    ("POST", "/online_booking/bookings/complete", "online_booking.booking.complete"),
    ("POST", "/online_booking/bookings/no_show", "online_booking.booking.no_show"),
    ("POST", "/online_booking/bookings/cancel", "online_booking.booking.cancel"),
    ("POST", "/online_booking/bookings/delete", "online_booking.booking.delete"),
    ("GET", "/online_booking/settings", "online_booking.settings.get"),
    ("POST", "/online_booking/settings", "online_booking.settings.update"),
    ("GET", "/online_booking/public/page", "online_booking.public.page"),
    ("GET", "/online_booking/public/services", "online_booking.public.services"),
    ("GET", "/online_booking/public/slots", "online_booking.public.slots"),
    ("GET", "/online_booking/public/booking", "online_booking.public.booking"),
    ("POST", "/online_booking/public/book", "online_booking.public.book"),
    ("POST", "/online_booking/public/cancel", "online_booking.public.cancel"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def manager_client(client, make_user):
    client.force_login(make_user("mia", host="a", role="hub_manager"))
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


@pytest.mark.django_db
def test_the_openapi_describes_the_online_booking_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("online_booking.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_online_booking_route():
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("online_booking.")
    }
    assert mine == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope_even_on_the_public_routes(client):
    for response in (
        get(client, "/online_booking/bookings"),
        get(client, "/online_booking/public/page"),
        post(client, "/online_booking/public/book", {}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_a_manager_works_the_inbox_but_neither_the_settings_nor_the_public_preview(
    manager_client, salon
):
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        status="pending",
        number="APT-1",
    )
    assert get(manager_client, "/online_booking/bookings").json()["total"] == 1
    confirmed = post(
        manager_client,
        "/online_booking/bookings/confirm",
        {"customer": "Lucía", "date": TUESDAY.isoformat()},
    )
    assert (confirmed.status_code, confirmed.json()["status"]) == (200, "confirmed")
    for response in (
        post(manager_client, "/online_booking/settings", {"is_enabled": False}),
        get(manager_client, "/online_booking/public/page"),
    ):
        assert (response.status_code, response.json()["error"]["code"]) == (
            403,
            "permission_denied",
        )


# The flows over HTTP


@pytest.mark.django_db
def test_the_owner_previews_the_page_books_sees_and_cancels_with_the_link(
    admin_client, salon
):
    assert (
        get(admin_client, "/online_booking/public/page").json()["title"]
        == "Book an appointment"
    )
    services = get(admin_client, "/online_booking/public/services").json()
    assert [row["name"] for row in services["rows"]] == ["Colour", "Haircut"]
    slots = admin_client.get(
        "/api/online_booking/public/slots",
        {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()},
        HTTP_HOST="a.localhost",
    )
    assert slots.status_code == 200 and slots.json()["slots"]
    booked = post(
        admin_client, "/online_booking/public/book", booking_data(salon, "10:00")
    )
    assert booked.status_code == 200
    token = booked.json()["token"]
    assert Appointment.objects.get(number=booked.json()["number"]).source == "online"
    seen = get(admin_client, "/online_booking/public/booking", token=token).json()
    assert (seen["status"], seen["can_cancel"]) == ("confirmed", True)
    cancelled = post(admin_client, "/online_booking/public/cancel", {"token": token})
    assert cancelled.json()["status"] == "cancelled"
    inbox = get(admin_client, "/online_booking/bookings", status="cancelled").json()
    assert [row["number"] for row in inbox["rows"]] == [booked.json()["number"]]


@pytest.mark.django_db
def test_a_refusal_is_the_envelope_with_its_field(admin_client, salon):
    refused = post(
        admin_client, "/online_booking/public/book", booking_data(salon, phone="12")
    )
    assert refused.status_code == 422
    assert set(refused.json()["error"]["fields"]) == {"phone"}
    refused = post(admin_client, "/online_booking/settings", {"primary_color": "blue"})
    assert (refused.status_code, set(refused.json()["error"]["fields"])) == (
        422,
        {"primary_color"},
    )


@pytest.mark.django_db
def test_the_settings_over_http(admin_client, db):
    saved = post(
        admin_client,
        "/online_booking/settings",
        {"is_enabled": True, "slot_interval": 30},
    )
    assert (
        saved.status_code,
        saved.json()["is_enabled"],
        saved.json()["slot_interval"],
    ) == (200, True, 30)
    assert get(admin_client, "/online_booking/settings").json()["slot_interval"] == 30
