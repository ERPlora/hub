"""The invoice app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. Receiving the issuer from the SaaS (``invoice.issuer.sync``) has no route: only the system
calls it.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.invoice.api import router
from apps.invoice.tests.conftest import ISSUER
from config.api import api

ROUTES = {
    ("GET", "/invoice/invoices", "invoice.invoice.list"),
    ("GET", "/invoice/invoices/detail", "invoice.invoice.get"),
    ("GET", "/invoice/invoices/by_source", "invoice.invoice.by_source"),
    ("GET", "/invoice/invoices/document", "invoice.invoice.document"),
    ("POST", "/invoice/invoices/print", "invoice.invoice.print"),
    ("GET", "/invoice/invoices/line_defaults", "invoice.invoice.line_defaults"),
    ("POST", "/invoice/invoices", "invoice.invoice.create"),
    ("POST", "/invoice/invoices/from_sale", "invoice.invoice.create_from_sale"),
    ("POST", "/invoice/invoices/substitute", "invoice.invoice.substitute"),
    ("POST", "/invoice/invoices/mark_paid", "invoice.invoice.mark_paid"),
    (
        "GET",
        "/invoice/invoices/rectification_preview",
        "invoice.invoice.rectification_preview",
    ),
    ("POST", "/invoice/invoices/rectify", "invoice.invoice.rectify"),
    (
        "POST",
        "/invoice/invoices/rectify_from_refund",
        "invoice.invoice.rectify_from_refund",
    ),
    (
        "POST",
        "/invoice/invoices/rectify_from_void",
        "invoice.invoice.rectify_from_void",
    ),
    ("GET", "/invoice/series", "invoice.series.list"),
    ("GET", "/invoice/series/peek_next", "invoice.series.peek_next"),
    ("POST", "/invoice/series", "invoice.series.create"),
    ("POST", "/invoice/series/update", "invoice.series.update"),
    ("GET", "/invoice/numbering/status", "invoice.numbering.status"),
    ("GET", "/invoice/numbering/gaps", "invoice.numbering.gaps"),
    ("GET", "/invoice/numbering/allocations", "invoice.numbering.allocations"),
    ("GET", "/invoice/issuer", "invoice.issuer.get"),
    ("POST", "/invoice/issuer", "invoice.issuer.update"),
}
LINE = {"description": "Course", "quantity": "1", "unit_price": 10000, "tax_rate": "21"}
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
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


@pytest.mark.django_db  # the host gate reads the registry's row of the hub (base.middleware)
def test_the_openapi_describes_the_invoice_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("invoice.")
    }
    assert served == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/invoice/invoices"),
        post(client, "/invoice/invoices", {"lines": [LINE]}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_the_owner_sets_up_the_issuer_and_issues_by_hand(admin_client):
    assert post(admin_client, "/invoice/issuer", ISSUER).status_code == 200
    created = post(admin_client, "/invoice/invoices", {"lines": [LINE], **RECIPIENT})
    assert created.status_code == 201
    body = created.json()
    assert (body["invoice_type"], body["total_amount"], body["status"]) == (
        "F1",
        12100,
        "issued",
    )
    listed = get(admin_client, "/invoice/invoices")
    assert (listed.status_code, listed.json()["total"]) == (200, 1)
    detail = get(admin_client, "/invoice/invoices/detail", number=body["number"])
    assert detail.json()["lines"][0]["description"] == "Course"
    document = get(admin_client, "/invoice/invoices/document", number=body["number"])
    assert body["number"] in document.json()["html"]
    # The rectification it would issue, read before issuing it (INVOICE-F08): nothing is written.
    seen = get(
        admin_client,
        "/invoice/invoices/rectification_preview",
        number=body["number"],
        reason="Wrong price",
    )
    assert seen.status_code == 200
    assert (seen.json()["original"]["number"], seen.json()["total_amount"]) == (body["number"], -12100)
    assert get(admin_client, "/invoice/invoices/detail", number=body["number"]).json()["status"] == "issued"


@pytest.mark.django_db
def test_an_employee_reads_issues_and_pays_but_neither_rectifies_nor_keeps_series(
    employee_client, make_user, client
):
    from apps.invoice.tests.conftest import run

    run("invoice.issuer.update", ISSUER)
    created = post(employee_client, "/invoice/invoices", {"lines": [LINE], **RECIPIENT})
    assert created.status_code == 201
    number = created.json()["number"]
    assert (
        post(employee_client, "/invoice/invoices/mark_paid", {"number": number}).json()[
            "status"
        ]
        == "paid"
    )
    preview = get(employee_client, "/invoice/invoices/rectification_preview", number=number, reason="x")
    assert (preview.status_code, preview.json()["error"]["code"]) == (403, "permission_denied")
    for path, data in (
        ("/invoice/invoices/rectify", {"number": number, "reason": "x"}),
        ("/invoice/series", {"code": "A", "invoice_type": "F1", "year": 2026}),
        ("/invoice/issuer", ISSUER),
    ):
        response = post(employee_client, path, data)
        assert (response.status_code, response.json()["error"]["code"]) == (
            403,
            "permission_denied",
        ), path


# The envelope


@pytest.mark.django_db
def test_a_422_says_the_field(admin_client):
    response = post(
        admin_client,
        "/invoice/invoices",
        {"lines": [{"description": "x", "quantity": "1", "unit_price": 1}]},
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"lines.0.tax_rate"}


@pytest.mark.django_db
def test_a_409_carries_its_domain_code_in_the_requests_language(admin_client):
    response = post(
        admin_client,
        "/invoice/invoices",
        {"lines": [LINE], **RECIPIENT},
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invoice.issuer_missing"
    assert error["message"].startswith("Configura el emisor")


@pytest.mark.django_db
def test_a_list_asks_for_at_most_a_hundred_rows(admin_client):
    response = get(admin_client, "/invoice/invoices", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_the_issuer_reads_empty_before_it_is_set_up(employee_client):
    body = get(employee_client, "/invoice/issuer").json()
    assert (body["configured"], body["legal_name"]) == (False, "")
