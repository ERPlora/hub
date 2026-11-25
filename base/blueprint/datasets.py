"""The datasets: what of each app travels, read with that app's own list and written with its own create."""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any
from uuid import UUID

import pydantic
from django.apps import apps as django_apps
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import OperationError

from base import blueprint_products
from base.blueprint.calls import (
    NO_NAME,
    PAGE,
    ROW_REFUSED,
    Loaded,
    _call,
    _create_each,
    _created,
    _key,
    _money,
    _pages,
    _quantity,
    _reason,
    _text,
    _total,
)
from base.blueprint.photos import _load_image

#: What a spreadsheet runs as a formula; the customers' export quotes a cell that starts with one (CUSTOMER-F09).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
CATEGORY_MISSING = _("«%(row)s»: the category «%(category)s» is not there, so it was left without it.")


@dataclass(frozen=True)
class Dataset:
    """One kind of thing an app lets travel, through that app's own operations."""

    key: str
    label: Promise
    rows: Callable[[OperationContext], list[dict]]
    ids: Callable[[OperationContext], list[str]]
    count: Callable[[OperationContext], int]
    load: Callable[[OperationContext, list[dict], Loaded], None]
    remove: Callable[[OperationContext, str], None]
    #: Personal data (a person's name, phone, email): it travels in a backup only, never in a template.
    personal: bool = False

    @property
    def app(self) -> str:
        return self.key.split(".", 1)[0]


def app_label(app: str) -> str:
    """The app's name as the person reads it, or its id for an app this hub does not have."""
    try:
        return str(django_apps.get_app_config(app).verbose_name)
    except LookupError:
        return app


# inventory: categories and products (INVENTORY-F12)


def _inventory_category_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            "name": row.name,
            "tax_category_key": row.tax_category_key or "",
            "description": row.description,
            "icon": row.icon,
            "color": row.color,
            "order": row.order,
        }
        for row in _pages(ctx, "inventory.category.list")
    ]


def _inventory_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "inventory.category.list")}

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name"), "tax_category_key": _text(row, "tax_category_key") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "order") if row.get(name) not in (None, "")}
        return fields

    _create_each(ctx, rows, loaded, name="inventory.category.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


def _inventory_product_rows(ctx: OperationContext) -> list[dict]:
    names = {row.id: row.name for row in _pages(ctx, "inventory.category.list")}
    return [
        {
            "name": row.name,
            "sku": row.sku,
            "price": row.price,
            "cost": row.cost,
            "stock": _quantity(row.stock, blank_zero=True),
            "low_stock_threshold": _quantity(row.low_stock_threshold),
            "unit": row.unit,
            "ean13": row.ean13 or "",
            "description": row.description,
            "tax_category_key": row.tax_category_key or "",
            "categories": sorted(names[pk] for pk in row.category_ids if pk in names),
            "track_stock": row.track_stock,
            "is_active": row.is_active,
            **blueprint_products.optional_fields(row),
        }
        for row in _pages(ctx, "inventory.product.list")
    ]


def _product_cells(row: dict, line: int) -> dict:
    """A product's row as the cells ``inventory.product.bulk_create`` reads."""
    return {
        "line": line,
        "name": _text(row, "name"),
        "sku": _text(row, "sku"),
        "price": _money(row.get("price", 0)),
        "cost": _money(row.get("cost", 0)),
        "stock": _text(row, "stock"),
        "low_stock_threshold": _text(row, "low_stock_threshold"),
        "ean13": _text(row, "ean13"),
        "description": _text(row, "description"),
        "unit": _text(row, "unit"),
        "product_type": _text(row, "product_type"),
        "price_quantity": _text(row, "price_quantity"),
        "pricing_unit": _text(row, "pricing_unit"),
        "tax_category_key": _text(row, "tax_category_key"),
    } | blueprint_products.allergens_cell(row)


def _create_products(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> list[tuple[str, dict]]:
    """Import ``rows``, a page at most; the ones created, each with its new id."""
    cells = [_product_cells(row, line) for line, row in enumerate(rows, start=1)]
    try:
        report = _call(ctx, "inventory.product.bulk_create", rows=cells)
    except (OperationError, pydantic.ValidationError) as exc:
        for row in rows:
            loaded.refuse(_text(row, "name") or _text(row, "sku"), _reason(exc))
        return []
    made = []
    for outcome in report.rows:
        row = rows[outcome.line - 1]
        if outcome.status == "created":
            made.append((_created(loaded, outcome), row))
        elif outcome.status == "skipped":
            loaded.already += 1
        else:
            # Named as the person knows it: its name, its code only without one.
            loaded.refuse(_text(row, "name") or outcome.key or _text(row, "sku"), outcome.reason)
    return made


def _product_change(row: dict, categories: dict[str, UUID], loaded: Loaded) -> dict:
    """What the import does not take of a product's row: its categories, by their ids, and its marks."""
    ids = []
    for name in blueprint_products.category_names(row):
        if _key(name) in categories:
            ids.append(categories[_key(name)])
        else:
            loaded.warn(str(CATEGORY_MISSING) % {"row": _text(row, "sku"), "category": name})
    return ({"category_ids": ids} if ids else {}) | blueprint_products.marks(row)


def _inventory_product_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    made: list[tuple[str, dict]] = []
    for start in range(0, len(rows), PAGE):
        made += _create_products(ctx, rows[start : start + PAGE], loaded)
    if not made:
        return
    categories = {_key(row.name): row.id for row in _pages(ctx, "inventory.category.list")}
    for pk, row in made:
        change = _product_change(row, categories, loaded)
        if not change:
            continue
        try:
            _call(ctx, "inventory.product.update", id=pk, **change)
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.warn(str(ROW_REFUSED) % {"row": _text(row, "sku"), "reason": _reason(exc)})
    for pk, row in made:
        _load_image(ctx, loaded, "inventory.product", pk, row, _text(row, "name") or _text(row, "sku"))


# service: categories and services


def _service_category_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            "name": row.name,
            "description": row.description,
            "parent": row.parent_name or "",
            "icon": row.icon,
            "color": row.color,
            "sort_order": row.sort_order,
        }
        for row in _pages(ctx, "service.category.list")
    ]


