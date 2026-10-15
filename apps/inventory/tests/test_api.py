"""The inventory app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a product or a category travels in the input (query string on GET,
body on POST), by its id or by its SKU or name.
"""

import json
import uuid

import pytest
from live.ninja import ensure_api_parity

from apps.inventory.api import router
from apps.tax.models import TaxCategory
from config.api import api

ROUTES = {
    ("GET", "/inventory/products", "inventory.product.list"),
    ("GET", "/inventory/products/detail", "inventory.product.get"),
    ("GET", "/inventory/products/for_sale", "inventory.product.list_for_sale"),
    ("GET", "/inventory/products/low_stock", "inventory.product.list_low_stock"),
    ("GET", "/inventory/products/export", "inventory.product.export"),
    ("POST", "/inventory/products", "inventory.product.create"),
    ("POST", "/inventory/products/bulk_create", "inventory.product.bulk_create"),
    ("POST", "/inventory/products/update", "inventory.product.update"),
    ("POST", "/inventory/products/delete", "inventory.product.delete"),
    ("GET", "/inventory/product_categories", "inventory.product_category.list"),
    ("POST", "/inventory/product_categories/add", "inventory.product_category.add"),
    ("POST", "/inventory/product_categories/remove", "inventory.product_category.remove"),
    ("GET", "/inventory/categories", "inventory.category.list"),
    ("GET", "/inventory/categories/export", "inventory.category.export"),
    ("POST", "/inventory/categories", "inventory.category.create"),
    ("POST", "/inventory/categories/bulk_create", "inventory.category.bulk_create"),
    ("POST", "/inventory/categories/update", "inventory.category.update"),
    ("POST", "/inventory/categories/delete", "inventory.category.delete"),
    ("GET", "/inventory/movements", "inventory.movement.list"),
    ("GET", "/inventory/stock/summary", "inventory.stock.get_summary"),
    ("POST", "/inventory/stock/receive", "inventory.stock.receive"),
    ("POST", "/inventory/stock/count", "inventory.stock.count"),
    ("POST", "/inventory/stock/write_off", "inventory.stock.write_off"),
    ("GET", "/inventory/units", "inventory.unit.list"),
    ("GET", "/inventory/config", "inventory.config.get"),
    ("POST", "/inventory/config", "inventory.config.update"),
}
TAX = "test.general"


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


@pytest.fixture
def tax(db):
    return TaxCategory.objects.create(key=TAX, name="General")


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


