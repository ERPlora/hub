"""The product export (INVENTORY-F11): every product that matches, not a page, with the headers the import reads and
the figures as the screen reads them, in the business's language."""

from decimal import Decimal

from django.utils import translation

from apps.inventory.schemas.products import ProductFiltersIn
from apps.inventory.tests.test_queries import general, product, read_csv, run

from .conftest import HUB_DB

#: The fixture taken from the read tests: the tax category the products here take.
__all__ = ["general"]
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
