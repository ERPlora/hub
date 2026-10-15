"""The printing app's routes: each bound to its operation, named in the SPA's route map, and the main
flows over HTTP. Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees
the test's transaction."""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.printing.api import router
from apps.printing.tests.conftest import RECEIPT
from config.api import api

ROUTES = {
    ("GET", "/printing/settings", "printing.settings.get"),
    ("POST", "/printing/settings", "printing.settings.update"),
    ("GET", "/printing/printers", "printing.printer.list"),
    ("GET", "/printing/printers/detail", "printing.printer.get"),
    ("GET", "/printing/printers/status", "printing.printer.status"),
    ("POST", "/printing/printers", "printing.printer.create"),
    ("POST", "/printing/printers/update", "printing.printer.update"),
    ("POST", "/printing/printers/test", "printing.printer.test"),
    ("GET", "/printing/jobs", "printing.job.list"),
    ("GET", "/printing/jobs/summary", "printing.job.summary"),
    ("POST", "/printing/jobs", "printing.job.create"),
    ("POST", "/printing/jobs/claim", "printing.job.claim"),
    ("POST", "/printing/jobs/complete", "printing.job.complete"),
    ("POST", "/printing/jobs/fail", "printing.job.fail"),
    ("POST", "/printing/jobs/retry", "printing.job.retry"),
    ("POST", "/printing/jobs/cancel", "printing.job.cancel"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host)


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


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_every_operation_has_a_route_and_is_open_to_api_keys():
    from live.operations import registry

    ops = {name for name in registry if name.startswith("printing.")}
    assert ops == {operation for _m, _p, operation in ROUTES}
    assert all(registry[name].expose_api for name in ops)
    assert all(registry[name].ai and registry[name].ai["description"] for name in ops)


def test_the_spas_route_map_names_every_printing_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op.startswith("printing.")}
    assert mine == ROUTES


@pytest.mark.django_db
def test_the_owner_adds_a_printer_tests_it_and_a_device_prints_it(admin_client):
    created = post(admin_client, "/printing/printers", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"})
    assert created.status_code == 201
    till = created.json()
    assert till["target"] == "network:192.168.1.50:9100"
    test = post(admin_client, "/printing/printers/test", {"printer": "Till"})
    assert test.status_code == 201
    assert test.json()["kind"] == "test_page"
    taken = post(admin_client, "/printing/jobs/claim", {"printers": [till["id"]], "device": "Till 1"}).json()["job"]
    assert (taken["kind"], taken["target"], taken["document"]) == ("test_page", "network:192.168.1.50:9100", {"locale": "en"})
    done = post(admin_client, "/printing/jobs/complete", {"job_id": taken["id"], "device": "Till 1", "attempt": 1}).json()
    assert (done["confirmed"], done["job"]["status"]) == (True, "done")
    assert get(admin_client, "/printing/printers/status", printer="Till").json()["printer"]["last_printed_at"]
    assert get(admin_client, "/printing/jobs", status="done").json()["total"] == 1


@pytest.mark.django_db
def test_the_employee_prints_and_reads_but_does_not_set_up_or_cancel(employee_client):
    queued = post(employee_client, "/printing/jobs", {"document_type": "receipt", "document": RECEIPT, "job_key": "sale-1"})
    assert queued.status_code == 201
    assert queued.json()["job"]["reference"] == "T-000123"
    again = post(employee_client, "/printing/jobs", {"document_type": "receipt", "document": RECEIPT, "job_key": "sale-1"})
    assert again.json()["duplicate"] is True
    assert get(employee_client, "/printing/jobs/summary").json()["pending"] == 1
    assert get(employee_client, "/printing/settings").json()["receipt_copies"] == 1
    refused = post(employee_client, "/printing/printers", {"name": "Till", "kind": "system", "usage": "receipt"})
    assert refused.status_code == 403
    refused = post(employee_client, "/printing/jobs/cancel", {"reference": "T-000123"})
    assert refused.status_code == 403


@pytest.mark.django_db
def test_a_wrong_address_is_a_422_at_its_field(admin_client):
    response = post(admin_client, "/printing/printers", {"name": "Till", "kind": "bluetooth", "address": "nope", "usage": "receipt"})
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"address": "Type the MAC as AA:BB:CC:DD:EE:FF."}


@pytest.mark.django_db
def test_a_job_that_cannot_be_cancelled_is_a_409(admin_client):
    post(admin_client, "/printing/jobs", {"document_type": "receipt", "document": RECEIPT})
    job = get(admin_client, "/printing/jobs").json()["rows"][0]
    assert post(admin_client, "/printing/jobs/cancel", {"job_id": job["id"], "reason": "test"}).status_code == 200
    response = post(admin_client, "/printing/jobs/cancel", {"job_id": job["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "printing.job_not_cancellable"


@pytest.mark.django_db
def test_an_unknown_document_type_is_a_422(admin_client):
    response = post(admin_client, "/printing/jobs", {"document_type": "kitchn", "document": {}})
    assert response.status_code == 422
    assert "document_type" in response.json()["error"]["fields"]
