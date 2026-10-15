"""VeriFactu with Invoicing and Sales, no mocks (VERIFACTU-F13, F14, F19): real charges, voids and refunds made
with the till's own operations, and the documents Invoicing issues for them.

**The same transaction** (WORKBOOK «Contrato con Facturación»): Invoicing asks for the record by name inside its
own emission, with the issuer's session and in a savepoint: the document and its record commit together or
neither does. A refusal of VeriFactu would fail again, so it undoes the whole emission; only a transient database
error leaves the document «pending» for the reaction to Invoicing's notice (``test_concurrency``).

Cases from the current module's ``desglose.hub``, ``recipient_snapshot`` and ``rectification_block``.
"""

import pytest
from django.db import transaction
from live.errors import Conflict

from apps.invoice.models import Invoice
from apps.tax.models import TaxRule
from apps.verifactu import xsd
from apps.verifactu.models import Chain, Record
from apps.verifactu.tests.conftest import RECIPIENT, ctx_for, deliver, manual, run

pytestmark = pytest.mark.django_db

CUT = [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]


@pytest.fixture
def shelf(issuer):
    for name, sku, price, category in (
        ("Shampoo", "SHA", 1210, "product.generic"),
        ("Menu", "MNU", 1100, "restaurant.food"),
        ("Physio", "PHY", 4000, "service.health"),
    ):
        run(
            "inventory.product.create",
            {"name": name, "sku": sku, "price": price, "tax_category_key": category},
        )


def charge(key: str, lines: list[dict], **more):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": lines,
            "payments": [{"method": "card"}],
            **more,
        },
    )


def record_of(invoice_id) -> Record:
    """The record sealed by the document's own emission; its later notice adds nothing."""
    record = Record.objects.get(invoice_id=invoice_id, correction=False, record_type="alta")
    assert deliver("invoice.invoice.issued").already is True
    return record


def valid(record: Record) -> None:
    xsd.validate_record(
        record.xml, obligado_name=record.issuer_name, obligado_nif=record.issuer_nif
    )


# The same transaction


def test_the_document_and_its_record_commit_together(issuer):
    with transaction.atomic():
        invoice = run(
            "invoice.invoice.create",
            {"series_code": "TICKET", "lines": CUT},
            ctx_for("hub_employee"),
        )
    assert invoice.verifactu_status == "sealed"
    record = Record.objects.get(invoice_id=invoice.id)
    assert (record.invoice_number, record.sequence, record.created_by) == (
        invoice.number,
        1,
        "tester",
    )


def test_when_the_emission_rolls_back_no_record_nor_number_is_left(issuer):
    with pytest.raises(RuntimeError), transaction.atomic():
        run(
            "invoice.invoice.create",
            {"series_code": "TICKET", "lines": CUT},
            ctx_for("hub_employee"),
        )
        assert Record.objects.exists()
        raise RuntimeError("the sale failed after its document")
    assert not Invoice.objects.exists()
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


def test_a_refusal_of_verifactu_undoes_the_whole_emission(issuer, at_emission):
    # VeriFactu refuses this F1 at the emission (its customer's tax id is gone): it would refuse again, so the
    # document is not issued and its series keeps the number.
    at_emission(lambda row: {"customer_tax_id": ""})
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.invoice.create",
            {**RECIPIENT, "lines": [{**CUT[0], "description": "Course"}]},
            ctx_for("hub_employee"),
        )
    assert refused.value.code == "verifactu.recipient_required"
    assert not Invoice.objects.exists()
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


# What the till charges, voids and refunds


def test_a_charged_ticket_is_registered_with_the_sales_money_to_the_cent(shelf):
    sale = charge(
        "verifactu-0001",
        [{"product": "SHA", "quantity": "2"}, {"product": "MNU"}, {"product": "PHY"}],
    )
    ticket = Invoice.objects.get(source_sale_id=sale.id, source_type="sale")
    record = record_of(ticket.id)
    assert (record.invoice_type, record.total_amount, record.tax_amount) == (
        "F2",
        ticket.total_amount,
        ticket.tax_amount,
    )
    assert record.total_amount == sale.total
    assert record.tax_breakdown == ticket.tax_breakdown
    # One breakdown line per real fiscal key: 21 %, 10 % and the exempt health service.
    assert record.xml.count("<sum1:DetalleDesglose>") == 3
    assert "<sum1:OperacionExenta>" in record.xml
    valid(record)


