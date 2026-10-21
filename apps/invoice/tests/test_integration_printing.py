"""Invoicing asks Printing for an invoice's A4 page by name (INVOICE-F18 → PRINTING-F08): «Print / PDF» queues the
page for the system printer, with VeriFactu's QR when the invoice has its record. No mocks: Invoicing numbers the
invoice, VeriFactu seals it and Printing queues the page. Without Printing on, without a system printer that takes
the page, without permission to print or with a record that cannot be read, nothing is queued and the device
prints the screen's paper.
"""

import dataclasses

import pytest
from django.utils.html import escape
from live.operations import registry

from apps.invoice.tests.conftest import ctx_for, run
from apps.printing.models import PrintJob

pytestmark = pytest.mark.django_db

LINE = {"description": "Haircut course", "quantity": "2", "unit_price": 5000, "tax_rate": "21"}
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, 28004 Madrid",
}


@pytest.fixture
def invoice(issuer):
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT})


@pytest.fixture
def office(db):
    """The computer's printer, the one that takes an A4 page."""
    return run("printing.printer.create", {"name": "Office", "kind": "system", "usage": "receipt"})


@pytest.fixture
def till(db):
    """A receipt printer: it never takes an A4 page."""
    return run(
        "printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"}
    )


def print_invoice(invoice, ctx=None, **more):
    return run("invoice.invoice.print", {"invoice_id": str(invoice.id), **more}, ctx)


def jobs() -> list[PrintJob]:
    return list(PrintJob.objects.select_related("printer").order_by("created_at", "id"))


def test_the_page_goes_to_the_system_printer(invoice, office, till):
    out = print_invoice(invoice)
    (job,) = jobs()
    assert out.model_dump() == {"queued": True, "job_id": job.id, "printer": "Office"}
    assert (job.format, job.document_type, job.source_app, job.reference, job.printer.name, job.copies) == (
        "a4",
        "invoice",
        "invoice",
        invoice.number,
        "Office",
        1,
    )
    assert job.job_key.startswith(f"invoice-{invoice.id}-print-")
    assert invoice.number in job.html and "Talleres Pérez SL" in job.html


def test_the_page_carries_the_verifactu_qr(invoice, office):
    record = run("verifactu.record.by_invoice", {"invoice_id": str(invoice.id)}).record
    assert record is not None
    print_invoice(invoice)
    (job,) = jobs()
    assert record.qr_svg in job.html and escape(record.qr_url) in job.html


def test_a_reprint_is_marked_as_a_copy_in_the_readers_language(invoice, office):
    print_invoice(invoice, ctx_for(language="es"), duplicate=True)
    print_invoice(invoice)
    copy, original = jobs()
    assert "Copia" in copy.html and "Factura" in copy.html
    assert "Copy" not in original.html


def test_each_press_prints_one_page(invoice, office):
    first, again = print_invoice(invoice), print_invoice(invoice)
    assert first.job_id != again.job_id
    assert len(jobs()) == 2


def test_by_number_too(invoice, office):
    out = run("invoice.invoice.print", {"number": invoice.number})
    assert out.queued is True


def test_with_only_a_receipt_printer_the_screen_prints_it(invoice, till):
    """A receipt printer never takes an A4 page: the page would wait in the queue for ever."""
    assert print_invoice(invoice).model_dump() == {"queued": False, "job_id": None, "printer": None}
    assert not PrintJob.objects.exists()


def test_without_printing_in_the_business_the_screen_prints_it(invoice, office, monkeypatch):
    monkeypatch.delitem(registry, "printing.job.create")
    assert print_invoice(invoice).queued is False


def test_without_permission_to_print_the_screen_prints_it(invoice, office):
    admin = ctx_for()
    out = print_invoice(invoice, dataclasses.replace(admin, permissions=admin.permissions - {"printing.print"}))
    assert out.queued is False
    assert not PrintJob.objects.exists()


def test_a_record_that_cannot_be_read_keeps_the_page_from_the_queue(invoice, office):
    """Never a page without its QR (VERIFACTU-F19): the screen's paper goes instead."""
    admin = ctx_for()
    out = print_invoice(invoice, dataclasses.replace(admin, permissions=admin.permissions - {"verifactu.view_record"}))
    assert out.queued is False
    assert not PrintJob.objects.exists()
