"""The code a ticket carries for its customer to ask for the full invoice (SALE-F29, INVOICE-F04): read with the sale
and printed under a QR of its own, which opens the business's public page for that ticket. Only a ticket whose
fiscal document Invoicing issued, or is issuing, carries it: a full invoice needs none, and without Invoicing there
is no page to open."""

import dataclasses

import pytest
from django.test import RequestFactory
from live.operations import registry

from apps.printing.models import PrintJob
from apps.sale.models.sales import Sale
from apps.sale.queries.receipt_codes import receipt_code, receipt_url
from apps.sale.tests.conftest import HUB_DB, A, ctx_for, run
from apps.sale.tests.test_integration_invoice import ISSUER, RECIPIENT

pytestmark = HUB_DB

CODE = "20261121-0001-K7Q2M9XD3FPA"
CLAIM_FIELDS = {"claim_qr_data", "claim_note", "claim_locator"}


@pytest.fixture
def coffee(product):
    product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def issuer(db):
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def till(db):
    return run(
        "printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"}
    )


def charge(key: str, ctx=None, **more):
    data = {"idempotency_key": key, "lines": [{"product": "COF"}], "payments": [{"method": "card"}], **more}
    return run("sale.sale.complete", data, ctx)


def documents() -> list[dict]:
    return [job.document for job in PrintJob.objects.order_by("created_at", "id")]


def test_the_code_opens_the_public_page_on_the_host_the_till_reached():
    request = RequestFactory().get("/", HTTP_HOST=f"{A.key}.localhost:8000")
    ctx = dataclasses.replace(ctx_for(), request=request)
    assert receipt_url(ctx, CODE) == f"http://{A.key}.localhost:8000/p/{A.key}/invoice/{CODE}"


def test_without_a_request_the_code_opens_the_business_own_host(settings):
    settings.HUB_BASE_DOMAIN = "erplora.com"
    assert receipt_url(ctx_for(), CODE) == f"https://{A.key}.erplora.com/p/{A.key}/invoice/{CODE}"


def test_a_ticket_reads_with_the_code_its_paper_prints(issuer, coffee):
    out = charge("claim-0001")
    code = receipt_code(Sale.objects.get(pk=out.id))
    assert out.invoice_type == "F2"
    assert out.receipt_code == code
    assert run("sale.sale.get", {"sale_id": str(out.id)}).receipt_code == code


def test_a_ticket_whose_fiscal_document_waits_already_carries_it(coffee):
    out = charge("claim-0002")
    assert out.invoice_status == "pending"
    assert out.receipt_code == receipt_code(Sale.objects.get(pk=out.id))


def test_a_full_invoice_carries_no_code(issuer, coffee):
    out = charge("claim-0003", document_type="invoice", **RECIPIENT)
    assert out.receipt_code is None


def test_without_invoicing_a_ticket_carries_no_code(coffee, monkeypatch):
    for name in [name for name in registry if name.startswith("invoice.")]:
        monkeypatch.delitem(registry, name)
    out = charge("claim-0004")
    assert out.invoice_status == "unavailable"
    assert out.receipt_code is None


def test_the_printed_ticket_and_its_copies_carry_the_code_under_its_qr(issuer, coffee, till):
    out = charge("claim-0005")
    run("sale.sale.print", {"sale_id": str(out.id)})
    url = receipt_url(ctx_for(), out.receipt_code)
    for document in documents():
        assert (document["claim_qr_data"], document["claim_locator"]) == (url, out.receipt_code)
        assert document["claim_note"]
        # The fiscal QR stays: one is to check the ticket at the AEAT, the other to ask for the invoice.
        assert document["qr_data"].startswith("https://") and document["qr_data"] != url
    assert len(documents()) == 2


def test_the_note_over_the_code_goes_in_the_seller_language(issuer, coffee, till):
    charge("claim-0006", ctx_for(language="en"))
    charge("claim-0007", ctx_for(language="es"))
    english, spanish = (document["claim_note"] for document in documents())
    assert english != spanish


def test_a_printed_full_invoice_carries_no_code(issuer, coffee, till):
    charge("claim-0008", document_type="invoice", **RECIPIENT)
    (document,) = documents()
    assert not CLAIM_FIELDS & set(document)
