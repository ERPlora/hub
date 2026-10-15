"""Invoicing and VeriFactu together, no mocks of VeriFactu (its WORKBOOK, «Contrato con Facturación»): every
document asks for its registration record by name (``verifactu.record.create``) inside its own transaction,
so the record is sealed in the same commit; VeriFactu absent → the document is issued «unavailable»; a
refusal → «pending», and VeriFactu's own reaction to ``invoice.invoice.issued`` seals it later; a programming
error is never swallowed (the document is not issued).
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext
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
