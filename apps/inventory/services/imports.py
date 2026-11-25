"""Importing products and categories from a CSV (INVENTORY-F09, F10): each row checked first, the report of
every row, and the amounts and quantities as a spreadsheet or a person writes them."""

import re
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from uuid import UUID

from babel import Locale, UnknownLocaleError
from babel.core import get_global
from babel.languages import get_official_languages
from babel.numbers import get_currency_precision
from django.conf import settings as django_settings
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import get, operation
from live.outbox import record_event

from apps.inventory import events, import_card
from apps.inventory.models import Category, fits_unit, measure_alike, Product, QUANTITY, Settings, StockMovement, Unit
from apps.inventory.queries.exports import FORMULA_STARTS
from apps.inventory.queries.reads import held
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas.fields import MAX_CENTS
from apps.inventory.schemas.imports import CategoryImportIn, ImportReportOut, ProductImportIn, ProductImportRowIn
from apps.inventory.services.movements import _move
from apps.inventory.services.products import EAN13_TAKEN, PRICING_UNIT_MISMATCH, _created_payload, _save
from apps.inventory.services.writes import SERVICE_HAS_NO_STOCK, _actor
from apps.tax.models import TaxCategory
from base import allergens
from base import operations as platform

# The reasons of an import report (INVENTORY-F09, F10).
ROW_NAME_OR_SKU_MISSING = _("Name or SKU missing")
ROW_TOO_LONG = _("A text is longer than its column allows")
ROW_PRICE_NOT_NUMERIC = _("Price is not a number")
ROW_SKU_REPEATED = _("SKU repeated in the file")
ROW_UNIT_UNKNOWN = _("Unit of measure not recognized: %(text)s")
ROW_TYPE_UNKNOWN = _("Product type not recognized: %(text)s")
ROW_QUANTITY_NOT_NUMERIC = _("Quantity is not a number")
ROW_AMOUNT_TOO_LARGE = _("Price or cost too large")
ROW_QUANTITY_TOO_LARGE = _("Quantity too large")
ROW_OFF_GRID = _("The quantity does not respect the step allowed for this unit")
ROW_TAX_CATEGORY_MISSING = _("The tax category is missing")
ROW_TAX_CATEGORY_UNKNOWN = _("Tax category not recognized: %(text)s")
ROW_NAME_MISSING = _("The name is missing")

#: A quantity holds at most 12 whole digits (DecimalField 15, 3).
MAX_QUANTITY = Decimal(10) ** (QUANTITY["max_digits"] - QUANTITY["decimal_places"])
#: What the export put in front of a cell a spreadsheet would run (queries.exports.FORMULA_STARTS).
EXPORT_GUARD = tuple(f"'{start}" for start in FORMULA_STARTS)
# A cell of a CSV: digits with decimals (at most the currency's for money, three for quantities), after normalizing.
_AMOUNT_RE = re.compile(r"^\d+(\.\d+)?$")
_QUANTITY_RE = re.compile(r"^\d+(\.\d{1,3})?$")