def _service_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "service.category.list")}
    # A parent before its children: the ones without a parent first.
    ordered = sorted(rows, key=lambda row: bool(_text(row, "parent")))

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name"), "parent": _text(row, "parent") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "sort_order") if row.get(name) not in (None, "")}
        return fields

    _create_each(ctx, ordered, loaded, name="service.category.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


SERVICE_FIELDS = (
    "tax_category_key", "pricing_type", "price", "min_price", "max_price", "cost", "duration_minutes", "buffer_before",
    "buffer_after", "max_capacity", "description", "short_description", "is_bookable", "requires_confirmation",
    "allow_online_booking", "sort_order", "is_featured", "sku", "barcode", "notes",
)  # fmt: skip


def _service_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            "name": row.name,
            "category": row.category_name or "",
            **{name: getattr(row, name) for name in SERVICE_FIELDS},
            **({"image": row.image} if row.image else {}),
        }
        for row in _pages(ctx, "service.service.list")
    ]


def _service_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "service.service.list")}

    def build(row: dict) -> dict:
        fields = {name: row[name] for name in SERVICE_FIELDS if name in row}
        if fields.get("tax_category_key") == "":
            fields["tax_category_key"] = None
        return {"name": _text(row, "name"), "category": _text(row, "category") or None, **fields}

    _create_each(ctx, rows, loaded, name="service.service.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"),
                 after=lambda row, pk: _load_image(ctx, loaded, "service.service", pk, row, _text(row, "name")))


# table: zones and tables


def _zone_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"name": row.name, "description": row.description, "color": row.color, "sort_order": row.sort_order}
        for row in _pages(ctx, "table.zone.list")
    ]


def _zone_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "table.zone.list")}

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name")}
        return fields | {name: row[name] for name in ("description", "color", "sort_order") if row.get(name) not in (None, "")}

    _create_each(ctx, rows, loaded, name="table.zone.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


def _table_key(zone: str, number: str) -> str:
    return f"{_key(zone)}\x00{_key(number)}" if number.strip() else ""


def _table_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"number": row.number, "name": row.name, "capacity": row.capacity, "shape": row.shape, "zone": row.zone_name or ""}
        for row in _pages(ctx, "table.table.list")
    ]


def _table_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_table_key(row.zone_name or "", row.number) for row in _pages(ctx, "table.table.list")}

    def build(row: dict) -> dict:
        fields = {"number": _text(row, "number"), "zone": _text(row, "zone") or None}
        return fields | {name: row[name] for name in ("name", "capacity", "shape") if row.get(name) not in (None, "")}

    _create_each(ctx, rows, loaded, name="table.table.create",
                 key=lambda row: _table_key(_text(row, "zone"), _text(row, "number")), existing=existing, build=build,
                 label=lambda row: " ".join(part for part in (_text(row, "zone"), _text(row, "number")) if part))


# customer: the customers (personal data: a backup only)

CUSTOMER_FIELDS = (
    "name", "email", "phone", "tax_id", "company_name", "address", "city", "postal_code", "country", "lifecycle_stage",
    "notes", "source",
)  # fmt: skip
#: Rows per call of ``customer.customer.import`` (its ceiling).
CUSTOMER_BATCH = 50


