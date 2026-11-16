"""A receipt whose caller does not say its currency is printed in the business's (flow business-currency, PRINTING-F07):
its country's, as ``base.business.get`` reads it from this hub's registry, never a euro fixed in the app nor a call to
erplora.com. The amounts' decimals are the server's (CLDR), never the browser's: a business in Japan prints yen without
cents, one in Tunisia dinars with three, one in Poland zlotys with two. An API key or the assistant that queues a
receipt without ``currency`` gets the same, and each hub its own."""

import json

import pytest
from live.context import OperationContext
from live.operations import get

from apps.printing.models import PrintJob
from apps.printing.tests.conftest import A, B, HUB_DB, RECEIPT, ctx_for, enqueue, run
from base import operations as base_operations
from base.models import Hub
from base.tenancy.context import use_hub

pytestmark = HUB_DB


def business_in(country: str, slug: str = A.key) -> None:
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


def test_each_hub_prints_in_its_own_business_s_currency(hub_b):
    business_in("JP", A.key)
    business_in("ES", B.key)
    assert printed(enqueue())["decimals"] == 0
    with use_hub(hub_b):
        in_b = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
        assert printed(in_b)["decimals"] == 2


@pytest.mark.parametrize(("country", "decimals"), [("JP", 0), ("TN", 3)])
def test_erploras_own_hub_prints_in_the_currency_of_its_issuer_s_country(settings, country, decimals, hub_b):
    # ERPlora's own hub (here business B's) has no business on erplora.com (no registry row, create_platform_hub): its
    # receipts keep the currency of its issuer's country, as its sales and invoices do (hub#286), never a 404 for want
    # of a business.
    settings.PLATFORM_HUB_SLUG = hub_b.slug
    settings.PLATFORM_ISSUER_COUNTRY = country
    with use_hub(hub_b):
        queued = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
        assert printed(queued)["decimals"] == decimals


def test_a_receipt_asks_base_for_the_business_s_currency(monkeypatch):
    # Printing asks the one question every app that charges asks (``base.operations.business_currency``, BASE-F50),
    # never a copy of its own that drifts in silence from it.
    business_in("ES")
    monkeypatch.setattr(base_operations, "business_currency", lambda scope: "KWD")
    assert printed(enqueue())["decimals"] == 3


def test_erploras_own_hub_takes_its_currency_from_base_business_get_too(settings, monkeypatch, hub_b):
    # ``base.business.get`` answers ERPlora's own hub (hub#329): printing asks it there as anywhere else, never a second
    # source of the same currency (here, an answer other than the one of ``PLATFORM_ISSUER_COUNTRY``).
    settings.PLATFORM_HUB_SLUG = hub_b.slug
    settings.PLATFORM_ISSUER_COUNTRY = "ES"
    business = get(base_operations.BUSINESS)
    answer = business.fn
    monkeypatch.setattr(business, "fn", lambda ctx, data: {**answer(ctx, data), "currency": "JPY"})
    with use_hub(hub_b):
        queued = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
        assert printed(queued)["decimals"] == 0
