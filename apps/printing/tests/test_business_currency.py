"""A receipt whose caller does not say its currency is printed in the business's (flow business-currency, PRINTING-F07):
its country's, as ``base.business.get`` reads it from this hub's registry (APP-BASE-6), never a euro fixed in the app
nor a call to erplora.com. The amounts' decimals are the server's (CLDR), never the browser's: a business in Japan
prints yen without cents, one in Tunisia dinars with three, one in Poland zlotys with two (hub#2129). An API key or the
assistant that queues a receipt without ``currency`` gets the same, and each hub its own."""

import json

import pytest
from live.context import OperationContext, Scope

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import A, B, RECEIPT, ctx_for, enqueue, run
from base.models import Hub

pytestmark = pytest.mark.django_db


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def printed(out) -> dict:
    return PrintJob.objects.get(pk=out.job.id).document


@pytest.mark.parametrize(("country", "decimals"), [("JP", 0), ("TN", 3), ("KW", 3)])
def test_a_receipt_without_currency_takes_the_decimals_of_the_business_s_currency(country, decimals):
    business_in(country)
    assert printed(enqueue(document={**RECEIPT, "total": 1800}))["decimals"] == decimals


def test_a_receipt_without_currency_in_a_business_in_poland_prints_zlotys_and_no_euro_anywhere():
    business_in("PL")
    document = printed(enqueue())
    assert document["decimals"] == 2
    assert "EUR" not in json.dumps(document) and "€" not in json.dumps(document, ensure_ascii=False)


def test_the_caller_s_currency_still_wins_over_the_business_s():
    # Sales and Cash pass the currency the sale kept: a sale charged before the business moved keeps its own.
    business_in("JP")
    assert printed(enqueue(currency="EUR"))["decimals"] == 2


def test_an_api_key_with_only_the_print_permission_gets_the_business_s_currency():
    business_in("JP")
    key = OperationContext(scope=A, actor="key", permissions=frozenset({"printing.print"}), language="en")
    queued = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, key)
    assert printed(queued)["decimals"] == 0


def test_each_hub_prints_in_its_own_business_s_currency():
    business_in("JP", "a")
    business_in("ES", "b")
    assert printed(enqueue())["decimals"] == 0
    in_b = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
    assert printed(in_b)["decimals"] == 2


@pytest.mark.parametrize(("country", "decimals"), [("JP", 0), ("TN", 3)])
def test_erploras_own_hub_prints_in_the_currency_of_its_issuer_s_country(settings, country, decimals):
    # Phase 1's platform hub has no business on erplora.com (no registry row, create_platform_hub): its receipts keep
    # the currency of its issuer's country, as its sales and invoices do (hub#286), never a 404 for want of a business.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = country
    platform = ctx_for(scope=Scope("host", "erplora"))
    queued = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, platform)
    assert printed(queued)["decimals"] == decimals
