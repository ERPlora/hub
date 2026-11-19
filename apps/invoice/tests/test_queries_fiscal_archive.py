"""What Invoicing reads for a business that left (``apps.invoice.queries.fiscal_archive``): whether its database holds
invoices, and every one of them, a page at a time."""

from apps.invoice.queries import fiscal_archive
from apps.invoice.tests.conftest import HUB_DB
from apps.invoice.tests.test_integration_verifactu import manual

pytestmark = HUB_DB


def test_a_database_keeps_fiscal_documents_once_it_holds_an_invoice(issuer):
    assert fiscal_archive.keeps_fiscal_documents() is False

    manual()

    assert fiscal_archive.keeps_fiscal_documents() is True


def test_every_invoice_is_read_in_the_order_it_was_issued_a_page_at_a_time(issuer, monkeypatch):
    made = [manual() for _ in range(5)]
    monkeypatch.setattr(fiscal_archive, "PAGE_ROWS", 2)

    assert [invoice.id for invoice in fiscal_archive.invoices()] == [invoice.id for invoice in made]
