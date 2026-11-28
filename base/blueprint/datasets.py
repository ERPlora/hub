"""The datasets: what of each app travels, read with that app's own list and written with its own create."""

import csv
import io
from functools import cache
from uuid import UUID

import pydantic
from django.apps import apps as django_apps
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import OperationError
from live.meta import module_configs

from base import activation, blueprint_products
from base.blueprint.calls import (
    NO_NAME,
    PAGE,
    ROW_REFUSED,
    Dataset,
    Loaded,
    _created,
    _money,
    _quantity,
    call,
    count_of,
    create_each,
    ids_of,
    natural_key,
    pages,
    reason,
    remover,
    text_of,
)
from base.blueprint.photos import load_image

#: What a spreadsheet runs as a formula; the customers' export quotes a cell that starts with one (CUSTOMER-F09).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
PRODUCT_IMAGES = ("inventory.product.set_image", "inventory.product.upload_image")
SERVICE_IMAGES = ("service.service.set_image", "service.service.upload_image")
CATEGORY_MISSING = _("«%(row)s»: the category «%(category)s» is not there, so it was left without it.")


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
        for row in pages(ctx, "inventory.category.list")
    ]


def _inventory_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "inventory.category.list")}

    def build(row: dict) -> dict:
        fields = {"name": text_of(row, "name"), "tax_category_key": text_of(row, "tax_category_key") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "order") if row.get(name) not in (None, "")}
        return fields

    create_each(ctx, rows, loaded, name="inventory.category.create", key=lambda row: natural_key(text_of(row, "name")),
                 existing=existing, build=build, label=lambda row: text_of(row, "name"))


def _inventory_product_rows(ctx: OperationContext) -> list[dict]:
    names = {row.id: row.name for row in pages(ctx, "inventory.category.list")}
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
        for row in pages(ctx, "inventory.product.list")
    ]


def _product_cells(row: dict, line: int) -> dict:
    """A product's row as the cells ``inventory.product.bulk_create`` reads."""
    return {
        "line": line,
        "name": text_of(row, "name"),
        "sku": text_of(row, "sku"),
        "price": _money(row.get("price", 0)),
        "cost": _money(row.get("cost", 0)),
        "stock": text_of(row, "stock"),
        "low_stock_threshold": text_of(row, "low_stock_threshold"),
        "ean13": text_of(row, "ean13"),
        "description": text_of(row, "description"),
        "unit": text_of(row, "unit"),
        "product_type": text_of(row, "product_type"),
        "price_quantity": text_of(row, "price_quantity"),
        "pricing_unit": text_of(row, "pricing_unit"),
        "tax_category_key": text_of(row, "tax_category_key"),
    } | blueprint_products.allergens_cell(row)


def _create_products(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> list[tuple[str, dict]]:
    """Import ``rows``, a page at most; the ones created, each with its new id."""
    cells = [_product_cells(row, line) for line, row in enumerate(rows, start=1)]
    try:
        report = call(ctx, "inventory.product.bulk_create", rows=cells)
    except (OperationError, pydantic.ValidationError) as exc:
        for row in rows:
            loaded.refuse(text_of(row, "name") or text_of(row, "sku"), reason(exc))
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
            loaded.refuse(text_of(row, "name") or outcome.key or text_of(row, "sku"), outcome.reason)
    return made


def _product_change(row: dict, categories: dict[str, UUID], loaded: Loaded) -> dict:
    """What the import does not take of a product's row: its categories, by their ids, and its marks."""
    ids = []
    for name in blueprint_products.category_names(row):
        if natural_key(name) in categories:
            ids.append(categories[natural_key(name)])
        else:
            loaded.warn(str(CATEGORY_MISSING) % {"row": text_of(row, "sku"), "category": name})
    return ({"category_ids": ids} if ids else {}) | blueprint_products.marks(row)


def _inventory_product_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    made: list[tuple[str, dict]] = []
    for start in range(0, len(rows), PAGE):
        made += _create_products(ctx, rows[start : start + PAGE], loaded)
    if not made:
        return
    categories = {natural_key(row.name): row.id for row in pages(ctx, "inventory.category.list")}
    for pk, row in made:
        change = _product_change(row, categories, loaded)
        if not change:
            continue
        try:
            call(ctx, "inventory.product.update", id=pk, **change)
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.warn(str(ROW_REFUSED) % {"row": text_of(row, "sku"), "reason": reason(exc)})
    for pk, row in made:
        load_image(ctx, loaded, PRODUCT_IMAGES, pk, row, text_of(row, "name") or text_of(row, "sku"))


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
        for row in pages(ctx, "service.category.list")
    ]


