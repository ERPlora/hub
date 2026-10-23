"""The customer app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. The two purchase commands have no route: only the system runs them.
"""

import json
import uuid

import pytest
from live.ninja import ensure_api_parity

from apps.customer.api import router
from apps.customer.models import CustomField
from config.api import api

ROUTES = {
    ("GET", "/customer/customers", "customer.customer.list"),
    ("GET", "/customer/customers/detail", "customer.customer.detail"),
    ("GET", "/customer/customers/stats", "customer.customer.stats"),
    ("GET", "/customer/customers/by_phone", "customer.customer.by_phone"),
    ("GET", "/customer/customers/export", "customer.customer.export"),
    ("POST", "/customer/customers", "customer.customer.create"),
    ("POST", "/customer/customers/update", "customer.customer.update"),
    ("POST", "/customer/customers/import", "customer.customer.import"),
    ("POST", "/customer/customers/set_groups", "customer.customer.set_groups"),
    ("POST", "/customer/customers/set_tags", "customer.customer.set_tags"),
    ("POST", "/customer/customers/delete", "customer.customer.delete"),
    ("POST", "/customer/customers/merge", "customer.customer.merge"),
    ("POST", "/customer/customers/erase", "customer.customer.erase"),
    ("GET", "/customer/groups", "customer.group.list"),
    ("POST", "/customer/groups", "customer.group.create"),
    ("POST", "/customer/groups/update", "customer.group.update"),
    ("POST", "/customer/groups/delete", "customer.group.delete"),
    ("GET", "/customer/tags", "customer.tag.list"),
    ("POST", "/customer/tags", "customer.tag.create"),
    ("POST", "/customer/tags/update", "customer.tag.update"),
    ("POST", "/customer/tags/delete", "customer.tag.delete"),
    ("GET", "/customer/fields", "customer.field.list"),
    ("POST", "/customer/fields", "customer.field.create"),
    ("POST", "/customer/fields/update", "customer.field.update"),
    ("POST", "/customer/fields/delete", "customer.field.delete"),
    ("GET", "/customer/activity", "customer.activity.list"),
    ("POST", "/customer/activity", "customer.activity.add"),
    ("POST", "/customer/notes", "customer.note.add"),
    ("GET", "/customer/purchases", "customer.purchase.list"),
    ("GET", "/customer/purchases/divergences", "customer.purchase.divergences"),
    ("GET", "/customer/consents", "customer.consent.history"),
    ("GET", "/customer/consents/state", "customer.consent.state"),
    ("POST", "/customer/consents/grant", "customer.consent.grant"),
    ("POST", "/customer/consents/withdraw", "customer.consent.withdraw"),
    ("GET", "/customer/orders", "customer.order.list"),
    ("GET", "/customer/orders/customer", "customer.order.customer"),
    ("POST", "/customer/orders/link", "customer.order.link"),
    ("GET", "/customer/health", "customer.health.detail"),
    ("POST", "/customer/health/grant", "customer.health.grant"),
    ("POST", "/customer/health/withdraw", "customer.health.withdraw"),
    ("POST", "/customer/health/update", "customer.health.update"),
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


# Binding


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_purchase_commands_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert {"customer.purchase.record", "customer.purchase.void", "customer.purchase.refund"}.isdisjoint(bound)


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


@pytest.mark.django_db  # the host gate reads the registry's row of the hub (base.middleware)
def test_openapi_names_every_route_after_its_operation(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("customer.")
    }
    assert served == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/customer/customers"),
        post(client, "/customer/customers", {"name": "x"}),
    ):
        assert (response.status_code, response.json()["error"]["code"]) == (
            401,
            "unauthorized",
        )


@pytest.mark.django_db
def test_the_employee_works_the_counter_but_neither_exports_nor_deletes(
    employee_client,
):
    created = post(employee_client, "/customer/customers", {"name": "Ana"})
    assert created.status_code == 201
    customer_id = created.json()["id"]
    assert get(employee_client, "/customer/customers").status_code == 200
    for response in (
        get(employee_client, "/customer/customers/export"),
        post(employee_client, "/customer/customers/delete", {"id": customer_id}),
        post(employee_client, "/customer/groups", {"name": "VIP"}),
    ):
        assert (response.status_code, response.json()["error"]["code"]) == (
            403,
            "permission_denied",
        )


@pytest.mark.django_db
def test_a_role_on_a_is_no_role_on_b(admin_client):
    assert (
        get(admin_client, "/customer/customers", host="b.localhost").status_code == 403
    )


# Validation


@pytest.mark.django_db
def test_an_invalid_card_is_422_per_field(admin_client):
    response = post(
        admin_client,
        "/customer/customers",
        {"name": "", "email": "ana@", "country": "Spain"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], set(error["fields"])) == (
        "invalid_payload",
        {"name", "email", "country"},
    )
    assert error["fields"]["email"] == "Enter a valid email."


