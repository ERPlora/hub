"""The payment app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST),
by its id or, as a person says it, by its name or reference.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.payment.api import router
from config.api import api

from .conftest import make_method, make_payment

ROUTES = {
    ("GET", "/payment/payments", "payment.payment.list"),
    ("GET", "/payment/payments/detail", "payment.payment.get"),
    ("POST", "/payment/payments", "payment.payment.create"),
    ("POST", "/payment/payments/approve", "payment.payment.approve"),
    ("POST", "/payment/payments/mark_sent", "payment.payment.mark_sent"),
    ("POST", "/payment/payments/mark_completed", "payment.payment.mark_completed"),
    ("POST", "/payment/payments/cancel", "payment.payment.cancel"),
    ("GET", "/payment/methods", "payment.method.list"),
    ("GET", "/payment/methods/detail", "payment.method.get"),
    ("POST", "/payment/methods", "payment.method.create"),
    ("POST", "/payment/methods/update", "payment.method.update"),
    ("POST", "/payment/methods/deactivate", "payment.method.deactivate"),
    ("POST", "/payment/methods/activate", "payment.method.activate"),
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


# The whole app over HTTP


@pytest.mark.django_db
def test_a_payment_from_its_method_to_completed(admin_client):
    method = post(admin_client, "/payment/methods", {"name": "BBVA account"})
    assert method.status_code == 201
    created = post(
        admin_client,
        "/payment/payments",
        {
            "method_id": method.json()["id"],
            "payment_date": "2026-10-10",
            "amount": 1250,
            "beneficiary_name": "Proveedor Norte SL",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert (body["status"], body["amount"], body["currency"]) == ("draft", 1250, "EUR")
    assert body["reference"].startswith("PAY-")
    reference = body["reference"]
    for path, status in (
        ("/payment/payments/approve", "approved"),
        ("/payment/payments/mark_sent", "sent"),
        ("/payment/payments/mark_completed", "completed"),
    ):
        response = post(admin_client, path, {"reference": reference})
        assert (response.status_code, response.json()["status"]) == (200, status), path
    detail = get(admin_client, "/payment/payments/detail", reference=reference.lower())
    assert detail.json()["status"] == "completed"
    page = get(admin_client, "/payment/payments", search=reference[-4:])
    assert [row["reference"] for row in page.json()["rows"]] == [reference]


@pytest.mark.django_db
def test_cancelling_over_http(admin_client):
    payment = make_payment(make_method())
    response = post(
        admin_client,
        "/payment/payments/cancel",
        {"id": str(payment.id), "reason": "Duplicated"},
    )
    assert (response.status_code, response.json()["cancel_reason"]) == (
        200,
        "Duplicated",
    )
    again = post(
        admin_client, "/payment/payments/cancel", {"id": str(payment.id), "reason": "x"}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "payment.not_cancellable"


@pytest.mark.django_db
def test_the_methods_over_http(admin_client):
    created = post(
        admin_client, "/payment/methods", {"name": "Cash drawer", "method_type": "cash"}
    )
    method_id = created.json()["id"]
    renamed = post(
        admin_client, "/payment/methods/update", {"id": method_id, "name": "Till cash"}
    )
    assert renamed.json()["name"] == "Till cash"
    assert (
        post(
            admin_client, "/payment/methods/deactivate", {"method": "till cash"}
        ).json()["is_active"]
        is False
    )
    listed = get(admin_client, "/payment/methods", is_active="false")
    assert [row["name"] for row in listed.json()["rows"]] == ["Till cash"]
    assert (
        post(admin_client, "/payment/methods/activate", {"id": method_id}).json()[
            "is_active"
        ]
        is True
    )


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/payment/payments"),
        post(client, "/payment/methods", {"name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_only_looks(employee_client):
    payment = make_payment(make_method())
    assert get(employee_client, "/payment/payments").status_code == 200
    assert get(employee_client, "/payment/methods").status_code == 200
    for response in (
        post(employee_client, "/payment/methods", {"name": "Card"}),
        post(
            employee_client,
            "/payment/payments",
            {
                "method_id": str(payment.method_id),
                "payment_date": "2026-10-10",
                "amount": 1,
                "beneficiary_name": "A",
            },
        ),
        post(employee_client, "/payment/payments/approve", {"id": str(payment.id)}),
        post(
            employee_client,
            "/payment/payments/cancel",
            {"id": str(payment.id), "reason": "x"},
        ),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/payment/payments", host="b.localhost").status_code == 403


# Validation and refusals


@pytest.mark.django_db
def test_an_invalid_payment_is_422_per_field(admin_client):
    method = make_method()
    response = post(
        admin_client,
        "/payment/payments",
        {
            "method_id": str(method.id),
            "payment_date": "14/10/2026",
            "amount": 0,
            "beneficiary_name": "",
            "beneficiary_iban": "ES00",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {
        "payment_date",
        "amount",
        "beneficiary_name",
        "beneficiary_iban",
    }
    assert (
        error["fields"]["amount"] == "The amount of a payment must be greater than 0."
    )


@pytest.mark.django_db
def test_a_deactivated_method_is_422_under_its_field(admin_client):
    method = make_method(is_active=False)
    response = post(
        admin_client,
        "/payment/payments",
        {
            "method_id": str(method.id),
            "payment_date": "2026-10-10",
            "amount": 100,
            "beneficiary_name": "A",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "payment.method_inactive",
        "message": "That payment method is deactivated: pick an active one.",
        "fields": {
            "method_id": "That payment method is deactivated: pick an active one."
        },
    }


@pytest.mark.django_db
def test_a_step_from_the_wrong_state_is_409(admin_client):
    payment = make_payment(make_method(), status="completed")
    response = post(admin_client, "/payment/payments/approve", {"id": str(payment.id)})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "payment.invalid_transition"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(admin_client):
    payment = make_payment(make_method(), status="completed")
    response = post(
        admin_client,
        "/payment/payments/cancel",
        {"id": str(payment.id), "reason": "x"},
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.json()["error"]["message"] == "El pago ya no admite cancelación."


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    # An undeclared filter is refused by the schema (test_schemas.py); over HTTP ninja's query
    # parser drops it before the schema sees it, as for every app.
    response = get(admin_client, "/payment/payments", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )
