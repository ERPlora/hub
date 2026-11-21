"""A document issued at night in a business of another zone is dated on the business's clock: its day, the year of
its series and the «today» of numbering are the business's, not the deployment's (Madrid). The records are sealed in
VeriFactu's testing environment and never sent: nothing here leaves the machine."""

import datetime as dt
import socket

import pytest
from django.utils import timezone

from apps.invoice import services
from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, ISSUER, deliver, run
from apps.sale.models import Refund, Sale
from apps.tax.models import TaxCategory, TaxRule

pytestmark = HUB_DB

#: 23:30 of 2 November in Bogotá; 05:30 of the 3rd in Madrid.
BOGOTA_NIGHT = ("America/Bogota", dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC))
#: 23:30 of 31 December 2026 in the Canary Islands; 00:30 of 1 January 2027 in Madrid.
CANARY_NEW_YEARS_EVE = ("Atlantic/Canary", dt.datetime(2026, 12, 31, 23, 30, tzinfo=dt.UTC))
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, Madrid",
}


@pytest.fixture(autouse=True)
def nothing_leaves(monkeypatch):
    real = socket.socket.connect

    def connect(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"tried to connect to {address}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
def at(monkeypatch, in_business_a):
    """``at((zone, instant))``: business A in ``zone``, its clock stopped at ``instant``."""

    def move(moment):
        zone, instant = moment
        monkeypatch.setattr(timezone, "now", lambda: instant)
        monkeypatch.setattr(in_business_a, "timezone", zone)

    return move


def manual():
    lines = [{"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]
    return run("invoice.invoice.create", {"lines": lines, **RECIPIENT})


def test_the_day_of_a_document_is_the_business_s_at_its_midnight(at):
    at(("Atlantic/Canary", dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC)))
    assert services._today() == dt.date(2026, 11, 2)


def test_an_invoice_at_night_is_dated_on_the_business_s_day(issuer, at):
    at(BOGOTA_NIGHT)
    invoice = Invoice.objects.get(pk=manual().id)
    assert (invoice.issue_date, invoice.operation_date) == (dt.date(2026, 11, 2), None)


def test_an_invoice_on_new_year_s_eve_numbers_in_the_business_s_year(issuer, at):
    at(CANARY_NEW_YEARS_EVE)
    invoice = Invoice.objects.get(pk=manual().id)
    assert (invoice.issue_date, invoice.year, invoice.number) == (dt.date(2026, 12, 31), 2026, "FACT-2026-000001")


def test_a_refund_at_night_is_rectified_on_the_business_s_day(product, charge, at):
    at(BOGOTA_NIGHT)
    product("Shampoo", "SHA", 1210, "product.generic")
    # Without an issuer the documents wait, and the relay issues them once it is set up.
    sale = charge("zone-refund-0001")
    payment = Sale.objects.get(pk=sale.id).payments.get()
    allocations = [{"payment_id": str(payment.id), "amount": 500}]
    run("sale.sale.refund", {"sale_id": str(sale.id), "reason": "Broken", "allocations": allocations, "lines": []})
    # A refund is stamped by the real clock, which the test cannot stop: it is put back to the night it was made.
    Refund.objects.filter(sale_id=sale.id).update(created_at=BOGOTA_NIGHT[1])
    run("invoice.issuer.update", ISSUER)
    deliver("sale.sale.completed")
    rectification = Invoice.objects.get(pk=deliver("sale.sale.refunded").invoice.id)
    assert (rectification.issue_date, rectification.operation_date) == (dt.date(2026, 11, 2), dt.date(2026, 11, 2))


def test_a_void_at_night_is_rectified_on_the_business_s_day(issuer, product, charge, at):
    at(BOGOTA_NIGHT)
    product("Shampoo", "SHA", 1210, "product.generic")
    sale = charge("zone-void-0001")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    rectification = Invoice.objects.get(pk=deliver("sale.sale.voided").invoice.id)
    assert (rectification.issue_date, rectification.operation_date) == (dt.date(2026, 11, 2), dt.date(2026, 11, 2))


def test_the_form_proposes_the_rate_of_the_day_the_invoice_is_dated(issuer, at):
    category = TaxCategory.objects.get(key="product.generic")
    TaxRule.objects.filter(category=category).delete()
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="10", valid_to=dt.date(2026, 11, 2))
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="21", valid_from=dt.date(2026, 11, 3))
    at(BOGOTA_NIGHT)
    assert run("invoice.invoice.line_defaults").tax_rate == 10


def test_on_new_year_s_eve_numbering_speaks_of_the_business_s_year(issuer, at):
    at(CANARY_NEW_YEARS_EVE)
    run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2026})
    run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2027})
    assert run("invoice.series.peek_next", {"code": "SHOP"}).year == 2026
    assert run("invoice.numbering.status").fiscal_year == 2026


def test_on_new_year_s_eve_a_rectification_preview_is_of_the_business_s_day(issuer, at):
    at(CANARY_NEW_YEARS_EVE)
    original = manual()
    preview = run("invoice.invoice.rectification_preview", {"invoice_id": str(original.id), "reason": "Wrong price"})
    assert (preview.issue_date, preview.next_number) == (dt.date(2026, 12, 31), "RECT-2026-000001")
