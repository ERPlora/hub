"""The modifier app's routes: each bound to its operation, and the whole app over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. No path parameters: a group, an option or a link travels in the input (query string on
GET, body on POST), by its id or as a person names it.
"""

import json
import uuid

import pytest
from live.ninja import ensure_api_parity

from apps.modifier.api import router
from config.api import api

from .conftest import GENERIC, make_category, make_product

ROUTES = {
    ("GET", "/modifier/groups", "modifier.group.list"),
    ("GET", "/modifier/groups/detail", "modifier.group.get"),
    ("GET", "/modifier/groups/for_target", "modifier.group.for_target"),
    ("POST", "/modifier/groups", "modifier.group.create"),
    ("POST", "/modifier/groups/update", "modifier.group.update"),
    ("POST", "/modifier/groups/delete", "modifier.group.delete"),
    ("GET", "/modifier/options", "modifier.option.list"),
    ("POST", "/modifier/options", "modifier.option.create"),
    ("POST", "/modifier/options/update", "modifier.option.update"),
    ("POST", "/modifier/options/delete", "modifier.option.delete"),
    ("GET", "/modifier/links", "modifier.link.list"),
    ("POST", "/modifier/links/attach", "modifier.link.attach"),
    ("POST", "/modifier/links/detach", "modifier.link.detach"),
    ("GET", "/modifier/selections/resolve", "modifier.selection.resolve"),
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


def test_the_reactions_to_inventory_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert not bound & {"modifier.link.drop_product", "modifier.link.drop_category"}


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/modifier/groups"),
        post(client, "/modifier/groups", {"name": "x"}),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_reads_but_does_not_write(employee_client):
    for path in ("/modifier/groups", "/modifier/options", "/modifier/links"):
        assert get(employee_client, path).status_code == 200, path
    for path, body in (
        ("/modifier/groups", {"name": "Sauces"}),
        ("/modifier/options", {"group": "Sauces", "name": "Mayo"}),
        ("/modifier/links/attach", {"group": "Sauces", "product": "BUR"}),
    ):
        response = post(employee_client, path, body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert get(admin_client, "/modifier/groups", host="b.localhost").status_code == 403


@pytest.mark.django_db
def test_an_invalid_group_is_422_per_field(admin_client):
    response = post(
        admin_client,
        "/modifier/groups",
        {"name": "", "min_choices": 60, "max_choices": -1},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_payload"
    assert set(error["fields"]) == {"name", "min_choices", "max_choices"}
    below = post(
        admin_client,
        "/modifier/groups",
        {"name": "A", "min_choices": 2, "max_choices": 1},
    )
    assert below.json()["error"]["fields"] == {
        "max_choices": "The maximum cannot be below the minimum (0 = no ceiling)."
    }
    assert get(admin_client, "/modifier/groups", limit=101).status_code == 422


@pytest.mark.django_db
def test_a_domain_refusal_is_a_409_with_its_code_and_field(admin_client):
    assert post(admin_client, "/modifier/groups", {"name": "Sauces"}).status_code == 201
    response = post(admin_client, "/modifier/groups", {"name": "SAUCES"})
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "modifier.group_name_taken",
        "message": "There is already a group with that name.",
        "fields": {"name": "There is already a group with that name."},
    }


@pytest.mark.django_db
def test_a_missing_group_is_404_and_a_group_not_named_is_422(admin_client):
    missing = get(admin_client, "/modifier/groups/detail", id=str(uuid.uuid7()))
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    assert get(admin_client, "/modifier/groups/detail").status_code == 422


@pytest.mark.django_db
def test_round_trip(admin_client):
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    sauces = post(
        admin_client, "/modifier/groups", {"name": "Sauces", "max_choices": 2}
    )
    assert sauces.status_code == 201
    group_id = sauces.json()["id"]
    doneness = post(
        admin_client,
        "/modifier/groups",
        {
            "name": "Doneness",
            "min_choices": 1,
            "max_choices": 1,
            "kitchen_name": "POINT",
        },
    )
    assert doneness.json()["is_required"] is True

    mayo = post(
        admin_client,
        "/modifier/options",
        {"group": "Sauces", "name": "Mayo", "price_delta": 30},
    )
    assert (mayo.status_code, mayo.json()["price_delta"]) == (201, 30)
    soda = post(
        admin_client,
        "/modifier/options",
        {
            "group_id": group_id,
            "name": "Soda",
            "price_delta": 250,
            "tax_category_key": GENERIC,
        },
    )
    assert soda.json()["tax_category_key"] == GENERIC
    rare = post(
        admin_client,
        "/modifier/options",
        {
            "group": "Doneness",
            "name": "Rare",
            "kitchen_name": "RARE",
            "is_default": True,
        },
    )
    assert rare.json()["is_default"] is True

    assert (
        post(
            admin_client,
            "/modifier/links/attach",
            {"group": "Sauces", "category": "Mains"},
        ).status_code
        == 201
    )
    assert (
        post(
            admin_client,
            "/modifier/links/attach",
            {"group": "Doneness", "product": "BUR-01"},
        ).status_code
        == 201
    )
    run_in = post(
        admin_client,
        "/modifier/links/attach",
        {"group": "Doneness", "product": "Burger"},
    )
    assert (run_in.status_code, run_in.json()["error"]["code"]) == (
        409,
        "modifier.link_exists",
    )
    # The burger is not in Mains yet: only its own group.
    assert [
        g["name"]
        for g in get(
            admin_client, "/modifier/groups/for_target", product="BUR-01"
        ).json()["groups"]
    ] == ["Doneness"]
    run_category = post(
        admin_client,
        "/inventory/product_categories/add",
        {"product": "BUR-01", "category": "Mains"},
    )
    assert run_category.status_code == 200
    target = get(
        admin_client, "/modifier/groups/for_target", product_id=str(burger.id)
    ).json()
    assert [g["name"] for g in target["groups"]] == ["Doneness", "Sauces"]

    page = get(admin_client, "/modifier/groups", search="sau").json()
    assert [
        (row["name"], row["option_count"], row["link_count"]) for row in page["rows"]
    ] == [("Sauces", 2, 1)]
    assert (
        get(admin_client, "/modifier/groups/detail", group="doneness").json()[
            "kitchen_name"
        ]
        == "POINT"
    )
    assert get(admin_client, "/modifier/options", group="Sauces").json()["total"] == 2
    assert (
        get(admin_client, "/modifier/links", category_id=str(mains.id)).json()["total"]
        == 1
    )

    # The till's valuation: the picks travel as a repeated query parameter, in the order chosen.
    valued = admin_client.get(
        "/api/modifier/selections/resolve",
        {
            "product": "BUR-01",
            "option_ids": [mayo.json()["id"], rare.json()["id"], soda.json()["id"]],
        },
        HTTP_HOST="a.localhost",
    )
    assert valued.status_code == 200, valued.content
    assert (valued.json()["folded_delta"], valued.json()["kitchen_text"]) == (
        30,
        "Mayo, RARE, Soda",
    )
    missing = get(
        admin_client,
        "/modifier/selections/resolve",
        product="BUR-01",
        option_ids=mayo.json()["id"],
    )
    assert (missing.status_code, missing.json()["error"]["code"]) == (
        409,
        "modifier.choice_below_min",
    )
    assert missing.json()["error"]["fields"] == {
        "option_ids": "Choose at least 1 in «Doneness»."
    }

    updated = post(
        admin_client,
        "/modifier/groups/update",
        {"group": "Sauces", "kitchen_name": "SAUCE"},
    )
    assert (updated.status_code, updated.json()["max_choices"]) == (200, 2)
    assert (
        post(
            admin_client,
            "/modifier/options/update",
            {"option": "Mayo", "price_delta": 40},
        ).json()["price_delta"]
        == 40
    )
    assert (
        post(
            admin_client,
            "/modifier/links/detach",
            {"group": "Sauces", "category": "Mains"},
        ).status_code
        == 200
    )
    assert (
        post(admin_client, "/modifier/options/delete", {"option": "Soda"}).status_code
        == 200
    )
    deleted = post(admin_client, "/modifier/groups/delete", {"group": "Sauces"})
    assert (deleted.status_code, deleted.json()) == (200, {"id": group_id})
    assert get(admin_client, "/modifier/groups/detail", id=group_id).status_code == 404


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(admin_client):
    response = admin_client.get(
        "/api/modifier/groups/detail",
        {"id": str(uuid.uuid7())},
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.json()["error"]["message"] == "Este grupo no existe."
