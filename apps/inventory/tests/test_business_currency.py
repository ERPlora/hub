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
from base import operations as base_operations
from base.models import Hub

from .conftest import B, ctx_for, ctx_with

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
    assert exported("en") == ["PLN\xa012.50", "PLN\xa08.20"]
    assert exported("es") == ["12,50\xa0PLN", "8,20\xa0PLN"]


def test_a_business_in_spain_still_exports_in_euros(gambas):
    business_in("ES")
    assert exported("en") == ["€12.50", "€8.20"]


def test_a_business_in_poland_imports_its_own_export_and_the_zloty_it_types():
    business_in("PL")
    # Its export (code off the figure), the glued one an older export wrote, and what a person types.
    assert imported("PLN\xa012.50", "PLN12.50", "12,50\xa0PLN", "12,50 zł", "zł 7", "3.40") == [1250, 1250, 1250, 1250, 700, 340]


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
    "PL": (["PLN\xa012.50", "PLN\xa08.20"], (12.5, 2)),
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


# One way to the currency (FIX-HUB-INVENTORY-OWN-COPY-OF-BUSINESS-CURRENCY): inventory asks the one question every app
# that charges asks (``base.operations.business_currency``, BASE-F50), never a copy of its own that drifts in silence.


def export_with(ctx) -> list[str]:
    """The price and cost the export (INVENTORY-F11) writes for a product of 1250 and 820 minor units."""
    tax = TaxCategory.objects.create(key="product.general", name="Product — general")
    Product.objects.create(name="Gambas", sku="GAM", tax_category=tax, price=1250, cost=820)
    return exported("en", ctx)


def import_with(ctx) -> tuple:
    """What the import (INVENTORY-F09) makes of a price typed «¥1250»: created, failed and the price it stored."""
    row = {"line": 2, "name": "Gambas", "sku": "GAM", "price": "¥1250", "tax_category_key": TAX}
    report = run("inventory.product.bulk_create", ProductImportIn(rows=[row]), ctx)
    return report.created, report.failed, Product.objects.filter(sku="GAM").values_list("price", flat=True).first()


def label_with(ctx) -> tuple:
    """The price and decimals the label (INVENTORY-F25) of a product of 1250 minor units carries."""
    admin = ctx_for(scope=ctx.scope)
    run("printing.printer.create", {"name": "Labels", "kind": "network", "address": "192.168.1.50", "usage": "label"}, admin)
    created = run("inventory.product.create", {"name": "Gambas", "sku": "GAM", "price": 1250, "tax_category_key": TAX}, admin)
    out = run("inventory.product.print_label", {"id": str(created.id)}, ctx)
    document = PrintJob.objects.get(pk=out.job_id).document
    return document["price"], document["decimals"]


#: The three operations that put an amount in the business's currency, what each gives in yen (no cents), and the only
#: permissions an API key needs to call it (the label also queues in Printing).
IN_YEN = {
    "export": (export_with, ["¥1250", "¥820"], ("inventory.export_product",)),
    "import": (import_with, (1, 0, 1250), ("inventory.import_product",)),
    "label": (label_with, (1250.0, 0), ("inventory.view_product", "printing.print")),
}


@pytest.mark.parametrize("caller", sorted(IN_YEN))
def test_each_amount_takes_the_currency_base_answers(caller, monkeypatch):
    business_in("ES")
    monkeypatch.setattr(base_operations, "business_currency", lambda scope: "JPY")
    through, in_yen, _permissions = IN_YEN[caller]
    assert through(ctx_for()) == in_yen


@pytest.mark.parametrize("caller", sorted(IN_YEN))
def test_erploras_own_hub_takes_its_currency_from_base_business_get_too(caller, settings, monkeypatch):
    # ``base.business.get`` answers ERPlora's own hub (hub#329): inventory asks it there as anywhere else, never a second
    # source of the same currency (here, an answer other than the one of ``PLATFORM_ISSUER_COUNTRY``).
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.PLATFORM_ISSUER_COUNTRY = "ES"
    business = get(base_operations.BUSINESS)
    answer = business.fn
    monkeypatch.setattr(business, "fn", lambda ctx, data: {**answer(ctx, data), "currency": "JPY"})
    through, in_yen, _permissions = IN_YEN[caller]
    assert through(ctx_for(scope=Scope("host", "erplora"))) == in_yen


@pytest.mark.parametrize("caller", sorted(IN_YEN))
def test_an_api_key_with_only_the_operation_s_permission_gets_the_business_s_currency(caller):
    # The key holds no permission of ``base.business.get``: the currency is read as the platform, never with its rights.
    business_in("JP")
    through, in_yen, permissions = IN_YEN[caller]
    assert through(ctx_with(*permissions)) == in_yen
