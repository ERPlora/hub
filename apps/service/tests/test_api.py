"""The service app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST),
by its id or by its name.
"""

import json
import uuid

import pytest
from live.ninja import ensure_api_parity

from apps.service.api import router
from config.api import api

from .conftest import make_customer, make_member, make_tax

ROUTES = {
    ("GET", "/service/services", "service.service.list"),
    ("GET", "/service/services/detail", "service.service.get"),
    ("GET", "/service/services/for_sale", "service.service.list_for_sale"),
    ("POST", "/service/services", "service.service.create"),
    ("POST", "/service/services/bulk_create", "service.service.bulk_create"),
    ("POST", "/service/services/update", "service.service.update"),
    ("POST", "/service/services/archive", "service.service.archive"),
    ("POST", "/service/services/restore", "service.service.restore"),
    ("GET", "/service/catalog/status", "service.catalog.status"),
    ("GET", "/service/categories", "service.category.list"),
    ("GET", "/service/categories/detail", "service.category.get"),
    ("POST", "/service/categories", "service.category.create"),
    ("POST", "/service/categories/update", "service.category.update"),
    ("POST", "/service/categories/delete", "service.category.delete"),
    ("GET", "/service/settings", "service.settings.get"),
    ("POST", "/service/settings", "service.settings.update"),
    ("GET", "/service/assignments", "service.assignment.list"),
    ("GET", "/service/assignments/eligible", "service.assignment.eligible"),
    ("POST", "/service/assignments/assign", "service.assignment.assign"),
    ("POST", "/service/assignments/update", "service.assignment.update"),
    ("POST", "/service/assignments/remove", "service.assignment.remove"),
    ("GET", "/service/packages", "service.package.list"),
    ("GET", "/service/packages/detail", "service.package.get"),
    ("POST", "/service/packages", "service.package.create"),
    ("POST", "/service/packages/update", "service.package.update"),
    ("POST", "/service/packages/delete", "service.package.delete"),
    ("GET", "/service/grants", "service.grant.list"),
    ("GET", "/service/grants/orphans", "service.grant.list_orphans"),
    ("GET", "/service/grants/void_check", "service.grant.void_check"),
    ("GET", "/service/grants/adjust_check", "service.grant.adjust_check"),
    ("GET", "/service/grants/redeem_check", "service.grant.redeem_check"),
    ("GET", "/service/grants/tender_options", "service.grant.tender_options"),
    ("POST", "/service/grants", "service.grant.create"),
    ("POST", "/service/grants/void", "service.grant.void"),
    ("POST", "/service/grants/adjust", "service.grant.adjust"),
    ("POST", "/service/grants/redeem", "service.grant.redeem"),
    ("GET", "/service/movements", "service.movement.list"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def tax(db):
    return make_tax()


@pytest.fixture
def admin_client(client, make_user, tax):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user, tax):
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


def test_the_reactions_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {"service.assignment.release_member", "service.grant.reassign"}


def test_the_sessions_of_the_till_have_no_route_sales_runs_them():
    # Sales keeps on its check line the session it reserved: a route would let the screen hold a
    # session no line knows about (WORKBOOK «Contrato con Ventas»).
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {
        "service.session.hold",
        "service.session.release",
        "service.session.settle",
        "service.session.expire",
        "service.session.return",
    }


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/service/services"),
        post(client, "/service/services", {"name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_creates_services_and_vouchers_but_does_not_archive(
    employee_client, tax
):
    for path in (
        "/service/services",
        "/service/categories",
        "/service/packages",
        "/service/settings",
    ):
        assert get(employee_client, path).status_code == 200, path
    created = post(
        employee_client,
        "/service/services",
        {"name": "Cut", "tax_category_key": tax.key},
    )
    assert created.status_code == 201
    for response in (
        post(
            employee_client, "/service/services/archive", {"id": created.json()["id"]}
        ),
        post(employee_client, "/service/settings", {"show_prices": False}),
        get(employee_client, "/service/grants/orphans"),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/service/services", host="b.localhost").status_code == 403


# Validation and refusals


@pytest.mark.django_db
def test_an_invalid_service_is_422_per_field(admin_client):
    response = post(
        admin_client,
        "/service/services",
        {"name": "", "price": -1, "pricing_type": "barter"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {"name", "price", "pricing_type"}


@pytest.mark.django_db
def test_a_service_without_a_tax_category_is_422_under_its_field(admin_client):
    response = post(admin_client, "/service/services", {"name": "Cut"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "tax_category_key": "Pick a tax category: without one the service cannot be charged."
    }


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/service/services", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_a_domain_refusal_is_a_409_with_its_code_and_field(admin_client):
    assert (
        post(admin_client, "/service/categories", {"name": "Hair"}).status_code == 201
    )
    response = post(admin_client, "/service/categories", {"name": "hair"})
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "service.category_name_taken",
        "message": "There is already a category with that name. Pick another name.",
        "fields": {
            "name": "There is already a category with that name. Pick another name."
        },
    }


@pytest.mark.django_db
def test_a_missing_service_is_404_and_one_not_named_is_422(admin_client):
    missing = get(admin_client, "/service/services/detail", id=str(uuid.uuid7()))
    assert (missing.status_code, missing.json()["error"]["code"]) == (
        404,
        "service.service_not_found",
    )
    assert get(admin_client, "/service/services/detail").status_code == 422


@pytest.mark.django_db
def test_the_messages_speak_spanish(admin_client):
    response = admin_client.post(
        "/api/service/services",
        json.dumps({"name": "Corte"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.json()["error"]["fields"] == {
        "tax_category_key": "Elige una categoría fiscal: sin ella el servicio no se puede cobrar."
    }


@pytest.mark.django_db
def test_an_employee_cannot_date_a_voucher_in_the_future(employee_client):
    future = "2099-01-01T10:00:00+00:00"
    response = post(employee_client, "/service/grants", {"package": "Bono", "customer": "Lucía", "granted_at": future})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"granted_at": "A voucher cannot be bought in the future."}


# The whole app over HTTP


@pytest.mark.django_db
def test_round_trip(admin_client, tax):
    hair = post(admin_client, "/service/categories", {"name": "Hair"}).json()
    created = post(
        admin_client,
        "/service/services",
        {
            "name": "Haircut",
            "price": 2000,
            "duration_minutes": 30,
            "tax_category_key": tax.key,
            "category_id": hair["id"],
        },
    )
    assert created.status_code == 201
    cut = created.json()
    assert (cut["status"], cut["category_name"]) == ("active", "Hair")
    page = get(
        admin_client,
        "/service/services",
        price_min=1500,
        price_max=2500,
        status="active",
    ).json()
    assert ([row["id"] for row in page["rows"]], page["total"]) == ([cut["id"]], 1)
    assert (
        get(admin_client, "/service/services/detail", service="haircut").json()["id"]
        == cut["id"]
    )
    assert (
        get(admin_client, "/service/services/for_sale").json()["rows"][0][
            "tax_category_key"
        ]
        == tax.key
    )
    assert get(admin_client, "/service/catalog/status").json() == {
        "services": 1,
        "sellable_services": 1,
        "needs_tax_setup": 0,
    }
    assert (
        post(
            admin_client,
            "/service/services/update",
            {"service": "Haircut", "price": 2200},
        ).json()["price"]
        == 2200
    )
    bulk = post(
        admin_client,
        "/service/services/bulk_create",
        {"services": [{"name": "Beard", "tax_category_key": tax.key}]},
    )
    assert (bulk.status_code, bulk.json()["created"]) == (201, 1)

    make_member("Ana", "López")
    assignment = post(
        admin_client,
        "/service/assignments/assign",
        {"service": "Haircut", "member": "Ana", "custom_price": 2500},
    )
    assert assignment.json()["price"] == 2500
    assert (
        get(admin_client, "/service/assignments/eligible", service="Haircut").json()[
            "rows"
        ][0]["full_name"]
        == "Ana López"
    )
    assert (
        get(admin_client, "/service/assignments", service_id=cut["id"]).json()["total"]
        == 1
    )
    assert post(
        admin_client,
        "/service/assignments/update",
        {"id": assignment.json()["id"], "is_primary": True},
    ).json()["is_primary"]

    package = post(
        admin_client,
        "/service/packages",
        {
            "name": "Bono 5",
            "max_uses": 5,
            "items": [{"service": "Haircut", "sessions": 5}],
        },
    )
    assert (package.status_code, package.json()["item_count"]) == (201, 1)
    make_customer("Lucía Pérez")
    grant = post(
        admin_client,
        "/service/grants",
        {"package": "Bono 5", "customer": "Lucía Pérez", "amount": 9000},
    )
    assert (grant.status_code, grant.json()["remaining"]) == (201, 5)
    grant_id = grant.json()["id"]
    assert (
        get(
            admin_client, "/service/grants/redeem_check", id=grant_id, service="Haircut"
        ).json()["redeemable"]
        is True
    )
    assert (
        post(
            admin_client,
            "/service/grants/redeem",
            {"id": grant_id, "service": "Haircut"},
        ).json()["remaining"]
        == 4
    )
    assert (
        get(admin_client, "/service/grants/void_check", id=grant_id).json()["reason"]
        == "in_use"
    )
    assert (
        get(admin_client, "/service/grants/adjust_check", id=grant_id).json()[
            "uses_left"
        ]
        == 4
    )
    adjusted = post(
        admin_client,
        "/service/grants/adjust",
        {"id": grant_id, "uses_delta": 1, "reason": "courtesy"},
    )
    assert adjusted.json()["remaining"] == 5
    assert (
        get(admin_client, "/service/grants", customer="Lucía Pérez").json()["rows"][0][
            "used"
        ]
        == 1
    )
    assert [
        row["kind"]
        for row in get(admin_client, "/service/movements", package="Bono 5").json()[
            "rows"
        ]
    ] == ["adjusted", "consumed"]
    assert get(admin_client, "/service/grants/orphans").json()["total"] == 0
    other = post(
        admin_client,
        "/service/grants",
        {"package": "Bono 5", "customer": "Lucía Pérez"},
    ).json()
    assert (
        post(
            admin_client, "/service/grants/void", {"id": other["id"], "reason": "twice"}
        ).json()["status"]
        == "voided"
    )
    assert (
        post(
            admin_client,
            "/service/packages/update",
            {"package": "Bono 5", "max_uses": 10},
        ).json()["max_uses"]
        == 10
    )
    assert (
        get(admin_client, "/service/packages/detail", package="Bono 5").json()[
            "grant_count"
        ]
        == 2
    )
    assert (
        post(
            admin_client, "/service/packages/delete", {"package": "Bono 5"}
        ).status_code
        == 200
    )
    assert get(admin_client, "/service/packages", status="deleted").json()["total"] == 1

    assert (
        post(admin_client, "/service/settings", {"default_duration": 45}).json()[
            "default_duration"
        ]
        == 45
    )
    assert get(admin_client, "/service/settings").json()["default_duration"] == 45
    assert (
        post(
            admin_client,
            "/service/categories/update",
            {"category": "Hair", "sort_order": 2},
        ).json()["sort_order"]
        == 2
    )
    assert (
        get(admin_client, "/service/categories/detail", category="hair").json()[
            "service_count"
        ]
        == 1
    )
    assert (
        post(admin_client, "/service/services/archive", {"service": "Haircut"}).json()[
            "status"
        ]
        == "archived"
    )
    assert (
        post(admin_client, "/service/services/restore", {"service": "Haircut"}).json()[
            "status"
        ]
        == "active"
    )
    assert (
        post(
            admin_client, "/service/assignments/remove", {"id": assignment.json()["id"]}
        ).status_code
        == 200
    )
    assert (
        post(
            admin_client, "/service/categories/delete", {"category": "Hair"}
        ).status_code
        == 200
    )
    assert get(admin_client, "/service/categories").json()["total"] == 0


def test_the_till_reads_the_vouchers_that_can_pay_a_service(employee_client, tax):
    from .conftest import make_grant, make_package, make_service

    cut = make_service("Cut", tax=tax)
    lucia = make_customer("Lucía Pérez")
    grant = make_grant(make_package("Bono", [cut], max_uses=3), lucia)
    response = get(
        employee_client,
        "/service/grants/tender_options",
        customer_id=str(lucia.id),
        service_id=str(cut.id),
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert [row["grant_id"] for row in body["rows"]] == [str(grant.id)]
    assert body["rows"][0]["default_reason"] == "only_option"