@pytest.mark.django_db
def test_a_bad_phone_is_422_under_the_phone(admin_client):
    error = post(
        admin_client, "/customer/customers", {"name": "Ana", "phone": "600111"}
    ).json()["error"]
    assert (error["code"], list(error["fields"])) == (
        "customer.phone_invalid",
        ["phone"],
    )


@pytest.mark.django_db
def test_a_customer_needs_its_id_or_a_reference(admin_client):
    response = get(admin_client, "/customer/customers/detail")
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "customer": "Give the customer's id, or their name, phone or email."
    }


@pytest.mark.django_db
def test_a_deleted_group_is_named_in_the_422(admin_client):
    customer = post(admin_client, "/customer/customers", {"name": "Ana"}).json()
    gone = str(uuid.uuid7())
    response = post(
        admin_client,
        "/customer/customers/set_groups",
        {"id": customer["id"], "group_ids": [gone]},
    )
    assert (response.status_code, response.json()) == (
        422,
        {
            "error": {
                "code": "customer.group_unavailable",
                "message": "That group no longer exists.",
                "fields": {"groups": "That group no longer exists."},
                "unavailable_ids": [gone],
            }
        },
    )


@pytest.mark.django_db
def test_a_limit_over_100_is_422(admin_client):
    response = get(admin_client, "/customer/customers", limit=101)
    assert (response.status_code, set(response.json()["error"]["fields"])) == (
        422,
        {"limit"},
    )


@pytest.mark.django_db
def test_an_unknown_card_is_404_with_the_apps_code(admin_client):
    response = get(admin_client, "/customer/customers/detail", id=str(uuid.uuid7()))
    assert (response.status_code, response.json()["error"]["code"]) == (
        404,
        "customer.customer_unavailable",
    )


# The flows over HTTP


@pytest.mark.django_db
def test_the_card_round_trip(admin_client):
    created = post(
        admin_client,
        "/customer/customers",
        {"name": "Ana García", "phone": "600 111 222"},
    ).json()
    customer_id = created["id"]
    assert (created["phone"], created["custom_fields"], created["consent"]) == (
        "+34600111222",
        [],
        [],
    )

    page = get(admin_client, "/customer/customers", search="garcia").json()
    assert ([row["id"] for row in page["rows"]], page["total"]) == ([customer_id], 1)
    assert (
        get(admin_client, "/customer/customers/detail", customer="600 111 222").json()[
            "id"
        ]
        == customer_id
    )
    assert [
        row["id"]
        for row in get(
            admin_client, "/customer/customers/by_phone", phone="34600111222"
        ).json()["rows"]
    ] == [customer_id]
    assert get(admin_client, "/customer/customers/stats").json() == {
        "total": 1,
        "active": 1,
        "vip": 0,
        "total_revenue": 0,
    }

    field = post(
        admin_client, "/customer/fields", {"name": "Allergies", "is_required": True}
    ).json()
    assert (
        post(
            admin_client,
            "/customer/fields/update",
            {"field": "allergies", "sort_order": 3},
        ).json()["sort_order"]
        == 3
    )
    rejected = post(
        admin_client,
        "/customer/customers/update",
        {"id": customer_id, "field_values": []},
    )
    assert (rejected.status_code, rejected.json()["error"]["code"]) == (
        422,
        "customer.field_required",
    )
    updated = post(
        admin_client,
        "/customer/customers/update",
        {
            "customer": "Ana García",
            "email": "ana@example.com",
            "field_values": [{"field_id": field["id"], "value": "Latex"}],
        },
    ).json()
    assert (updated["email"], updated["custom_fields"][0]["value"]) == (
        "ana@example.com",
        "Latex",
    )

    group = post(admin_client, "/customer/groups", {"name": "VIP"})
    assert group.status_code == 201
    assert (
        post(admin_client, "/customer/groups", {"name": "vip"}).json()["error"]["code"]
        == "customer.group_name_taken"
    )
    assert post(
        admin_client,
        "/customer/customers/set_groups",
        {"id": customer_id, "groups": ["VIP"]},
    ).json()["group_ids"] == [group.json()["id"]]
    assert (
        get(admin_client, "/customer/groups").json()["rows"][0]["customer_count"] == 1
    )
    tag = post(admin_client, "/customer/tags", {"name": "Moroso"}).json()
    assert post(
        admin_client,
        "/customer/customers/set_tags",
        {"id": customer_id, "tag_ids": [tag["id"]]},
    ).json()["tag_ids"] == [tag["id"]]
    assert (
        post(
            admin_client, "/customer/tags/update", {"id": tag["id"], "color": "danger"}
        ).json()["color"]
        == "danger"
    )
    assert get(admin_client, "/customer/tags").json()["total"] == 1

    note = post(
        admin_client,
        "/customer/notes",
        {"customer_id": customer_id, "content": "Prefers mornings"},
    )
    assert (note.status_code, note.json()["kind"]) == (201, "note_added")
    entry = post(
        admin_client,
        "/customer/activity",
        {"customer_id": customer_id, "kind": "appointment.visit", "title": "Visit"},
    )
    assert entry.status_code == 201
    assert [
        row["kind"]
        for row in get(
            admin_client, "/customer/activity", customer_id=customer_id
        ).json()["rows"]
    ] == [
        "appointment.visit",
        "note_added",
    ]

    granted = post(
        admin_client,
        "/customer/consents/grant",
        {"customer_id": customer_id, "channel": "email", "notice_text": "Yes"},
    )
    assert (granted.status_code, granted.json()["contact_point"]) == (
        201,
        "ana@example.com",
    )
    assert (
        post(
            admin_client,
            "/customer/consents/withdraw",
            {"customer_id": customer_id, "channel": "email"},
        ).status_code
        == 201
    )
    assert [
        row["state"]
        for row in get(
            admin_client, "/customer/consents/state", customer_id=customer_id
        ).json()["rows"]
    ] == ["withdrawn"]
    assert (
        get(admin_client, "/customer/consents", customer_id=customer_id).json()["total"]
        == 2
    )

    order = str(uuid.uuid7())
    assert (
        post(
            admin_client,
            "/customer/orders/link",
            {"order_id": order, "customer_id": customer_id},
        ).json()["customer_id"]
        == customer_id
    )
    assert get(admin_client, "/customer/orders/customer", order_id=order).json() == {
        "order_id": order,
        "customer_id": customer_id,
    }
    assert [
        row["order_id"]
        for row in get(
            admin_client, "/customer/orders", customer_id=customer_id
        ).json()["rows"]
    ] == [order]
    assert (
        get(admin_client, "/customer/purchases", customer_id=customer_id).json()[
            "total"
        ]
        == 0
    )
    assert get(admin_client, "/customer/purchases/divergences").json()["rows"] == []

    exported = get(admin_client, "/customer/customers/export").json()
    assert (exported["filename"], exported["rows"]) == ("customers.csv", 1)
    assert "'+34600111222" in exported["csv"]

    duplicate = post(
        admin_client,
        "/customer/customers",
        {"name": "ana garcia", "tax_id": "12345678Z"},
    ).json()
    merged = post(
        admin_client,
        "/customer/customers/merge",
        {"id": customer_id, "absorbed_id": duplicate["id"]},
    ).json()
    assert merged["tax_id"] == "12345678Z"

    assert post(
        admin_client, "/customer/fields/delete", {"id": field["id"]}
    ).json() == {"id": field["id"]}
    assert not CustomField.objects.exists()
    assert post(admin_client, "/customer/tags/delete", {"tag": "Moroso"}).json() == {
        "id": tag["id"]
    }
    assert (
        post(admin_client, "/customer/groups/delete", {"group": "VIP"}).status_code
        == 200
    )
    assert (
        post(
            admin_client, "/customer/groups/update", {"group": "VIP", "name": "Gold"}
        ).status_code
        == 404
    )

    assert post(
        admin_client, "/customer/customers/delete", {"id": customer_id}
    ).json() == {"id": customer_id}
    assert (
        get(admin_client, "/customer/customers/detail", id=customer_id).status_code
        == 404
    )
    assert post(
        admin_client, "/customer/customers/erase", {"id": customer_id, "reason": "GDPR"}
    ).json() == {"id": customer_id}


