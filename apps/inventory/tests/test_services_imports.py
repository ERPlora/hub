"""Importing products and categories from a file, and the product export imported back."""

from decimal import Decimal

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.inventory import events
from apps.inventory.models import Category, Product
from apps.inventory.schemas.categories import CategoryIn
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.imports import CategoryImportIn, ProductImportIn
from apps.inventory.tests.test_services import (
    TAX,
    clear_outbox,
    configure,
    create,
    event_names,
    general,
    movements,
    outbox,
    refused,
    run,
    stock_of,
    write_off,
)
from apps.tax.models import TaxCategory

from .conftest import HUB_DB, ctx_with

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


# inventory.category.bulk_create (INVENTORY-F10)


def import_categories(*rows):
    return run(
        "inventory.category.bulk_create",
        CategoryImportIn(rows=[{"line": n + 2, **row} for n, row in enumerate(rows)]),
    )


def test_import_categories_with_a_report_per_row():
    TaxCategory.objects.create(key="test.food", name="Restaurant food")
    run("inventory.category.create", CategoryIn(name="Drinks"))

    report = import_categories(
        {"name": "Food", "tax_category_key": "Restaurant food"},
        {"name": "drinks"},
        {"name": "Desserts", "slug": "postres", "tax_category_key": "test.food"},
        {"name": ""},
        {"name": "Wines", "tax_category_key": "IVA 99"},
        {"name": "Food"},
    )

    assert (
        report.dry_run,
        report.total,
        report.created,
        report.skipped,
        report.failed,
    ) == (False, 6, 2, 2, 2)
    assert [(row.line, row.key, row.status, row.reason) for row in report.rows] == [
        (2, "Food", "created", ""),
        (3, "drinks", "skipped", ""),
        (4, "Desserts", "created", ""),
        (5, "", "failed", "The name is missing"),
        (6, "Wines", "failed", "Tax category not recognized: IVA 99"),
        (7, "Food", "skipped", ""),
    ]
    food, desserts = (
        Category.objects.get(name="Food"),
        Category.objects.get(name="Desserts"),
    )
    assert (food.slug, food.tax_category.key, desserts.slug) == (
        "food",
        "test.food",
        "postres",
    )
    assert (
        event_names().count(events.CATEGORY_CREATED) == 3
    )  # the one by hand and the two imported


def test_repeating_a_category_file_duplicates_nothing():
    import_categories({"name": "Food"})
    assert import_categories({"name": "Food"}).skipped == 1
    assert Category.objects.count() == 1


def test_imported_categories_go_after_the_last_one_in_the_order_of_the_file():
    run("inventory.category.create", CategoryIn(name="Starters", order=2))

    import_categories({"name": "Wines"}, {"name": ""}, {"name": "Beers"})

    assert list(Category.objects.order_by("order", "name").values_list("name", "order")) == [
        ("Starters", 2),
        ("Wines", 3),
        ("Beers", 4),
    ]


# inventory.product.bulk_create (INVENTORY-F09)


def import_products(*rows, dry_run=False, role="hub_admin"):
    data = ProductImportIn(
        rows=[{"line": n + 2, **row} for n, row in enumerate(rows)], dry_run=dry_run
    )
    return run("inventory.product.bulk_create", data, role)


def row(sku, name=None, **cells):
    return {
        "name": sku.title() if name is None else name,
        "sku": sku,
        "price": "1",
        "tax_category_key": TAX,
        **cells,
    }


def test_the_rehearsal_checks_every_row_and_creates_nothing():
    report = import_products(row("CAF"), row("TEA", price="abc"), dry_run=True)
    assert (
        report.dry_run,
        report.total,
        report.ready,
        report.created,
        report.failed,
    ) == (True, 2, 1, 0, 1)
    assert [row.status for row in report.rows] == ["ready", "failed"]
    assert not Product.objects.exists() and outbox() == []


