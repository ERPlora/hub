"""The exports (``apps/inventory/queries/exports.py``). The product export (INVENTORY-F11) has every product that
matches, not a page, with the headers the import reads and the figures as the screen reads them, in the business's
language; the category export, every live category with how many products it has."""

from decimal import Decimal

import pytest
from django.utils import translation
from live.errors import PermissionDenied

from apps.inventory.models import Category, Product
from apps.inventory.schemas.categories import CategoryFiltersIn
from apps.inventory.schemas.products import ProductFiltersIn

from .conftest import HUB_DB, link, product, read_csv, run

pytestmark = HUB_DB


def test_the_export_has_every_filtered_product_not_just_a_page_with_the_import_headers(
    general,
):
    for n in range(120):
        product(f"Item {n:03}", f"IT-{n:03}", tax=general)
    product("Other", "OTH")

    with translation.override("en"):
        export = run("inventory.product.export", ProductFiltersIn(search="item"))

    assert (export.filename, export.content_type) == (
        "inventory-products.csv",
        "text/csv",
    )
    rows = read_csv(export, ",")
    assert rows[0] == [
        "Name",
        "SKU",
        "Price",
        "Cost",
        "Stock",
        "Threshold",
        "EAN-13",
        "Description",
        "Allergens",
        "Unit",
        "Tax category",
        "Active",
    ]
    assert len(rows) == 121
    assert rows[1] == [
        "Item 000",
        "IT-000",
        "€1.00",
        "€0.00",
        "0",
        "10",
        "",
        "",
        "",
        "ud",
        "product.general",
        "Yes",
    ]


def test_the_spanish_export_reads_like_the_screen_and_uses_the_semicolon_of_excel(
    general,
):
    product(
        "Gambas",
        "GAM",
        tax=general,
        price=1250,
        cost=820,
        stock=Decimal("2.500"),
        unit="kg",
        ean13="8412345678905",
        is_active=False,
    )

    with translation.override("es"):
        export = run("inventory.product.export", ProductFiltersIn())

    assert export.filename == "inventario-productos.csv"
    header, row = read_csv(export, ";")
    assert header[0] == "Nombre" and header[-2:] == ["Categoría fiscal", "Activo"]
    assert row == [
        "Gambas",
        "GAM",
        "12,50\xa0€",
        "8,20\xa0€",
        "2,5",
        "10",
        "8412345678905",
        "",
        "",
        "kg",
        "product.general",
        "No",
    ]


@pytest.mark.parametrize(
    ("operation", "schema", "rows", "column"),
    [
        (
            "inventory.product.export",
            ProductFiltersIn,
            lambda: [product(f"Item {n}", stock=Decimal("5")) for n in range(4)],
            "stock",
        ),
        (
            "inventory.category.export",
            CategoryFiltersIn,
            lambda: [Category.objects.create(name=f"Group {n}", color="#ff0000") for n in range(4)],
            "color",
        ),
    ],
)
def test_an_export_settles_its_ties_the_way_the_list_does(operation, schema, rows, column):
    in_order = [row.name for row in sorted(rows(), key=lambda row: row.id)]

    def exported(sort):
        with translation.override("en"):
            export = run(operation, schema(sort=sort))
        return [line[0] for line in read_csv(export, ",")[1:]]

    assert exported(column) == in_order
    assert exported(f"-{column}") == in_order[::-1]


def test_an_empty_export_has_only_the_header():
    rows = read_csv(run("inventory.product.export", ProductFiltersIn()), ",")
    assert len(rows) == 1


def test_the_category_export():
    drinks = Category.objects.create(name="Drinks", slug="drinks")
    link(product("Coffee"), drinks)
    Category.objects.create(name="Gone", is_deleted=True)

    with translation.override("es"):
        export = run("inventory.category.export", CategoryFiltersIn())

    assert export.filename == "inventario-categorias.csv"
    assert read_csv(export, ";") == [
        ["Nombre", "Slug", "Productos"],
        ["Drinks", "drinks", "1"],
    ]


def test_without_the_export_permission_nothing_is_handed_over():
    for name, data in (
        ("inventory.product.export", ProductFiltersIn()),
        ("inventory.category.export", CategoryFiltersIn()),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")


def test_a_text_cell_a_spreadsheet_would_run_as_a_formula_gets_an_apostrophe(general):
    # =HYPERLINK(…) or @SUM(…) typed as a name would run in Excel; a negative stock is a number.
    product("=HYPERLINK(1)", "@SUM(A1)", tax=general, description="+cmd", stock=Decimal("-3"))
    link(Product.objects.get(), Category.objects.create(name="-Drinks", slug="drinks"))

    [header, row] = read_csv(run("inventory.product.export", ProductFiltersIn()), ",")
    cells = dict(zip(header, row, strict=True))
    assert (cells["Name"], cells["SKU"], cells["Description"], cells["Stock"]) == ("'=HYPERLINK(1)", "'@SUM(A1)", "'+cmd", "-3")
    assert read_csv(run("inventory.category.export", CategoryFiltersIn()), ",")[1] == ["'-Drinks", "drinks", "1"]
