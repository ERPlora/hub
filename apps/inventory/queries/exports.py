"""Exports: every row that matches, not a page, with the figures as the screen reads them, in a CSV the import
reads back."""

import csv
import io
from decimal import Decimal

from babel import Locale
from babel.numbers import format_decimal, get_decimal_symbol
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.inventory.queries.categories import _categories, _filter_categories
from apps.inventory.queries.products import _products, filter_products
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas import CategoryFiltersIn, ExportOut, ProductFiltersIn
from base import allergens
from base import operations as platform
from base.business import money_text

PRODUCTS_FILENAME = _("inventory-products.csv")
CATEGORIES_FILENAME = _("inventory-categories.csv")
# The export's headers are the ones the import recognizes.
PRODUCT_HEADERS = (
    _("Name"),
    _("SKU"),
    _("Price"),
    _("Cost"),
    _("Stock"),
    _("Threshold"),
    _("EAN-13"),
    _("Description"),
    _("Allergens"),
    _("Unit"),
    _("Tax category"),
    _("Active"),
)
CATEGORY_HEADERS = (_("Name"), _("Slug"), _("Products"))
YES, NO = _("Yes"), _("No")
CSV_CONTENT_TYPE = "text/csv"
# Excel reads a CSV as UTF-8 only with it.
BOM = "\ufeff"
#: What a spreadsheet runs as a formula at the start of a cell (=HYPERLINK, @SUM…): a text cell that
#: starts so gets an apostrophe in front, which the import takes back (services.EXPORT_GUARD).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


@operation(
    "inventory.product.export",
    kind="query",
    permission="inventory.export_product",
    input=ProductFiltersIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "description": "Export to CSV every product that matches the search and the filters, with the headers the import reads.",
        "asks": {
            "en": (
                "export my products to a spreadsheet",
                "give me the catalog as a CSV",
            ),
            "es": (
                "exporta mis productos a una hoja de cálculo",
                "pásame el catálogo en CSV",
            ),
        },
    },
)
def export_products(ctx: OperationContext, params: ProductFiltersIn) -> dict:
    products = filter_products(_products(current_settings()), params)
    currency = platform.business_currency(ctx.scope)
    rows = [
        [
            _text_cell(product.name),
            _text_cell(product.sku),
            _money(product.price, currency),
            _money(product.cost, currency),
            quantity_text(product.stock),
            quantity_text(product.low_stock_threshold),
            _text_cell(product.ean13 or ""),
            _text_cell(product.description),
            allergens.names(product.allergens),
            product.unit,
            _text_cell(product.tax_category.key if product.tax_category else ""),
            str(YES if product.is_active else NO),
        ]
        for product in products
    ]
    return _csv(PRODUCTS_FILENAME, PRODUCT_HEADERS, rows)


@operation(
    "inventory.category.export",
    kind="query",
    permission="inventory.export_product",
    input=CategoryFiltersIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "description": "Export the product categories to CSV: name, slug and number of active products.",
        "asks": {
            "en": (
                "export my categories to a spreadsheet",
                "give me the categories as a CSV",
            ),
            "es": (
                "exporta mis categorías a una hoja de cálculo",
                "pásame las categorías en CSV",
            ),
        },
    },
)
def export_categories(ctx: OperationContext, params: CategoryFiltersIn) -> dict:
    categories = _filter_categories(_categories(), params)
    rows = [
        [_text_cell(category.name), _text_cell(category.slug), str(category.product_count)]
        for category in categories
    ]
    return _csv(CATEGORIES_FILENAME, CATEGORY_HEADERS, rows)


def quantity_text(value: Decimal) -> str:
    """A quantity as the person reads it: exact, ungrouped, without trailing zeros (2,5 · 3 · 0,532)."""
    return format_decimal(
        value, locale=_locale(), group_separator=False, decimal_quantization=False
    )


def _locale() -> Locale:
    """The request's language as a CLDR locale (``es``, ``en``…), for babel."""
    return Locale.parse(translation.get_language() or settings.LANGUAGE_CODE, sep="-")


def _money(cents: int, currency: str) -> str:
    """«2,20 €» in Spanish, «€2.20» in English (CLDR), in the business's ``currency`` with its decimals, ungrouped so
    that the import reads it back («PLN 2.20»: the code off the figure, as the browser writes it)."""
    return money_text(cents, currency, grouped=False)


def _text_cell(text: str) -> str:
    """A text cell of an export, with an apostrophe in front of what a spreadsheet would run.

    Only text: a figure (a stock of -3) is written as it is.
    """
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def _csv(filename, headers, rows) -> dict:
    """A CSV with the delimiter Excel expects in the language: «;» where the comma is the decimal separator."""
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter=";" if get_decimal_symbol(_locale()) == "," else ","
    )
    writer.writerow([str(header) for header in headers])
    writer.writerows(rows)
    return {
        "filename": str(filename),
        "content_type": CSV_CONTENT_TYPE,
        "content": BOM + buffer.getvalue(),
    }
