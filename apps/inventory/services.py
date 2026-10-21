"""Write operations of the inventory app: one operation = one transaction, with its events in the outbox.

Every change of stock goes through ``_move``: the product's row is locked, its balance and its ledger
movement are written together, and ``inventory.stock.changed`` is recorded. Several products are
locked in the order of their ids, so two writes never wait for each other in a circle. A quantity off
the step of its unit is refused, never rounded. Nothing is validated after something was written:
every check runs first, so a refusal leaves no trace.
"""

import re
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from babel.numbers import get_currency_precision
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import UnknownOperation, get, operation
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import (
    ACTOR_MAX_LENGTH,
    Category,
    fits_unit,
    increment_of,
    Product,
    ProductCategory,
    QUANTITY,
    RefundStock,
    SaleStock,
    Settings,
    StockMovement,
    Unit,
    UNIT_SPECS,
)
from apps.inventory.queries import (
    FORMULA_STARTS,
    config_row,
    current_settings,
    find_category,
    find_product,
    held,
    load_category,
    load_product,
    quantity_text,
    tracks_stock,
)
from apps.inventory.schemas import (
    CategoryImportIn,
    CategoryIn,
    CategoryOut,
    CategoryPatchIn,
    CategoryRefIn,
    ConfigOut,
    ConfigPatchIn,
    CountIn,
    DeletedOut,
    ImportReportOut,
    MAX_CENTS,
    ProductCategoryIn,
    ProductCategoryLinkOut,
    ProductImportIn,
    ProductIn,
    ProductOut,
    ProductPatchIn,
    ProductRefIn,
    PrintLabelOut,
    ProductSoldOutIn,
    ProductsOut,
    ReceiveIn,
    RefundStockOut,
    SaleCompletedIn,
    SaleRefundedIn,
    SaleStockOut,
    SaleVoidedIn,
    WriteOffIn,
)
from apps.tax.models import TaxCategory

SKU_TAKEN = _("That SKU already exists in the catalog.")
EAN13_TAKEN = _("Another product of the catalog already has that EAN-13.")
TAX_CATEGORY_UNKNOWN = _("This tax category does not exist in Taxes.")
CATEGORY_UNKNOWN = _("This category does not exist.")
OFF_GRID = _("The quantity does not respect the step allowed for this unit: use multiples of %(step)s.")
UNIT_HAS_STOCK = _(
    "The unit of a product with stock cannot be changed. Count its stock to zero and change it afterwards."
)
PRICING_UNIT_MISMATCH = _("The price must refer to a unit of the same kind as the product's unit.")
SERVICE_HAS_NO_STOCK = _("A service has no stock.")
STOCK_NOT_TRACKED = _("This article does not track its stock: there is nothing to write off.")
INSUFFICIENT_STOCK = _("There is not enough stock to complete the operation.")
LINE_PRODUCT_UNKNOWN = _("This product does not exist in this hub.")
LABEL_QUEUE_UNAVAILABLE = _("The print queue is not available here: print the label from the browser.")
SKU_NOT_BARCODE = _(
    "This SKU cannot be turned into a barcode: use letters without accents, digits and signs."
)
# The reasons of an import report (INVENTORY-F09, F10).
ROW_NAME_OR_SKU_MISSING = _("Name or SKU missing")
ROW_TOO_LONG = _("A text is longer than its column allows")
ROW_PRICE_NOT_NUMERIC = _("Price is not a number")
ROW_SKU_REPEATED = _("SKU repeated in the file")
ROW_UNIT_UNKNOWN = _("Unit of measure not recognized: %(text)s")
ROW_QUANTITY_NOT_NUMERIC = _("Quantity is not a number")
ROW_AMOUNT_TOO_LARGE = _("Price or cost too large")
ROW_QUANTITY_TOO_LARGE = _("Quantity too large")
ROW_OFF_GRID = _("The quantity does not respect the step allowed for this unit")
ROW_TAX_CATEGORY_MISSING = _("The tax category is missing")
ROW_TAX_CATEGORY_UNKNOWN = _("Tax category not recognized: %(text)s")
ROW_NAME_MISSING = _("The name is missing")

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "inventory.system"
THOUSANDTHS = Decimal("0.001")
#: The Hub has no currency of its own yet: euros (the export says so too).
CURRENCY = "EUR"
#: A quantity holds at most 12 whole digits (DecimalField 15, 3).
MAX_QUANTITY = Decimal(10) ** (QUANTITY["max_digits"] - QUANTITY["decimal_places"])
#: What the export put in front of a cell a spreadsheet would run (queries.FORMULA_STARTS).
EXPORT_GUARD = tuple(f"'{start}" for start in FORMULA_STARTS)
# A cell of a CSV: digits with at most two (money) or three (quantities) decimals, after normalizing.
_AMOUNT_RE = re.compile(r"^\d+(\.\d{1,2})?$")
_QUANTITY_RE = re.compile(r"^\d+(\.\d{1,3})?$")
# What a pasted amount may carry around its digits: the euro sign or code and (no-break) spaces.
_AMOUNT_NOISE = re.compile(r"[€\s  ]|EUR", re.IGNORECASE)
_PRODUCT_CONSTRAINTS = {
    "inventory_product_live_sku_unique": ("sku", SKU_TAKEN, "inventory.sku_taken"),
    "inventory_product_live_ean13_unique": ("ean13", EAN13_TAKEN, "inventory.ean13_taken"),
}


