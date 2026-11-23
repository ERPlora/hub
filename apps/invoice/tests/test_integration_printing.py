"""Invoicing asks Printing for an invoice's A4 page by name (INVOICE-F18 → PRINTING-F08): «Print / PDF» queues the
page for the system printer, with VeriFactu's QR when the invoice has its record. No mocks: Invoicing numbers the
invoice, VeriFactu seals it and Printing queues the page. Without Printing on, without a system printer that takes
the page, without permission to print or with a record that cannot be read, nothing is queued and the print fails
with why: the invoice's screen prints its own paper instead, and the assistant's receipt says it was not done.
"""

import dataclasses

import pytest
from django.utils import translation
from django.utils.html import escape
from live.errors import Conflict
from live.operations import registry

from apps.invoice.tests.conftest import HUB_DB, ctx_for, run
from apps.printing.models import PrintJob
from base.tests.test_services_assistant import answered, asked, call

pytestmark = HUB_DB

LINE = {"description": "Haircut course", "quantity": "2", "unit_price": 5000, "tax_rate": "21"}
YES = {"call_id": "c1", "accepted": True}
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
    assert out.model_dump() == {"job_id": job.id, "printer": "Office"}
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
    assert out.printer == "Office"


def not_printed(invoice, ctx=None) -> str:
    """The code ``invoice.invoice.print`` fails with; nothing is queued."""
    with pytest.raises(Conflict) as failed:
        print_invoice(invoice, ctx)
    assert not PrintJob.objects.exists()
    return failed.value.code


def test_with_only_a_receipt_printer_it_is_not_printed(invoice, till):
    """A receipt printer never takes an A4 page: the page would wait in the queue for ever."""
    assert not_printed(invoice) == "invoice.no_printer"


def test_without_printing_in_the_business_it_is_not_printed(invoice, office, monkeypatch):
    monkeypatch.delitem(registry, "printing.job.create")
    assert not_printed(invoice) == "invoice.no_printer"


def test_without_permission_to_print_it_is_not_printed(invoice, office):
    admin = ctx_for()
    assert not_printed(invoice, dataclasses.replace(admin, permissions=admin.permissions - {"printing.print"})) == (
        "invoice.no_printer"
    )


def test_a_record_that_cannot_be_read_keeps_the_page_from_the_queue(invoice, office):
    """Never a page without its QR (VERIFACTU-F19)."""
    admin = ctx_for()
    unreadable = dataclasses.replace(admin, permissions=admin.permissions - {"verifactu.view_record"})
    assert not_printed(invoice, unreadable) == "invoice.record_unreadable"


# ── From the assistant (BASE-F97, BASE-F99) ───────────────────────────────────────────────────────────────────────────
# hub#2293: with no printer for the page, the receipt under the answer said «Done: Print in Invoicing» and nothing was
# printed. A page no printer takes is not done: the receipt says why, and only a page a printer took says «Done».

PRINT_ASK = {"role": "user", "content": "imprímeme la factura"}


def printed_from_the_assistant(invoice, language: str, without: frozenset[str] = frozenset()) -> dict:
    """The receipt's row of the yes of a person ``without`` some permissions to the card that prints ``invoice``,
    asked in ``language``."""
    admin = ctx_for(language=language)
    person = dataclasses.replace(admin, permissions=admin.permissions - without)

    def turn_of(*calls, decision=None):
        data = {"messages": [PRINT_ASK, asked(*calls)], "pending": list(calls), "decision": decision}
        with translation.override(language):
            return run("base.assistant.turn", data, person).model_dump(mode="json")

    plan = answered(call("invoice.invoice.print", {"invoice_id": str(invoice.id)}), decision=YES, turn_of=turn_of)
    [row] = plan["executed"]
    return row


@pytest.mark.parametrize(
    ("language", "said"),
    [
        ("es", "Ninguna impresora del sistema recibe esta factura: ábrela para imprimirla o guardarla en PDF."),
        ("en", "No system printer takes this invoice: open it to print it or save it as PDF."),
    ],
)
def test_from_the_assistant_a_page_no_printer_takes_is_not_done_and_says_why(invoice, till, language, said):
    row = printed_from_the_assistant(invoice, language)
    assert (row["outcome"], row["code"], row["reason"]) == ("error", "invoice.no_printer", {language: said})
    assert not PrintJob.objects.exists()


def test_from_the_assistant_a_page_the_system_printer_took_is_done(invoice, office):
    row = printed_from_the_assistant(invoice, "es")
    assert (row["outcome"], row["code"], row["reason"]) == ("ok", "", {})
    assert [job.printer.name for job in jobs()] == ["Office"]


def test_from_the_assistant_a_record_that_cannot_be_read_says_the_page_never_goes_without_its_qr(invoice, office):
    row = printed_from_the_assistant(invoice, "es", without=frozenset({"verifactu.view_record"}))
    assert (row["outcome"], row["code"]) == ("error", "invoice.record_unreadable")
    assert row["reason"] == {"es": "No se pudo leer su registro de VeriFactu, y una factura nunca se imprime sin su QR."}
    assert not PrintJob.objects.exists()
