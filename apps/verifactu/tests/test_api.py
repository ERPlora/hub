"""The verifactu app's routes: each bound to its operation, the SPA's map in step, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's transaction.
Receiving the account's photo (``verifactu.config.sync``) has no route: only the system calls it.
"""

import json

import pytest
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.verifactu import certificates
from apps.verifactu.api import router
from apps.verifactu.models import OwnCertificate, Record
from apps.verifactu.tests.conftest import b64, make_p12, manual
from config.api import api

ROUTES = {
    ("GET", "/verifactu/config", "verifactu.config.get"),
    ("POST", "/verifactu/config", "verifactu.config.update"),
    ("POST", "/verifactu/config/go_live", "verifactu.config.go_live"),
    ("POST", "/verifactu/config/back_to_testing", "verifactu.config.back_to_testing"),
    ("POST", "/verifactu/certificate", "verifactu.certificate.upload"),
    ("POST", "/verifactu/certificate/remove", "verifactu.certificate.remove"),
    ("POST", "/verifactu/representation", "verifactu.representation.submit"),
    ("GET", "/verifactu/representation/model", "verifactu.representation.model"),
    ("GET", "/verifactu/records", "verifactu.record.list"),
    ("GET", "/verifactu/records/detail", "verifactu.record.get"),
    ("GET", "/verifactu/records/by_invoice", "verifactu.record.by_invoice"),
    ("POST", "/verifactu/records", "verifactu.record.create"),
    ("POST", "/verifactu/records/correct", "verifactu.record.correct"),
    ("POST", "/verifactu/records/cancel", "verifactu.record.cancel"),
    ("POST", "/verifactu/records/transmit", "verifactu.record.transmit"),
    ("POST", "/verifactu/records/reconcile", "verifactu.record.reconcile"),
    ("GET", "/verifactu/contingency", "verifactu.contingency.list"),
    ("POST", "/verifactu/contingency/process", "verifactu.contingency.process"),
    ("POST", "/verifactu/contingency/retry", "verifactu.contingency.retry"),
    ("GET", "/verifactu/events", "verifactu.event.list"),
    (
        "GET",
        "/verifactu/stats/compliance_summary",
        "verifactu.stats.compliance_summary",
    ),
    ("GET", "/verifactu/stats/records_by_status", "verifactu.stats.records_by_status"),
    (
        "GET",
        "/verifactu/stats/contingency_summary",
        "verifactu.stats.contingency_summary",
    ),
    ("GET", "/verifactu/stats/events_recent", "verifactu.stats.events_recent"),
    ("GET", "/verifactu/aeat_records", "verifactu.aeat_record.list"),
    ("POST", "/verifactu/aeat/query", "verifactu.aeat.query"),
    ("GET", "/verifactu/chain/status", "verifactu.chain.status"),
    ("POST", "/verifactu/chain/validate", "verifactu.chain.validate"),
    ("POST", "/verifactu/chain/recover_from_aeat", "verifactu.chain.recover_from_aeat"),
    ("POST", "/verifactu/chain/recover_manual", "verifactu.chain.recover_manual"),
    ("GET", "/verifactu/diagnostics/last", "verifactu.diagnostic.last"),
    ("POST", "/verifactu/diagnostics/run", "verifactu.diagnostic.run"),
    ("POST", "/verifactu/test_invoice", "verifactu.test_invoice.create"),
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data=None, host="a.localhost"):
    return client.post(
        f"/api{path}",
        json.dumps(data or {}),
        content_type="application/json",
        HTTP_HOST=host,
    )


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("bea", host="a", role="hub_employee"))
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


def test_the_spas_map_has_every_route():
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("verifactu.")
    }
    assert mine == ROUTES


@pytest.mark.django_db
def test_anonymous_gets_the_401_envelope(client):
    for response in (
        get(client, "/verifactu/records"),
        post(client, "/verifactu/contingency/process"),
    ):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_an_issued_invoice_is_recorded_and_read_over_http(admin_client, issuer):
    invoice = manual(series_code="TICKET")
    created = post(admin_client, "/verifactu/records", {"invoice_id": str(invoice.id)})
    assert created.status_code == 201
    assert created.json()["record"]["invoice_number"] == invoice.number
    listed = get(admin_client, "/verifactu/records", search=invoice.number)
    assert listed.status_code == 200
    assert [row["invoice_number"] for row in listed.json()["rows"]] == [invoice.number]
    detail = get(
        admin_client, "/verifactu/records/detail", invoice_number=invoice.number
    )
    assert detail.json()["status"] == "pending"