@pytest.mark.django_db
def test_the_import_over_http(admin_client):
    response = post(
        admin_client,
        "/customer/customers/import",
        {"rows": [{"name": "Ana", "phone": "600111222"}, {"name": ""}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["created"], body["skipped"], body["rows"][1]["errors"]) == (
        1,
        1,
        {"name": "Ensure this value has at least 1 character."},
    )


# Health data (CUSTOMER-F32)


@pytest.mark.django_db
def test_the_health_block_over_http(employee_client):
    ana = post(employee_client, "/customer/customers", {"name": "Ana"}).json()
    refused = post(
        employee_client, "/customer/health/update", {"customer_id": ana["id"], "allergies": "PPD"}
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "customer.health_consent_required",
    )
    granted = post(
        employee_client,
        "/customer/health/grant",
        {"customer_id": ana["id"], "notice_text": "I let this business keep my allergies."},
    )
    assert (granted.status_code, granted.json()["consent"]) == (200, "granted")
    saved = post(
        employee_client,
        "/customer/health/update",
        {"customer_id": ana["id"], "allergies": "PPD", "sensitivity_test_result": "positive"},
    )
    assert (saved.status_code, saved.json()["error"]["fields"]) == (
        422,
        {"sensitivity_test_on": "Enter the date of the test."},
    )
    saved = post(
        employee_client, "/customer/health/update", {"customer_id": ana["id"], "allergies": "PPD"}
    )
    assert (saved.status_code, saved.json()["allergies"]) == (200, "PPD")
    block = get(employee_client, "/customer/health", customer_id=ana["id"]).json()
    assert (block["consent"], block["allergies"]) == ("granted", "PPD")
    gone = post(employee_client, "/customer/health/withdraw", {"customer_id": ana["id"]})
    assert (gone.status_code, gone.json()["consent"], gone.json()["allergies"]) == (
        200,
        "withdrawn",
        "",
    )
