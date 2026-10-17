"""The sale app's routes: each bound to its operation, and the main flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from live.ninja import ensure_api_parity
from live.operations import UnknownOperation
from live.operations import get as get_operation

from apps.sale.api import router
from config.api import api

ROUTES = {
    ("GET", "/sale/sales", "sale.sale.list"),
    ("GET", "/sale/sales/detail", "sale.sale.get"),
    ("GET", "/sale/sales/by_key", "sale.sale.by_idempotency_key"),
    ("GET", "/sale/sales/stats", "sale.sale.stats"),
    ("GET", "/sale/sales/today", "sale.sale.today"),
    ("GET", "/sale/sales/last_7_days", "sale.sale.last_7_days"),
    ("GET", "/sale/sales/by_staff", "sale.sale.by_staff"),
    ("POST", "/sale/sales", "sale.sale.complete"),
    ("POST", "/sale/sales/complete_over_limit", "sale.sale.complete_over_limit"),
    ("POST", "/sale/sales/void", "sale.sale.void"),
    ("POST", "/sale/sales/refund", "sale.sale.refund"),
    ("POST", "/sale/sales/issue_documents", "sale.sale.issue_documents"),
    ("GET", "/sale/checkout/preview", "sale.checkout.preview"),
    ("GET", "/sale/orders", "sale.order.list"),
    ("GET", "/sale/orders/detail", "sale.order.get"),
    ("POST", "/sale/orders", "sale.order.open"),
    ("POST", "/sale/orders/add_line", "sale.order.add_line"),
    ("POST", "/sale/orders/add_open_line", "sale.order.add_open_line"),
    ("POST", "/sale/orders/add_service_line", "sale.order.add_service_line"),
    ("POST", "/sale/orders/apply_voucher", "sale.order.apply_voucher"),
    ("POST", "/sale/orders/remove_voucher", "sale.order.remove_voucher"),
    ("POST", "/sale/orders/update_line", "sale.order.update_line"),
    ("POST", "/sale/orders/set_line_staff", "sale.order.set_line_staff"),
    ("POST", "/sale/orders/split_line", "sale.order.split_line"),
    ("POST", "/sale/orders/remove_line", "sale.order.remove_line"),
    ("POST", "/sale/orders/void_line", "sale.order.void_line"),
    ("POST", "/sale/orders/fire", "sale.order.fire"),
    ("POST", "/sale/orders/split", "sale.order.split"),
    ("POST", "/sale/orders/merge", "sale.order.merge"),
    ("POST", "/sale/orders/void", "sale.order.void"),
    ("POST", "/sale/orders/set_discount", "sale.order.set_discount"),
    (
        "POST",
        "/sale/orders/set_discount_over_limit",
        "sale.order.set_discount_over_limit",
    ),
    ("POST", "/sale/orders/set_line_discount", "sale.order.set_line_discount"),
    (
        "POST",
        "/sale/orders/set_line_discount_over_limit",
        "sale.order.set_line_discount_over_limit",
    ),
    ("POST", "/sale/orders/set_label", "sale.order.set_label"),
    ("POST", "/sale/orders/set_appointment", "sale.order.set_appointment"),
    ("GET", "/sale/payment_methods", "sale.payment_method.list"),
    ("POST", "/sale/payment_methods", "sale.payment_method.create"),
    ("GET", "/sale/settings", "sale.settings.get"),
    ("POST", "/sale/settings", "sale.settings.update"),
    ("GET", "/sale/pos_settings", "sale.pos_settings.get"),
    ("GET", "/sale/departments", "sale.department.list"),
    ("POST", "/sale/departments", "sale.department.create"),
    ("POST", "/sale/departments/update", "sale.department.update"),
    ("POST", "/sale/departments/delete", "sale.department.delete"),
    ("GET", "/sale/quick_notes", "sale.quick_note.list"),
    ("POST", "/sale/quick_notes", "sale.quick_note.create"),
    ("POST", "/sale/quick_notes/update", "sale.quick_note.update"),
    ("POST", "/sale/quick_notes/delete", "sale.quick_note.delete"),
    ("GET", "/sale/business_day", "sale.business_day.get"),
    ("GET", "/sale/refunds", "sale.refund.list"),
    ("GET", "/sale/refunds/options", "sale.refund.options"),
    ("GET", "/sale/refunds/by_key", "sale.refund.by_idempotency_key"),
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
def employee_client(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    return client


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_no_sale_operation_republishes_the_tax_of_the_territory():
    # The territory's tax is Taxes' (``tax.settings.get``): every sale screen reads it there (TAX-F11).
    with pytest.raises(UnknownOperation):
        get_operation("sale.sale.tax_kind")


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_reactions_have_no_route():
    # Only the platform runs them: when Customers merges two cards, when Invoicing issues a document.
    bound = {operation for _m, _p, operation in ROUTES}
    assert {"sale.customer.reassign", "sale.sale.record_invoice"}.isdisjoint(bound)


@pytest.mark.django_db
def test_an_employee_builds_and_charges_a_check_over_http(employee_client, product):
    product("Coffee", "COF", 150, "restaurant.drink")
    opened = post(
        employee_client,
        "/sale/orders",
        {"label": "Bar", "lines": [{"product": "COF", "quantity": "2"}]},
    )
    assert opened.status_code == 201
    order = opened.json()
    assert order["provisional_total"] == 300
    preview = get(employee_client, "/sale/checkout/preview", order_id=order["id"])
    assert preview.status_code == 200 and preview.json()["total"] == 300
    charged = post(
        employee_client,
        "/sale/sales",
        {
            "idempotency_key": "http-key-0001",
            "order_id": order["id"],
            "order_version": order["version"],
            "payments": [{"method": "cash", "tendered": 500}],
        },
    )
    assert charged.status_code == 201
    sale = charged.json()
    assert (sale["total"], sale["change_total"], sale["status"]) == (
        300,
        200,
        "completed",
    )
    listed = get(employee_client, "/sale/sales")
    assert listed.json()["total"] == 1
    assert (
        get(employee_client, "/sale/sales/detail", sale=sale["number"]).json()["id"]
        == sale["id"]
    )


@pytest.mark.django_db
def test_an_employee_neither_voids_nor_reads_the_figures(employee_client):
    assert (
        post(
            employee_client,
            "/sale/sales/void",
            {"sale": "20990101-0001", "reason": "x"},
        ).status_code
        == 403
    )
    response = get(employee_client, "/sale/sales/stats")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_bad_payload_is_a_422_by_field(admin_client):
    response = post(admin_client, "/sale/sales", {"idempotency_key": "short"})
    assert response.status_code == 422
    assert "idempotency_key" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_a_refusal_is_the_error_envelope(admin_client, product):
    product("Gold", "GLD", 120000, "product.generic")
    response = post(
        admin_client,
        "/sale/sales",
        {
            "idempotency_key": "http-key-0001",
            "lines": [{"product": "GLD"}],
            "payments": [{"method": "cash", "tendered": 120000}],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "sale.cash_limit_exceeded"


@pytest.mark.django_db
def test_without_a_session_nothing_is_read(client):
    assert get(client, "/sale/sales").status_code == 401


@pytest.mark.django_db
def test_the_settings_over_http(admin_client):
    assert (
        post(admin_client, "/sale/settings", {"require_customer": True}).json()[
            "require_customer"
        ]
        is True
    )
    assert get(admin_client, "/sale/settings").json()["require_customer"] is True
    assert get(admin_client, "/sale/pos_settings").json()["require_customer"] is True


@pytest.mark.django_db
def test_an_employee_pays_a_line_with_a_voucher_over_http_and_an_exhausted_one_is_a_409(
    employee_client, customer
):
    from live.context import system_context
    from live.operations import get as operation

    from apps.sale.tests.conftest import A

    def svc(name, data):
        op = operation(name)
        return op(system_context(A), op.input.model_validate(data))

    haircut = svc(
        "service.service.create",
        {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
    )
    lucia = customer("Lucía Pérez")
    package = svc(
        "service.package.create",
        {"name": "Bono 1", "max_uses": 1, "items": [{"service_id": str(haircut.id)}]},
    )
    grant = svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(lucia.id)},
    )
    opened = post(employee_client, "/sale/orders", {"service_lines": [{"service_id": str(haircut.id)}]})
    assert opened.status_code == 201, opened.content
    order = opened.json()
    line = order["lines"][0]["id"]
    applied = post(
        employee_client,
        "/sale/orders/apply_voucher",
        {"order_id": order["id"], "line_id": line, "grant_id": str(grant.id)},
    )
    assert applied.status_code == 200, applied.content
    assert applied.json()["lines"][0]["paid_by_voucher"] is True
    other = post(employee_client, "/sale/orders", {"service_lines": [{"service_id": str(haircut.id)}]}).json()
    refused = post(
        employee_client,
        "/sale/orders/apply_voucher",
        {"order_id": other["id"], "line_id": other["lines"][0]["id"], "grant_id": str(grant.id)},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "service.grant_no_uses_left"
    undone = post(
        employee_client,
        "/sale/orders/remove_voucher",
        {"order_id": order["id"], "line_id": line},
    )
    assert undone.status_code == 200 and undone.json()["lines"][0]["paid_by_voucher"] is False
