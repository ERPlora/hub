"""The task app's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction.
"""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.task.api import router
from config.api import api

from .conftest import make_member, make_task

ROUTES = {
    ("GET", "/task/tasks", "task.task.list"),
    ("GET", "/task/tasks/mine", "task.task.mine"),
    ("GET", "/task/tasks/detail", "task.task.detail"),
    ("GET", "/task/tasks/subtasks", "task.task.subtasks"),
    ("POST", "/task/tasks", "task.task.create"),
    ("POST", "/task/tasks/update", "task.task.update"),
    ("POST", "/task/tasks/set_status", "task.task.set_status"),
    ("POST", "/task/tasks/complete", "task.task.complete"),
    ("POST", "/task/tasks/assign", "task.task.assign"),
    ("POST", "/task/tasks/delete", "task.task.delete"),
    ("GET", "/task/comments", "task.comment.list"),
    ("POST", "/task/comments", "task.comment.add"),
    ("GET", "/task/projects", "task.project.list"),
    ("GET", "/task/projects/detail", "task.project.detail"),
    ("POST", "/task/projects", "task.project.create"),
    ("POST", "/task/projects/update", "task.project.update"),
    ("POST", "/task/projects/delete", "task.project.delete"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost", **headers):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host, **headers
    )


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin", first_name="Marta"))
    return client


@pytest.fixture
def employee(make_user):
    user = make_user("bea", host="a", role="hub_employee", first_name="Bea", last_name="Ruiz")
    return user, make_member("Bea", "Ruiz", user=user)


@pytest.fixture
def employee_client(client, employee):
    client.force_login(employee[0])
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
def test_the_openapi_describes_the_task_routes(client):
    paths = client.get("/api/openapi.json", HTTP_HOST="a.localhost").json()["paths"]
    served = {
        (method.upper(), path.removeprefix("/api"), op["operationId"])
        for path, methods in paths.items()
        for method, op in methods.items()
        if op["operationId"].startswith("task.")
    }
    assert served == ROUTES


def test_the_spas_route_map_names_every_task_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("task.")
    }
    assert mine == ROUTES


# Authentication and permissions


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/task/tasks"), post(client, "/task/tasks", {"title": "t"})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_employee_works_their_own_tasks_and_does_not_manage(employee_client, employee):
    created = post(employee_client, "/task/tasks", {"title": "Restock shampoo", "to_me": True})
    assert created.status_code == 422  # «to_me» belongs to assign, not to create
    created = post(employee_client, "/task/tasks", {"title": "Restock shampoo"})
    assert created.status_code == 201, created.content
    task_id = created.json()["id"]
    assigned = post(employee_client, "/task/tasks/assign", {"id": task_id, "to_me": True})
    assert assigned.json()["assignee_name"] == "Bea Ruiz"
    assert post(employee_client, "/task/tasks/complete", {"id": task_id}).json()["status"] == "done"
    assert [row["title"] for row in get(employee_client, "/task/tasks").json()["rows"]] == ["Restock shampoo"]
    for path, body in (
        ("/task/tasks/delete", {"id": task_id}),
        ("/task/projects", {"code": "c", "name": "n"}),
    ):
        response = post(employee_client, path, body)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.django_db
def test_someone_elses_task_is_a_404_for_an_employee(employee_client):
    other = make_task("Ana's", assigned_to=make_member())
    response = post(employee_client, "/task/tasks/complete", {"id": str(other.id)})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "That task does not exist in this business."


# Flows over HTTP


@pytest.mark.django_db
def test_a_task_from_creation_to_its_comments(admin_client):
    make_member("Ana", "López")
    project = post(admin_client, "/task/projects", {"code": "opening", "name": "Opening", "color": "#AA3300"})
    assert project.status_code == 201
    created = post(
        admin_client,
        "/task/tasks",
        {"title": "Buy towels", "project": "opening", "assignee": "Ana", "due_date": "2026-10-20", "priority": "high"},
    )
    assert created.status_code == 201
    task = created.json()
    assert (task["project_name"], task["assignee_name"], task["due_date"]) == ("Opening", "Ana López", "2026-10-20")
    sub = post(admin_client, "/task/tasks", {"title": "White ones", "parent_id": task["id"]})
    assert sub.json()["project_name"] == "Opening"
    comment = post(admin_client, "/task/comments", {"task": task["number"], "text": "Ordered"})
    assert comment.status_code == 201 and comment.json()["author_name"] == "Marta"
    assert get(admin_client, "/task/tasks/detail", task="Buy towels").json()["comment_count"] == 1
    assert [row["title"] for row in get(admin_client, "/task/tasks/subtasks", id=task["id"]).json()["rows"]] == [
        "White ones"
    ]
    assert get(admin_client, "/task/comments", task_id=task["id"]).json()["total"] == 1
    status = post(admin_client, "/task/tasks/set_status", {"id": task["id"], "status": "blocked"})
    assert status.json()["status"] == "blocked"
    updated = post(admin_client, "/task/tasks/update", {"id": task["id"], "due_date": None})
    assert updated.json()["due_date"] is None
    assert get(admin_client, "/task/projects/detail", project="opening").json()["task_count"] == 2
    assert post(admin_client, "/task/projects/update", {"project": "opening", "is_active": False}).json()["is_active"] is False
    assert post(admin_client, "/task/tasks/delete", {"id": task["id"]}).status_code == 200
    assert post(admin_client, "/task/projects/delete", {"project": "opening"}).status_code == 200
    assert get(admin_client, "/task/tasks").json()["total"] == 0


@pytest.mark.django_db
def test_my_tasks_over_http(employee_client, employee):
    make_task("Mine", assigned_to=employee[1])
    assert [row["title"] for row in get(employee_client, "/task/tasks/mine").json()["rows"]] == ["Mine"]


# Errors


@pytest.mark.django_db
def test_an_unknown_filter_or_field_is_a_422(admin_client):
    # The live stream and the assistant validate the input with the schema, which forbids extras; a GET
    # of ninja drops unknown query keys before the schema sees them (a gap of packages/live, reported).
    from pydantic import ValidationError

    from apps.task.schemas import TaskListIn

    with pytest.raises(ValidationError):
        TaskListIn.model_validate({"colour": "red"})
    response = post(admin_client, "/task/tasks", {"title": "t", "author": "someone else"})
    assert response.status_code == 422
    assert "author" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_a_refusal_names_its_field(admin_client):
    response = post(admin_client, "/task/tasks", {"title": "t", "project": "nowhere"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"project": "That project does not exist in this business."}
    response = post(admin_client, "/task/tasks", {"title": "  "})
    assert response.status_code == 422 and "title" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_completing_a_closed_task_is_a_409(admin_client):
    task = make_task(status="cancelled")
    response = post(admin_client, "/task/tasks/complete", {"id": str(task.id)})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "task.task_already_closed"


@pytest.mark.django_db
def test_an_error_message_follows_the_language_of_the_request(admin_client):
    response = post(
        admin_client, "/task/tasks/complete", {"task": "ghost"}, HTTP_ACCEPT_LANGUAGE="es"
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Esa tarea no existe en este negocio."
