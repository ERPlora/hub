"""Prices and costs in the business's currency (flow business-currency): its country's, as ``base.business.get`` reads
it from this hub's registry (APP-BASE-6), never a euro fixed in the app. A business in Poland exports its catalog in
zlotys and imports it back (also with the «zł» it types), prints its labels in zlotys; one in Spain stays in euros; each
hub its own. The amounts keep the decimals of the currency (the yen has none)."""

import csv
import io

import pytest
from django.utils import translation
from live.context import Scope
from live.operations import get

from apps.inventory.models import Product
from apps.inventory.schemas import ProductFiltersIn, ProductImportIn
from apps.printing.models import PrintJob
from apps.tax.models import TaxCategory
from base.models import Hub

from .conftest import B, ctx_for

pytestmark = pytest.mark.django_db

TAX = "product.generic"


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def run(name, data, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), data if isinstance(data, op.input) else op.input.model_validate(data))


def exported(language: str, ctx=None) -> list[str]:
    """The price and cost cells of the one product of the export, in ``language``."""
    with translation.override(language):
        export = run("inventory.product.export", ProductFiltersIn(), ctx)
    rows = list(csv.reader(io.StringIO(export.content[1:]), delimiter=";" if language == "es" else ","))
    return rows[1][2:4]


def imported(*prices: str) -> list[int]:
    rows = [{"line": n + 2, "name": f"P{n}", "sku": f"P{n}", "price": price, "tax_category_key": TAX} for n, price in enumerate(prices)]
    report = run("inventory.product.bulk_create", ProductImportIn(rows=rows))
    assert report.failed == 0, [row.reason for row in report.rows]
    return [Product.objects.get(sku=f"P{n}").price for n in range(len(prices))]


@pytest.fixture
def gambas(db):
    tax = TaxCategory.objects.create(key="product.general", name="Product — general")
    return Product.objects.create(name="Gambas", sku="GAM", tax_category=tax, price=1250, cost=820)


def test_a_business_in_poland_exports_its_prices_in_zlotys(gambas):
    business_in("PL")
    assert exported("en") == ["PLN12.50", "PLN8.20"]
    assert exported("es") == ["12,50\xa0PLN", "8,20\xa0PLN"]


def test_a_business_in_spain_still_exports_in_euros(gambas):
    business_in("ES")
    assert exported("en") == ["€12.50", "€8.20"]


def test_a_business_in_poland_imports_its_own_export_and_the_zloty_it_types():
    business_in("PL")
    assert imported("PLN12.50", "12,50\xa0PLN", "12,50 zł", "zł 7", "3.40") == [1250, 1250, 1250, 700, 340]


def test_a_business_in_poland_does_not_take_a_euro_amount_for_a_zloty_one():
    business_in("PL")
    rows = [{"line": 2, "name": "Euro", "sku": "EUR1", "price": "12,50 €", "tax_category_key": TAX}]
    report = run("inventory.product.bulk_create", ProductImportIn(rows=rows))
    assert (report.created, report.failed) == (0, 1)


def test_each_hub_reads_amounts_in_its_own_business_s_currency():
    business_in("PL", "a")
    business_in("ES", "b")
    a = run("inventory.product.bulk_create", ProductImportIn(rows=[{"line": 2, "name": "A", "sku": "A1", "price": "PLN12.50", "tax_category_key": TAX}]))
    b = run(
        "inventory.product.bulk_create",
        ProductImportIn(rows=[{"line": 2, "name": "B", "sku": "B1", "price": "PLN12.50", "tax_category_key": TAX}]),
        ctx_for(scope=B),
    )
    assert (a.created, b.created, b.failed) == (1, 0, 1)


def test_the_label_takes_the_price_in_the_business_s_currency_with_its_decimals():
    # The yen has no cents: 1210 is ¥1,210 on the label, not 12.10.
    business_in("JP")
    run("printing.printer.create", {"name": "Labels", "kind": "network", "address": "192.168.1.50", "usage": "label"})
    created = run("inventory.product.create", {"name": "Shampoo", "sku": "SHA", "price": 1210, "tax_category_key": TAX})
    out = run("inventory.product.print_label", {"id": str(created.id)})
    document = PrintJob.objects.get(pk=out.job_id).document
    assert (document["price"], document["decimals"]) == (1210.0, 0)


#: ERPlora's own hub by its issuer's country: the price and cost its export writes and its import reads back (en,
#: ungrouped), and the label's price with its decimals (the yen has none).
ISSUER_COUNTRIES = {
    "PL": (["PLN12.50", "PLN8.20"], (12.5, 2)),
    "JP": (["¥1250", "¥820"], (1250.0, 0)),
}


@pytest.fixture(params=sorted(ISSUER_COUNTRIES))
def erplora(request, settings):
    """ERPlora's own hub with its issuer in the country of ``request.param``. Phase 1 gives it no business on
    erplora.com (no registry row, create_platform_hub): its catalog is in the currency of its issuer's country, as its
    sales, invoices and price lists are."""
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = request.param
    amounts, label = ISSUER_COUNTRIES[request.param]
    return ctx_for(scope=Scope("host", "erplora")), amounts, label


def test_erploras_own_hub_imports_prices_and_costs_in_the_currency_of_its_issuer_s_country(erplora):
    platform, (price, cost), _label = erplora
    row = {"line": 2, "name": "Gambas", "sku": "GAM", "price": price, "cost": cost, "tax_category_key": TAX}
    report = run("inventory.product.bulk_create", ProductImportIn(rows=[row]), platform)
    assert (report.created, report.failed) == (1, 0), [row.reason for row in report.rows]
    product = Product.objects.get(sku="GAM")
    assert (product.price, product.cost) == (1250, 820)


def test_erploras_own_hub_exports_in_the_currency_of_its_issuer_s_country(erplora, gambas):
    platform, amounts, _label = erplora
    assert exported("en", platform) == amounts


def test_erploras_own_hub_labels_in_the_currency_of_its_issuer_s_country(erplora):
    platform, _amounts, label = erplora
    run("printing.printer.create", {"name": "Labels", "kind": "network", "address": "192.168.1.50", "usage": "label"}, platform)
    created = run("inventory.product.create", {"name": "Gambas", "sku": "GAM", "price": 1250, "tax_category_key": TAX}, platform)
    out = run("inventory.product.print_label", {"id": str(created.id)}, platform)
    document = PrintJob.objects.get(pk=out.job_id).document
    assert (document["price"], document["decimals"]) == label
