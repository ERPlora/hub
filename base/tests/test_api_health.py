"""The Home's health row's route (``base/api_home_health.py``): ``GET /api/home/health`` calls ``base.health.list``."""

from base import api_home_health
from base.tenancy.tests.business import HOST, HUB_DB, A, in_business_a
from base.tests.routes import bound_routes, published_routes, spa_routes

__all__ = ["in_business_a"]

#: base/tests/test_api.py's map of the SPA's routes takes these too.
HEALTH_ROUTES = {("GET", "/home/health", "base.health.list")}


def test_its_one_route_calls_the_operation_and_the_spa_knows_it():
    assert bound_routes(api_home_health.router) == HEALTH_ROUTES
    assert spa_routes("base.health.") == HEALTH_ROUTES


@HUB_DB
def test_the_hub_s_api_publishes_it(client):
    assert published_routes(client, "base.health.", HOST) == HEALTH_ROUTES


@HUB_DB
def test_a_stranger_is_refused_and_an_employee_is_told_nothing(client, make_user):
    assert client.get("/api/home/health", HTTP_HOST=HOST).status_code in (401, 403)

    client.force_login(make_user("ana", host=A.key, role="hub_employee"))
    response = client.get("/api/home/health", HTTP_HOST=HOST)

    assert (response.status_code, response.json()) == (200, {"items": []})


@HUB_DB
def test_the_owner_is_told_whether_the_receipt_printer_answers_in_their_language(client, make_user):
    client.force_login(make_user("boss", host=A.key, role="hub_owner"))

    response = client.get("/api/home/health", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

    assert response.status_code == 200, response.content
    printing = [item for item in response.json()["items"] if item["app"] == "printing"]
    assert printing == [
        {
            "key": "printing",
            "app": "printing",
            "state": "not_configured",
            "title": "Impresora sin configurar",
            "action": "Configurar la impresión",
            "route": "/printing/printers",
        }
    ]