def test_an_import_reads_spanish_and_english_amounts_and_quantities():
    configure(low_stock_threshold=7)
    report = import_products(
        row("A", price="2,20 €", cost="1.234,56", stock="3"),
        row(
            "B",
            price="2.20",
            cost="",
            stock="2,5",
            unit="kg",
            low_stock_threshold="0,5",
        ),
        row("C", price="€1,234.50", stock=""),
        row("D", price="12,50\xa0€", ean13=" 8412345678905 ", description="The best"),
    )
    assert report.created == 4
    products = {product.sku: product for product in Product.objects.all()}
    assert (
        products["A"].price,
        products["A"].cost,
        products["A"].stock,
        products["A"].low_stock_threshold,
    ) == (220, 123456, 3, 7)
    assert (
        products["B"].price,
        products["B"].cost,
        products["B"].stock,
        products["B"].unit,
        products["B"].low_stock_threshold,
    ) == (
        220,
        0,
        Decimal("2.5"),
        "kg",
        Decimal("0.5"),
    )
    assert (products["C"].price, products["C"].stock) == (123450, 0)
    assert (products["D"].price, products["D"].ean13, products["D"].description) == (
        1250,
        "8412345678905",
        "The best",
    )


def test_an_imported_product_is_active_physical_follows_the_business_and_has_no_categories():
    import_products(row("A", stock="4"))
    product = Product.objects.get()
    assert (
        product.is_active,
        product.product_type,
        product.track_stock,
        product.categories.count(),
    ) == (True, "physical", None, 0)
    assert movements(product.id) == [("initial", Decimal("4.000"), Decimal("4.000"))]
    assert event_names() == [events.PRODUCT_CREATED, events.STOCK_CHANGED]


def test_a_row_says_its_type_and_what_its_price_refers_to():
    report = import_products(
        row("CUT", product_type=" Service "),
        row("HAM", price="2,50", unit="g", price_quantity="100", stock="500"),
        row("SAF", price="9", unit="g", pricing_unit="KG"),
        row("OIL", unit="ml", price_quantity="0,5", pricing_unit="l", product_type="physical"),
    )

    assert [row.reason for row in report.rows] == [""] * 4
    assert {
        product.sku: (product.product_type, product.unit, product.price_quantity, product.pricing_unit)
        for product in Product.objects.all()
    } == {
        "CUT": ("service", "ud", 1, "ud"),
        "HAM": ("physical", "g", 100, "g"),
        "SAF": ("physical", "g", 1, "kg"),
        "OIL": ("physical", "ml", Decimal("0.5"), "l"),
    }


@pytest.mark.parametrize(
    ("cells", "reason"),
    [
        ({"product_type": "combo"}, "Product type not recognized: combo"),
        ({"product_type": "service", "stock": "2"}, "A service has no stock."),
        ({"price_quantity": "many"}, "Quantity is not a number"),
        ({"price_quantity": "0"}, "Quantity is not a number"),
        ({"price_quantity": "-100"}, "Quantity is not a number"),
        ({"price_quantity": "1000000000000"}, "Quantity too large"),
        ({"price_quantity": "0.5"}, "The quantity does not respect the step allowed for this unit"),
        (
            {"unit": "kg", "pricing_unit": "g", "price_quantity": "0.5"},
            "The quantity does not respect the step allowed for this unit",
        ),
        ({"pricing_unit": "lb"}, "Unit of measure not recognized: lb"),
        ({"unit": "g", "pricing_unit": "l"}, "The price must refer to a unit of the same kind as the product's unit."),
    ],
)
def test_a_row_whose_type_or_price_quantity_cannot_be_fails_alone_and_the_rehearsal_says_the_same(cells, reason):
    rows = (row("BAD", **cells), row("GOOD"))

    rehearsal, real = import_products(*rows, dry_run=True), import_products(*rows)

    assert [(row.key, row.status, row.reason) for row in rehearsal.rows] == [("BAD", "failed", reason), ("GOOD", "ready", "")]
    assert [(row.key, row.status, row.reason) for row in real.rows] == [("BAD", "failed", reason), ("GOOD", "created", "")]
    assert Product.objects.get().sku == "GOOD"


