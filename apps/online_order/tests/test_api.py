"""Online orders' routes: each bound to its operation, with the permissions of whoever calls.

Requests go to business A's host (``HOST``, scope ``A``) with Django's sync test client, which sees the test's
transaction.
"""

import pytest
from live.ninja import ensure_api_parity

from apps.flow.tests.test_api import get, post
from apps.online_order.api import router
from apps.online_order.models import TableCode
from base.tests.routes import bound_routes, published_routes, spa_routes
from config.api import api

from .conftest import HOST, HUB_DB, A, make_table

ROUTES = {
    ("GET", "/online_order/qr_codes", "online_order.qr_code.list"),
    ("POST", "/online_order/qr_codes/regenerate", "online_order.qr_code.regenerate"),
}


@pytest.fixture
def manager_client(client, make_user):
    client.force_login(make_user("boss", host=A.key, role="hub_manager"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("ana", host=A.key, role="hub_employee"))
    return client


def test_each_route_bound_to_its_operation():
    assert bound_routes(router) == ROUTES


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


@HUB_DB  # the host gate reads the registry's row of the hub (base.middleware)
def test_openapi_matches_the_spa_route_map(client):
    assert published_routes(client, "online_order.", HOST) == spa_routes("online_order.") == ROUTES


@HUB_DB
def test_anonymous_gets_the_401_envelope(client):
    for response in (get(client, "/online_order/qr_codes"), post(client, "/online_order/qr_codes/regenerate", {})):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@HUB_DB
def test_a_manager_regenerates_a_table_s_code_and_reads_it(manager_client):
    table = make_table("4")
    made = post(manager_client, "/online_order/qr_codes/regenerate", {"table": "4"})
    assert made.status_code == 200
    assert made.json()["table_id"] == str(table.id)
    listed = get(manager_client, "/online_order/qr_codes")
    assert listed.status_code == 200
    [row] = listed.json()["rows"]
    assert (row["code"], row["url"]) == (made.json()["code"], made.json()["url"])
    assert row["url"].startswith(f"http://{HOST}/p/{A.key}/order/")


@HUB_DB
def test_an_employee_neither_reads_nor_regenerates(employee_client):
    table = make_table("4")
    responses = (
        get(employee_client, "/online_order/qr_codes"),
        post(employee_client, "/online_order/qr_codes/regenerate", {"id": str(table.id)}),
    )
    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"
    assert TableCode.objects.count() == 0


@HUB_DB
def test_a_table_not_said_is_a_422(manager_client):
    response = post(manager_client, "/online_order/qr_codes/regenerate", {})
    assert response.status_code == 422