def _uncell(text: str) -> str:
    """A cell of the customers' CSV as it was typed: the quote the export puts before a formula's sign goes."""
    return text[1:] if text[:1] == "'" and text[1:2] in FORMULA_STARTS and len(text) > 1 else text


def _customer_rows(ctx: OperationContext) -> list[dict]:
    exported = _call(ctx, "customer.customer.export")
    return [
        {name: _uncell(line.get(name) or "") for name in CUSTOMER_FIELDS}
        for line in csv.DictReader(io.StringIO(exported.csv))
    ]


def _customer_identity(name: str, phone: str, email: str) -> str:
    return f"{_key(name)}\x00{phone.strip()}\x00{_key(email)}"


def _customer_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_customer_identity(row.name, row.phone, row.email) for row in _pages(ctx, "customer.customer.list")}
    fresh = []
    for row in rows:
        values = {name: _text(row, name) for name in CUSTOMER_FIELDS}
        if not values["name"]:
            loaded.refuse("", str(NO_NAME))
        elif _customer_identity(values["name"], values["phone"], values["email"]) in existing:
            loaded.already += 1
        else:
            fresh.append(values)
    for start in range(0, len(fresh), CUSTOMER_BATCH):
        chunk = fresh[start : start + CUSTOMER_BATCH]
        try:
            result = _call(ctx, "customer.customer.import", rows=chunk)
        except (OperationError, pydantic.ValidationError) as exc:
            for values in chunk:
                loaded.refuse(values["name"], _reason(exc))
            continue
        for outcome in result.rows:
            if outcome.id is not None:
                loaded.created.append(str(outcome.id))
            else:
                loaded.refuse(chunk[outcome.index]["name"], next(iter(outcome.errors.values()), ""))


def _ids(name: str, **params: Any) -> Callable[[OperationContext], list[str]]:
    return lambda ctx: [str(row.id) for row in _pages(ctx, name, **params)]


def _count(name: str) -> Callable[[OperationContext], int]:
    return lambda ctx: _total(ctx, name)


def _remover(name: str) -> Callable[[OperationContext, str], None]:
    return lambda ctx, pk: _call(ctx, name, id=pk)


#: Every dataset, in load order: what a row names is loaded before it (a category before its products).
DATASETS: tuple[Dataset, ...] = (
    Dataset(
        key="inventory.category",
        label=pgettext_lazy("blueprint dataset", "Product categories"),
        rows=_inventory_category_rows,
        ids=_ids("inventory.category.list"),
        count=_count("inventory.category.list"),
        load=_inventory_category_load,
        remove=_remover("inventory.category.delete"),
    ),
    Dataset(
        key="inventory.product",
        label=pgettext_lazy("blueprint dataset", "Products"),
        rows=_inventory_product_rows,
        ids=_ids("inventory.product.list"),
        count=_count("inventory.product.list"),
        load=_inventory_product_load,
        remove=_remover("inventory.product.delete"),
    ),
    Dataset(
        key="service.category",
        label=pgettext_lazy("blueprint dataset", "Service categories"),
        rows=_service_category_rows,
        ids=_ids("service.category.list"),
        count=_count("service.category.list"),
        load=_service_category_load,
        remove=_remover("service.category.delete"),
    ),
    Dataset(
        key="service.service",
        label=pgettext_lazy("blueprint dataset", "Services"),
        rows=_service_rows,
        ids=_ids("service.service.list"),
        count=_count("service.service.list"),
        load=_service_load,
        remove=_remover("service.service.archive"),
    ),
    Dataset(
        key="table.zone",
        label=pgettext_lazy("blueprint dataset", "Zones"),
        rows=_zone_rows,
        ids=_ids("table.zone.list"),
        count=_count("table.zone.list"),
        load=_zone_load,
        remove=_remover("table.zone.delete"),
    ),
    Dataset(
        key="table.table",
        label=pgettext_lazy("blueprint dataset", "Tables"),
        rows=_table_rows,
        ids=_ids("table.table.list"),
        count=_count("table.table.list"),
        load=_table_load,
        remove=_remover("table.table.delete"),
    ),
    Dataset(
        key="customer.customer",
        label=pgettext_lazy("blueprint dataset", "Customers"),
        rows=_customer_rows,
        ids=_ids("customer.customer.list"),
        count=_count("customer.customer.list"),
        load=_customer_load,
        remove=_remover("customer.customer.delete"),
        personal=True,
    ),
)


@cache
def _datasets_by_key() -> dict[str, Dataset]:
    return {dataset.key: dataset for dataset in DATASETS}


def dataset(key: str) -> Dataset:
    """The dataset ``key`` (``KeyError`` for one that does not exist)."""
    return _datasets_by_key()[key]


def datasets_of(app: str) -> list[Dataset]:
    """The datasets of ``app``, in load order."""
    return [dataset for dataset in DATASETS if dataset.app == app]