# Products (INVENTORY-F01 to F05, F08, F20, F26)


@operation(
    "inventory.product.create",
    kind="command",
    permission="inventory.add_product",
    input=ProductIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Create a product of the catalog with its tax category, its categories and, if given, "
        "its initial stock.",
        "risk": "normal",
    },
)
def create_product(ctx: OperationContext, data: ProductIn) -> dict:
    """Saved whole or not at all: the product, its categories and its initial stock (an «initial» movement)."""
    settings = current_settings()
    tax_category = _tax_category(data.tax_category_key)
    categories = _live_categories(data.category_ids)
    pricing_unit = data.pricing_unit or data.unit
    _check_pricing_unit(data.unit, pricing_unit)
    if data.product_type == Product.Type.SERVICE and data.initial_stock:
        raise _service_has_no_stock("initial_stock")
    threshold = Decimal(settings.low_stock_threshold) if data.low_stock_threshold is None else data.low_stock_threshold
    _check_grid(data.initial_stock, data.unit, "initial_stock")
    _check_grid(threshold, data.unit, "low_stock_threshold")
    _check_grid(data.price_quantity, pricing_unit, "price_quantity")
    product = Product(
        name=data.name,
        sku=data.sku,
        ean13=data.ean13 or None,
        description=data.description,
        product_type=data.product_type,
        price=data.price,
        cost=data.cost,
        low_stock_threshold=threshold,
        unit=data.unit,
        price_quantity=data.price_quantity,
        pricing_unit=pricing_unit,
        tax_category=tax_category,
        track_stock=None if data.product_type == Product.Type.SERVICE else data.track_stock,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save(product)
    _link(product, categories)
    record_event(
        ctx,
        events.PRODUCT_CREATED,
        {
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "category_ids": sorted(str(category.id) for category in categories),
        },
    )
    for category in sorted(categories, key=lambda category: category.id):
        _record_link(ctx, events.PRODUCT_CATEGORIZED, product.id, category.id)
    if data.initial_stock:
        _move(ctx, product, StockMovement.Type.INITIAL, data.initial_stock)
    return load_product(product.id)


@operation(
    "inventory.product.bulk_create",
    kind="command",
    permission="inventory.import_product",
    input=ProductImportIn,
    output=ImportReportOut,
    expose_api=True,
    ai={
        "description": "Create many products at once (a CSV import): each row created, skipped because its SKU "
        "already exists, or failed with its reason; dry_run only checks.",
        "risk": "high",
    },
)
def bulk_create_products(ctx: OperationContext, data: ProductImportIn) -> dict:
    """Each row is checked on its own and reported; a row whose SKU a live product has is skipped untouched.

    Created rows are active «physical» products that follow the business's stock control, without
    categories; their stock leaves an «initial» movement. The rehearsal (``dry_run``) writes nothing.
    """
    settings = current_settings()
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
        outcome = _check_product_row(row, name, sku, settings, tax_categories)
        if isinstance(outcome, str):
            report.append(_row(row.line, sku, "failed", reason=outcome))
            continue
        if outcome["ean13"] and outcome["ean13"] in live_eans:
            report.append(_row(row.line, sku, "failed", reason=str(EAN13_TAKEN)))
            continue
        if outcome["ean13"]:
            live_eans.add(outcome["ean13"])
        if data.dry_run:
            report.append(_row(row.line, sku, "ready"))
            continue
        stock = outcome.pop("stock")
        product = Product(**outcome, created_by=_actor(ctx), updated_by=_actor(ctx))
        _save(product)
        record_event(
            ctx, events.PRODUCT_CREATED, {"id": str(product.id), "sku": product.sku, "name": product.name, "category_ids": []}
        )
        if stock:
            _move(ctx, product, StockMovement.Type.INITIAL, stock)
        report.append(_row(row.line, sku, "created", id=product.id))
    return _report(report, dry_run=data.dry_run)


@operation(
    "inventory.product.update",
    kind="command",
    permission="inventory.change_product",
    input=ProductPatchIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Change a product, named by its id, SKU or name: its data, active or not, its stock "
        "control and its categories. The SKU, the type and the stock are not changed here.",
        "risk": "normal",
    },
)
def update_product(ctx: OperationContext, data: ProductPatchIn) -> dict:
    """Changes only the fields sent, with its categories, in one step; no change, no event."""
    product = find_product(data.id, data.product, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id", "product", "category_ids"})
    if "tax_category_key" in sent:
        sent["tax_category"] = _tax_category(sent.pop("tax_category_key"))
    if "ean13" in sent:
        sent["ean13"] = sent["ean13"] or None
    unit = sent.get("unit", product.unit)
    if unit != product.unit and product.stock != 0:
        raise Conflict(str(UNIT_HAS_STOCK), code="inventory.unit_has_stock", fields={"unit": str(UNIT_HAS_STOCK)})
    # Not sent: the one it had, unless the new unit measures something else (then the new unit).
    pricing_unit = sent.get("pricing_unit") or _same_kind(product.pricing_unit, unit)
    sent["pricing_unit"] = pricing_unit
    _check_pricing_unit(unit, pricing_unit)
    _check_grid(sent.get("low_stock_threshold", product.low_stock_threshold), unit, "low_stock_threshold")
    _check_grid(sent.get("price_quantity", product.price_quantity), pricing_unit, "price_quantity")
    added, removed = [], []
    if data.category_ids is not None:
        wanted = {category.id: category for category in _live_categories(data.category_ids)}
        current = set(product.category_links.values_list("category_id", flat=True))
        added = sorted(set(wanted) - current)
        removed = sorted(current - set(wanted))
    changes = {field: value for field, value in sent.items() if getattr(product, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(product, field, value)
        product.updated_by = _actor(ctx)
        _save(product, update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.PRODUCT_UPDATED, _product_payload(product))
    if removed:
        ProductCategory.objects.filter(product=product, category_id__in=removed).delete()
    ProductCategory.objects.bulk_create([ProductCategory(product=product, category_id=category_id) for category_id in added])
    for category_id in removed:
        _record_link(ctx, events.PRODUCT_UNCATEGORIZED, product.id, category_id)
    for category_id in added:
        _record_link(ctx, events.PRODUCT_CATEGORIZED, product.id, category_id)
    return load_product(product.id)


@operation(
    "inventory.product.delete",
    kind="command",
    permission="inventory.delete_product",
    input=ProductRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a product of the catalog, named by its id, SKU or name (logically: its movements "
        "stay and its SKU and EAN-13 are freed).",
        "risk": "high",
    },
)
def delete_product(ctx: OperationContext, data: ProductRefIn) -> dict:
    product = find_product(data.id, data.product, lock=True)
    product.is_deleted, product.is_active, product.deleted_at = True, False, timezone.now()
    product.updated_by = _actor(ctx)
    product.save(update_fields=["is_deleted", "is_active", "deleted_at", "updated_by", "updated_at"])
    record_event(ctx, events.PRODUCT_DELETED, {"id": str(product.id), "sku": product.sku, "name": product.name})
    return {"id": product.id}


@operation(
    "inventory.product.set_sold_out",
    kind="command",
    permission="inventory.change_product",
    input=ProductSoldOutIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Mark a product sold out («86»: the till stops offering it, it stays active) or put it "
        "back on sale, named by its id, SKU or name.",
        "risk": "normal",
    },
)
def set_sold_out(ctx: OperationContext, data: ProductSoldOutIn) -> dict:
    """INVENTORY-F29: the till's catalog (INVENTORY-F27) re-runs on the event; no change, no event."""
    product = find_product(data.id, data.product, lock=True)
    if product.is_sold_out != data.sold_out:
        product.is_sold_out = data.sold_out
        product.updated_by = _actor(ctx)
        product.save(update_fields=["is_sold_out", "updated_by", "updated_at"])
        record_event(ctx, events.PRODUCT_UPDATED, _product_payload(product))
    return load_product(product.id)


@operation(
    "inventory.product.print_label",
    kind="command",
    permission="inventory.view_product",
    input=ProductRefIn,
    output=PrintLabelOut,
    expose_api=True,
    ai={
        "description": "Print the barcode label of a product (its name, its SKU as the code and its price) on the "
        "printer of the «Label» function, named by its id, SKU or name; each call prints one label.",
        "risk": "normal",
    },
)
def print_label(ctx: OperationContext, data: ProductRefIn) -> dict:
    """INVENTORY-F25: Printing's queue takes the label (PRINTING-F12); a person who cannot reach it gets
    ``inventory.label_queue_unavailable`` and nothing queued, so the screen prints from the browser."""
    product = find_product(data.id, data.product)
    # Code 128, the code the label printer draws, carries the printable ASCII only.
    if not all(" " <= char <= "~" for char in product.sku):
        raise Conflict(str(SKU_NOT_BARCODE), code="inventory.sku_not_barcode")
    try:
        create_job = get("printing.job.create")
        queued = create_job(
            ctx,
            create_job.input.model_validate(
                {
                    "document_type": "barcode_label",
                    "document": {
                        "product_name": product.name,
                        "barcode": product.sku,
                        "price": float(Decimal(product.price).scaleb(-get_currency_precision(CURRENCY))),
                    },
                    "currency": CURRENCY,
                    "source_app": "inventory",
                    "source_ref": product.sku,
                }
            ),
        )
    except (UnknownOperation, AppInactive, PermissionDenied):
        raise Conflict(str(LABEL_QUEUE_UNAVAILABLE), code="inventory.label_queue_unavailable") from None
    return {"job_id": queued.job.id, "printer_name": queued.job.printer_name}


@operation(
    "inventory.product_category.add",
    kind="command",
    permission="inventory.change_product",
    input=ProductCategoryIn,
    output=ProductCategoryLinkOut,
    expose_api=True,
    ai={"description": "Put a product in a category so that the till groups it there.", "risk": "normal"},
)
def add_product_category(ctx: OperationContext, data: ProductCategoryIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    category = find_category(data.category_id, data.category, hold=True)
    _, created = ProductCategory.objects.get_or_create(product=product, category=category)
    if created:
        _record_link(ctx, events.PRODUCT_CATEGORIZED, product.id, category.id)
    return {"product_id": product.id, "category_id": category.id, "changed": created}


@operation(
    "inventory.product_category.remove",
    kind="command",
    permission="inventory.change_product",
    input=ProductCategoryIn,
    output=ProductCategoryLinkOut,
    expose_api=True,
    ai={"description": "Take a product out of a category.", "risk": "normal"},
)
def remove_product_category(ctx: OperationContext, data: ProductCategoryIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    category = find_category(data.category_id, data.category)
    removed, _ = ProductCategory.objects.filter(product=product, category=category).delete()
    if removed:
        _record_link(ctx, events.PRODUCT_UNCATEGORIZED, product.id, category.id)
    return {"product_id": product.id, "category_id": category.id, "changed": bool(removed)}


# Categories (INVENTORY-F06, F07, F10)


@operation(
    "inventory.category.create",
    kind="command",
    permission="inventory.add_category",
    input=CategoryIn,
    output=CategoryOut,
    expose_api=True,
    ai={"description": "Create a product category; its slug is made from the name when not given.", "risk": "normal"},
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    tax_category = _tax_category(data.tax_category_key) if data.tax_category_key else None
    category = Category.objects.create(
        **data.model_dump(exclude={"slug", "tax_category_key"}),
        slug=data.slug or slugify(data.name),
        tax_category=tax_category,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    record_event(ctx, events.CATEGORY_CREATED, {"id": str(category.id), "name": category.name})
    return load_category(category.id)


@operation(
    "inventory.category.bulk_create",
    kind="command",
    permission="inventory.add_category",
    input=CategoryImportIn,
    output=ImportReportOut,
    expose_api=True,
    ai={
        "description": "Create many categories at once (a CSV import); one whose name already exists is skipped, "
        "so repeating the file duplicates nothing.",
        "risk": "high",
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


@operation(
    "inventory.category.update",
    kind="command",
    permission="inventory.change_category",
    input=CategoryPatchIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Change a category, named by its id or name; what is not sent (icon, colour, order, "
        "description) is kept.",
        "risk": "normal",
    },
)
def update_category(ctx: OperationContext, data: CategoryPatchIn) -> dict:
    category = find_category(data.id, data.category, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id", "category"})
    # An empty slug is made again from the name (the new one when it changes), as on create.
    if sent.get("slug") == "":
        sent["slug"] = slugify(sent.get("name", category.name))
    if "tax_category_key" in sent:
        key = sent.pop("tax_category_key")
        sent["tax_category"] = _tax_category(key) if key else None
    changes = {field: value for field, value in sent.items() if getattr(category, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(category, field, value)
        category.updated_by = _actor(ctx)
        category.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.CATEGORY_UPDATED, {"id": str(category.id), "name": category.name})
    return load_category(category.id)


@operation(
    "inventory.category.delete",
    kind="command",
    permission="inventory.delete_category",
    input=CategoryRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a category, named by its id or name: its products stay, only unlinked from it.",
        "risk": "high",
    },
)
def delete_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    """Logical, and every product linked to it (active or not) is unlinked in the same step."""
    category = find_category(data.id, data.category, lock=True)
    product_ids = sorted(ProductCategory.objects.filter(category=category).values_list("product_id", flat=True))
    ProductCategory.objects.filter(category=category).delete()
    category.is_deleted, category.deleted_at, category.updated_by = True, timezone.now(), _actor(ctx)
    category.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
    for product_id in product_ids:
        _record_link(ctx, events.PRODUCT_UNCATEGORIZED, product_id, category.id)
    record_event(ctx, events.CATEGORY_DELETED, {"id": str(category.id), "name": category.name})
    return {"id": category.id}


# Stock (INVENTORY-F13, F14, F15, F18)


@operation(
    "inventory.stock.receive",
    kind="command",
    permission="inventory.adjust_stock",
    input=ReceiveIn,
    output=ProductsOut,
    expose_api=True,
    ai={
        "description": "Record goods received: raises the stock of one or more products (by id, SKU or name), "
        "with the unit cost and the delivery note's number.",
        "risk": "normal",
    },
)
def receive_stock(ctx: OperationContext, data: ReceiveIn) -> dict:
    """All lines or none: a line without a product, with a service or off its unit's step refuses the whole."""
    named = []
    for index, line in enumerate(data.items):
        field = f"items.{index}.product_id" if line.product_id is not None else f"items.{index}.product"
        try:
            named.append((index, field, find_product(line.product_id, line.product).id, line))
        except NotFound as exc:
            raise _line_product_unknown(field) from exc
    products = _locked({product_id for _, _, product_id, _ in named})
    lines = []
    for index, field, product_id, line in named:
        product = products.get(product_id)
        if product is None:  # deleted meanwhile
            raise _line_product_unknown(field)
        if product.product_type == Product.Type.SERVICE:
            raise _service_has_no_stock(field)
        _check_grid(line.qty, product.unit, f"items.{index}.qty")
        lines.append((product_id, line))
    settings = current_settings()
    before = {product_id: product.stock for product_id, product in products.items()}
    for product_id, line in lines:
        product = products[product_id]
        if line.unit_cost is not None:
            product.cost = line.unit_cost
        _move(ctx, product, StockMovement.Type.RECEPTION, line.qty, reference=data.reference, unit_cost=line.unit_cost)
    for product_id, product in products.items():
        _crossing(ctx, product, settings, before[product_id], StockMovement.Type.RECEPTION, data.reference)
    return {"rows": [load_product(product_id) for product_id in dict.fromkeys(product_id for product_id, _ in lines)]}


@operation(
    "inventory.stock.count",
    kind="command",
    permission="inventory.adjust_stock",
    input=CountIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Apply a stock count: the product's balance becomes the ABSOLUTE value counted, with a "
        "mandatory reason; the ledger records the difference.",
        "risk": "normal",
    },
)
def count_stock(ctx: OperationContext, data: CountIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    field = "product_id" if data.product_id is not None else "product"
    if product.product_type == Product.Type.SERVICE:
        raise _service_has_no_stock(field)
    _check_grid(data.stock, product.unit, "stock")
    previous = product.stock
    difference = data.stock - previous
    if difference:
        _move(ctx, product, StockMovement.Type.COUNT, difference, reason=data.reason)
        _crossing(ctx, product, current_settings(), previous, StockMovement.Type.COUNT, "")
    return load_product(product.id)


@operation(
    "inventory.stock.write_off",
    kind="command",
    permission="inventory.adjust_stock",
    input=WriteOffIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Write off stock without a sale (waste, breakage, own consumption) with its reason; a "
        "service or an article without stock control is refused (there is no stock to lower).",
        "risk": "normal",
    },
)
def write_off_stock(ctx: OperationContext, data: WriteOffIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    if product.product_type == Product.Type.SERVICE:
        raise _service_has_no_stock("product_id" if data.product_id is not None else "product")
    _check_grid(data.qty, product.unit, "qty")
    settings = current_settings()
    # Never a silent success: a write-off that would lower nothing says so (2026-10-14).
    if not tracks_stock(product, settings):
        raise Conflict(str(STOCK_NOT_TRACKED), code="inventory.stock_not_tracked", fields={"qty": str(STOCK_NOT_TRACKED)})
    if not settings.allow_sell_without_stock and product.stock < data.qty:
        raise Conflict(str(INSUFFICIENT_STOCK), code="inventory.insufficient_stock", fields={"qty": str(INSUFFICIENT_STOCK)})
    previous = product.stock
    _move(ctx, product, StockMovement.Type.WRITE_OFF, -data.qty, reason=data.reason)
    _crossing(ctx, product, settings, previous, StockMovement.Type.WRITE_OFF, "")
    return load_product(product.id)


# Settings (INVENTORY-F19)


@operation(
    "inventory.config.update",
    kind="command",
    permission="inventory.manage_settings",
    input=ConfigPatchIn,
    output=ConfigOut,
    expose_api=True,
    ai={
        "description": "Change the inventory settings: allow selling without stock, the default low-stock "
        "threshold and whether stock is tracked (an article's own decision wins).",
        "risk": "normal",
    },
)
def update_config(ctx: OperationContext, data: ConfigPatchIn) -> dict:
    """One row per business; changing the threshold does not touch the products that exist."""
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    changes = {field: value for field, value in sent.items() if getattr(settings, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.CONFIG_UPDATED, {})
    return config_row(settings)


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time.

    Two first saves at once: the second waits on the single-row constraint and then locks the first's.
    """
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with transaction.atomic():
            return Settings.objects.create(updated_by=_actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


# Reactions to the Sales app (events.py; INVENTORY-F21, F22, F23, F24)


@operation(
    "inventory.stock.apply_sale",
    kind="command",
    permission=SYSTEM,
    input=SaleCompletedIn,
    output=SaleStockOut,
    ai={
        "description": "Lower the stock of a paid sale's articles and of its menus' components (run by the "
        "platform when Sales reports a paid sale).",
        "risk": "high",
    },
)
def apply_sale(ctx: OperationContext, data: SaleCompletedIn) -> dict:
    """Each line (or each component of a menu) lowers its article once, with the sale as reference.

    Services, free-price lines, unknown or deleted products and articles without stock control move
    nothing; without «selling without stock» an article that does not reach is not lowered. A sale
    seen before, or voided before it arrived, changes nothing.
    """
    sale, created = _sale_stock(data.sale_id, SaleStock.State.UNMOVED)
    if not created:
        return _sale_result(sale, applied=False, movements=0)
    # INVENTORY-F16: the numbers the ledger shows and finds this sale by.
    sale.sale_number = data.sale_number[: SaleStock._meta.get_field("sale_number").max_length]
    sale.document_number = _document_number(ctx, data.sale_id)[: SaleStock._meta.get_field("document_number").max_length]
    units = [
        (unit.product_id, unit.quantity)
        for item in data.items
        for unit in (item.components or [item])
        if unit.product_id is not None and not unit.is_service and unit.quantity > 0
    ]
    products = _locked({product_id for product_id, _ in units})
    settings = current_settings()
    before = {product_id: product.stock for product_id, product in products.items()}
    moved = 0
    for product_id, quantity in units:
        product = products.get(product_id)
        if product is None or not tracks_stock(product, settings):
            continue
        if not settings.allow_sell_without_stock and product.stock < quantity:
            continue
        _move(ctx, product, StockMovement.Type.SALE, -quantity, reference=str(data.sale_id))
        moved += 1
    for product_id, product in products.items():
        if product.stock != before[product_id]:
            _crossing(ctx, product, settings, before[product_id], StockMovement.Type.SALE, str(data.sale_id))
    if moved:
        sale.state = SaleStock.State.MOVED
    sale.save(update_fields=["state", "sale_number", "document_number", "updated_at"])
    return _sale_result(sale, applied=True, movements=moved)


@operation(
    "inventory.stock.restore_sale",
    kind="command",
    permission=SYSTEM,
    input=SaleVoidedIn,
    output=SaleStockOut,
    ai={
        "description": "Give back to each article exactly what a voided sale took, read from the ledger (run by "
        "the platform when Sales reports a void).",
        "risk": "high",
    },
)
def restore_sale(ctx: OperationContext, data: SaleVoidedIn) -> dict:
    """Restores once what the ledger says the sale lowered, even if the article stopped tracking stock.

    A void that arrives before its sale is noted, so the late sale lowers nothing. A product deleted
    after the sale gets nothing back.
    """
    sale, created = _sale_stock(data.sale_id, SaleStock.State.VOIDED)
    if not created and sale.state == SaleStock.State.VOIDED:
        return _sale_result(sale, applied=False, movements=0)
    restored = 0
    if not created and sale.state == SaleStock.State.MOVED:
        taken = _still_out(data.sale_id)
        products = _locked(set(taken))
        settings = current_settings()
        for product_id, product in products.items():
            if taken[product_id] <= 0:
                continue
            previous = product.stock
            _move(ctx, product, StockMovement.Type.VOID, taken[product_id], reference=str(data.sale_id))
            _crossing(ctx, product, settings, previous, StockMovement.Type.VOID, str(data.sale_id))
            restored += 1
    if not created:
        sale.state = SaleStock.State.VOIDED
        sale.save(update_fields=["state", "updated_at"])
    return _sale_result(sale, applied=True, movements=restored)


@operation(
    "inventory.stock.restore_refund",
    kind="command",
    permission=SYSTEM,
    input=SaleRefundedIn,
    output=RefundStockOut,
    ai={
        "description": "Put back in the stock the units a refund of Sales returns, never more than its sale took "
        "(run by the platform when Sales reports a refund).",
        "risk": "high",
    },
)
def restore_refund(ctx: OperationContext, data: SaleRefundedIn) -> dict:
    """Each returned line gives its article back once per refund (INVENTORY-F24).

    Never more than the sale still has out according to the ledger (what it lowered minus what earlier
    refunds gave back), so nothing it did not lower comes back: a service, a free-price line, an article
    without stock control or one that did not reach. An article that no longer tracks its stock is left
    as it is. A refund of a sale voided (or not seen) gives nothing back. The movement «refund» carries
    the sale as reference, so a later void restores only what is still out.
    """
    note, created = _refund_stock(data.refund_id, data.sale_id)
    if not created:
        return _refund_result(note, applied=False, movements=0)
    sale = SaleStock.objects.select_for_update().filter(sale_id=data.sale_id).first()
    returned: dict[UUID, Decimal] = defaultdict(Decimal)
    for line in data.lines:
        if line.product_id is not None and line.quantity > 0:
            returned[line.product_id] += line.quantity
    moved = 0
    if sale is not None and sale.state == SaleStock.State.MOVED and returned:
        out = _still_out(data.sale_id)
        settings = current_settings()
        for product_id, product in _locked(set(returned)).items():
            quantity = min(returned[product_id], out[product_id])
            if quantity <= 0 or not tracks_stock(product, settings):
                continue
            previous = product.stock
            _move(ctx, product, StockMovement.Type.REFUND, quantity, reason=data.reason, reference=str(data.sale_id))
            _crossing(ctx, product, settings, previous, StockMovement.Type.REFUND, str(data.sale_id))
            moved += 1
    if moved:
        note.movements = moved
        note.save(update_fields=["movements"])
    return _refund_result(note, applied=True, movements=moved)


# Helpers


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _q(value: Decimal) -> str:
    """A quantity in an event: always three decimals, so its consumers read it the same way."""
    return str(value.quantize(THOUSANDTHS))


def _tax_category(key: str, field: str = "tax_category_key") -> TaxCategory:
    """The active tax category of ``key``, held for the write that names it (see ``held``)."""
    tax_category = next(iter(held(TaxCategory.objects.filter(key=key, is_active=True)[:1])), None)
    if tax_category is None:
        raise InvalidPayload(str(TAX_CATEGORY_UNKNOWN), code="invalid_field", fields={field: str(TAX_CATEGORY_UNKNOWN)})
    return tax_category


def _live_categories(category_ids: list[UUID]) -> list[Category]:
    """The live categories of ``category_ids``, held for the write that puts a product in them (see ``held``)."""
    wanted = list(dict.fromkeys(category_ids))
    live = Category.objects.filter(pk__in=wanted, is_deleted=False).order_by("id")
    categories = {category.id: category for category in held(live)}
    if len(categories) != len(wanted):
        raise InvalidPayload(str(CATEGORY_UNKNOWN), code="invalid_field", fields={"category_ids": str(CATEGORY_UNKNOWN)})
    return [categories[category_id] for category_id in wanted]


def _check_grid(qty: Decimal, unit: str, field: str) -> None:
    if not fits_unit(qty, unit):
        message = str(OFF_GRID) % {"step": f"{quantity_text(increment_of(unit))} {unit}"}
        raise Conflict(message, code="inventory.off_grid_quantity", fields={field: message})


def _check_pricing_unit(unit: str, pricing_unit: str) -> None:
    if UNIT_SPECS[unit].category != UNIT_SPECS[pricing_unit].category:
        message = str(PRICING_UNIT_MISMATCH)
        raise InvalidPayload(message, code="invalid_field", fields={"pricing_unit": message})


def _same_kind(pricing_unit: str, unit: str) -> str:
    """The pricing unit to keep when the unit changes: the same one if it measures alike, else the new unit."""
    return pricing_unit if UNIT_SPECS[pricing_unit].category == UNIT_SPECS[unit].category else unit


def _line_product_unknown(field: str) -> InvalidPayload:
    message = str(LINE_PRODUCT_UNKNOWN)
    return InvalidPayload(message, code="invalid_field", fields={field: message})


def _service_has_no_stock(field: str) -> Conflict:
    return Conflict(str(SERVICE_HAS_NO_STOCK), code="inventory.service_has_no_stock", fields={field: str(SERVICE_HAS_NO_STOCK)})


def _save(product: Product, **options) -> None:
    """Save in a savepoint, so that a SKU or an EAN-13 taken by another live product says so."""
    try:
        with transaction.atomic():
            product.save(**options)
    except IntegrityError as exc:
        for constraint, (field, message, code) in _PRODUCT_CONSTRAINTS.items():
            if constraint in str(exc):
                raise Conflict(str(message), code=code, fields={field: str(message)}) from exc
        raise


def _link(product: Product, categories: list[Category]) -> None:
    ProductCategory.objects.bulk_create([ProductCategory(product=product, category=category) for category in categories])


def _record_link(ctx: OperationContext, name: str, product_id: UUID, category_id: UUID) -> None:
    record_event(ctx, name, {"product_id": str(product_id), "category_id": str(category_id)})


def _product_payload(product: Product) -> dict:
    return {
        "id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "product_type": product.product_type,
        "price": product.price,
        "cost": product.cost,
        "unit": product.unit,
        "tax_category_key": product.tax_category.key if product.tax_category else None,
        "is_active": product.is_active,
        "is_sold_out": product.is_sold_out,
        "track_stock": product.track_stock,
    }


def _locked(product_ids: set[UUID]) -> dict[UUID, Product]:
    """The live products, their rows locked in the order of their ids (no two writes wait in a circle)."""
    products = Product.objects.select_for_update().filter(pk__in=product_ids, is_deleted=False).order_by("id")
    return {product.id: product for product in products}


def _move(
    ctx: OperationContext,
    product: Product,
    movement_type: str,
    qty: Decimal,
    *,
    reason: str = "",
    reference: str = "",
    unit_cost: int | None = None,
) -> StockMovement:
    """The balance and its movement, written together; ``product``'s row is already locked."""
    product.stock += qty
    product.updated_by = _actor(ctx)
    product.save(update_fields=["stock", "cost", "updated_by", "updated_at"])
    movement = StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        qty=qty,
        stock_after=product.stock,
        reason=reason,
        reference=reference,
        unit_cost=unit_cost,
        actor=_actor(ctx),
    )
    record_event(
        ctx,
        events.STOCK_CHANGED,
        {"product_id": str(product.id), "movement_type": movement_type, "qty": _q(qty), "stock_after": _q(product.stock)},
    )
    return movement


def _crossing(
    ctx: OperationContext, product: Product, settings: Settings, previous: Decimal, movement_type: str, reference: str
) -> None:
    """INVENTORY-F18: an article with stock control crossing its threshold, down («below») or up («recovered»).

    Decided once per operation on the total it moved, so staying on either side never repeats it.
    """
    if not tracks_stock(product, settings):
        return
    threshold, current = product.low_stock_threshold, product.stock
    if previous > threshold >= current:
        crossing = "below"
    elif previous <= threshold < current:
        crossing = "recovered"
    else:
        return
    record_event(
        ctx,
        events.STOCK_THRESHOLD_CROSSED,
        {
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "previous_quantity": _q(previous),
            "current_quantity": _q(current),
            "low_stock_threshold": _q(threshold),
            "crossing": crossing,
            "movement_type": movement_type,
            "reference": reference,
        },
    )


def _sale_stock(sale_id: UUID, state: str) -> tuple[SaleStock, bool]:
    """The sale's note, created with ``state`` if it is new, or the existing one with its row locked.

    Two deliveries of the same sale at once: the second waits on the unique key until the first commits.
    """
    try:
        with transaction.atomic():
            return SaleStock.objects.create(sale_id=sale_id, state=state), True
    except IntegrityError:
        return SaleStock.objects.select_for_update().get(sale_id=sale_id), False


def _document_number(ctx: OperationContext, sale_id: UUID) -> str:
    """The number of the sale's ticket or invoice, read from Sales by its operation; empty when Sales is not
    reachable, does not know the sale or it has no fiscal document yet."""
    try:
        get_sale = get("sale.sale.get")
        found = get_sale(ctx, get_sale.input.model_validate({"sale_id": str(sale_id)}))
    except (UnknownOperation, AppInactive, PermissionDenied, NotFound):
        return ""
    return found.invoice_number


def _sale_result(sale: SaleStock, *, applied: bool, movements: int) -> dict:
    return {"sale_id": sale.sale_id, "state": sale.state, "applied": applied, "movements": movements}


def _still_out(sale_id: UUID) -> dict[UUID, Decimal]:
    """Per article, what the sale lowered and no refund has given back yet, read from the ledger."""
    out: dict[UUID, Decimal] = defaultdict(Decimal)
    for product_id, qty in StockMovement.objects.filter(
        movement_type__in=[StockMovement.Type.SALE, StockMovement.Type.REFUND], reference=str(sale_id)
    ).values_list("product_id", "qty"):
        out[product_id] -= qty
    return out


def _refund_stock(refund_id: UUID, sale_id: UUID) -> tuple[RefundStock, bool]:
    """The refund's note, created if it is new; two deliveries at once: the second waits on the unique key."""
    try:
        with transaction.atomic():
            return RefundStock.objects.create(refund_id=refund_id, sale_id=sale_id), True
    except IntegrityError:
        return RefundStock.objects.select_for_update().get(refund_id=refund_id), False


def _refund_result(note: RefundStock, *, applied: bool, movements: int) -> dict:
    return {"refund_id": note.refund_id, "sale_id": note.sale_id, "applied": applied, "movements": movements}


# Imports


def _check_product_row(row, name: str, sku: str, settings: Settings, tax_categories: dict) -> dict | str:
    """The fields of a new product from one CSV row (its name and SKU already read), or why it cannot be."""
    ean13 = _unguarded(row.ean13.strip())
    if len(name) > 200 or len(sku) > 64 or len(ean13) > 13:
        return str(ROW_TOO_LONG)
    price, cost = parse_amount(row.price), parse_amount(row.cost)
    if price is None or cost is None:
        return str(ROW_PRICE_NOT_NUMERIC)
    if max(price, cost) > MAX_CENTS:
        return str(ROW_AMOUNT_TOO_LARGE)
    unit = row.unit.strip().lower() or Unit.UNIT
    if unit not in Unit.values:
        return str(ROW_UNIT_UNKNOWN) % {"text": row.unit.strip()}
    stock = parse_quantity(row.stock) if row.stock.strip() else Decimal("0")
    threshold = (
        parse_quantity(row.low_stock_threshold) if row.low_stock_threshold.strip() else Decimal(settings.low_stock_threshold)
    )
    if stock is None or threshold is None:
        return str(ROW_QUANTITY_NOT_NUMERIC)
    if max(stock, threshold) >= MAX_QUANTITY:
        return str(ROW_QUANTITY_TOO_LARGE)
    if not fits_unit(stock, unit) or not fits_unit(threshold, unit):
        return str(ROW_OFF_GRID)
    key = row.tax_category_key.strip()
    if not key:
        return str(ROW_TAX_CATEGORY_MISSING)
    if key not in tax_categories:
        return str(ROW_TAX_CATEGORY_UNKNOWN) % {"text": key}
    return {
        "name": name,
        "sku": sku,
        "ean13": ean13 or None,
        "description": _unguarded(row.description),
        "price": price,
        "cost": cost,
        "stock": stock,
        "low_stock_threshold": threshold,
        "unit": unit,
        "pricing_unit": unit,
        "tax_category": tax_categories[key],
    }


def _unguarded(text: str) -> str:
    """A cell without the apostrophe the export put in front of what a spreadsheet would run."""
    return text[1:] if text.startswith(EXPORT_GUARD) else text


def parse_amount(text: str) -> int | None:
    """Cents of an amount as a CSV or a person writes it, or ``None`` if it is not one (empty = 0).

    2,20 · 2.20 · 1.234,56 · 1,234.56 · 12,50 € · €2.20: with both separators, the rightmost one is the
    decimal one; with only commas, the comma is; never more than two decimals, never negative.
    """
    raw = _AMOUNT_NOISE.sub("", text)
    if not raw:
        return 0
    normalized = _decimal_point(raw)
    if normalized is None or not _AMOUNT_RE.match(normalized):
        return None
    return int(Decimal(normalized) * 100)


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
