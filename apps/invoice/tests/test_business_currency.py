"""An invoice issued by hand keeps the business's currency (flow business-currency): its country's, as
``base.business.get`` reads it from this hub's registry (APP-BASE-6), never a euro fixed in the app. A business in
Poland invoices in zlotys (Odoo, Business Central, Square… issue in the business's own currency); one in Spain, in
euros, as VeriFactu reads them. The document writes the amounts with the decimals of that currency. What is already
issued keeps the currency it was issued in."""

import pytest
from django.utils import translation
from live.context import Scope, system_context

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import A, B, ISSUER, ctx_for, run
from base import operations as base_operations
from base.models import Hub

pytestmark = pytest.mark.django_db

RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, 28004 Madrid",
}
LINES = [{"description": "Haircut course", "quantity": "2", "unit_price": 5000, "tax_rate": "21"}]


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def manual(ctx=None):
    return run("invoice.invoice.create", {"lines": LINES, **RECIPIENT}, ctx)


def document(invoice, ctx=None) -> str:
    with translation.override("en"):
        return run("invoice.invoice.document", {"invoice_id": str(invoice.id)}, ctx).html


def test_a_business_in_poland_invoices_in_zlotys(issuer):
    business_in("PL")
    invoice = manual()
    assert invoice.currency == "PLN"
    assert Invoice.objects.get(pk=invoice.id).currency == "PLN"
    html = document(invoice)
    assert "PLN\xa0121.00" in html and "PLN121" not in html and "€" not in html


def test_a_business_in_spain_still_invoices_in_euros(issuer):
    business_in("ES")
    invoice = manual()
    assert invoice.currency == "EUR"
    assert "€121.00" in document(invoice)


def test_the_document_writes_the_amounts_with_the_decimals_of_the_currency(issuer):
    # The yen has no cents: 12100 is ¥12,100, not ¥121.
    business_in("JP")
    invoice = manual()
    assert (invoice.currency, invoice.total_amount) == ("JPY", 12100)
    assert "¥12,100" in document(invoice)


def test_each_hub_invoices_in_its_own_business_s_currency(issuer):
    business_in("PL", "a")
    business_in("ES", "b")
    run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
    assert manual().currency == "PLN"
    assert manual(ctx_for(scope=B)).currency == "EUR"


def test_an_issued_invoice_keeps_its_currency_when_the_business_s_changes(issuer):
    business_in("ES")
    invoice = manual()
    business_in("PL")
    assert run("invoice.invoice.get", {"invoice_id": str(invoice.id)}).currency == "EUR"


@pytest.mark.parametrize(("country", "currency", "decimals"), [("HU", "HUF", 2), ("JP", "JPY", 0), ("ES", "EUR", 2)])
def test_an_invoice_says_the_decimals_of_its_currency_as_the_server_counts_them(issuer, country, currency, decimals):
    # The screens divide its minor units by them: the forint has two here (CLDR), though a browser's Intl says none.
    business_in(country)
    invoice = manual()
    assert (invoice.currency, invoice.currency_decimals) == (currency, decimals)
    listed = run("invoice.invoice.list", {}).rows
    assert {(row.currency, row.currency_decimals) for row in listed if row.id == invoice.id} == {(currency, decimals)}


@pytest.mark.parametrize(("country", "currency"), [("ES", "EUR"), ("PL", "PLN")])
def test_erploras_own_hub_invoices_in_the_currency_of_its_issuer_s_country(settings, country, currency):
    # Phase 1's platform hub has no business on erplora.com (no registry row, create_platform_hub): ERPlora's
    # invoices keep the currency of the country its issuer is set up in, Spain's, rather than failing.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = ctx_for(scope=Scope("host", "erplora"))
    run("invoice.issuer.update", ISSUER, platform)
    assert manual(system_context(platform.scope)).currency == currency


@pytest.mark.parametrize("platform_hub", [False, True], ids=["a-business-s-hub", "erploras-own-hub"])
def test_a_manual_invoice_asks_base_for_the_business_s_currency(settings, monkeypatch, platform_hub):
    # FIX-HUB-INVOICE-OWN-COPY-OF-BUSINESS-CURRENCY: invoicing asks the one question every app that charges asks
    # (``base.operations.business_currency``, BASE-F50), on ERPlora's own hub too, never a copy of its own that drifts
    # in silence from it (here, an answer other than the one of the business's or the issuer's country).
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = "ES"
    business_in("ES")
    scope = Scope("host", "erplora") if platform_hub else A
    ctx = ctx_for(scope=scope)
    run("invoice.issuer.update", ISSUER, ctx)
    asked = []
    monkeypatch.setattr(base_operations, "business_currency", lambda scope: asked.append(scope) or "KWD")
    invoice = manual(system_context(scope) if platform_hub else ctx)
    assert (invoice.currency, invoice.currency_decimals) == ("KWD", 3)
    assert asked == [scope]