def test_the_import_report_says_why_each_row_did_not_go_in():
    create("Coffee", "CAF")
    deleted = create("Old", "OLD")
    run("inventory.product.delete", ProductRefIn(id=deleted.id))
    clear_outbox()

    report = import_products(
        row("CAF"),  # already in the catalog
        row("OLD"),  # a deleted product's SKU: a new product
        row("NEW", name=""),
        row("", name="No SKU"),
        row("P1", price="abc"),
        row("P2", cost="1,2,3"),
        row("NEW2"),
        row("NEW2"),
        row("Q1", stock="1.5"),
        row("Q2", stock="many"),
        row("T1", tax_category_key=""),
        row("T2", tax_category_key="iva 99"),
        row("U1", unit="lb"),
        row("E1", ean13="12345678901234"),
        row("N1", price="-3"),
    )

    assert [(row.line, row.key, row.status, row.reason) for row in report.rows] == [
        (2, "CAF", "skipped", ""),
        (3, "OLD", "created", ""),
        (4, "NEW", "failed", "Name or SKU missing"),
        (5, "", "failed", "Name or SKU missing"),
        (6, "P1", "failed", "Price is not a number"),
        (7, "P2", "failed", "Price is not a number"),
        (8, "NEW2", "created", ""),
        (9, "NEW2", "failed", "SKU repeated in the file"),
        (
            10,
            "Q1",
            "failed",
            "The quantity does not respect the step allowed for this unit",
        ),
        (11, "Q2", "failed", "Quantity is not a number"),
        (12, "T1", "failed", "The tax category is missing"),
        (13, "T2", "failed", "Tax category not recognized: iva 99"),
        (14, "U1", "failed", "Unit of measure not recognized: lb"),
        (15, "E1", "failed", "A text is longer than its column allows"),
        (16, "N1", "failed", "Price is not a number"),
    ]
    assert (report.total, report.created, report.skipped, report.failed) == (
        15,
        2,
        1,
        12,
    )
    assert (
        Product.objects.get(sku="CAF", is_deleted=False).name == "Coffee"
    )  # the existing one is not touched


def test_an_imported_ean13_of_a_live_product_fails_that_row_only():
    create("Coffee", "CAF", ean13="8412345678905")
    report = import_products(row("A", ean13="8412345678905"), row("B"))
    assert [(row.status, row.reason) for row in report.rows] == [
        ("failed", "Another product of the catalog already has that EAN-13."),
        ("created", ""),
    ]


def test_an_ean13_written_twice_in_the_file_goes_to_the_first_row_that_goes_in():
    ean13 = "8412345678905"
    report = import_products(
        row("BAD", ean13=ean13, allergens="shellfish"), row("A", ean13=ean13), row("B", ean13=ean13)
    )
    assert [(row.key, row.status, row.reason) for row in report.rows] == [
        ("BAD", "failed", "Allergen not recognized: shellfish"),
        ("A", "created", ""),
        ("B", "failed", "Another product of the catalog already has that EAN-13."),
    ]


def test_importing_needs_its_own_permission():
    refused(PermissionDenied, lambda: import_products(row("A"), role="hub_employee"))
    refused(
        PermissionDenied,
        lambda: get("inventory.product.bulk_create")(
            ctx_with("inventory.add_product"), ProductImportIn(rows=[{"line": 2}])
        ),
    )


def test_an_imported_category_name_or_slug_too_long_fails_its_row_and_is_never_cut():
    report = import_categories({"name": "x" * 101}, {"name": "Food", "slug": "y" * 121}, {"name": "Bebidas Frías", "slug": "Bebidas Frías"})
    assert [(row.status, row.reason) for row in report.rows] == [
        ("failed", "A text is longer than its column allows"),
        ("failed", "A text is longer than its column allows"),
        ("created", ""),
    ]
    assert Category.objects.get().slug == "bebidas-frias"  # a slug cell is normalized like a typed one


def test_an_import_takes_back_the_apostrophe_the_export_puts_in_front_of_a_formula():
    import_products(row("'@SUM(A1)", name="'=HYPERLINK(1)", description="'+cmd"))
    import_categories({"name": "'-Drinks"})
    product = Product.objects.get()
    assert (product.name, product.sku, product.description) == ("=HYPERLINK(1)", "@SUM(A1)", "+cmd")
    assert Category.objects.get().name == "-Drinks"


