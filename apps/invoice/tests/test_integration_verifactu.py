"""Invoicing and VeriFactu together, no mocks of VeriFactu (its WORKBOOK, «Contrato con Facturación»): every
document asks for its registration record by name (``verifactu.record.create``) inside its own transaction,
so the record is sealed in the same commit; VeriFactu absent → the document is issued «unavailable»; a
refusal → «pending», and VeriFactu's own reaction to ``invoice.invoice.issued`` seals it later; a programming
error is never swallowed (the document is not issued).
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.context import OperationContext, system_context
from django.db import OperationalError
from live.errors import Conflict, LiveMisuse, PermissionDenied
from live.operations import UnknownOperation
from live.models import OutboxEvent

from apps.invoice import services
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import A, ctx_for, run
from apps.verifactu import events as verifactu_events
from apps.verifactu.models import Record

pytestmark = pytest.mark.django_db

RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}
LINE = {"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}


def manual(ctx=None):
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT}, ctx)


def test_issuing_seals_its_registration_record_in_the_same_commit(issuer):
    invoice = manual()
    assert invoice.verifactu_status == "sealed"
    record = Record.objects.get(invoice_id=invoice.id)
    assert (record.record_type, record.invoice_number, record.status) == (
        Record.Type.ALTA,
        invoice.number,
        Record.Status.PENDING,
    )
    # VeriFactu's reaction to the notice (the backup) answers the same record.
    event = OutboxEvent.objects.filter(name="invoice.invoice.issued").latest(
        "created_at"
    )
    again = verifactu_events.react(A, event.name, event.payload)
    assert (again.already, Record.objects.filter(invoice_id=invoice.id).count()) == (
        True,
        1,
    )
    # A read of the document says nothing of it: only the answer of the operation that issued it.
    assert (
        run("invoice.invoice.get", {"invoice_id": str(invoice.id)}).verifactu_status
        is None
    )


@pytest.mark.parametrize(
    ("region", "tax", "code"),
    [(None, "vat", "01"), ("ES-CN", "igic", "03"), ("ES-CE", "ipsi", "02"), ("ES-ML", "ipsi", "02")],
)
def test_a_typed_rate_is_declared_with_the_tax_of_the_business_territory(issuer, region, tax, code):
    # TAX-F11 (pm#629 VF-17): a line without a tax category takes the tax family of the business's territory;
    # a Canary business's typed 7 % is IGIC (Impuesto 03), never VAT (01). Nothing is sent to the AEAT here.
    run("tax.settings.update", {"region_code": region})
    invoice = run("invoice.invoice.create", {"lines": [{**LINE, "tax_rate": "7"}], **RECIPIENT})
    assert [(entry.tax, entry.rate, entry.quota) for entry in invoice.tax_breakdown] == [
        (tax, Decimal("7.00"), 70)
    ]
    record = Record.objects.get(invoice_id=invoice.id)
    assert [entry["tax"] for entry in record.tax_breakdown] == [tax]
    assert re.findall(r"<sum1:Impuesto>(\d+)</sum1:Impuesto>", record.xml) == [code]


def test_without_verifactu_the_document_is_issued_unavailable(issuer, monkeypatch):
    def absent(name):
        raise UnknownOperation(name)

    monkeypatch.setattr(services, "get_operation", absent)
    invoice = manual()
    assert invoice.verifactu_status == "unavailable"
    assert not Record.objects.exists()


def test_a_document_verifactu_cannot_declare_is_not_issued_and_spends_no_number(issuer):
    # VeriFactu's refusals are deterministic (they would fail again): issuing without its record would print a
    # document that is never declared (RD 1007/2023: the record is made when the document is). So nothing is
    # issued and the series gives its number back. Here, a ticket of before the operation's description
    # (DescripcionOperacion, mandatory) is replaced by its full invoice, which copies that empty description.
    ticket = run(
        "invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE]}
    )
    Invoice.objects.filter(pk=ticket.id).update(description="")
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT})
    assert refused.value.code == "verifactu.impossible_record"
    assert not Invoice.objects.filter(invoice_type="F3").exists()
    assert not InvoiceSeries.objects.filter(code="FACT", current_number__gt=0).exists()


def test_a_refusal_for_who_issues_is_not_swallowed_either(issuer):
    # Someone who issues invoices but may not seal records (403 of VeriFactu): nothing is issued.
    issuing_only = OperationContext(
        scope=A,
        actor="clerk",
        permissions=frozenset(
            p for p in ctx_for().permissions if not p.startswith("verifactu.")
        ),
        language="en",
    )
    with pytest.raises(PermissionDenied):
        manual(issuing_only)
    assert not Invoice.objects.exists()
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


def test_in_production_without_a_way_to_the_aeat_nothing_is_issued(issuer, settings):
    # Working-rules §15: in production nothing is charged that can never reach the AEAT. VeriFactu refuses to
    # seal with its route's own code; the document is undone and the series gives its number back.
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    system = system_context(A)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system,
    )
    run("verifactu.config.go_live")
    run("verifactu.config.sync", {"version": 2, "live_paid": False}, system)
    with pytest.raises(Conflict) as refused:
        manual()
    assert refused.value.code == "verifactu.live_option_unpaid"
    assert str(refused.value).startswith("Nothing was issued")
    assert "the live option of VeriFactu is not in your plan" in str(refused.value)
    assert not Invoice.objects.exists()
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()
    assert not Record.objects.exists()
    with translation.override("es"), pytest.raises(Conflict) as en_espanol:
        manual(ctx_for(language="es"))
    assert str(en_espanol.value).startswith("No se ha emitido nada")
    assert "la opción en vivo de VeriFactu no está en tu plan" in str(en_espanol.value)


def test_a_transient_database_error_leaves_it_pending_for_its_reaction(
    issuer, monkeypatch
):
    # Only what may work on a retry goes on without the record: VeriFactu's reaction seals it later.
    class Interrupted:
        class input:  # noqa: N801 - the shape of an operation: its input schema and its call
            @staticmethod
            def model_validate(data):
                return data

        def __call__(self, ctx, data):
            raise OperationalError("the connection dropped")

    monkeypatch.setattr(services, "get_operation", lambda name: Interrupted())
    invoice = manual()
    assert invoice.verifactu_status == "pending"
    assert not Record.objects.exists()
    monkeypatch.undo()
    event = OutboxEvent.objects.filter(name="invoice.invoice.issued").latest(
        "created_at"
    )
    sealed = verifactu_events.react(A, event.name, event.payload)
    assert (sealed.already, sealed.record.invoice_number) == (False, invoice.number)


def test_a_document_of_a_sale_answers_its_verifactu_status(issuer, product, charge):
    product()
    charge("inv-vf-0001")
    ticket = Invoice.objects.get(source_type="sale")
    assert Record.objects.filter(invoice=ticket).exists()
    answer = run(
        "invoice.invoice.create_from_sale", {"sale_id": str(ticket.source_sale_id)}
    )
    assert (answer.already, answer.verifactu_status) == (True, None)


def test_a_programming_error_of_verifactu_undoes_the_issue(issuer, monkeypatch):
    class Broken:
        class input:  # noqa: N801 - the shape of an operation: its input schema and its call
            @staticmethod
            def model_validate(data):
                return data

        def __call__(self, ctx, data):
            raise LiveMisuse("broken on purpose")

    monkeypatch.setattr(services, "get_operation", lambda name: Broken())
    with pytest.raises(LiveMisuse):
        manual()
    assert not Invoice.objects.exists()
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


def test_the_invoice_has_every_field_verifactu_reads():
    # VeriFactu's WORKBOOK, «Contrato con Facturación», point 2: what it reads of the row.
    workbook = Path(apps.get_app_config("verifactu").path, "WORKBOOK.md").read_text(
        encoding="utf-8"
    )
    section = workbook.split("### Contrato con Facturación", 1)[1]
    point = section.split("\n2. ", 1)[1].split("\n3. ", 1)[0]
    names = set(re.findall(r"`([a-z_]+)`", point)) - {"invoice"}
    assert names >= {
        "number",
        "tax_breakdown",
        "description",
        "rectifies",
        "substitutes",
    }
    for name in sorted(names):
        Invoice._meta.get_field(name)
