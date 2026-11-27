"""The tips app's routes: each bound to its operation, and recording, adjusting and voiding a tip over HTTP.

Requests go to business A's host with Django's sync test client, which sees the test's transaction in A's own
database.
"""

import pytest
from django.test import Client
from live.ninja import ensure_api_parity
from live.operations import registry

from apps.flow.tests.test_api import get, post
from apps.sale.models import PaymentMethod
from apps.tip.api import router
from base.tests.routes import bound_routes, spa_routes
from config.api import api

from .conftest import CARD, HUB_DB, charge

ROUTES = {
    ("GET", "/tip/settings", "tip.settings.get"),
    ("POST", "/tip/settings", "tip.settings.update"),
    ("GET", "/tip/suggestions", "tip.suggestion.get"),
    ("GET", "/tip/tips", "tip.tip.list"),
    ("GET", "/tip/tips/detail", "tip.tip.get"),
    ("POST", "/tip/tips", "tip.tip.add"),
    ("POST", "/tip/tips/update", "tip.tip.update"),
    ("POST", "/tip/tips/void", "tip.tip.void"),
    ("GET", "/tip/report", "tip.report.get"),
    ("GET", "/tip/report/mine", "tip.report.mine"),
}
#: The platform's own reactions to Sales' events: no route.
REACTIONS = {"tip.sale.void", "tip.sale.refund"}


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("ana", role="hub_employee"))
    return client


@pytest.fixture
def admin_client(make_user):
    """Its own client: the employee's and the admin's sessions side by side."""
    admin = Client()
    admin.force_login(make_user("boss", role="hub_admin"))
    return admin


def test_every_route_is_bound_to_its_operation():
    assert bound_routes(router) == ROUTES


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_spas_route_map_names_every_tips_route():
    assert spa_routes("tip.") == ROUTES


def test_every_operation_but_the_reactions_has_a_route_and_is_open_to_api_keys():
    ops = {name for name in registry if name.startswith("tip.")}
    assert ops - REACTIONS == {operation for _m, _p, operation in ROUTES}
    assert all(registry[name].expose_api for name in ops - REACTIONS)
    assert not any(registry[name].expose_api for name in REACTIONS)


@HUB_DB
def test_a_tip_is_recorded_adjusted_and_voided_over_http(coffee, employee_client, admin_client):
    sale = charge(payments=CARD)
    added = post(employee_client, "/tip/tips", {"sale": sale.number, "method": "card", "amount": 150})
    assert added.status_code == 201, added.content
    tip = added.json()
    assert (tip["sale_number"], tip["amount"], tip["status"]) == (sale.number, 150, "active")
    listed = get(employee_client, "/tip/tips")
    assert [row["id"] for row in listed.json()["rows"]] == []  # an employee sees only their own: nobody served it
    adjusted = post(admin_client, "/tip/tips/update", {"id": tip["id"], "amount": 200, "reason": "typo"})
    assert adjusted.json()["amount"] == 200
    voided = post(admin_client, "/tip/tips/void", {"id": tip["id"], "reason": "wrong sale"})
    assert voided.json()["status"] == "voided"
    assert get(admin_client, "/tip/tips", status="voided").json()["total"] == 1


@HUB_DB
def test_a_refusal_is_the_error_envelope_and_a_bad_payload_a_422_by_field(coffee, employee_client):
    sale = charge(payments=CARD)
    refused = post(employee_client, "/tip/tips", {"sale": sale.number, "method": "cash", "amount": 150})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "tip.cash_register_closed"
    bad = post(employee_client, "/tip/tips", {"sale": sale.number, "method": "card", "amount": 0})
    assert bad.status_code == 422
    assert "amount" in bad.json()["error"]["fields"]


@HUB_DB
def test_the_employee_neither_adjusts_nor_changes_the_settings(employee_client):
    assert post(employee_client, "/tip/settings", {"enabled": True}).status_code == 403
    assert get(employee_client, "/tip/settings").json()["enabled"] is False


@HUB_DB
def test_the_suggestions_of_a_charge_are_read_over_http(employee_client):
    card = PaymentMethod.objects.get(type="card", is_active=True)
    read = get(employee_client, "/tip/suggestions", method_id=str(card.id), total=1000)
    assert read.status_code == 200, read.content
    assert (read.json()["enabled"], read.json()["suggestions"]) == (False, [])


@HUB_DB
def test_the_report_is_read_by_whoever_manages_and_my_tips_by_the_employee(coffee, employee_client, admin_client):
    added = post(admin_client, "/tip/tips", {"sale": charge(payments=CARD).number, "method": "card", "amount": 150})
    assert added.status_code == 201, added.content
    report = get(admin_client, "/tip/report", by="shift")
    assert report.status_code == 200, report.content
    assert (report.json()["by"], report.json()["totals"]["card"]) == ("shift", 150)
    assert get(employee_client, "/tip/report").status_code == 403
    unlinked = get(employee_client, "/tip/report/mine")
    assert (unlinked.status_code, unlinked.json()["error"]["code"]) == (409, "tip.member_not_linked")