def test_the_reactions_to_sales_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {"inventory.stock.apply_sale", "inventory.stock.restore_sale", "inventory.stock.restore_refund"}


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/inventory/products"), post(client, "/inventory/products", {"name": "x"})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_but_does_not_write(employee_client):
    for path in ("/inventory/products", "/inventory/categories", "/inventory/movements", "/inventory/stock/summary"):
        assert get(employee_client, path).status_code == 200, path
    for response in (
        get(employee_client, "/inventory/config"),
        get(employee_client, "/inventory/products/export"),
        post(employee_client, "/inventory/products", {"name": "x", "sku": "X", "price": 1, "tax_category_key": TAX}),
        post(employee_client, "/inventory/stock/count", {"product": "x", "stock": 1, "reason": "count"}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/inventory/products", host="b.localhost").status_code == 403


# Validation and refusals


@pytest.mark.django_db
def test_an_invalid_product_is_422_per_field(admin_client):
    response = post(admin_client, "/inventory/products", {"name": "", "sku": "X", "price": -1, "tax_category_key": TAX, "unit": "lb"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {"name", "price", "unit"}


@pytest.mark.django_db
def test_the_sku_is_not_editable(admin_client):
    response = post(admin_client, "/inventory/products/update", {"product": "X", "sku": "NEW"})
    assert (response.status_code, set(response.json()["error"]["fields"])) == (422, {"sku"})


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/inventory/products", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (422, {"limit"})


@pytest.mark.django_db
def test_a_domain_refusal_is_a_409_with_its_code_and_field(admin_client):
    product = {"name": "Coffee", "sku": "CAF", "price": 150, "tax_category_key": TAX}
    assert post(admin_client, "/inventory/products", product).status_code == 201
    response = post(admin_client, "/inventory/products", product)
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "inventory.sku_taken",
        "message": "That SKU already exists in the catalog.",
        "fields": {"sku": "That SKU already exists in the catalog."},
    }


@pytest.mark.django_db
def test_a_missing_product_is_404_and_a_product_not_named_is_422(admin_client):
    missing = get(admin_client, "/inventory/products/detail", id=str(uuid.uuid7()))
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    unnamed = get(admin_client, "/inventory/products/detail")
    assert unnamed.status_code == 422


# The whole app over HTTP


@pytest.mark.django_db
def test_round_trip(admin_client):
    drinks = post(admin_client, "/inventory/categories", {"name": "Drinks"})
    assert drinks.status_code == 201
    created = post(
        admin_client,
        "/inventory/products",
        {"name": "Coffee", "sku": "CAF", "price": 150, "tax_category_key": TAX, "initial_stock": "10", "category_ids": [drinks.json()["id"]]},
    )
    assert created.status_code == 201
    coffee = created.json()
    assert (coffee["stock"], coffee["category_ids"], coffee["needs_tax_setup"]) == ("10.000", [drinks.json()["id"]], False)

    page = get(admin_client, "/inventory/products", search="caf").json()
    assert ([row["id"] for row in page["rows"]], page["total"]) == ([coffee["id"]], 1)
    assert get(admin_client, "/inventory/products/detail", product="caf").json()["id"] == coffee["id"]

    updated = post(admin_client, "/inventory/products/update", {"product": "Coffee", "price": 180})
    assert (updated.status_code, updated.json()["price"]) == (200, 180)

    received = post(admin_client, "/inventory/stock/receive", {"items": [{"product": "CAF", "qty": "5", "unit_cost": 90}], "reference": "ALB-1"})
    assert (received.status_code, received.json()["rows"][0]["stock"]) == (200, "15.000")
    counted = post(admin_client, "/inventory/stock/count", {"product_id": coffee["id"], "stock": "12", "reason": "weekly count"})
    assert counted.json()["stock"] == "12.000"
    written_off = post(admin_client, "/inventory/stock/write_off", {"product": "coffee", "qty": "2", "reason": "spilled"})
    assert written_off.json()["stock"] == "10.000"

    movements = get(admin_client, "/inventory/movements", product_id=coffee["id"]).json()
    assert [row["movement_type"] for row in movements["rows"]] == ["write_off", "count", "reception", "initial"]
    summary = get(admin_client, "/inventory/stock/summary").json()
    assert (summary["active_products"], summary["products_in_stock"]) == (1, 1)
    assert get(admin_client, "/inventory/products/for_sale").json()["rows"][0]["price"] == 180
    assert get(admin_client, "/inventory/products/low_stock").json()["total"] == 1  # 10 <= 10
    assert get(admin_client, "/inventory/units").json()["total"] == 8

    export = get(admin_client, "/inventory/products/export").json()
    assert export["filename"] == "inventory-products.csv" and "CAF" in export["content"]
    assert "Drinks" in get(admin_client, "/inventory/categories/export").json()["content"]

    link = {"product": "CAF", "category": "drinks"}
    assert post(admin_client, "/inventory/product_categories/remove", link).json()["changed"] is True
    assert post(admin_client, "/inventory/product_categories/add", link).json()["changed"] is True
    assert get(admin_client, "/inventory/product_categories").json()["total"] == 1

    category = post(admin_client, "/inventory/categories/update", {"category": "Drinks", "color": "#ff0000"})
    assert category.json()["color"] == "#ff0000"
    assert get(admin_client, "/inventory/categories").json()["rows"][0]["product_count"] == 1

    imported = post(admin_client, "/inventory/products/bulk_create", {"rows": [{"line": 2, "name": "Tea", "sku": "TEA", "price": "1,20", "tax_category_key": TAX}]})
    assert (imported.status_code, imported.json()["created"]) == (200, 1)
    categories = post(admin_client, "/inventory/categories/bulk_create", {"rows": [{"line": 2, "name": "Food"}, {"line": 3, "name": "drinks"}]})
    assert (categories.json()["created"], categories.json()["skipped"]) == (1, 1)

    assert get(admin_client, "/inventory/config").json()["track_stock"] is True
    assert post(admin_client, "/inventory/config", {"allow_sell_without_stock": True}).json()["allow_sell_without_stock"] is True

    assert post(admin_client, "/inventory/categories/delete", {"category": "Drinks"}).status_code == 200
    deleted = post(admin_client, "/inventory/products/delete", {"product": "CAF"})
    assert (deleted.status_code, deleted.json()) == (200, {"id": coffee["id"]})
    assert get(admin_client, "/inventory/products/detail", id=coffee["id"]).status_code == 404