def test_voiding_a_charged_sale_registers_its_r5_as_an_alta_not_an_anulacion(shelf):
    sale = charge("verifactu-0002", [{"product": "SHA"}])
    ticket = Invoice.objects.get(source_sale_id=sale.id, source_type="sale")
    record_of(ticket.id)
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    rect = Invoice.objects.get(source_sale_id=sale.id, source_type="void")
    record = record_of(rect.id)
    assert (record.record_type, record.invoice_type, record.rectification_kind) == (
        "alta",
        "R5",
        "I",
    )
    assert record.rectified == [
        {
            "issuer_nif": ticket.issuer_tax_id,
            "number": ticket.number,
            "issue_date": ticket.issue_date.isoformat(),
        }
    ]
    assert record.total_amount == -ticket.total_amount
    assert not Record.objects.filter(record_type="anulacion").exists()
    valid(record)


def test_a_partial_refund_registers_its_rectification_by_differences(shelf):
    sale = charge("verifactu-0003", [{"product": "SHA"}, {"product": "MNU"}])
    record_of(Invoice.objects.get(source_sale_id=sale.id, source_type="sale").id)
    from apps.sale.models import Sale

    payment = Sale.objects.get(pk=sale.id).payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Late",
            "allocations": [{"payment_id": str(payment.id), "amount": 1000}],
        },
    )
    rect = Invoice.objects.get(source_refund__sale_id=sale.id)
    record = record_of(rect.id)
    assert (record.invoice_type, record.total_amount, record.description) == (
        "R5",
        -1000,
        "Late",
    )
    assert record.xml.count("<sum1:DetalleDesglose>") == 2
    valid(record)


def test_the_equivalence_surcharge_travels_inside_its_vat_line(shelf):
    root = TaxRule.objects.get(
        category__key="product.generic", country_code="ES", parent__isnull=True
    )
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "tax_category_key": "product.generic",
            "rate_pct": "5.2",
            "tax_type": "surcharge",
            "parent_id": str(root.id),
            "component_label": "Recargo de equivalencia",
        },
    )
    sale = charge("verifactu-0004", [{"product": "SHA"}])
    record = record_of(
        Invoice.objects.get(source_sale_id=sale.id, source_type="sale").id
    )
    assert (
        "<sum1:TipoRecargoEquivalencia>5.20</sum1:TipoRecargoEquivalencia>"
        in record.xml
    )
    assert "<sum1:TipoImpositivo>5.20</sum1:TipoImpositivo>" not in record.xml
    valid(record)


def test_a_ticket_replaced_by_a_full_invoice_is_declared_in_its_f3(shelf):
    sale = charge("verifactu-0005", [{"product": "SHA"}])
    ticket = Invoice.objects.get(source_sale_id=sale.id, source_type="sale")
    record_of(ticket.id)
    full = run(
        "invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}
    ).invoice
    record = record_of(full.id)
    assert (record.invoice_type, record.recipient_tax_id) == (
        "F3",
        RECIPIENT["customer_tax_id"],
    )
    assert f"<sum1:NumSerieFactura>{ticket.number}</sum1:NumSerieFactura>" in record.xml
    valid(record)


def test_a_full_invoice_to_an_eu_business_names_its_vat_number(issuer):
    invoice = manual(
        customer_name="Muster GmbH",
        customer_tax_id="DE129273398",
        customer_country="DE",
        customer_id_type="02",
        customer_address="Hauptstraße 1, Berlin",
    )
    record = record_of(invoice.id)
    assert (
        "<sum1:IDOtro><sum1:CodigoPais>DE</sum1:CodigoPais><sum1:IDType>02</sum1:IDType><sum1:ID>DE129273398</sum1:ID></sum1:IDOtro>"
        in record.xml
    )
    valid(record)


def test_the_documents_ask_for_their_record_and_qr(shelf):
    sale = charge("verifactu-0006", [{"product": "SHA"}])
    ticket = Invoice.objects.get(source_sale_id=sale.id, source_type="sale")
    record = record_of(ticket.id)
    found = run(
        "verifactu.record.by_invoice",
        {"invoice_id": str(ticket.id)},
        ctx_for("hub_employee"),
    )
    assert (found.record.id, found.record.qr_url) == (record.id, record.qr_url)
    assert "prewww2.aeat.es" in found.record.qr_url