def test_an_amount_or_a_quantity_too_large_fails_its_row_and_the_rehearsal_says_the_same():
    rows = (
        row("P", price="99999999999999999999"),
        row("C", cost="100000000000000"),
        row("S", stock="9999999999999"),  # 13 whole digits
        row("T", low_stock_threshold="1000000000000"),
        row("OK", stock="999999999999"),  # 12 whole digits: the most a quantity holds
    )
    refusals = [
        ("P", "failed", "Price or cost too large"),
        ("C", "failed", "Price or cost too large"),
        ("S", "failed", "Quantity too large"),
        ("T", "failed", "Quantity too large"),
    ]

    rehearsal = import_products(*rows, dry_run=True)
    real = import_products(*rows)

    assert [(row.key, row.status, row.reason) for row in rehearsal.rows] == [*refusals, ("OK", "ready", "")]
    assert [(row.key, row.status, row.reason) for row in real.rows] == [*refusals, ("OK", "created", "")]
    assert stock_of(Product.objects.get().id) == Decimal("999999999999")


EXPORT_FIELDS = {
    "Name": "name",
    "SKU": "sku",
    "Price": "price",
    "Cost": "cost",
    "Stock": "stock",
    "Threshold": "low_stock_threshold",
    "EAN-13": "ean13",
    "Description": "description",
    "Unit": "unit",
    "Tax category": "tax_category_key",
}


def exported_rows():
    """The product export read back as the import's rows (its headers are the import's)."""
    import csv
    import io

    from apps.inventory.schemas.products import ProductFiltersIn

    content = run("inventory.product.export", ProductFiltersIn()).content.lstrip("﻿")
    return [
        {field: cells[header] for header, field in EXPORT_FIELDS.items()} for cells in csv.DictReader(io.StringIO(content))
    ]


def test_the_catalog_exported_and_imported_again_is_skipped_untouched_even_with_a_negative_stock():
    # INVENTORY-F11: the export imports back without changes; F09: a live SKU is skipped, whatever its cells.
    configure(allow_sell_without_stock=True)
    wine = create("Wine", "WIN", initial_stock="5")
    write_off(wine.id, "8")  # -3: sold without stock
    create("=Gambas", "GAM", unit="kg", initial_stock="2.5", ean13="8412345678905", price=1250)
    rows = exported_rows()
    clear_outbox()

    report = import_products(*rows)

    assert (report.total, report.skipped, report.failed, report.created) == (2, 2, 0, 0)
    assert outbox() == [] and stock_of(wine.id) == Decimal("-3")


def test_an_exported_catalog_imports_into_an_empty_one_as_it_was():
    create("=Gambas", "GAM", unit="kg", initial_stock="2.5", ean13="8412345678905", price=1250, cost=820)
    rows = exported_rows()
    run("inventory.product.delete", ProductRefIn(product="GAM"))

    assert import_products(*rows).created == 1
    again = Product.objects.get(is_deleted=False)
    assert (again.name, again.price, again.cost, again.stock, again.unit, again.ean13) == (
        "=Gambas",
        1250,
        820,
        Decimal("2.5"),
        "kg",
        "8412345678905",
    )


def test_a_stock_sold_below_zero_imports_into_an_empty_catalog_as_it_was():
    configure(allow_sell_without_stock=True)
    wine = create("Wine", "WIN", initial_stock="5")
    write_off(wine.id, "8")
    rows = exported_rows()
    run("inventory.product.delete", ProductRefIn(product="WIN"))

    report = import_products(*rows)

    assert (report.created, report.failed) == (1, 0)
    again = Product.objects.get(is_deleted=False)
    assert (again.stock, movements(again.id)) == (Decimal("-3"), [("initial", Decimal("-3"), Decimal("-3"))])


@pytest.mark.parametrize(
    ("cells", "reason"),
    [
        ({"stock": "-2,5", "unit": "kg"}, ""),
        ({"stock": "many"}, "Quantity is not a number"),
        ({"stock": "-"}, "Quantity is not a number"),
        ({"stock": "--3"}, "Quantity is not a number"),
        ({"stock": "3-"}, "Quantity is not a number"),
        ({"stock": "-1,5,0"}, "Quantity is not a number"),
        ({"stock": "-0.0001", "unit": "kg"}, "Quantity is not a number"),
        ({"stock": "-9999999999999"}, "Quantity too large"),
        ({"stock": "-2.5"}, "The quantity does not respect the step allowed for this unit"),
        ({"low_stock_threshold": "-3"}, "Quantity is not a number"),
    ],
)
def test_only_the_stock_may_be_below_zero_and_what_is_not_a_number_still_fails(cells, reason):
    [outcome] = import_products(row("NEG", **cells), dry_run=True).rows

    assert (outcome.status, outcome.reason) == ("ready" if not reason else "failed", reason)
