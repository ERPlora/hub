"""The staff app's routes: each bound to its operation, and the main flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: ids (or names) travel in the input.
"""

import json
import uuid

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.staff.api import router
from apps.staff.models import Member, TimeOff
from config.api import api

from .conftest import make_member, make_time_off

ROUTES = {
    ("GET", "/staff/members", "staff.member.list"),
    ("GET", "/staff/members/detail", "staff.member.detail"),
    ("GET", "/staff/members/mine", "staff.member.mine"),
    ("GET", "/staff/members/current", "staff.member.current"),
    ("GET", "/staff/members/compensation", "staff.member.compensation"),
    ("GET", "/staff/members/stats", "staff.member.stats"),
    ("POST", "/staff/members", "staff.member.create"),
    ("POST", "/staff/members/bulk_create", "staff.member.bulk_create"),
    ("POST", "/staff/members/update", "staff.member.update"),
    ("POST", "/staff/members/deactivate", "staff.member.deactivate"),
    ("POST", "/staff/members/terminate", "staff.member.terminate"),
    ("GET", "/staff/commissions", "staff.commission.summary"),
    ("GET", "/staff/commissions/report", "staff.commission.report"),
    ("GET", "/staff/roles", "staff.role.list"),
    ("POST", "/staff/roles", "staff.role.create"),
    ("POST", "/staff/roles/update", "staff.role.update"),
    ("GET", "/staff/schedules", "staff.schedule.list"),
    ("GET", "/staff/schedules/detail", "staff.schedule.detail"),
    ("POST", "/staff/schedules", "staff.schedule.create"),
    ("POST", "/staff/schedules/update", "staff.schedule.update"),
    ("POST", "/staff/schedules/set_active", "staff.schedule.set_active"),
    ("POST", "/staff/schedules/delete", "staff.schedule.delete"),
    ("GET", "/staff/availability", "staff.availability.for_member"),
    ("GET", "/staff/time_off", "staff.time_off.list"),
    ("GET", "/staff/time_off/detail", "staff.time_off.detail"),
    ("GET", "/staff/time_off/today", "staff.time_off.today"),
    ("GET", "/staff/time_off/mine", "staff.time_off.mine"),
    ("POST", "/staff/time_off", "staff.time_off.create"),
    ("POST", "/staff/time_off/request", "staff.time_off.request"),
    ("POST", "/staff/time_off/approve", "staff.time_off.approve"),
    ("POST", "/staff/time_off/reject", "staff.time_off.reject"),
    ("POST", "/staff/time_off/cancel", "staff.time_off.cancel"),
    ("GET", "/staff/settings", "staff.settings.get"),
    ("GET", "/staff/accounts", "staff.account.list"),
    ("POST", "/staff/settings", "staff.settings.update"),
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
def boss(client, make_user):
    user = make_user("boss", host="a", role="hub_admin")
    client.force_login(user)
    return user


@pytest.fixture
def employee(client, make_user):
    user = make_user("ana", host="a", role="hub_employee")
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


@pytest.mark.django_db  # the host gate reads the registry's row of the hub (base.middleware)
def test_openapi_publishes_the_operations_with_their_ids(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("staff.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_staff_route():
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("staff.")
    }
    assert mine == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/staff/members"),
        post(client, "/staff/members", {"first_name": "A", "last_name": "B"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_the_team_but_neither_writes_nor_sees_pay(employee, client):
    assert get(client, "/staff/members").status_code == 200
    assert get(client, "/staff/time_off/today").status_code == 200
    for response in (
        get(client, "/staff/members/compensation"),
        get(client, "/staff/commissions"),
        get(client, "/staff/commissions/report"),
        post(client, "/staff/members", {"first_name": "A", "last_name": "B"}),
        post(client, "/staff/roles", {"name": "Stylist"}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_the_commission_report_over_http_today_by_default_and_a_bad_period_is_422(boss, client):
    # flow: STAFF-F21 (paso 3: la comisión del día)
    make_member("Ana", commission_rate="15")
    body = get(client, "/staff/commissions/report").json()
    assert (body["sales_available"], body["total_sold"], body["total_commission"]) == (True, 0, 0)
    assert body["date_from"] == body["date_to"]
    assert [(row["full_name"], row["commission_rate"], row["sold"], row["commission"]) for row in body["rows"]] == [
        ("Ana López", "15.00", 0, 0)
    ]
    response = get(client, "/staff/commissions/report", date_from="2026-08-19", date_to="2026-08-18")
    assert response.status_code == 422
    assert list(response.json()["error"]["fields"]) == ["date_to"]


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(boss, client):
    assert get(client, "/staff/members", host="b.localhost").status_code == 403


# Validation


@pytest.mark.django_db
def test_an_invalid_record_is_422_per_field(boss, client):
    response = post(
        client,
        "/staff/members",
        {"first_name": "", "last_name": "López", "commission_rate": 120},
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"first_name", "commission_rate"}


@pytest.mark.django_db
def test_a_limit_over_100_or_an_unknown_sort_is_422(boss, client):
    for params in ({"limit": 101}, {"sort": "salary"}):
        response = get(client, "/staff/members", **params)
        assert response.status_code == 422


@pytest.mark.django_db
def test_a_schedule_error_names_the_day_and_its_field(boss, client):
    member = make_member()
    response = post(
        client,
        "/staff/schedules",
        {
            "member_id": str(member.id),
            "days": [{"weekday": 1, "start_time": "18:00", "end_time": "09:00"}],
        },
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"days.0.end_time"}


@pytest.mark.django_db
def test_an_error_follows_the_language_of_the_request(boss, client):
    response = post(
        client,
        "/staff/members/update",
        {"id": str(uuid.uuid7()), "phone": "1"},
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Ese miembro del personal no existe en este negocio."
    )


# Flows over HTTP


@pytest.mark.django_db
def test_the_record_round_trip(boss, client):
    role = post(client, "/staff/roles", {"name": "Stylist", "color": "#ff0000"})
    assert role.status_code == 201

    created = post(
        client,
        "/staff/members",
        {
            "first_name": "Ana",
            "last_name": "López",
            "role": "stylist",
            "hourly_rate": 1500,
        },
    )
    assert created.status_code == 201
    member = created.json()
    assert (member["role_name"], member["status"]) == ("Stylist", "active")

    page = get(client, "/staff/members", search="ana", sort="-name").json()
    assert [row["id"] for row in page["rows"]] == [member["id"]]
    assert (
        get(client, "/staff/members/detail", member="Ana López").json()["id"]
        == member["id"]
    )
    pay = get(client, "/staff/members/compensation", id=member["id"]).json()["rows"][0]
    assert pay["hourly_rate"] == 1500

    updated = post(
        client,
        "/staff/members/update",
        {"member": "Ana", "phone": "600", "hire_date": None},
    )
    assert (updated.status_code, updated.json()["phone"]) == (200, "600")
    assert (
        post(client, "/staff/members/deactivate", {"id": member["id"]}).json()["status"]
        == "inactive"
    )
    terminated = post(
        client, "/staff/members/terminate", {"id": member["id"], "reason": "moved"}
    )
    assert (terminated.status_code, terminated.json()["id"]) == (200, member["id"])
    assert get(client, "/staff/members/detail", id=member["id"]).status_code == 404


@pytest.mark.django_db
def test_an_ambiguous_name_is_a_409(boss, client):
    make_member("Ana", "López")
    make_member("Ana", "Ruiz")
    response = get(client, "/staff/members/detail", member="Ana")
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "staff.ambiguous_member",
    )


@pytest.mark.django_db
def test_the_time_off_round_trip(boss, client, make_user):
    me = make_user("eva", host="a", role="hub_employee")
    member = make_member("Eva", "Sanz", user=me.person)

    created = post(
        client,
        "/staff/time_off",
        {
            "member": "Eva",
            "start_date": "2026-10-12",
            "end_date": "2026-10-13",
            "reason": "Trip",
        },
    )
    assert created.status_code == 201
    leave_id = created.json()["id"]
    clash = post(
        client,
        "/staff/time_off",
        {
            "member_id": str(member.id),
            "start_date": "2026-10-13",
            "end_date": "2026-10-13",
        },
    )
    assert (clash.status_code, clash.json()["error"]["code"]) == (
        409,
        "staff.overlapping_time_off",
    )

    approved = post(client, "/staff/time_off/approve", {"id": leave_id})
    assert (approved.status_code, approved.json()["status"]) == (200, "approved")
    again = post(client, "/staff/time_off/approve", {"id": leave_id})
    assert (again.status_code, again.json()["error"]["code"]) == (
        409,
        "staff.invalid_transition",
    )
    detail = get(client, "/staff/time_off/detail", id=leave_id).json()
    assert (detail["reason"], detail["approved_by_name"]) == ("Trip", "boss")
    days = get(
        client,
        "/staff/availability",
        member_id=str(member.id),
        date_from="2026-10-12",
        date_to="2026-10-12",
    ).json()["days"]
    assert days[0]["time_off"] == [
        {"is_full_day": True, "start_time": None, "end_time": None}
    ]

    client.force_login(me)
    asked = post(
        client,
        "/staff/time_off/request",
        {"start_date": "2026-11-02", "end_date": "2026-11-02"},
    )
    assert asked.status_code == 201
    mine = get(client, "/staff/time_off/mine").json()
    assert {row["id"] for row in mine["rows"]} == {leave_id, asked.json()["id"]}
    assert (
        post(client, "/staff/time_off/cancel", {"id": asked.json()["id"]}).json()[
            "status"
        ]
        == "cancelled"
    )
    assert TimeOff.objects.get(pk=leave_id).status == "approved"


@pytest.mark.django_db
def test_the_schedule_round_trip(boss, client):
    member = make_member()
    week = [
        {
            "weekday": 0,
            "start_time": "09:00",
            "end_time": "18:00",
            "break_start": "13:00",
            "break_end": "14:00",
        }
    ]
    created = post(client, "/staff/schedules", {"member": "Ana", "days": week})
    assert (created.status_code, created.json()["name"]) == (201, "Regular schedule")
    schedule_id = created.json()["id"]
    assert (
        get(client, "/staff/schedules", member_id=str(member.id)).json()["total"] == 1
    )
    days = get(
        client,
        "/staff/availability",
        member="Ana",
        date_from="2026-10-12",
        date_to="2026-10-12",
    ).json()["days"]
    assert days[0]["available"] == [
        {"start": "09:00:00", "end": "13:00:00"},
        {"start": "14:00:00", "end": "18:00:00"},
    ]
    assert (
        post(
            client,
            "/staff/schedules/update",
            {"id": schedule_id, "name": "Usual", "days": week},
        ).json()["name"]
        == "Usual"
    )
    assert (
        post(
            client,
            "/staff/schedules/set_active",
            {"id": schedule_id, "is_active": False},
        ).json()["is_active"]
        is False
    )
    assert post(client, "/staff/schedules/delete", {"id": schedule_id}).json() == {
        "id": schedule_id
    }


@pytest.mark.django_db
def test_settings_and_bulk_over_http(boss, client):
    assert get(client, "/staff/settings").json()["default_work_start"] == "09:00"
    saved = post(
        client, "/staff/settings", {"default_work_start": "08:30", "default_break_duration": 45}
    )
    assert saved.json() == {
        "default_work_start": "08:30",
        "default_work_end": "18:00",
        "default_break_duration": 45,
    }
    # A retired setting (it changed nothing) is refused by its name, and nothing is saved.
    retired = post(client, "/staff/settings", {"default_break_duration": 30, "max_daily_hours": 9})
    assert retired.status_code == 422
    assert retired.json()["error"]["fields"] == {"max_daily_hours": "This field is not allowed."}
    assert get(client, "/staff/settings").json()["default_break_duration"] == 45
    bulk = post(
        client,
        "/staff/members/bulk_create",
        {
            "members": [
                {"first_name": "A", "last_name": "B"},
                {"first_name": " ", "last_name": "C"},
            ]
        },
    )
    assert bulk.status_code == 201
    assert (len(bulk.json()["created"]), bulk.json()["skipped"]) == (
        1,
        [{"index": 1, "reason": "name_required"}],
    )
    assert Member.objects.count() == 1
    assert get(client, "/staff/members/stats").json()["active"] == 1


@pytest.mark.django_db
def test_a_field_the_batch_does_not_know_never_brings_it_down(boss, client):
    # gh:services#152 (STAFF-F07): the old batch was refused whole for a field it did not know, and a
    # row past the hundredth was lost without a word; now that field is left out and 101 rows are a 422.
    bulk = post(
        client,
        "/staff/members/bulk_create",
        {"members": [{"first_name": "Ana", "last_name": "B", "nickname": "Anita"}]},
    )
    assert bulk.status_code == 201
    assert (len(bulk.json()["created"]), bulk.json()["skipped"]) == (1, [])
    rows = [{"first_name": f"P{n}", "last_name": "Q"} for n in range(101)]
    too_many = post(client, "/staff/members/bulk_create", {"members": rows})
    assert too_many.status_code == 422
    assert Member.objects.count() == 1


@pytest.mark.django_db
def test_my_record_over_http(employee, client):
    member = make_member("Ana", user=employee.person, hourly_rate=1200)
    assert get(client, "/staff/members/mine").json()["member"]["hourly_rate"] == 1200
    make_time_off(member, "2026-10-12")
    assert get(client, "/staff/time_off/mine").json()["total"] == 1


@pytest.mark.django_db
def test_the_current_record_over_http_says_only_who_and_never_the_pay(employee, client):
    # flow: SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo»)
    assert get(client, "/staff/members/current").json() == {"member": None}
    member = make_member("Ana", user=employee.person, hourly_rate=1200)
    assert get(client, "/staff/members/current").json() == {
        "member": {"id": str(member.id), "full_name": "Ana López"}
    }
    client.logout()
    assert get(client, "/staff/members/current").status_code == 401


@pytest.mark.django_db
def test_the_hub_user_selector_over_http(boss, client, employee):
    client.force_login(boss)
    rows = get(client, "/staff/accounts").json()["rows"]
    assert {row["user_id"] for row in rows} == {str(boss.person.id), str(employee.person.id)}
    client.force_login(employee)
    assert get(client, "/staff/accounts").status_code == 403
