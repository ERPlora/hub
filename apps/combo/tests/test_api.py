"""The combo app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. A pick travels in the query string of ``resolve`` as a JSON object per ``choices``.
"""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.combo.api import router
from config.api import api

from .conftest import FOOD, make_combo, make_group, make_option, make_product

ROUTES = {
    ("GET", "/combo/combos", "combo.combo.list"),
    ("GET", "/combo/combos/detail", "combo.combo.get"),
    ("GET", "/combo/combos/for_sale", "combo.combo.for_sale"),
    ("GET", "/combo/combos/resolve", "combo.combo.resolve"),
    ("POST", "/combo/combos", "combo.combo.create"),
    ("POST", "/combo/combos/update", "combo.combo.update"),
    ("POST", "/combo/combos/delete", "combo.combo.delete"),
    ("POST", "/combo/groups", "combo.group.create"),
    ("POST", "/combo/groups/update", "combo.group.update"),
    ("POST", "/combo/groups/delete", "combo.group.delete"),
    ("POST", "/combo/groups/reorder", "combo.group.reorder"),
    ("POST", "/combo/options", "combo.option.create"),
    ("POST", "/combo/options/bulk_create", "combo.option.bulk_create"),
    ("POST", "/combo/options/update", "combo.option.update"),
    ("POST", "/combo/options/delete", "combo.option.delete"),
    ("POST", "/combo/options/reorder", "combo.option.reorder"),
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
    client.force_login(make_user("bea", host="a", role="hub_employee"))
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
    assert [problem for problem in ensure_api_parity(api) if "combo." in problem] == []


@pytest.mark.django_db
def test_the_openapi_describes_the_combo_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("combo.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_combo_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("combo.")
    }
    assert mine == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/combo/combos"),
        post(client, "/combo/combos", {"name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_and_prices_menus_but_does_not_build_them(employee_client):
    combo = make_combo("Menu of the day")
    make_option(make_group(combo, "Starters"), make_product("Lentils"))
    assert get(employee_client, "/combo/combos").json()["total"] == 1
    assert (
        get(employee_client, "/combo/combos/for_sale").json()["rows"][0]["name"]
        == "Menu of the day"
    )
    line = get(
        employee_client,
        "/combo/combos/resolve",
        combo="menu of the day",
        choices=json.dumps({"product": "Lentils"}),
    )
    assert line.status_code == 200, line.content
    assert line.json()["amount"] == 1350
    for path, body in (
        ("/combo/combos", {"name": "x", "supply_kind": "goods"}),
        ("/combo/combos/delete", {"id": str(combo.id)}),
        ("/combo/groups", {"combo_id": str(combo.id), "name": "Mains"}),
    ):
        response = post(employee_client, path, body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "permission_denied"


# Flows over HTTP


@pytest.mark.django_db
def test_a_menu_from_creation_to_the_till(admin_client):
    make_product("Lentils", sku="LEN", price=700)
    make_product("Hake", sku="HAK", price=1400)
    make_product("Water", sku="WAT", price=200)
    created = post(
        admin_client,
        "/combo/combos",
        {"name": "Menu of the day", "price": 1350, "tax_category_key": FOOD},
    )
    assert created.status_code == 201, created.content
    menu = created.json()
    assert (menu["sellable"], [b["code"] for b in menu["blockers"]]) == (
        False,
        ["combo.no_choices"],
    )
    for name in ("Starters", "Mains", "Drink"):
        assert (
            post(
                admin_client,
                "/combo/groups",
                {"combo": "Menu of the day", "name": name},
            ).status_code
            == 201
        )
    starters = post(
        admin_client,
        "/combo/options",
        {"combo": "Menu of the day", "group": "Starters", "product": "LEN"},
    )
    assert starters.status_code == 201, starters.content
    hake = post(
        admin_client,
        "/combo/options",
        {
            "combo": "Menu of the day",
            "group": "Mains",
            "product": "Hake",
            "price_delta": 200,
        },
    ).json()
    drink = get(admin_client, "/combo/combos/detail", combo="Menu of the day").json()[
        "groups"
    ][2]
    bulk = post(
        admin_client,
        "/combo/options/bulk_create",
        {"group_id": drink["id"], "product_ids": [str(make_product("Wine").id)]},
    )
    assert bulk.status_code == 201
    post(admin_client, "/combo/options", {"group_id": drink["id"], "product": "Water"})
    detail = get(admin_client, "/combo/combos/detail", id=menu["id"]).json()
    assert detail["sellable"] is True
    assert [g["name"] for g in detail["groups"]] == ["Starters", "Mains", "Drink"]
    reordered = post(
        admin_client,
        "/combo/groups/reorder",
        {"id": menu["id"], "group_ids": [detail["groups"][i]["id"] for i in (1, 0, 2)]},
    )
    assert [g["name"] for g in reordered.json()["groups"]] == [
        "Mains",
        "Starters",
        "Drink",
    ]
    picks = [json.dumps({"product": name}) for name in ("Lentils", "Hake", "Water")]
    line = get(
        admin_client, "/combo/combos/resolve", id=menu["id"], choices=picks
    ).json()
    assert (line["amount"], line["split"], line["tax_category_key"]) == (
        1550,
        False,
        FOOD,
    )
    assert [c["product_name"] for c in line["components"]] == [
        "Hake",
        "Lentils",
        "Water",
    ]
    sold_out = post(
        admin_client, "/combo/options/update", {"id": hake["id"], "is_available": False}
    )
    assert sold_out.json()["status"] == "sold_out"
    refused = get(admin_client, "/combo/combos/resolve", id=menu["id"], choices=picks)
    assert refused.status_code == 409
    assert refused.json()["error"] == {
        "code": "combo.option_sold_out",
        "message": "“Hake” is sold out.",
    }
    updated = post(
        admin_client, "/combo/combos/update", {"id": menu["id"], "is_active": False}
    )
    assert updated.json()["is_active"] is False
    assert get(admin_client, "/combo/combos/for_sale").json()["total"] == 0
    assert (
        post(admin_client, "/combo/options/delete", {"id": hake["id"]}).status_code
        == 200
    )
    assert (
        post(
            admin_client,
            "/combo/groups/delete",
            {"combo": "Menu of the day", "group": "Mains"},
        ).status_code
        == 200
    )
    assert (
        post(admin_client, "/combo/combos/delete", {"id": menu["id"]}).status_code
        == 200
    )
    assert get(admin_client, "/combo/combos").json()["total"] == 0


# Errors


@pytest.mark.django_db
def test_a_refusal_on_a_field_is_a_422_with_its_field(admin_client):
    response = post(
        admin_client, "/combo/combos", {"name": "Menu of the day", "price": 1350}
    )
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"tax_category_key"}
    response = post(admin_client, "/combo/combos", {"name": "x", "hub_id": "b"})
    assert response.status_code == 422


@pytest.mark.django_db
def test_a_domain_refusal_is_a_409_with_its_code(admin_client):
    combo = make_combo()
    make_group(combo, "Starters")
    response = post(
        admin_client, "/combo/groups", {"combo_id": str(combo.id), "name": "starters"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "combo.group_exists"


@pytest.mark.django_db
def test_an_unknown_menu_is_a_404(admin_client):
    response = get(admin_client, "/combo/combos/detail", combo="brunch")
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "That menu does not exist in this business."
    )
