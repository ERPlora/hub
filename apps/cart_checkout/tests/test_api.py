"""The cart_checkout app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a record travels in the input (query string on GET, body on POST), by
its id or, as a person says it, by its session code, its customer or its order number.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from apps.cart_checkout.api import router
from config.api import api

from .conftest import make_cart, make_order

ROUTES = {
    ("GET", "/cart_checkout/carts", "cart_checkout.cart.list"),
    ("GET", "/cart_checkout/carts/detail", "cart_checkout.cart.get"),
    ("POST", "/cart_checkout/carts", "cart_checkout.cart.create"),
    ("POST", "/cart_checkout/carts/mark_abandoned", "cart_checkout.cart.mark_abandoned"),
    ("POST", "/cart_checkout/carts/delete", "cart_checkout.cart.delete"),
    ("POST", "/cart_checkout/carts/clear", "cart_checkout.cart.clear"),
    ("POST", "/cart_checkout/carts/cleanup_expired", "cart_checkout.cart.cleanup_expired"),
    ("GET", "/cart_checkout/items", "cart_checkout.item.list"),
    ("GET", "/cart_checkout/items/detail", "cart_checkout.item.get"),
    ("POST", "/cart_checkout/items", "cart_checkout.item.add"),
    ("POST", "/cart_checkout/items/update", "cart_checkout.item.update"),
    ("POST", "/cart_checkout/items/remove", "cart_checkout.item.remove"),
    ("POST", "/cart_checkout/checkout/initiate", "cart_checkout.checkout.initiate"),
    ("GET", "/cart_checkout/orders", "cart_checkout.order.list"),
    ("GET", "/cart_checkout/orders/detail", "cart_checkout.order.get"),
    ("POST", "/cart_checkout/orders/mark_paid", "cart_checkout.order.mark_paid"),
    ("POST", "/cart_checkout/orders/fail", "cart_checkout.order.fail"),
    ("POST", "/cart_checkout/orders/complete", "cart_checkout.order.complete"),
    ("POST", "/cart_checkout/customers/erase", "cart_checkout.customer.erase"),
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
def test_from_a_new_cart_to_a_completed_order(admin_client):
    created = post(
        admin_client,
        "/cart_checkout/carts",
        {"session_token": "sess_http", "customer_email": "ana@example.com"},
    )
    assert created.status_code == 201
    assert (created.json()["status"], created.json()["currency"]) == ("active", "EUR")
    line = post(
        admin_client,
        "/cart_checkout/items",
        {"session_token": "sess_http", "product_ref": "p-1", "product_name": "Champú", "quantity": "0.5", "unit_price": 1200},
    )
    assert line.status_code == 201
    assert (line.json()["item"]["line_total"], line.json()["cart"]["total_amount"]) == (600, 600)
    order = post(admin_client, "/cart_checkout/checkout/initiate", {"customer": "ana@example.com"})
    assert order.status_code == 201
    number = order.json()["order_number"]
    assert number.startswith("OS-")
    for path, status in (("/cart_checkout/orders/mark_paid", "paid"), ("/cart_checkout/orders/complete", "completed")):
        response = post(admin_client, path, {"order_number": number.lower()})
        assert (response.status_code, response.json()["status"]) == (200, status), path
    cart = get(admin_client, "/cart_checkout/carts/detail", session_token="sess_http")
    assert (cart.json()["status"], [i["product_name"] for i in cart.json()["items"]]) == ("converted", ["Champú"])
    orders = get(admin_client, "/cart_checkout/orders", search=number[-4:])
    assert [row["order_number"] for row in orders.json()["rows"]] == [number]


@pytest.mark.django_db
def test_a_session_code_in_use_answers_409_under_its_field(admin_client):
    make_cart("sess_1")
    response = post(admin_client, "/cart_checkout/carts", {"session_token": "sess_1"})
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "cart_checkout.session_taken",
            "message": "There is already a cart with that session.",
            "fields": {"session_token": "There is already a cart with that session."},
        }
    }


@pytest.mark.django_db
def test_a_bad_quantity_answers_422_under_its_field(admin_client):
    make_cart("sess_1")
    response = post(
        admin_client,
        "/cart_checkout/items",
        {"session_token": "sess_1", "product_ref": "p", "product_name": "x", "quantity": "0", "unit_price": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"quantity": "The quantity must be greater than 0."}


@pytest.mark.django_db
def test_a_step_from_the_wrong_state_answers_409(admin_client):
    order = make_order(status="completed")
    response = post(admin_client, "/cart_checkout/orders/fail", {"order_id": str(order.id), "reason": "late"})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "cart_checkout.invalid_transition")


@pytest.mark.django_db
def test_an_unknown_cart_answers_404(admin_client):
    response = get(admin_client, "/cart_checkout/carts/detail", session_token="nope")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "cart_checkout.cart_not_found")


@pytest.mark.django_db
def test_an_employee_looks_but_does_not_touch(employee_client):
    make_cart("sess_1")
    assert get(employee_client, "/cart_checkout/carts").json()["total"] == 1
    refused = post(employee_client, "/cart_checkout/carts/delete", {"session_token": "sess_1"})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")


@pytest.mark.django_db
def test_without_a_session_nothing(client):
    assert get(client, "/cart_checkout/orders").status_code == 401


@pytest.mark.django_db
def test_the_spanish_caller_hears_spanish(admin_client):
    make_cart("sess_1", status="abandoned")
    response = post(
        admin_client, "/cart_checkout/carts/clear", {"session_token": "sess_1"}, HTTP_ACCEPT_LANGUAGE="es"
    )
    assert response.json()["error"]["message"] == "Este carrito ya no admite cambios: está Abandonado."


@pytest.mark.django_db
def test_a_line_too_large_answers_422_not_500(admin_client):
    make_cart("sess_1")
    response = post(
        admin_client,
        "/cart_checkout/items",
        {"session_token": "sess_1", "product_ref": "p", "product_name": "x", "quantity": "1000000", "unit_price": 9999999999999},
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"quantity"}


@pytest.mark.django_db
def test_erasing_a_customer_over_http(admin_client):
    make_cart("sess_1", customer_email="ana@example.com", customer_name="Ana")
    response = post(admin_client, "/cart_checkout/customers/erase", {"email": "ana@example.com"})
    assert (response.status_code, response.json()) == (200, {"carts": 1, "orders": 0})