def _service_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "service.category.list")}
    # A parent before its children: the ones without a parent first.
    ordered = sorted(rows, key=lambda row: bool(text_of(row, "parent")))

    def build(row: dict) -> dict:
        fields = {"name": text_of(row, "name"), "parent": text_of(row, "parent") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "sort_order") if row.get(name) not in (None, "")}
        return fields

    create_each(ctx, ordered, loaded, name="service.category.create", key=lambda row: natural_key(text_of(row, "name")),
                 existing=existing, build=build, label=lambda row: text_of(row, "name"))


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
        for row in pages(ctx, "service.service.list")
    ]


def _service_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "service.service.list")}

    def build(row: dict) -> dict:
        fields = {name: row[name] for name in SERVICE_FIELDS if name in row}
        if fields.get("tax_category_key") == "":
            fields["tax_category_key"] = None
        return {"name": text_of(row, "name"), "category": text_of(row, "category") or None, **fields}

    create_each(ctx, rows, loaded, name="service.service.create", key=lambda row: natural_key(text_of(row, "name")),
                 existing=existing, build=build, label=lambda row: text_of(row, "name"),
                 after=lambda row, pk: load_image(ctx, loaded, SERVICE_IMAGES, pk, row, text_of(row, "name")))


# table: zones and tables


def _zone_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"name": row.name, "description": row.description, "color": row.color, "sort_order": row.sort_order}
        for row in pages(ctx, "table.zone.list")
    ]


def _zone_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "table.zone.list")}

    def build(row: dict) -> dict:
        fields = {"name": text_of(row, "name")}
        return fields | {name: row[name] for name in ("description", "color", "sort_order") if row.get(name) not in (None, "")}

    create_each(ctx, rows, loaded, name="table.zone.create", key=lambda row: natural_key(text_of(row, "name")),
                 existing=existing, build=build, label=lambda row: text_of(row, "name"))


def _table_key(zone: str, number: str) -> str:
    return f"{natural_key(zone)}\x00{natural_key(number)}" if number.strip() else ""


def _table_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"number": row.number, "name": row.name, "capacity": row.capacity, "shape": row.shape, "zone": row.zone_name or ""}
        for row in pages(ctx, "table.table.list")
    ]


def _table_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_table_key(row.zone_name or "", row.number) for row in pages(ctx, "table.table.list")}

    def build(row: dict) -> dict:
        fields = {"number": text_of(row, "number"), "zone": text_of(row, "zone") or None}
        return fields | {name: row[name] for name in ("name", "capacity", "shape") if row.get(name) not in (None, "")}

    create_each(ctx, rows, loaded, name="table.table.create",
                 key=lambda row: _table_key(text_of(row, "zone"), text_of(row, "number")), existing=existing, build=build,
                 label=lambda row: " ".join(part for part in (text_of(row, "zone"), text_of(row, "number")) if part))


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
    exported = call(ctx, "customer.customer.export")
    return [
        {name: _uncell(line.get(name) or "") for name in CUSTOMER_FIELDS}
        for line in csv.DictReader(io.StringIO(exported.csv))
    ]


def _customer_identity(name: str, phone: str, email: str) -> str:
    return f"{natural_key(name)}\x00{phone.strip()}\x00{natural_key(email)}"


def _customer_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_customer_identity(row.name, row.phone, row.email) for row in pages(ctx, "customer.customer.list")}
    fresh = []
    for row in rows:
        values = {name: text_of(row, name) for name in CUSTOMER_FIELDS}
        if not values["name"]:
            loaded.refuse("", str(NO_NAME))
        elif _customer_identity(values["name"], values["phone"], values["email"]) in existing:
            loaded.already += 1
        else:
            fresh.append(values)
    for start in range(0, len(fresh), CUSTOMER_BATCH):
        chunk = fresh[start : start + CUSTOMER_BATCH]
        try:
            result = call(ctx, "customer.customer.import", rows=chunk)
        except (OperationError, pydantic.ValidationError) as exc:
            for values in chunk:
                loaded.refuse(values["name"], reason(exc))
            continue
        for outcome in result.rows:
            if outcome.id is not None:
                loaded.created.append(str(outcome.id))
            else:
                loaded.refuse(chunk[outcome.index]["name"], next(iter(outcome.errors.values()), ""))


