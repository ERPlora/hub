"""The tax app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.tax.api import router
from config.api import api

ROUTES = {
    ("GET", "/tax/categories", "tax.category.list"),
    ("GET", "/tax/categories/detail", "tax.category.get"),
    ("POST", "/tax/categories", "tax.category.create"),
    ("GET", "/tax/rules", "tax.rule.list"),
    ("GET", "/tax/rules/status", "tax.rule.status"),
    ("GET", "/tax/rules/parent_candidates", "tax.rule.parent_candidates"),
    ("GET", "/tax/rules/countries", "tax.rule.countries"),
    ("POST", "/tax/rules", "tax.rule.create"),
    ("POST", "/tax/rules/bulk_create", "tax.rule.bulk_create"),
    ("POST", "/tax/rules/end", "tax.rule.end"),
    ("POST", "/tax/rules/deactivate", "tax.rule.deactivate"),
    ("POST", "/tax/rules/activate", "tax.rule.activate"),
    ("GET", "/tax/aliases", "tax.alias.list"),
    ("GET", "/tax/aliases/resolve", "tax.alias.resolve"),
    ("POST", "/tax/aliases", "tax.alias.create"),
    ("GET", "/tax/rates/calculate", "tax.rate.calculate"),
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


def test_the_openapi_describes_the_tax_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("tax.")
    }
    assert served == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/tax/categories"),
        post(client, "/tax/categories", {"key": "x", "name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_and_calculates_but_does_not_write(employee_client):
    assert get(employee_client, "/tax/categories").status_code == 200
    assert get(employee_client, "/tax/rules").status_code == 200
    calculated = get(
        employee_client,
        "/tax/rates/calculate",
        amount=10_000,
        tax_category_key="product.generic",
    )
    assert (calculated.status_code, calculated.json()["tax"]) == (200, 2_100)
    response = post(
        employee_client, "/tax/categories", {"key": "product.x", "name": "X"}
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        403,
        "permission_denied",
    )


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/tax/categories", host="b.localhost").status_code == 403


# Validation: 422 per field


@pytest.mark.django_db
def test_an_invalid_rule_is_422_per_field(admin_client):
    response = post(
        admin_client,
        "/tax/rules",
        {
            "country_code": "ES",
            "region_code": "PT-20",
            "tax_category_key": "product.generic",
            "operation_class": "exempt",
            "rate_pct": 21,
            "valid_from": "2026-02-01",
            "valid_to": "2026-01-31",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {"region_code", "rate_pct", "valid_to"}


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/tax/rules", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_an_unknown_category_is_422_on_its_field(admin_client):
    response = post(
        admin_client,
        "/tax/rules",
        {"country_code": "ES", "tax_category_key": "nothing", "rate_pct": 4},
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_field",
        "message": "This tax category does not exist.",
        "fields": {"tax_category_key": "This tax category does not exist."},
    }


@pytest.mark.django_db
def test_a_refusal_follows_the_language_of_the_request(admin_client):
    response = post(
        admin_client,
        "/tax/rules",
        {
            "country_code": "ES",
            "tax_category_key": "product.generic",
            "rate_pct": 25,
            "valid_from": "2030-01-01",
        },
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "tax.rule_overlaps"
    assert error["fields"]["valid_from"].startswith(
        "Se solapa con otra regla activa de este país, región y categoría"
    )


# The flows over HTTP


@pytest.mark.django_db
def test_change_a_rate_from_a_date(admin_client):
    # TAX-F07 against the seeded Spanish baseline: end 21 % and create 22 % from the day after.
    current = get(
        admin_client,
        "/tax/rules",
        country_code="ES",
        tax_category_key="product.generic",
    ).json()
    [rule] = current["rows"]
    ended = post(
        admin_client, "/tax/rules/end", {"id": rule["id"], "valid_to": "2030-12-31"}
    )
    assert (ended.status_code, ended.json()["valid_to"]) == (200, "2030-12-31")
    created = post(
        admin_client,
        "/tax/rules",
        {
            "country_code": "ES",
            "tax_category_key": "product.generic",
            "rate_pct": 22,
            "valid_from": "2031-01-01",
        },
    )
    assert (created.status_code, created.json()["rate_pct"]) == (201, "22.00")
    old = get(
        admin_client,
        "/tax/rates/calculate",
        amount=100,
        tax_category_key="product.generic",
        date="2030-12-31",
    )
    new = get(
        admin_client,
        "/tax/rates/calculate",
        amount=100,
        tax_category_key="product.generic",
        date="2031-01-01",
    )
    assert (old.json()["tax"], new.json()["tax"]) == (21, 22)


@pytest.mark.django_db
def test_deactivate_and_bring_back_by_voice(admin_client):
    named = {"country_code": "ES", "tax_category_key": "Restauración — comida"}
    off = post(admin_client, "/tax/rules/deactivate", named)
    assert (off.status_code, off.json()["is_active"]) == (200, False)
    inactive = get(admin_client, "/tax/rules", status="inactive").json()
    assert [row["tax_category_key"] for row in inactive["rows"]] == ["restaurant.food"]
    on = post(admin_client, "/tax/rules/activate", named)
    assert (on.status_code, on.json()["is_active"]) == (200, True)


@pytest.mark.django_db
def test_a_new_category_its_rule_and_an_alias(admin_client):
    created = post(
        admin_client, "/tax/categories", {"key": "product.books", "name": "Libros"}
    )
    assert (created.status_code, created.json()["is_system"]) == (201, False)
    again = post(
        admin_client, "/tax/categories", {"key": "product.books", "name": "Otra"}
    )
    assert (again.status_code, again.json()["error"]["fields"]) == (
        409,
        {"key": "There is already a tax category with that key."},
    )
    rule = post(
        admin_client,
        "/tax/rules",
        {"country_code": "ES", "tax_category_key": "Libros", "rate_pct": 4},
    )
    assert (rule.status_code, rule.json()["tax_category_key"]) == (201, "product.books")
    alias = post(
        admin_client,
        "/tax/aliases",
        {"alias": "Revistas", "tax_category_key": "product.books"},
    )
    assert (alias.status_code, alias.json()["alias"]) == (201, "revistas")
    resolved = get(admin_client, "/tax/aliases/resolve", text="REVISTAS").json()
    assert (resolved["tax_category_key"], resolved["matched_by"]) == (
        "product.books",
        "alias",
    )
    page = get(admin_client, "/tax/categories", search="libros").json()
    assert [(row["key"], row["rate_pct"]) for row in page["rows"]] == [
        ("product.books", "4.00")
    ]


@pytest.mark.django_db
def test_bulk_create_and_status(admin_client):
    status = get(admin_client, "/tax/rules/status", country_code="PT").json()
    assert (status["matching_rules"], status["configured"]) == (0, False)
    rows = [
        {"country_code": "PT", "tax_category_key": "product.generic", "rate_pct": 23},
        {"country_code": "PT", "tax_category_key": "restaurant.food", "rate_pct": 13},
    ]
    created = post(admin_client, "/tax/rules/bulk_create", {"rules": rows})
    assert (created.status_code, len(created.json()["rules"])) == (201, 2)
    assert (
        get(admin_client, "/tax/rules/status", country_code="PT").json()["configured"]
        is True
    )


@pytest.mark.django_db
def test_a_calculation_without_a_rule_is_a_409(admin_client):
    response = get(
        admin_client,
        "/tax/rates/calculate",
        amount=100,
        tax_category_key="product.generic",
        country_code="PT",
    )
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "tax.no_rate",
    )


@pytest.mark.django_db
def test_rules_that_cannot_be_read_are_an_internal_error_never_a_missing_app(
    admin_client,
):
    # hub#1102, hub#2410: an outage reading the rules stops the calculation with the plain «Internal
    # error» of every route (in the reader's language), never «this app is not active» nor the
    # internal text of the failure, and never a guessed rate.
    from django.db import connection
    from django.utils import translation
    from django.utils.translation import gettext

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE tax_taxrule RENAME TO tax_taxrule_hidden")
    try:
        response = admin_client.get(
            "/api/tax/rates/calculate",
            {
                "amount": 100,
                "tax_category_key": "product.generic",
                "allow_missing_rate": "true",
            },
            HTTP_HOST="a.localhost",
            HTTP_ACCEPT_LANGUAGE="es",
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE tax_taxrule_hidden RENAME TO tax_taxrule")
    error = response.json()["error"]
    assert (response.status_code, error["code"]) == (500, "internal_error")
    assert "tax_taxrule" not in error["message"]
    with translation.override("es"):
        assert error["message"] == gettext("Internal error")
