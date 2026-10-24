"""BASE-G150, G100, G02, G04 and G48: the documentation of the business's API, shown or hidden in Settings › General.

Whoever runs the business turns «Show the API documentation» on (it comes off); then anyone of the business reads it:
the OpenAPI document of what the apps this business has publish (``expose_api``) — never the platform's own routes,
nor an app its plan does not give — with the bearer key that opens it, and only the schemas those routes use. Off, the
document is not given. It is built from the hub's own API (django-ninja), so it grows and shrinks with the apps.
"""

import json

import pytest
from live.models import OutboxEvent
from live.operations import registry as operation_registry

from base import entitlement
from base.models import Membership

pytestmark = pytest.mark.django_db

HOST = "a.localhost:8000"


def get(client, path, host=HOST):
    return client.get(f"/api{path}", HTTP_HOST=host)


def post(client, path, body=None, host=HOST):
    return client.post(f"/api{path}", json.dumps(body or {}), content_type="application/json", HTTP_HOST=host)


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def olga(make_user, client):
    user = make_user("saas:1", host="a", role=Membership.Role.OWNER, first_name="Olga")
    client.force_login(user)
    return user


@pytest.fixture
def eva(make_user):
    return make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva")


def turn_on(client):
    response = post(client, "/api-docs/settings/update", {"docs_enabled": True})
    assert response.status_code == 200, response.content
    return response.json()


class TestShowingIt:
    def test_it_comes_off_and_says_who_may_change_it(self, client, olga):
        response = get(client, "/api-docs/settings")
        assert response.status_code == 200, response.content
        assert response.json() == {"docs_enabled": False, "can_change": True}

    def test_off_the_document_is_not_given(self, client, olga):
        response = get(client, "/api-docs")
        assert response.status_code == 409
        assert code(response) == "base.api_docs_hidden"

    def test_who_runs_the_business_turns_it_on_and_off(self, client, olga):
        assert turn_on(client) == {"docs_enabled": True, "can_change": True}
        assert get(client, "/api-docs").status_code == 200
        off = post(client, "/api-docs/settings/update", {"docs_enabled": False})
        assert off.json()["docs_enabled"] is False
        assert code(get(client, "/api-docs")) == "base.api_docs_hidden"
        changed = OutboxEvent.objects.filter(name="base.api_doc.settings_changed").count()
        assert changed == 2

    def test_anyone_else_reads_it_and_cannot_change_it(self, client, olga, eva):
        turn_on(client)
        client.force_login(eva)
        assert get(client, "/api-docs/settings").json() == {"docs_enabled": True, "can_change": False}
        assert get(client, "/api-docs").status_code == 200
        refused = post(client, "/api-docs/settings/update", {"docs_enabled": False})
        assert refused.status_code == 403 and code(refused) == "permission_denied"

    def test_nobody_without_a_session(self, client, olga):
        turn_on(client)
        client.logout()
        assert get(client, "/api-docs").status_code == 401


class TestTheDocument:
    def document(self, client) -> dict:
        turn_on(client)
        response = get(client, "/api-docs")
        assert response.status_code == 200, response.content
        return response.json()

    def test_only_what_the_apps_publish_with_the_bearer_key_that_opens_it(self, client, olga):
        answer = self.document(client)
        document = answer["document"]
        operations = [op for path in document["paths"].values() for op in path.values()]
        assert operations, "some app publishes its API"
        published = {name for name, op in operation_registry.items() if op.expose_api}
        assert {op["operationId"] for op in operations} <= published
        assert not any(path.startswith(("/api/keys", "/api/approvals", "/api/api-docs", "/api/people")) for path in document["paths"])
        assert "/api/cart_checkout/carts" in document["paths"]
        assert document["components"]["securitySchemes"] == {"ApiKey": {"type": "http", "scheme": "bearer"}}
        assert document["security"] == [{"ApiKey": []}]
        assert all("security" not in op for op in operations)
        assert answer["keys_available"] is False
        assert {app["id"] for app in answer["apps"]} == {tag for op in operations for tag in op["tags"]}
        carts = document["paths"]["/api/cart_checkout/carts"]["get"]
        assert carts["description"] == operation_registry["cart_checkout.cart.list"].ai["description"]

    def test_only_the_schemas_its_routes_use(self, client, olga):
        document = self.document(client)["document"]
        text = json.dumps(document["paths"])
        schemas = document["components"].get("schemas", {})
        referenced = {name for name in schemas if f"#/components/schemas/{name}" in json.dumps(document)}
        assert set(schemas) == referenced
        assert "ApiKeyCreateIn" not in schemas and "ApprovalIn" not in schemas
        assert "#/components/schemas/" in text

    def test_an_app_the_plan_does_not_give_is_not_in_it(self, client, olga, monkeypatch):
        monkeypatch.setattr(entitlement, "blocked_apps", lambda scope: frozenset({"cart_checkout"}))
        document = self.document(client)["document"]
        assert not any(path.startswith("/api/cart_checkout/") for path in document["paths"])
        assert any(path.startswith("/api/tax/") for path in document["paths"])


API_DOC_ROUTES = {
    ("GET", "/api-docs", "base.api_doc.get"),
    ("GET", "/api-docs/settings", "base.api_doc.settings"),
    ("POST", "/api-docs/settings/update", "base.api_doc.settings_update"),
}


def test_the_switch_is_followed_live_and_the_document_is_asked_once():
    """The whole document is far bigger than a live result may be (``live.sse.MAX_RESULT_BYTES``): never live."""
    from live.live_registry import live_registry

    from base import events

    on = live_registry.subscribable
    assert on["base.api_doc.settings"] == [events.API_DOC_SETTINGS_CHANGED]
    assert "base.api_doc.get" not in on
