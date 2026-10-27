"""The printing app's routes: each bound to its operation, named in the SPA's route map, and the main
flows over HTTP. Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees
the test's transaction."""

import json

import pytest
from django.conf import settings
from django.test import Client
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
    ("GET", "/printing/devices", "printing.device.list"),
    ("POST", "/printing/devices", "printing.device.register"),
    ("POST", "/printing/devices/update", "printing.device.update"),
    ("POST", "/printing/devices/retire", "printing.device.retire"),
    ("GET", "/printing/devices/coverage", "printing.device.coverage"),
}
#: The device's own id, as the SPA sends it in X-Device-Id: never in a URL (access logs keep URLs).
DEVICE = "3f1c9a52-6b0e-4c1d-9a77-0d2b5f8e4c11"


def get(client, path, host="a.localhost", device=None, **params):
    headers = {"HTTP_X_DEVICE_ID": device} if device else {}
    return client.get(f"/api{path}", params, HTTP_HOST=host, **headers)


def post(client, path, data, host="a.localhost", device=None):
    headers = {"HTTP_X_DEVICE_ID": device} if device else {}
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host, **headers)


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
    # The platform's own have no door: no route, no API key, no assistant — the scheduled prune (PRINTING-F20)
    # and the read of /ws/print's hello (printing.device.get: the device's id never travels in a URL).
    platform = {"printing.job.prune", "printing.device.get"}
    assert platform <= ops
    assert all(not registry[name].expose_api and not registry[name].ai for name in platform)
    ops -= platform
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


def session_of(make_user, username, role):
    client = Client()
    client.force_login(make_user(username, host="a", role=role))
    return client


@pytest.mark.django_db
def test_an_employee_takes_no_job_until_a_manager_sets_up_the_device(make_user):
    # FIX-PRINTING-JOBS-CLAIMED-BY-ANY-DEVICE: POST /api/printing/jobs/claim with an employee's session handed
    # the job of any printer it named.
    manager = session_of(make_user, "mar", "hub_manager")
    employee = session_of(make_user, "ana", "hub_employee")
    till = post(manager, "/printing/printers", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"}).json()
    post(manager, "/printing/jobs", {"document_type": "receipt", "document": RECEIPT})
    claim = {"printers": [till["id"]], "device": DEVICE}

    refused = post(employee, "/printing/jobs/claim", claim)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "printing.device_not_registered"
    assert get(manager, "/printing/jobs").json()["rows"][0]["status"] == "pending"
    assert post(employee, "/printing/devices", {"name": "Till", "printers": [till["id"]]}, device=DEVICE).status_code == 403

    set_up = post(manager, "/printing/devices", {"name": "Till", "printers": [till["id"]]}, device=DEVICE)
    assert set_up.status_code == 201
    assert (set_up.json()["name"], set_up.json()["this_device"]) == ("Till", True)
    taken = post(employee, "/printing/jobs/claim", claim).json()["job"]
    assert taken is not None
    done = post(employee, "/printing/jobs/complete", {"job_id": taken["id"], "device": DEVICE, "attempt": 1}).json()
    assert (done["confirmed"], done["job"]["device"]) == (True, "Till")

    mine = get(employee, "/printing/devices", device=DEVICE).json()
    theirs = get(employee, "/printing/devices", device="9b7d2e40-1a35-4f6c-8e21-5c0a7d3b9f02").json()
    assert [(row["name"], row["this_device"]) for row in mine["rows"]] == [("Till", True)]
    assert [row["this_device"] for row in theirs["rows"]] == [False]
    assert DEVICE not in json.dumps(mine)


@pytest.mark.django_db
def test_setting_up_a_device_needs_its_own_id(admin_client):
    till = post(admin_client, "/printing/printers", {"name": "Till", "kind": "system", "usage": "receipt"}).json()
    response = post(admin_client, "/printing/devices", {"name": "Till", "printers": [till["id"]]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "printing.device_required"


@pytest.mark.django_db
def test_a_manager_retires_a_device_and_it_takes_nothing_more(make_user):
    manager = session_of(make_user, "mar", "hub_manager")
    till = post(manager, "/printing/printers", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"}).json()
    device = post(manager, "/printing/devices", {"name": "Till", "printers": [till["id"]]}, device=DEVICE).json()
    renamed = post(manager, "/printing/devices/update", {"device_id": device["id"], "name": "Front till"})
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Front till")
    assert post(manager, "/printing/devices/retire", {"device_id": device["id"]}).status_code == 200
    assert get(manager, "/printing/devices").json()["rows"] == []
    refused = post(manager, "/printing/jobs/claim", {"printers": [till["id"]], "device": DEVICE})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "printing.device_not_registered")