@operation(
    "inventory.product.bulk_create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.import_product",
    input=ProductImportIn,
    output=ImportReportOut,
    expose_api=True,
    ai={
        "description": "Create many products at once (a CSV import): each row created, skipped because its SKU "
        "already exists, or failed with its reason; dry_run only checks.",
        "risk": "high",
        "asks": {
            "en": (
                "import my product catalog from a CSV file",
                "load all the items of this CSV into the catalog",
            ),
            "es": (
                "importa mi catálogo de productos desde un archivo CSV",
                "carga todos los artículos de este CSV en el catálogo",
            ),
        },
        "summary": import_card.summary,
    },
)
def bulk_create_products(ctx: OperationContext, data: ProductImportIn) -> dict:
    """Each row is checked on its own and reported; a row whose SKU a live product has is skipped untouched.

    Created rows are active products that follow the business's stock control, without categories, «physical» and
    priced by one of their unit unless the row says otherwise; their stock leaves an «initial» movement. The rehearsal
    (``dry_run``) writes nothing.
    """
    settings = current_settings()
    currency = platform.business_currency(ctx.scope)
    rows = data.rows
    skus = [_unguarded(row.sku.strip()) for row in rows]
    live_skus = set(Product.objects.filter(is_deleted=False, sku__in=skus).values_list("sku", flat=True))
    eans = {_unguarded(row.ean13.strip()) for row in rows if row.ean13.strip()}
    live_eans = set(Product.objects.filter(is_deleted=False, ean13__in=eans).values_list("ean13", flat=True))
    keys = {row.tax_category_key.strip() for row in rows if row.tax_category_key.strip()}
    # Held in the order Taxes locks them (by key), so neither waits for the other in a circle.
    tax_categories = {
        tax.key: tax for tax in held(TaxCategory.objects.filter(key__in=keys, is_active=True).order_by("key"))
    }
    file = _ProductFile(settings, currency, tax_categories, live_eans)
    seen_skus: set[str] = set()
    report = []
    for row in rows:
        name, sku = _unguarded(row.name.strip()), _unguarded(row.sku.strip())
        # Who the row is comes first: a product already in the catalog is skipped whatever its other
        # cells say (its own export, a stock below zero included, imports back untouched).
        if not name or not sku:
            report.append(_row(row.line, sku, "failed", reason=str(ROW_NAME_OR_SKU_MISSING)))
            continue
        if sku in seen_skus:
            report.append(_row(row.line, sku, "failed", reason=str(ROW_SKU_REPEATED)))
            continue
        seen_skus.add(sku)
        if sku in live_skus:
            report.append(_row(row.line, sku, "skipped"))
            continue
        fields = _product_fields(row, {"name": name, "sku": sku}, file)
        if isinstance(fields, str):
            report.append(_row(row.line, sku, "failed", reason=fields))
        elif data.dry_run:
            report.append(_row(row.line, sku, "ready"))
        else:
            report.append(_row(row.line, sku, "created", id=_create_product(ctx, fields).id))
    return _report(report, dry_run=data.dry_run)


@operation(
    "inventory.category.bulk_create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.add_category",
    input=CategoryImportIn,
    output=ImportReportOut,
    expose_api=True,
    ai={
        "description": "Create many categories at once (a CSV import); one whose name already exists is skipped, "
        "so repeating the file duplicates nothing.",
        "risk": "high",
        "asks": {
            "en": (
                "import product categories from a CSV file",
                "load these categories from a CSV",
            ),
            "es": (
                "importa las categorías de producto desde un archivo CSV",
                "carga estas categorías desde un CSV",
            ),
        },
        "summary": import_card.summary,
    },
)
def bulk_create_categories(ctx: OperationContext, data: CategoryImportIn) -> dict:
    """The fiscal text of a row is read by Taxes (key, name in any language or learned alias), all first."""
    texts = {row.tax_category_key.strip() for row in data.rows if row.tax_category_key.strip()}
    resolve = get("tax.alias.resolve")
    resolved = {text: resolve(ctx, resolve.input(text=text)).tax_category_key for text in texts}
    keys = {key for key in resolved.values() if key}
    tax_categories = {
        tax.key: tax for tax in held(TaxCategory.objects.filter(key__in=keys, is_active=True).order_by("key"))
    }
    taken = {name.casefold() for name in Category.objects.filter(is_deleted=False).values_list("name", flat=True)}
    report = []
    for row in data.rows:
        name, text = _unguarded(row.name.strip()), row.tax_category_key.strip()
        slug = slugify(_unguarded(row.slug.strip()) or name)
        if not name:
            report.append(_row(row.line, "", "failed", reason=str(ROW_NAME_MISSING)))
            continue
        if len(name) > 100 or len(slug) > 120:
            report.append(_row(row.line, name, "failed", reason=str(ROW_TOO_LONG)))
            continue
        tax_category = tax_categories.get(resolved.get(text)) if text else None
        if text and tax_category is None:
            report.append(_row(row.line, name, "failed", reason=str(ROW_TAX_CATEGORY_UNKNOWN) % {"text": text}))
            continue
        if name.casefold() in taken:
            report.append(_row(row.line, name, "skipped"))
            continue
        taken.add(name.casefold())
        category = Category.objects.create(
            name=name,
            slug=slug,
            tax_category=tax_category,
            created_by=_actor(ctx),
            updated_by=_actor(ctx),
        )
        record_event(ctx, events.CATEGORY_CREATED, {"id": str(category.id), "name": category.name})
        report.append(_row(row.line, name, "created", id=category.id))
    return _report(report, dry_run=False)


