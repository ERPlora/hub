"""The schedule app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from django.conf import settings
from django.utils import translation
from live.ninja import ensure_api_parity

from apps.schedule.api import router
from apps.schedule.models import SpecialDay
from config.api import api

from .conftest import make_override, make_special_day

ROUTES = {
    ("GET", "/schedule/week", "schedule.week.get"),
    ("POST", "/schedule/week/set_day", "schedule.week.set_day"),
    ("POST", "/schedule/week/confirm", "schedule.week.confirm"),
    ("GET", "/schedule/special_days", "schedule.special_day.list"),
    ("POST", "/schedule/special_days", "schedule.special_day.create"),
    ("POST", "/schedule/special_days/bulk_create", "schedule.special_day.bulk_create"),
    ("POST", "/schedule/special_days/update", "schedule.special_day.update"),
    ("POST", "/schedule/special_days/delete", "schedule.special_day.delete"),
    ("GET", "/schedule/overrides", "schedule.override.list"),
    ("POST", "/schedule/overrides", "schedule.override.create"),
    ("POST", "/schedule/overrides/update", "schedule.override.update"),
    ("POST", "/schedule/overrides/delete", "schedule.override.delete"),
    ("GET", "/schedule/settings", "schedule.settings.get"),
    ("POST", "/schedule/settings", "schedule.settings.update"),
    ("GET", "/schedule/is_open", "schedule.business.is_open"),
    ("GET", "/schedule/hours", "schedule.hours.for_range"),
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
    client.force_login(make_user("ana", host="a", role="hub_employee"))
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
def test_the_openapi_describes_the_schedule_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("schedule.")
    }
    assert served == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/schedule/week"),
        post(client, "/schedule/week/confirm", {}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_but_does_not_write(employee_client):
    for path in (
        "/schedule/week",
        "/schedule/special_days",
        "/schedule/overrides",
        "/schedule/settings",
        "/schedule/is_open",
    ):
        assert get(employee_client, path).status_code == 200, path
    assert (
        get(employee_client, "/schedule/hours", date_from="2026-08-17").status_code
        == 200
    )
    response = post(
        employee_client, "/schedule/week/set_day", {"weekday": 0, "is_closed": True}
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        403,
        "permission_denied",
    )


# Flows over HTTP


@pytest.mark.django_db
def test_set_a_day_and_read_the_week(admin_client):
    response = post(
        admin_client,
        "/schedule/week/set_day",
        {
            "weekday": "lunes",
            "intervals": [
                {"open_time": "17:00", "close_time": "20:00"},
                {"open_time": "10:00", "close_time": "14:00"},
            ],
        },
    )
    assert response.status_code == 200
    monday = get(admin_client, "/schedule/week").json()["days"][0]
    assert monday["intervals"] == [
        {"open_time": "10:00:00", "close_time": "14:00:00"},
        {"open_time": "17:00:00", "close_time": "20:00:00"},
    ]


@pytest.mark.django_db
def test_a_bad_day_is_a_422_under_its_field(admin_client):
    response = post(
        admin_client,
        "/schedule/week/set_day",
        {
            "weekday": 0,
            "intervals": [
                {"open_time": "09:00", "close_time": "14:00"},
                {"open_time": "13:00", "close_time": "18:00"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "intervals": "Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash."
    }


@pytest.mark.django_db
def test_the_422_speaks_the_requests_language(admin_client):
    with translation.override("es"):
        response = post(
            admin_client,
            "/schedule/week/set_day",
            {"weekday": 0, "intervals": []},
            HTTP_ACCEPT_LANGUAGE="es",
        )
    assert response.json()["error"]["fields"] == {
        "intervals": "Un día abierto necesita al menos un tramo horario."
    }


@pytest.mark.django_db
def test_a_special_day_create_a_duplicate_409_update_and_delete(admin_client):
    created = post(
        admin_client,
        "/schedule/special_days",
        {"date": "2026-12-25", "name": "Christmas"},
    )
    assert (created.status_code, created.json()["is_closed"]) == (201, True)
    duplicate = post(
        admin_client, "/schedule/special_days", {"date": "2026-12-25", "name": "Again"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == {
        "code": "schedule.special_day_exists",
        "message": "There is already a special day on that date.",
        "fields": {"date": "There is already a special day on that date."},
    }
    updated = post(
        admin_client,
        "/schedule/special_days/update",
        {"special_day": "christmas", "recurring_yearly": True},
    )
    assert (updated.status_code, updated.json()["recurring_yearly"]) == (200, True)
    listed = get(admin_client, "/schedule/special_days", search="christ").json()
    assert [row["name"] for row in listed["rows"]] == ["Christmas"]
    deleted = post(
        admin_client, "/schedule/special_days/delete", {"special_day": "2026-12-25"}
    )
    assert deleted.status_code == 200 and not SpecialDay.objects.exists()


@pytest.mark.django_db
def test_an_unknown_reference_is_a_404(admin_client):
    response = post(
        admin_client, "/schedule/special_days/delete", {"special_day": "Easter"}
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        404,
        "not_found",
    )


@pytest.mark.django_db
def test_the_bulk_over_http(admin_client):
    make_special_day("2026-01-01", "New Year")
    response = post(
        admin_client,
        "/schedule/special_days/bulk_create",
        {
            "special_days": [
                {"date": "2026-01-01", "name": "New Year"},
                {"date": "2026-01-06", "name": "Epiphany"},
            ]
        },
    )
    assert response.status_code == 201
    assert [skip["code"] for skip in response.json()["skipped"]] == ["already_exists"]


@pytest.mark.django_db
def test_a_temporary_change_overlapping_another_is_a_409_under_the_start(admin_client):
    make_override("2026-08-01", "2026-08-31", "Holidays")
    response = post(
        admin_client,
        "/schedule/overrides",
        {"start_date": "2026-08-20", "end_date": "2026-09-05", "reason": "More"},
    )
    assert response.status_code == 409
    assert set(response.json()["error"]["fields"]) == {"start_date"}
    backwards = post(
        admin_client,
        "/schedule/overrides",
        {"start_date": "2026-09-05", "end_date": "2026-09-01", "reason": "x"},
    )
    assert (backwards.status_code, set(backwards.json()["error"]["fields"])) == (
        422,
        {"end_date"},
    )
    listed = get(admin_client, "/schedule/overrides").json()
    assert [row["reason"] for row in listed["rows"]] == ["Holidays"]
    assert (
        post(
            admin_client,
            "/schedule/overrides/update",
            {"override": "Holidays", "reason": "Summer"},
        ).json()["reason"]
        == "Summer"
    )
    assert (
        post(
            admin_client, "/schedule/overrides/delete", {"override": "2026-08-10"}
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_settings_is_open_and_hours_over_http(admin_client):
    saved = post(admin_client, "/schedule/settings", {"week_starts_on": 7})
    assert (saved.status_code, saved.json()["week_starts_on"]) == (200, 7)
    assert get(admin_client, "/schedule/settings").json()["timezone"] == "Europe/Madrid"
    # 2026-08-17 is a Monday of the default week (09:00–18:00).
    verdict = get(admin_client, "/schedule/is_open", when="2026-08-17T10:00").json()
    assert (verdict["is_open"], verdict["code"], verdict["source"]) == (
        True,
        "open_interval",
        "weekly",
    )
    bad = get(admin_client, "/schedule/is_open", when="tomorrow")
    assert (bad.status_code, bad.json()["error"]["fields"]) == (
        422,
        {"when": "That date and time are not valid."},
    )
    hours = get(
        admin_client, "/schedule/hours", date_from="2026-08-17", date_to="2026-08-18"
    ).json()
    assert hours["days"][0]["spans"] == [
        {"start": "2026-08-17T09:00:00", "end": "2026-08-17T18:00:00"}
    ]
    assert post(admin_client, "/schedule/week/confirm", {}).json()["confirmed"] is True


def test_the_spas_route_map_names_every_schedule_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op.startswith("schedule.")}
    assert mine == ROUTES


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "params", "field"),
    [
        ("/schedule/is_open", {"when": "0001-01-01T10:00"}, "when"),
        ("/schedule/is_open", {"when": "0001-01-01T00:30+01:00"}, "when"),
        ("/schedule/is_open", {"when": "9999-12-31T23:30-01:00"}, "when"),
        ("/schedule/is_open", {"when": "9999-12-31T23:30+00:00"}, "when"),
        ("/schedule/hours", {"date_from": "0001-01-01"}, "date_from"),
        ("/schedule/hours", {"date_from": "2200-12-01", "date_to": "9999-12-31"}, "date_to"),
    ],
)
def test_the_ends_of_the_calendar_are_a_422_not_a_500(admin_client, path, params, field):
    response = get(admin_client, path, **params)
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {field: "Choose a date between 1900 and 2200."}
