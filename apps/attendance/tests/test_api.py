"""The attendance app's routes: each bound to its operation, and the main flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: ids (or a person's name) travel in the input. The two system
operations (the scheduled review and the reaction to a termination) have no route.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.attendance.api import router
from apps.attendance.models import Correction, Record
from apps.staff.models import Member
from config.api import api

ROUTES = {
    ("GET", "/attendance/current", "attendance.record.current"),
    ("GET", "/attendance/records", "attendance.record.list"),
    ("GET", "/attendance/records/detail", "attendance.record.detail"),
    ("GET", "/attendance/records/export", "attendance.record.export"),
    ("POST", "/attendance/records/correct", "attendance.record.correct"),
    ("POST", "/attendance/clock_in", "attendance.record.clock_in"),
    ("POST", "/attendance/clock_out", "attendance.record.clock_out"),
    ("POST", "/attendance/breaks/start", "attendance.break.start"),
    ("POST", "/attendance/breaks/end", "attendance.break.end"),
    ("GET", "/attendance/corrections", "attendance.correction.list"),
    ("GET", "/attendance/presence", "attendance.presence.list"),
    ("GET", "/attendance/people", "attendance.person.list"),
    ("GET", "/attendance/settings", "attendance.settings.get"),
    ("POST", "/attendance/settings", "attendance.settings.update"),
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
def ana(client, make_user):
    """An employee with her staff record, signed in."""
    user = make_user("ana", role="hub_employee", first_name="Ana", last_name="López")
    Member.objects.create(first_name="Ana", last_name="López", user=user)
    client.force_login(user)
    return user


@pytest.fixture
def boss(client, make_user):
    user = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    Member.objects.create(first_name="Marta", last_name="Jefa", user=user)
    client.force_login(user)
    return user


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


def test_openapi_publishes_the_operations_with_their_ids(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("attendance.")
    }
    assert served == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/attendance/current"),
        post(client, "/attendance/clock_in", {}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_clocks_a_whole_day_over_http(ana, client):
    assert get(client, "/attendance/current").json()["open"] is None
    opened = post(client, "/attendance/clock_in", {})
    assert opened.status_code == 200 and opened.json()["status"] == "open"
    assert post(client, "/attendance/breaks/start", {}).status_code == 200
    assert get(client, "/attendance/current").json()["today"]["running"] == "break"
    assert post(client, "/attendance/breaks/end", {}).status_code == 200
    closed = post(client, "/attendance/clock_out", {})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    page = get(client, "/attendance/records").json()
    assert page["total"] == 1 and page["rows"][0]["break_count"] == 1


@pytest.mark.django_db
def test_a_refusal_is_the_409_envelope_with_its_code(ana, client):
    post(client, "/attendance/clock_in", {})
    response = post(client, "/attendance/clock_in", {})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attendance.already_clocked_in"


@pytest.mark.django_db
def test_an_employee_neither_corrects_nor_sees_the_team_nor_saves_settings(ana, client):
    Member.objects.create(first_name="Marta", last_name="Jefa")
    day = Record.objects.create(
        member=Member.objects.get(user=ana),
        clock_in_at="2026-10-06T07:00Z",
        clock_out_at="2026-10-06T15:00Z",
        status="closed",
        work_date="2026-10-06",
    )
    for response in (
        get(client, "/attendance/presence"),
        get(client, "/attendance/people"),
        post(
            client,
            "/attendance/records/correct",
            {
                "record_id": str(day.id),
                "clock_in_at": "2026-10-06T06:00:00Z",
                "reason": "Mine",
            },
        ),
        post(client, "/attendance/settings", {"auto_close_after_hours": 3}),
        post(client, "/attendance/clock_in", {"member": "Marta"}),
    ):
        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "permission_denied"
    # Its own days, history and the settings are its to read.
    assert get(client, "/attendance/records/detail", id=str(day.id)).status_code == 200
    assert (
        get(client, "/attendance/corrections", record_id=str(day.id)).status_code == 200
    )
    assert get(client, "/attendance/settings").status_code == 200


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(ana, client):
    assert get(client, "/attendance/current", host="b.localhost").status_code == 403


@pytest.mark.django_db
def test_a_correction_over_http_and_its_history(boss, client, make_user):
    worker = make_user("bea", role="hub_employee")
    bea = Member.objects.create(first_name="Bea", last_name="Ruiz", user=worker)
    day = Record.objects.create(
        member=bea,
        clock_in_at="2026-10-06T07:00Z",
        status="needs_review",
        work_date="2026-10-06",
    )
    response = post(
        client,
        "/attendance/records/correct",
        {
            "record_id": str(day.id),
            "clock_in_at": "2026-10-06T07:00:00Z",
            "clock_out_at": "2026-10-06T15:00:00Z",
            "reason": "Forgot to clock out",
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "closed"
    history = get(client, "/attendance/corrections", record_id=str(day.id)).json()
    assert [(c["reason"], c["created_by_name"]) for c in history["rows"]] == [
        ("Forgot to clock out", "Marta Jefa")
    ]
    assert Correction.objects.count() == 1


@pytest.mark.django_db
def test_an_invalid_correction_is_422_per_field(boss, client):
    response = post(
        client,
        "/attendance/records/correct",
        {
            "record_id": "x",
            "clock_in_at": "2026-10-06T08:00:00Z",
            "clock_out_at": "2026-10-06T07:00:00Z",
            "reason": "a",
        },
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {
        "record_id",
        "clock_out_at",
        "reason",
    }


@pytest.mark.django_db
def test_a_limit_over_100_or_an_unknown_sort_is_422(boss, client):
    for params in ({"limit": 101}, {"sort": "salary"}):
        assert get(client, "/attendance/records", **params).status_code == 422


@pytest.mark.django_db
def test_the_export_comes_as_csv_text(boss, client):
    response = get(
        client,
        "/attendance/records/export",
        date_from="2026-10-01",
        date_to="2026-10-31",
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["filename"], body["rows"]) == ("attendance-2026-10.csv", 0)
    assert body["csv"].startswith("date,user,clock_in")


@pytest.mark.django_db
def test_a_refusal_follows_the_language_of_the_request(ana, client):
    response = client.post(
        "/api/attendance/clock_out",
        "{}",
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    assert (
        response.json()["error"]["message"]
        == "No hay ninguna jornada abierta: ficha la entrada primero."
    )
