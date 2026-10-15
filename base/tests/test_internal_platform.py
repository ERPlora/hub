"""The SaaS's door to ERPlora's platform hub (contract point 4; PLAN-SAAS §4): ``/internal/platform/invoices``, signed
as every ``/internal`` call (``base.internal``), as ``saas-next/hubs/hub_client.py`` calls it.

- ``GET …/health``: 200 ``{"status": "ok"}`` only when the platform hub has its issuer and VeriFactu answers; else 503
  ``{"status": "unconfigured", "detail"}`` (the SaaS's gate before charging live).
- ``POST …``: the body of ``platform_payload()`` → 201 ``{"status", "qr", "error": null}``; the same invoice again →
  200 with the same; a body out of contract → 422 with the error envelope.
- ``GET …/{id}``: its status, 404 ``invoice.platform_unknown`` when it never arrived; ``GET …/{id}/pdf``: its PDF.

Every view runs its operation as the system on ``PLATFORM_HUB_SLUG``.
"""

import copy
import json

import pytest

from apps.invoice.models import Invoice
from apps.invoice.tests.test_platform import BODY
from apps.invoice.tests.test_platform_invoices import PLATFORM, PLATFORM_ISSUER, system
from apps.invoice.tests.conftest import run
from base.tests.test_internal import code, signed

ROOT = "/internal/platform/invoices"
HOST = "hub.erplora.internal"


def post(client, body, **more):
    return signed(
        client, "post", ROOT, body, host="hubs.localhost", with_v2=True, **more
    )


def get(client, path, **more):
    """A GET as the SaaS signs it: an empty body, v1 and v2 (the path)."""
    return signed(client, "get", path, b"", host="hubs.localhost", with_v2=True, **more)


@pytest.fixture
def platform_hub(db, settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.ERPLORA_ENVIRONMENT = "pre"
    run("invoice.issuer.update", PLATFORM_ISSUER, system())


# Health


def test_health_is_ok_with_its_issuer(client, platform_hub):
    answer = get(client, f"{ROOT}/health")

    assert (answer.status_code, answer.json()) == (200, {"status": "ok"})


def test_health_without_an_issuer_is_503_and_says_why(client, db, settings):
    settings.PLATFORM_HUB_SLUG = PLATFORM.key

    answer = get(client, f"{ROOT}/health")

    assert answer.status_code == 503
    assert answer.json()["status"] == "unconfigured"
    assert "issuer" in answer.json()["detail"]


def test_health_unsigned_is_401(client, platform_hub):
    answer = client.get(f"{ROOT}/health", HTTP_HOST="hubs.localhost")

    assert (answer.status_code, code(answer)) == (401, "internal.unsigned")


# Issuing


def test_an_invoice_is_issued_with_its_qr(client, platform_hub):
    answer = post(client, BODY)

    assert answer.status_code == 201
    body = answer.json()
    assert set(body) == {"status", "qr", "error"}
    assert (body["status"], body["error"]) == ("issued", None)
    assert body["qr"].startswith("https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?")
    assert Invoice.objects.get().platform_ref is not None


def test_posting_it_again_answers_the_same_with_200(client, platform_hub):
    first = post(client, BODY)

    again = post(client, BODY)

    assert (again.status_code, again.json()) == (200, first.json())
    assert Invoice.objects.count() == 1


def test_it_answers_on_the_private_name_of_the_hub_too(client, platform_hub, settings):
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, HOST]

    answer = signed(client, "post", ROOT, BODY, host=HOST, with_v2=True)

    assert answer.status_code == 201


def test_a_body_out_of_contract_is_422_with_the_fields(client, platform_hub):
    body = copy.deepcopy(BODY)
    del body["lines"]

    answer = post(client, body)

    assert answer.status_code == 422
    error = answer.json()["error"]
    assert error["code"] == "internal.payload_invalid"
    assert "lines" in error["fields"]
    assert Invoice.objects.count() == 0


def test_a_body_that_is_no_json_object_is_422(client, platform_hub):
    answer = post(client, b"[1, 2]")

    assert (answer.status_code, code(answer)) == (422, "internal.payload_invalid")


def test_a_refusal_of_the_operation_keeps_its_code(client, platform_hub):
    body = copy.deepcopy(BODY)
    body["tax_treatment"] = "mystery"
    body["lines"][0]["tax_treatment"] = "mystery"

    answer = post(client, body)

    assert (answer.status_code, code(answer)) == (
        422,
        "invoice.platform_tax_treatment_unknown",
    )


def test_a_signature_over_another_body_is_401(client, platform_hub):
    raw = json.dumps(BODY).encode()
    answer = signed(
        client, "post", ROOT, raw, host="hubs.localhost", secret="not-the-secret"
    )

    assert (answer.status_code, code(answer)) == (401, "internal.unsigned")
    assert Invoice.objects.count() == 0


def test_issuing_is_a_post(client, platform_hub):
    assert get(client, ROOT).status_code == 405


# Status and PDF


def test_its_status(client, platform_hub):
    issued = post(client, BODY).json()

    answer = get(client, f"{ROOT}/{BODY['id']}")

    assert (answer.status_code, answer.json()) == (200, issued)


def test_the_status_of_an_invoice_that_never_arrived_is_404(client, platform_hub):
    answer = get(client, f"{ROOT}/{BODY['id']}")

    assert (answer.status_code, code(answer)) == (404, "invoice.platform_unknown")


def test_its_pdf(client, platform_hub):
    post(client, BODY)

    answer = get(client, f"{ROOT}/{BODY['id']}/pdf")

    assert answer.status_code == 200
    assert answer["Content-Type"] == "application/pdf"
    assert answer.content.startswith(b"%PDF-")
    assert 'filename="ERP-2026-00123.pdf"' in answer["Content-Disposition"]


def test_the_pdf_of_an_invoice_that_never_arrived_is_404(client, platform_hub):
    answer = get(client, f"{ROOT}/{BODY['id']}/pdf")

    assert (answer.status_code, code(answer)) == (404, "invoice.platform_unknown")