@dataclass(frozen=True)
class _ProductFile:
    """What the rows of a file of products are read with: the business's settings and currency, the tax categories
    the rows name, and the EAN-13 codes already taken, by a live product or by an earlier row of the file."""

    settings: Settings
    currency: str
    tax_categories: dict[str, TaxCategory]
    taken_eans: set[str]


def _product_fields(row: ProductImportRowIn, fields: dict, file: _ProductFile) -> dict | str:
    """The fields of a new product from one CSV row (``fields``: its name and SKU, already read), or why it cannot be."""
    for read in _READ_IN_ORDER:
        outcome = read(row, fields, file)
        if isinstance(outcome, str):
            return outcome
        fields = outcome
    return fields


def _read_texts(row: ProductImportRowIn, fields: dict, _file: _ProductFile) -> dict | str:
    ean13 = _unguarded(row.ean13.strip())
    if len(fields["name"]) > 200 or len(fields["sku"]) > 64 or len(ean13) > 13:
        return str(ROW_TOO_LONG)
    return {**fields, "ean13": ean13 or None, "description": _unguarded(row.description)}


def _read_amounts(row: ProductImportRowIn, fields: dict, file: _ProductFile) -> dict | str:
    price, cost = parse_amount(row.price, file.currency), parse_amount(row.cost, file.currency)
    if price is None or cost is None:
        return str(ROW_PRICE_NOT_NUMERIC)
    if max(price, cost) > MAX_CENTS:
        return str(ROW_AMOUNT_TOO_LARGE)
    return {**fields, "price": price, "cost": cost}


def _read_stock(row: ProductImportRowIn, fields: dict, file: _ProductFile) -> dict | str:
    """Its unit, its stock and its threshold, both on the unit's step."""
    unit = row.unit.strip().lower() or Unit.UNIT
    if unit not in Unit.values:
        return str(ROW_UNIT_UNKNOWN) % {"text": row.unit.strip()}
    stock = parse_quantity(row.stock) if row.stock.strip() else Decimal("0")
    threshold = (
        parse_quantity(row.low_stock_threshold)
        if row.low_stock_threshold.strip()
        else Decimal(file.settings.low_stock_threshold)
    )
    refusal = _quantity_refusal(unit, stock, threshold)
    return refusal or {**fields, "stock": stock, "low_stock_threshold": threshold, "unit": unit}


def _read_price_per(row: ProductImportRowIn, fields: dict, _file: _ProductFile) -> dict | str:
    """What its price refers to: one of its unit, unless the row says another quantity or another unit."""
    unit = row.pricing_unit.strip().lower() or fields["unit"]
    if unit not in Unit.values:
        return str(ROW_UNIT_UNKNOWN) % {"text": row.pricing_unit.strip()}
    if not measure_alike(unit, fields["unit"]):
        return str(PRICING_UNIT_MISMATCH)
    # No price is per nothing: a zero is refused like a negative.
    quantity = (parse_quantity(row.price_quantity) or None) if row.price_quantity.strip() else Decimal("1")
    refusal = _quantity_refusal(unit, quantity)
    return refusal or {**fields, "price_quantity": quantity, "pricing_unit": unit}


def _read_type(row: ProductImportRowIn, fields: dict, _file: _ProductFile) -> dict | str:
    product_type = row.product_type.strip().lower() or Product.Type.PHYSICAL
    if product_type not in Product.Type.values:
        return str(ROW_TYPE_UNKNOWN) % {"text": row.product_type.strip()}
    if product_type == Product.Type.SERVICE and fields["stock"]:
        return str(SERVICE_HAS_NO_STOCK)
    return {**fields, "product_type": product_type}


def _read_tax_category(row: ProductImportRowIn, fields: dict, file: _ProductFile) -> dict | str:
    key = row.tax_category_key.strip()
    if not key:
        return str(ROW_TAX_CATEGORY_MISSING)
    if key not in file.tax_categories:
        return str(ROW_TAX_CATEGORY_UNKNOWN) % {"text": key}
    return {**fields, "tax_category": file.tax_categories[key]}


def _read_allergens(row: ProductImportRowIn, fields: dict, _file: _ProductFile) -> dict | str:
    return allergens.read_into(row.allergens, fields)


def _take_ean13(_row: ProductImportRowIn, fields: dict, file: _ProductFile) -> dict | str:
    if fields["ean13"] in file.taken_eans:
        return str(EAN13_TAKEN)
    if fields["ean13"]:
        file.taken_eans.add(fields["ean13"])
    return fields


