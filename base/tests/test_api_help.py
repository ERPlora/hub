"""The help window's route (``base/api_help.py``): ``GET /api/help`` calls ``base.help.get``, mounted on the hub's API."""

import pytest
from live.meta import module_configs

from base import api_help
from base.tenancy.tests.business import HOST, HUB_DB, A, in_business_a
from base.tests.help_workbooks import ready_tables
from base.tests.routes import bound_routes, published_routes, spa_routes

__all__ = ["in_business_a"]

#: base/tests/test_api.py's map of the SPA's routes takes these too.
HELP_ROUTES = {("GET", "/help", "base.help.get")}


def test_its_one_route_calls_the_operation_and_the_spa_knows_it():
    assert bound_routes(api_help.router) == HELP_ROUTES
    assert spa_routes("base.help.") == HELP_ROUTES


@HUB_DB
def test_the_hub_s_api_publishes_it(client):
    assert published_routes(client, "base.help.", HOST) == HELP_ROUTES


@HUB_DB
def test_a_stranger_gets_no_help_and_an_employee_gets_a_module_s_in_their_language(client, make_user, monkeypatch, tmp_path):
    ready_tables(monkeypatch, tmp_path)
    assert client.get("/api/help?app=table", HTTP_HOST=HOST).status_code in (401, 403)

    client.force_login(make_user("ana", host=A.key, role="hub_employee"))
    response = client.get("/api/help?app=table", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

    assert response.status_code == 200, response.content
    assert {key: response.json()[key] for key in ("app", "name", "language")} == {"app": "table", "name": "Mesas", "language": "es"}
    assert response.json()["screens"][0]["title"] == "Plano de sala"


@HUB_DB
@pytest.mark.parametrize("app", ["table", "nope"])
def test_a_module_without_its_help_ready_answers_404_with_its_code(client, make_user, monkeypatch, app):
    for config in module_configs():
        monkeypatch.setattr(config, "help", None)
    client.force_login(make_user("ana", host=A.key, role="hub_employee"))
    response = client.get(f"/api/help?app={app}", HTTP_HOST=HOST)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "base.help_missing")