#: The datasets the platform holds for Inventory, Services, Tables and Customers, in load order: what a row names is loaded
#: before it (a category before its products). Any other app declares its own (:data:`HOOK`).
PLATFORM_DATASETS: tuple[Dataset, ...] = (
    Dataset(
        key="inventory.category",
        models=("Category",),
        label=pgettext_lazy("blueprint dataset", "Product categories"),
        rows=_inventory_category_rows,
        ids=ids_of("inventory.category.list"),
        count=count_of("inventory.category.list"),
        load=_inventory_category_load,
        remove=remover("inventory.category.delete"),
    ),
    Dataset(
        key="inventory.product",
        models=("Product", "ProductCategory"),
        label=pgettext_lazy("blueprint dataset", "Products"),
        rows=_inventory_product_rows,
        ids=ids_of("inventory.product.list"),
        count=count_of("inventory.product.list"),
        load=_inventory_product_load,
        remove=remover("inventory.product.delete"),
        images=PRODUCT_IMAGES,
    ),
    Dataset(
        key="service.category",
        models=("Category",),
        label=pgettext_lazy("blueprint dataset", "Service categories"),
        rows=_service_category_rows,
        ids=ids_of("service.category.list"),
        count=count_of("service.category.list"),
        load=_service_category_load,
        remove=remover("service.category.delete"),
    ),
    Dataset(
        key="service.service",
        models=("Service",),
        label=pgettext_lazy("blueprint dataset", "Services"),
        rows=_service_rows,
        ids=ids_of("service.service.list"),
        count=count_of("service.service.list"),
        load=_service_load,
        remove=remover("service.service.archive"),
        images=SERVICE_IMAGES,
    ),
    Dataset(
        key="table.zone",
        models=("Zone",),
        label=pgettext_lazy("blueprint dataset", "Zones"),
        rows=_zone_rows,
        ids=ids_of("table.zone.list"),
        count=count_of("table.zone.list"),
        load=_zone_load,
        remove=remover("table.zone.delete"),
    ),
    Dataset(
        key="table.table",
        models=("Table",),
        label=pgettext_lazy("blueprint dataset", "Tables"),
        rows=_table_rows,
        ids=ids_of("table.table.list"),
        count=count_of("table.table.list"),
        load=_table_load,
        remove=remover("table.table.delete"),
    ),
    Dataset(
        key="customer.customer",
        models=("Customer",),
        label=pgettext_lazy("blueprint dataset", "Customers"),
        rows=_customer_rows,
        ids=ids_of("customer.customer.list"),
        count=count_of("customer.customer.list"),
        load=_customer_load,
        remove=remover("customer.customer.delete"),
        personal=True,
    ),
)


#: The hook of a ``LiveAppConfig`` that says what of the app travels in a blueprint: a list of :class:`Dataset`.
HOOK = "blueprint_datasets"


@cache
def every_dataset() -> tuple[Dataset, ...]:
    """Every dataset, in load order: app by app, each after the apps it requires, so that what a row names is there
    before it (a product before the modifier group that applies to it); inside an app, in its own order."""
    by_app: dict[str, list[Dataset]] = {}
    for part in PLATFORM_DATASETS:
        by_app.setdefault(part.app, []).append(part)
    for config in module_configs():
        if (declared := getattr(config, HOOK, None)) is not None:
            by_app.setdefault(config.label, []).extend(declared())
    order = activation.in_requires_order(by_app, activation.module_graph())
    return tuple(part for app in order for part in by_app[app])


@cache
def _datasets_by_key() -> dict[str, Dataset]:
    return {dataset.key: dataset for dataset in every_dataset()}


def dataset(key: str) -> Dataset:
    """The dataset ``key`` (``KeyError`` for one that does not exist)."""
    return _datasets_by_key()[key]


def datasets_of(app: str) -> list[Dataset]:
    """The datasets of ``app``, in load order."""
    return [dataset for dataset in every_dataset() if dataset.app == app]