#: What reads a row, each adding to the fields or saying why the row fails. A row with several reasons tells the first;
#: the EAN-13 is taken last, by a row that goes in.
_READ_IN_ORDER: tuple[Callable[[ProductImportRowIn, dict, _ProductFile], dict | str], ...] = (
    _read_texts, _read_amounts, _read_stock, _read_price_per, _read_type, _read_tax_category, _read_allergens, _take_ean13,
)  # fmt: skip


def _quantity_refusal(unit: str, *quantities: Decimal | None) -> str:
    """Why ``quantities``, as read, are not all quantities of ``unit``; empty if they are."""
    if None in quantities:
        return str(ROW_QUANTITY_NOT_NUMERIC)
    if max(quantities) >= MAX_QUANTITY:
        return str(ROW_QUANTITY_TOO_LARGE)
    return "" if all(fits_unit(quantity, unit) for quantity in quantities) else str(ROW_OFF_GRID)


def _create_product(ctx: OperationContext, fields: dict) -> Product:
    stock = fields.pop("stock")
    product = Product(**fields, created_by=_actor(ctx), updated_by=_actor(ctx))
    _save(product)
    record_event(ctx, events.PRODUCT_CREATED, _created_payload(product, []))
    if stock:
        _move(ctx, product, StockMovement.Type.INITIAL, stock)
    return product


def _unguarded(text: str) -> str:
    """A cell without the apostrophe the export put in front of what a spreadsheet would run."""
    return text[1:] if text.startswith(EXPORT_GUARD) else text


def parse_amount(text: str, currency: str) -> int | None:
    """Minor units of an amount of ``currency`` as a CSV or a person writes it, or ``None`` if it is not one (empty = 0).

    2,20 · 2.20 · 1.234,56 · 1,234.56 · 12,50 € · €2.20 · PLN12.50 · 12,50 zł: with both separators, the rightmost one
    is the decimal one; with only commas, the comma is; never more decimals than the currency's, never negative.
    """
    raw = _amount_noise(currency).sub("", text)
    if not raw:
        return 0
    decimals = get_currency_precision(currency)
    normalized = _decimal_point(raw)
    if normalized is None or not _AMOUNT_RE.match(normalized) or len(normalized.partition(".")[2]) > decimals:
        return None
    return int(Decimal(normalized).scaleb(decimals))


@cache
def _amount_noise(currency: str) -> re.Pattern:
    """What a pasted amount of ``currency`` may carry around its digits: (no-break) spaces, its code and its symbol in
    the app's languages and in those of the countries that pay in it («PLN», «zł»; «EUR», «€»)."""
    languages = {code for code, _name in django_settings.LANGUAGES}
    for territory, usages in get_global("territory_currencies").items():
        if any(usage[0] == currency for usage in usages):
            languages.update(get_official_languages(territory, de_facto=True))
    marks = {currency}
    for language in languages:
        with suppress(UnknownLocaleError, ValueError):
            marks.add(Locale.parse(language).currency_symbols.get(currency, currency))
    written = "|".join(re.escape(mark) for mark in sorted(marks, key=len, reverse=True))
    return re.compile(rf"[\s\u00a0\u202f]|{written}", re.IGNORECASE)


def parse_quantity(text: str) -> Decimal | None:
    """A quantity as written (2,5 · 0.532 · 3), at most three decimals and never negative; ``None`` if not one."""
    normalized = _decimal_point(text.strip().replace(" ", ""))
    if normalized is None or not _QUANTITY_RE.match(normalized):
        return None
    return Decimal(normalized)


def _decimal_point(raw: str) -> str | None:
    last_comma, last_dot = raw.rfind(","), raw.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        return raw.replace(".", "").replace(",", ".") if last_comma > last_dot else raw.replace(",", "")
    if last_comma >= 0:
        return None if raw.count(",") > 1 else raw.replace(",", ".")
    return raw


def _row(line: int, key: str, status: str, *, id: UUID | None = None, reason: str = "") -> dict:
    return {"line": line, "key": key, "status": status, "id": id, "reason": reason}


def _report(rows: list[dict], *, dry_run: bool) -> dict:
    counts = defaultdict(int)
    for row in rows:
        counts[row["status"]] += 1
    return {
        "dry_run": dry_run,
        "total": len(rows),
        "ready": counts["ready"],
        "created": counts["created"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "rows": rows,
    }