@pytest.mark.django_db
def test_without_a_gateway_sending_is_a_clear_409_never_accepted(
    admin_client, issuer, settings
):
    settings.VERIFACTU_GATEWAY_URL = ""
    invoice = manual(series_code="TICKET")
    post(admin_client, "/verifactu/records", {"invoice_id": str(invoice.id)})
    response = post(
        admin_client, "/verifactu/records/transmit", {"invoice_number": invoice.number}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verifactu.gateway_unavailable"
    assert Record.objects.get().status == "pending"


@pytest.mark.django_db
def test_the_employee_reads_but_does_not_send(employee_client, issuer):
    assert get(employee_client, "/verifactu/records").status_code == 200
    assert get(employee_client, "/verifactu/config").status_code == 200
    response = post(employee_client, "/verifactu/contingency/process")
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_bad_fingerprint_is_a_422_on_its_field(admin_client, issuer):
    response = post(
        admin_client,
        "/verifactu/chain/recover_manual",
        {"fingerprint": "XYZ", "invoice_number": "OLD-1", "issue_date": "2026-10-01"},
    )
    assert response.status_code == 422
    assert "fingerprint" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_another_hubs_records_are_not_seen_from_this_one(client, make_user, issuer):
    invoice = manual(series_code="TICKET")
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    post(client, "/verifactu/records", {"invoice_id": str(invoice.id)})
    # Phase 1 has no tenancy (one database): the host only scopes who may act. A user of another hub
    # has no permission here.
    other = make_user("eve", host="b", role="hub_admin")
    client.force_login(other)
    assert get(client, "/verifactu/records").status_code == 403


@pytest.fixture
def manager_client(client, make_user):
    client.force_login(make_user("mia", host="a", role="hub_manager"))
    return client


@pytest.mark.django_db
def test_the_certificate_is_uploaded_and_removed_over_http(
    admin_client, issuer, settings
):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    uploaded = post(
        admin_client,
        "/verifactu/certificate",
        {"p12_base64": b64(make_p12()), "password": "secret"},
    )
    assert uploaded.status_code == 201
    certificate = uploaded.json()["own_certificate"]
    assert (certificate["loaded"], certificate["holder_tax_id"]) == (True, "B12345674")
    assert "secret" not in uploaded.content.decode()
    assert "sealed" not in json.dumps(get(admin_client, "/verifactu/config").json())
    removed = post(admin_client, "/verifactu/certificate/remove")
    assert removed.status_code == 200
    assert removed.json()["own_certificate"]["loaded"] is False
    assert not OwnCertificate.objects.exists()


@pytest.mark.django_db
def test_a_certificate_of_another_holder_is_a_409_with_its_code(
    admin_client, issuer, settings
):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    response = post(
        admin_client,
        "/verifactu/certificate",
        {"p12_base64": b64(make_p12(org_id="VATES-B99999999")), "password": "secret"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "verifactu.certificate_holder_mismatch"


@pytest.mark.django_db
def test_without_configure_the_certificate_is_a_403(manager_client, issuer, settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    body = {"p12_base64": b64(make_p12()), "password": "secret"}
    assert post(manager_client, "/verifactu/certificate", body).status_code == 403
    assert post(manager_client, "/verifactu/certificate/remove").status_code == 403
    assert not OwnCertificate.objects.exists()


# The signed authorisation (VERIFACTU-F05, F06)

SAAS = "http://saas.internal:8001"
HUB_ID = "01920000-0000-7000-8000-000000000abc"


def pdf_b64(size: int = 0, text: bytes = b"signed") -> str:
    import base64

    return base64.b64encode(b"%PDF-1.7 " + text + b"0" * size).decode()


@pytest.fixture
def linked(issuer, settings):
    from live.context import system_context

    from apps.verifactu.tests.conftest import A, run

    settings.SAAS_INTERNAL_URL = SAAS
    run("verifactu.config.sync", {"version": 1, "hub_id": HUB_ID}, system_context(A))


@pytest.mark.django_db
def test_the_authorisation_travels_over_http_beyond_djangos_upload_ceiling(admin_client, linked):
    import httpx
    import respx

    # A scan of the signed model weighs more than Django's 2.5 MB for any other view.
    signed = pdf_b64(3 * 1024 * 1024)
    body = {
        "signer_tax_id": "12345678Z",
        "signer_name": "Ana Pérez",
        "signer_document_type": "dni",
        "signed_model_base64": signed,
        "id_copy_base64": pdf_b64(),
        "representation_proof_base64": pdf_b64(),
    }
    assert len(json.dumps(body)) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    with respx.mock:
        route = respx.post(f"{SAAS}/internal/hubs/{HUB_ID}/representation").mock(
            return_value=httpx.Response(201, json={"status": "submitted", "version": 1, "submitted_at": None})
        )
        response = post(admin_client, "/verifactu/representation", body)
    assert response.status_code == 201
    assert response.json()["representation"]["status"] == "submitted"
    assert json.loads(route.calls.last.request.content)["documents"]["signed_model"] == signed
    # Nothing of the documents comes back.
    assert signed[:64] not in response.content.decode()


@pytest.mark.django_db
def test_a_body_beyond_the_uploads_ceiling_is_a_413_before_it_is_read(admin_client, linked):
    response = admin_client.post(
        "/api/verifactu/representation",
        "{}",
        content_type="application/json",
        HTTP_HOST="a.localhost",
        CONTENT_LENGTH=str(33 * 1024 * 1024),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


@pytest.mark.django_db
def test_a_422_never_echoes_the_documents(admin_client, linked):
    signed = pdf_b64(text=b"Ana's signed model")
    response = post(
        admin_client,
        "/verifactu/representation",
        {"signer_document_type": "passport", "signed_model_base64": signed, "id_copy_base64": signed},
    )
    assert response.status_code == 422
    assert signed not in response.content.decode()


@pytest.mark.django_db
def test_the_model_is_served_as_a_pdf_to_download(admin_client, linked):
    import httpx
    import respx

    with respx.mock:
        respx.get(f"{SAAS}/internal/representation/model").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 Anexo I")
        )
        response = get(admin_client, "/verifactu/representation/model")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == (
        'attachment; filename="anexo-i-otorgamiento-representacion-erplora.pdf"'
    )
    assert response.content == b"%PDF-1.4 Anexo I"


@pytest.mark.django_db
def test_the_spas_client_asking_json_gets_the_operations_output(admin_client, linked):
    import base64

    import httpx
    import respx

    with respx.mock:
        respx.get(f"{SAAS}/internal/representation/model").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 Anexo I")
        )
        response = admin_client.get(
            "/api/verifactu/representation/model", HTTP_HOST="a.localhost", HTTP_ACCEPT="application/json"
        )
    assert response.status_code == 200
    model = response.json()
    assert (model["filename"], model["content_type"]) == (
        "anexo-i-otorgamiento-representacion-erplora.pdf",
        "application/pdf",
    )
    assert base64.b64decode(model["content_base64"]) == b"%PDF-1.4 Anexo I"


@pytest.mark.django_db
def test_the_model_without_the_saas_is_a_503_envelope(admin_client, linked):
    import httpx
    import respx

    with respx.mock:
        respx.get(f"{SAAS}/internal/representation/model").mock(side_effect=httpx.ConnectError("refused"))
        response = get(admin_client, "/verifactu/representation/model")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "verifactu.saas_unreachable"


@pytest.mark.django_db
def test_without_configure_the_authorisation_is_a_403(manager_client, linked):
    body = {"signer_document_type": "dni", "signed_model_base64": pdf_b64(), "id_copy_base64": pdf_b64()}
    assert post(manager_client, "/verifactu/representation", body).status_code == 403
    assert get(manager_client, "/verifactu/representation/model").status_code == 403


@pytest.mark.django_db
def test_a_422_never_echoes_the_password(admin_client, issuer):
    response = post(
        admin_client,
        "/verifactu/certificate",
        {"password": "hunter2-secret"},
    )
    assert response.status_code == 422
    assert "hunter2" not in response.content.decode()
