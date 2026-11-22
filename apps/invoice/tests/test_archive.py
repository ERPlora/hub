"""What Invoicing hands the fiscal archive of a business that left besides its rows (``fiscal_archive_documents`` on its
config): each invoice's A4 as a PDF, as it was handed over. Real VeriFactu records and real WeasyPrint, no mocks.

A PDF carries the second its fonts were cut, so the same page printed twice is not the same file: what each PDF is, is
told by the page it was printed from (``printer``).
"""

import dataclasses

import pytest
from django.apps import apps
from django.utils import translation
from live.context import system_context
from live.operations import UnknownOperation

from apps.invoice.services import issuing
from apps.invoice.models import Invoice
from apps.invoice.queries import fiscal_archive, render_document
from apps.invoice.tests.conftest import A, HUB_DB
from apps.invoice.tests.test_integration_verifactu import manual
from apps.verifactu import chain
from apps.verifactu.models import Record
from base import pdf

pytestmark = HUB_DB


@pytest.fixture
def printer(monkeypatch) -> dict[bytes, str]:
    """Each PDF WeasyPrint prints from now on, with the page it printed."""
    printed, render = {}, pdf.render_pdf

    def spied(html: str) -> bytes:
        made = render(html)
        printed[made] = html
        return made

    monkeypatch.setattr(pdf, "render_pdf", spied)
    return printed


def kept(language: str = "en") -> dict[str, tuple[str, bytes]]:
    """Each file Invoicing hands the archive, by its name: what it is called and its bytes."""
    ctx = dataclasses.replace(system_context(A), language=language)
    documents = apps.get_app_config("invoice").fiscal_archive_documents(ctx)
    return {name: (called, make()) for name, called, make in documents}


def page(invoice, *, language: str = "en", qr: bool = False) -> str:
    """``invoice``'s A4 in ``language``, with its record's QR or without it."""
    invoice = Invoice.objects.get(pk=invoice.id)
    code = None
    if qr:
        url = Record.objects.get(invoice_id=invoice.id).qr_url
        code = {"url": url, "svg": chain.qr_svg_data_uri(url)}
    with translation.override(language):
        return render_document(invoice, qr=code)


def pages(documents: dict[str, tuple[str, bytes]], printed: dict[bytes, str]) -> dict[str, tuple[str, str]]:
    return {name: (called, printed[content]) for name, (called, content) in documents.items()}


@pytest.mark.parametrize("aeat", ["accepted", "accepted_with_errors", "rejected", "pending"])
def test_each_invoice_is_kept_as_the_pdf_of_its_a4_with_the_qr_of_its_record_whatever_the_aeat_answered(
    issuer, printer, aeat
):
    invoice = manual()
    Record.objects.filter(invoice_id=invoice.id).update(status=aeat)

    documents = kept()

    assert pages(documents, printer) == {f"{invoice.id}.pdf": (invoice.number, page(invoice, qr=True))}
    assert documents[f"{invoice.id}.pdf"][1].startswith(b"%PDF-")
    assert page(invoice, qr=True) != page(invoice, qr=False)
    assert "QR tributario" in printer[documents[f"{invoice.id}.pdf"][1]]


def test_without_verifactu_an_invoice_is_kept_without_a_qr(issuer, printer, monkeypatch):
    def absent(name):
        raise UnknownOperation(name)

    with monkeypatch.context() as without:
        without.setattr(issuing, "get_operation", absent)
        invoice = manual()
    assert not Record.objects.exists()

    documents = kept()

    assert pages(documents, printer) == {f"{invoice.id}.pdf": (invoice.number, page(invoice))}
    assert "QR tributario" not in printer[documents[f"{invoice.id}.pdf"][1]]


def test_an_invoice_is_printed_in_its_own_language_else_in_the_business_one(issuer, printer):
    own, plain = manual(), manual()
    Invoice.objects.filter(pk=own.id).update(language="es")

    in_english, in_spanish = pages(kept("en"), printer), pages(kept("es"), printer)

    assert in_english[f"{own.id}.pdf"][1] == page(own, language="es", qr=True) != page(own, language="en", qr=True)
    assert in_english[f"{plain.id}.pdf"][1] == page(plain, language="en", qr=True)
    assert in_spanish[f"{plain.id}.pdf"][1] == page(plain, language="es", qr=True)


def test_every_invoice_is_kept_in_the_order_it_was_issued_read_a_page_at_a_time(issuer, monkeypatch):
    made = [manual() for _ in range(3)]
    monkeypatch.setattr(fiscal_archive, "PAGE_ROWS", 2)
    monkeypatch.setattr(pdf, "render_pdf", lambda html: b"%PDF-")

    documents = kept()

    assert list(documents) == [f"{invoice.id}.pdf" for invoice in made]
    assert [called for called, _ in documents.values()] == [invoice.number for invoice in made]


def test_nothing_is_printed_until_the_archive_asks_for_it(issuer, printer):
    manual()
    documents = list(apps.get_app_config("invoice").fiscal_archive_documents(system_context(A)))

    assert (len(documents), printer) == (1, {})
    documents[0][2]()
    assert len(printer) == 1
