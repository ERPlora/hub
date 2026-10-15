"""The pricing app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.pricing.api import router
from config.api import api

from .conftest import make_group, make_list, make_product

ROUTES = {
    ("GET", "/pricing/price_lists", "pricing.price_list.list"),
    ("GET", "/pricing/price_lists/detail", "pricing.price_list.get"),
    ("POST", "/pricing/price_lists", "pricing.price_list.create"),
    ("POST", "/pricing/price_lists/update", "pricing.price_list.update"),
    ("POST", "/pricing/price_lists/set_default", "pricing.price_list.set_default"),
    ("POST", "/pricing/price_lists/deactivate", "pricing.price_list.deactivate"),
    ("POST", "/pricing/price_lists/activate", "pricing.price_list.activate"),
    ("GET", "/pricing/price_items", "pricing.price_item.list"),
    ("POST", "/pricing/price_items", "pricing.price_item.add"),
    ("POST", "/pricing/price_items/update", "pricing.price_item.update"),
    ("POST", "/pricing/price_items/remove", "pricing.price_item.remove"),
    ("GET", "/pricing/rules", "pricing.rule.list"),
    ("POST", "/pricing/rules", "pricing.rule.create"),
    ("POST", "/pricing/rules/update", "pricing.rule.update"),
    ("POST", "/pricing/rules/deactivate", "pricing.rule.deactivate"),
    ("POST", "/pricing/rules/activate", "pricing.rule.activate"),
    ("GET", "/pricing/prices/resolve", "pricing.price.resolve"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("bea", host="a", role="hub_employee"))
    return client


# Binding


def test_every_route_is_bound_to_its_operation_and_the_reactions_have_none():
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
def test_the_openapi_describes_the_pricing_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("pricing.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_pricing_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("pricing.")
    }
    assert mine == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/pricing/price_lists"), post(client, "/pricing/price_lists", {"code": "c", "name": "n"})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_and_asks_for_prices_but_does_not_manage(employee_client):
    product = make_product("Shampoo", "SH-1", price=1250)
    assert get(employee_client, "/pricing/price_lists").status_code == 200
    answer = get(employee_client, "/pricing/prices/resolve", product="SH-1", quantity="2", when="2026-07-15T10:00:00+02:00")
    assert answer.status_code == 200, answer.content
    assert (answer.json()["unit_price"], answer.json()["line_amount"], answer.json()["product_id"]) == (1250, 2500, str(product.id))
    refused = post(employee_client, "/pricing/price_lists", {"code": "c", "name": "n"})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")


# Flows


@pytest.mark.django_db
def test_a_list_its_price_and_a_rule_over_http(admin_client):
    make_group("VIP")
    product = make_product("Shampoo", "SH-1", price=1500)
    created = post(admin_client, "/pricing/price_lists", {"code": "VIP", "name": "VIP members", "customer_group": "VIP"})
    assert created.status_code == 201, created.content
    list_id = created.json()["id"]
    added = post(admin_client, "/pricing/price_items", {"price_list_id": list_id, "product": "SH-1", "price": 1200})
    assert added.status_code == 201, added.content
    rows = get(admin_client, "/pricing/price_items", price_list_id=list_id).json()["rows"]
    assert [(row["name"], row["price"], row["base_price"]) for row in rows] == [("Shampoo", 1200, 1500)]
    rule = post(admin_client, "/pricing/rules", {"code": "TEN", "name": "Ten", "rule_type": "percent", "percent": "10"})
    assert rule.status_code == 201, rule.content
    detail = get(admin_client, "/pricing/price_lists/detail", price_list="vip").json()
    assert (detail["customer_group_name"], detail["item_count"]) == ("VIP", 1)
    assert product.id


@pytest.mark.django_db
def test_refusals_come_in_the_envelope_with_their_field(admin_client):
    make_list("VIP")
    duplicate = post(admin_client, "/pricing/price_lists", {"code": "vip", "name": "Again"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "pricing.duplicate_code"
    assert set(duplicate.json()["error"]["fields"]) == {"code"}
    incoherent = post(admin_client, "/pricing/rules", {"code": "X", "name": "X", "rule_type": "fixed"})
    assert incoherent.status_code == 422
    assert set(incoherent.json()["error"]["fields"]) == {"amount"}
    # The live stream and the assistant validate with the schema, which forbids extras; a GET of ninja
    # drops unknown query keys before the schema sees them (the gap of packages/live task reported).
    from pydantic import ValidationError

    from apps.pricing.schemas import PriceListListIn

    with pytest.raises(ValidationError):
        PriceListListIn.model_validate({"colour": "red"})
    unknown = post(admin_client, "/pricing/price_lists", {"code": "X", "name": "X", "segment": "retail"})
    assert (unknown.status_code, set(unknown.json()["error"]["fields"])) == (422, {"segment"})
    too_many = get(admin_client, "/pricing/rules", limit=101)
    assert too_many.status_code == 422


@pytest.mark.django_db
def test_the_general_list_and_its_switches_over_http(admin_client):
    make_list("OLD", is_default=True)
    make_list("NEW")
    made = post(admin_client, "/pricing/price_lists/set_default", {"price_list": "NEW"})
    assert (made.status_code, made.json()["is_default"]) == (200, True)
    refused = post(admin_client, "/pricing/price_lists/deactivate", {"price_list": "NEW"})
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "pricing.price_list_is_default")
    assert post(admin_client, "/pricing/price_lists/deactivate", {"price_list": "OLD"}).status_code == 200
