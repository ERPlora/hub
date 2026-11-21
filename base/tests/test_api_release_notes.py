"""The release notes' route (``base/api_release_notes.py``): ``GET /api/system/release-notes`` calls
``base.release_note.list``, mounted on the hub's API."""

import pytest

from base import api_release_notes, release_notes
from base.tenancy.tests.business import HOST, HUB_DB, A, in_business_a
from base.tests.routes import bound_routes, published_routes, spa_routes
from base.tests.test_queries_release_notes import NOTES

__all__ = ["in_business_a"]

#: base/tests/test_api.py's map of the SPA's routes takes these too.
RELEASE_NOTE_ROUTES = {("GET", "/system/release-notes", "base.release_note.list")}


@pytest.fixture(autouse=True)
def shipped(monkeypatch):
    monkeypatch.setattr(release_notes, "shipped", lambda: NOTES)


def test_its_one_route_calls_the_operation_and_the_spa_knows_it():
    assert bound_routes(api_release_notes.router) == RELEASE_NOTE_ROUTES
    assert spa_routes("base.release_note.") == RELEASE_NOTE_ROUTES


@HUB_DB
def test_the_hub_s_api_publishes_it(client):
    assert published_routes(client, "base.release_note.", HOST) == RELEASE_NOTE_ROUTES


@HUB_DB
def test_a_stranger_reads_nothing_and_an_employee_reads_them_in_their_language(client, make_user):
    assert client.get("/api/system/release-notes", HTTP_HOST=HOST).status_code in (401, 403)

    client.force_login(make_user("ana", host=A.key, role="hub_employee"))
    response = client.get("/api/system/release-notes?limit=2", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

    assert response.status_code == 200, response.content
    assert [(item["id"], item["title"]) for item in response.json()["items"]] == [
        ("2026-11-19-allergens", "título de allergens"),
        ("2026-11-12-tables", "título de tables"),
    ]
    assert response.json()["total"] == 3
