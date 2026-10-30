"""The flow app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. The engine (react and the two scheduled tasks) has no route: no person and no API key
reaches it.
"""

import json

import pytest
from django.conf import settings
from live.models import OutboxEvent
from live.ninja import ensure_api_parity

from apps.flow.api import router
from apps.flow.models import Flow
from apps.task.models import Task
from config.api import api

from .conftest import TASK_STEP, make_draft, make_flow

ROUTES = {
    ("GET", "/flow/flows", "flow.flow.list"),
    ("GET", "/flow/flows/detail", "flow.flow.detail"),
    ("GET", "/flow/flows/status", "flow.flow.status"),
    ("GET", "/flow/flows/test", "flow.flow.test"),
    ("POST", "/flow/flows", "flow.flow.create"),
    ("POST", "/flow/flows/update", "flow.flow.update"),
    ("POST", "/flow/flows/set_enabled", "flow.flow.set_enabled"),
    ("POST", "/flow/flows/duplicate", "flow.flow.duplicate"),
    ("POST", "/flow/flows/delete", "flow.flow.delete"),
    ("POST", "/flow/flows/grant", "flow.flow.grant"),
    ("POST", "/flow/flows/run", "flow.flow.run"),
    ("GET", "/flow/runs", "flow.run.list"),
    ("GET", "/flow/runs/detail", "flow.run.get"),
    ("POST", "/flow/runs/retry", "flow.run.retry"),
    ("GET", "/flow/drafts", "flow.draft.list"),
    ("GET", "/flow/drafts/detail", "flow.draft.get"),
    ("POST", "/flow/drafts", "flow.draft.propose"),
    ("POST", "/flow/drafts/dismiss", "flow.draft.dismiss"),
    ("GET", "/flow/catalog", "flow.catalog.read"),
    ("GET", "/flow/events/sample", "flow.event.sample"),
    ("GET", "/flow/secrets", "flow.secret.list"),
    ("POST", "/flow/secrets", "flow.secret.set"),
    ("POST", "/flow/secrets/delete", "flow.secret.delete"),
    ("GET", "/flow/questions", "flow.question.list"),
    ("GET", "/flow/questions/detail", "flow.question.get"),
    ("POST", "/flow/questions/answer", "flow.question.answer"),
    ("GET", "/flow/recipes", "flow.recipe.list"),
    ("POST", "/flow/recipes/enable", "flow.recipe.enable"),
    ("POST", "/flow/recipes/disable", "flow.recipe.disable"),
    ("POST", "/flow/recipes/restore", "flow.recipe.restore"),
    ("POST", "/flow/recipes/repair", "flow.recipe.repair"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_owner"))
    return client


@pytest.fixture
def manager_client(client, make_user):
    client.force_login(make_user("mia", host="a", role="hub_manager"))
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


@pytest.mark.django_db
def test_the_openapi_describes_the_flow_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("flow.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_flow_route():
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("flow.")
    }
    assert mine == ROUTES


# Who may


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/flow/flows"), post(client, "/flow/flows", {})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_a_manager_neither_sees_nor_changes_automations(manager_client):
    for response in (
        get(manager_client, "/flow/flows"),
        post(manager_client, "/flow/flows", {}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


# The flows over HTTP


@pytest.mark.django_db
def test_create_grant_turn_on_and_run_by_hand(owner_client):
    created = post(
        owner_client,
        "/flow/flows",
        {"name": "Weekly review", "trigger": {"kind": "manual"}, "steps": [TASK_STEP]},
    )
    assert created.status_code == 201, created.content
    flow_id = created.json()["id"]
    assert created.json()["missing_grants"] == ["task.task.create"]
    granted = post(
        owner_client,
        "/flow/flows/grant",
        {"id": flow_id, "operations": ["task.task.create"]},
    )
    assert granted.json()["missing_grants"] == []
    paused = post(owner_client, "/flow/flows/run", {"id": flow_id})
    assert (paused.status_code, paused.json()["error"]["code"]) == (
        409,
        "flow.disabled",
    )
    assert post(
        owner_client, "/flow/flows/set_enabled", {"flow": "weekly", "enabled": True}
    ).json()["enabled"]
    ran = post(owner_client, "/flow/flows/run", {"id": flow_id})
    assert ran.status_code == 200, ran.content
    assert ran.json()["status"] == "succeeded"
    assert Task.objects.get().title == "Welcome the new customer"
    runs = get(owner_client, "/flow/runs", flow_id=flow_id).json()
    assert (runs["total"], runs["failed"]) == (1, 0)


@pytest.mark.django_db
def test_a_step_that_names_what_is_not_here_is_a_422_by_field(owner_client):
    response = post(
        owner_client,
        "/flow/flows",
        {"steps": [TASK_STEP | {"operation": "spa.sauna.heat"}]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "steps.0.operation": "That action does not exist in this business: «spa.sauna.heat»."
    }
    shape = post(
        owner_client, "/flow/flows", {"steps": [TASK_STEP | {"operation": ""}]}
    )
    assert shape.status_code == 422
    assert shape.json()["error"]["fields"] == {
        "steps.0.command.operation": "Choose what this step does."
    }


@pytest.mark.django_db
def test_try_reads_its_document_as_json_text(owner_client):
    OutboxEvent.objects.create(
        scope_kind="host",
        scope_key="a",
        name="sale.sale.completed",
        payload={"total": 20000},
    )
    document = {
        "trigger": {
            "kind": "event",
            "event": "sale.sale.completed",
            "filter": {"input.total": {"gte": 10000}},
        },
        "steps": [TASK_STEP],
    }
    tried = get(owner_client, "/flow/flows/test", document=json.dumps(document))
    assert tried.status_code == 200, tried.content
    assert (tried.json()["starts"], tried.json()["steps"][0]["outcome"]) == (
        True,
        "not_allowed",
    )
    assert Task.objects.count() == 0


@pytest.mark.django_db
def test_list_detail_copy_delete_and_the_catalog(owner_client):
    flow = make_flow("Welcome")
    page = get(owner_client, "/flow/flows", search="welc").json()
    assert [row["name"] for row in page["rows"]] == ["Welcome"]
    assert get(owner_client, "/flow/flows/detail", flow="Welcome").json()["id"] == str(
        flow.id
    )
    copied = post(owner_client, "/flow/flows/duplicate", {"id": str(flow.id)})
    assert (copied.status_code, copied.json()["name"]) == (201, "Copy of Welcome")
    assert post(owner_client, "/flow/flows/delete", {"id": str(flow.id)}).json() == {
        "id": str(flow.id)
    }
    assert get(owner_client, "/flow/flows/detail", id=str(flow.id)).status_code == 404
    catalog = get(owner_client, "/flow/catalog").json()
    assert "customer.customer.created" in {event["name"] for event in catalog["events"]}
    status = get(
        owner_client,
        "/flow/flows/status",
        event="customer.customer.created",
        operation="task.task.create",
    )
    # The copy listens to the same event with no permission yet: half built.
    assert status.json() == {"total": 0, "enabled": 0, "unfinished": 1}


@pytest.mark.django_db
def test_drafts_over_http(owner_client):
    proposed = post(
        owner_client,
        "/flow/drafts",
        {"name": "Call them", "definition": {"steps": [TASK_STEP]}, "notes": []},
    )
    assert proposed.status_code == 201, proposed.content
    other = make_draft()
    assert {row["id"] for row in get(owner_client, "/flow/drafts").json()["rows"]} == {
        proposed.json()["id"],
        str(other.id),
    }
    created = post(
        owner_client,
        "/flow/flows",
        {"name": "Call them", "draft_id": proposed.json()["id"]},
    )
    assert created.status_code == 201
    again = post(
        owner_client,
        "/flow/flows",
        {"name": "Call them", "draft_id": proposed.json()["id"]},
    )
    assert (again.status_code, again.json()["error"]["code"]) == (
        409,
        "flow.draft_decided",
    )
    assert Flow.objects.count() == 1
    assert (
        post(owner_client, "/flow/drafts/dismiss", {"id": str(other.id)}).json()[
            "status"
        ]
        == "dismissed"
    )


@pytest.mark.django_db
def test_the_sample_of_this_business_only(owner_client):
    OutboxEvent.objects.create(
        scope_kind="host",
        scope_key="b",
        name="sale.sale.completed",
        payload={"total": 1},
    )
    assert (
        get(owner_client, "/flow/events/sample", event="sale.sale.completed").json()[
            "found"
        ]
        is False
    )


@pytest.mark.django_db
def test_the_recipes_over_http_list_on_off_restore_and_repair(owner_client):
    gap = "appointment/customer_cancelled"
    listed = get(owner_client, "/flow/recipes")
    assert listed.status_code == 200
    assert gap in {recipe["ref"] for recipe in listed.json()["recipes"]}

    on = post(owner_client, "/flow/recipes/enable", {"recipe": gap})
    assert on.status_code == 200, on.json()
    assert (on.json()["created"], on.json()["flow"]["enabled"], on.json()["flow"]["grants"]) == (
        True,
        True,
        ["task.task.create"],
    )
    off = post(owner_client, "/flow/recipes/disable", {"recipe": gap})
    assert (off.status_code, off.json()["enabled"]) == (200, False)
    assert post(owner_client, "/flow/recipes/restore", {"recipe": gap}).status_code == 200
    assert post(owner_client, "/flow/recipes/repair", {"recipe": gap}).status_code == 200

    unknown = post(owner_client, "/flow/recipes/enable", {"recipe": "appointment/nothing"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "flow.recipe_not_found")
    malformed = post(owner_client, "/flow/recipes/enable", {"recipe": "nothing"})
    assert malformed.status_code == 422
    Flow.objects.filter(recipe=gap).update(deleted_at=Flow.objects.get(recipe=gap).created_at)
    never = post(owner_client, "/flow/recipes/disable", {"recipe": gap})
    assert (never.status_code, never.json()["error"]["code"]) == (404, "flow.recipe_not_on")


@pytest.mark.django_db
def test_a_manager_neither_reads_nor_turns_on_recipes(manager_client):
    for response in (
        get(manager_client, "/flow/recipes"),
        post(manager_client, "/flow/recipes/enable", {"recipe": "appointment/customer_cancelled"}),
    ):
        assert (response.status_code, response.json()["error"]["code"]) == (403, "permission_denied")
