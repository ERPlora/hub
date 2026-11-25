"""The products of the catalog (INVENTORY-F01 to F05, F20, F26, F29, F34, F35): create, edit, delete, restore,
sell out and bring back from a separate copy, with the SKU and the EAN-13 a live product keeps to itself."""

from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import Category, Product, ProductCategory, StockMovement, UNIT_SPECS
from apps.inventory.queries.products import load_product
from apps.inventory.queries.reads import find_product, held
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas.fields import DeletedOut, ProductRefIn
from apps.inventory.schemas.products import (
    ProductIn,
    ProductOut,
    ProductPatchIn,
    ProductRecoverIn,
    ProductRestoreIn,
    ProductSoldOutIn,
)
from apps.inventory.services.movements import _move
from apps.inventory.services.product_images import _change_image
from apps.inventory.services.writes import (
    SYSTEM,
    _actor,
    _check_grid,
    _product_payload,
    _record_link,
    _service_has_no_stock,
    _tax_category,
)
from base import images
from base.assistant import card_order

SKU_TAKEN = _("That SKU already exists in the catalog.")
EAN13_TAKEN = _("Another product of the catalog already has that EAN-13.")

CATEGORY_UNKNOWN = _("This category does not exist.")

UNIT_HAS_STOCK = _(
    "The unit of a product with stock cannot be changed. Count its stock to zero and change it afterwards."
)
PRICING_UNIT_MISMATCH = _("The price must refer to a unit of the same kind as the product's unit.")

_PRODUCT_CONSTRAINTS = {
    "inventory_product_live_sku_unique": ("sku", SKU_TAKEN, "inventory.sku_taken"),
    "inventory_product_live_ean13_unique": ("ean13", EAN13_TAKEN, "inventory.ean13_taken"),
}




@operation(
    "inventory.product.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.add_product",
    input=ProductIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Create a product of the catalog with its tax category, its categories and, if given, "
        "its initial stock.",
        "risk": "normal",
        "summary": card_order.said_first("name", "price", "tax_category_key"),
        "asks": {
            "en": (
                "add a new product: Iced Coffee, 3.50",
                "create the product Croissant at 2 euros",
                "add a lemon tart to my catalog at 4 euros",
            ),
            "es": (
                "crea un producto nuevo: Café helado a 3,50",
                "da de alta el cruasán, vale 2 euros",
                "añade una tarta de limón al catálogo a 4 euros",
            ),
        },
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
        allergens=data.allergens,
        product_type=data.product_type,
        price=data.price,
        cost=data.cost,
        low_stock_threshold=threshold,
        unit=data.unit,
        price_quantity=data.price_quantity,
        pricing_unit=pricing_unit,
        tax_category=tax_category,
        track_stock=None if data.product_type == Product.Type.SERVICE else data.track_stock,
        is_active=data.is_active,
        show_on_website=data.show_on_website,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save(product)
    _link(product, categories)
    record_event(ctx, events.PRODUCT_CREATED, _created_payload(product, categories))
    for category in sorted(categories, key=lambda category: category.id):
        _record_link(ctx, events.PRODUCT_CATEGORIZED, product.id, category.id)
    if data.initial_stock:
        _move(ctx, product, StockMovement.Type.INITIAL, data.initial_stock)
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.product.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_product",
    input=ProductPatchIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Change a product, named by its id, SKU or name: its data, active or not, its stock "
        "control, its categories and whether the website's catalog shows it. The SKU, the type and the stock are not "
        "changed here.",
        "risk": "normal",
        "check": "inventory.product.get",
        "asks": {
            "en": (
                "change the price of the coffee to 1.80",
                "rename the Tea product and make it inactive",
                "the croissant now costs 2.20",
                "hide the product Coffee from the website",
            ),
            "es": (
                "cámbiale el precio al café a 1,80",
                "renombra el producto Té y desactívalo",
                "el cruasán ahora cuesta 2,20",
                "oculta el producto Café de la página web",
            ),
        },
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
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.product.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.delete_product",
    input=ProductRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a product of the catalog, named by its id, SKU or name (logically: its movements "
        "stay and its SKU and EAN-13 are freed).",
        "risk": "high",
        "check": "inventory.product.get",
        "asks": {
            "en": (
                "delete the product Old Tea",
                "remove the croissant from the catalog",
            ),
            "es": (
                "borra el producto Té viejo",
                "quita el cruasán del catálogo",
            ),
        },
    },
)
def delete_product(ctx: OperationContext, data: ProductRefIn) -> dict:
    """INVENTORY-F04: its movements stay; its photo of its own goes with it (INVENTORY-F31), once this is saved. An
    image of the library is ERPlora's, not the business's: it stays, so that restoring it (INVENTORY-F34) shows it."""
    product = find_product(data.id, data.product, lock=True)
    photo = product.image
    product.is_deleted, product.is_active, product.deleted_at = True, False, timezone.now()
    product.image = photo if images.kind_of(photo) == images.CATALOG else ""
    product.updated_by = _actor(ctx)
    product.save(update_fields=["is_deleted", "is_active", "deleted_at", "image", "updated_by", "updated_at"])
    images.let_go(ctx, photo)
    record_event(ctx, events.PRODUCT_DELETED, {"id": str(product.id), "sku": product.sku, "name": product.name})
    return {"id": product.id}


@operation(
    "inventory.product.restore",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=ProductRestoreIn,
    output=ProductOut,
    ai={
        "description": "Bring a deleted product back to the catalog, the same product with its stock movements and "
        "its image of the library (run by the platform when ERPlora's staff recovers the business from a separate "
        "copy).",
        "risk": "normal",
    },
)
def restore_product(ctx: OperationContext, data: ProductRestoreIn) -> dict:
    """INVENTORY-F34: a deleted product back in every list and in the till, the same product (deleting keeps it,
    INVENTORY-F04): its id, its codes, its categories, its stock and its image of the library, with every movement that
    hangs from it. One deleted before deleting kept that image has none: it gets back the one it showed in the copy,
    as one made again does (``base.images.from_copy``). Active and on sale, as unarchiving does: the «sold out» it had
    was another day's. Not while another live product holds its SKU or its EAN-13 (it was made again since). Repeating
    it on a product already back answers well and announces again, as deleting does, and changes nothing of it."""
    product = find_product(data.id, None, lock=True, rows=Product.objects.all())
    if product.is_deleted:
        product.is_deleted, product.deleted_at, product.is_active, product.is_sold_out = False, None, True, False
        product.image = product.image or images.from_copy(ctx, data.image)
        product.updated_by = _actor(ctx)
        _save(
            product,
            update_fields=["is_deleted", "deleted_at", "is_active", "is_sold_out", "image", "updated_by", "updated_at"],
        )
    record_event(ctx, events.PRODUCT_RESTORED, _product_payload(product))
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.product.set_sold_out",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_product",
    input=ProductSoldOutIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Mark a product sold out («86»: the till stops offering it, it stays active) or put it "
        "back on sale, named by its id, SKU or name.",
        "risk": "normal",
        "check": "inventory.product.get",
        "asks": {
            "en": (
                "mark the Tea as sold out for today",
                "we ran out of croissants, stop offering them",
                "put the coffee back on sale",
            ),
            "es": (
                "marca el té con hielo como agotado",
                "se nos han acabado los cruasanes, que no se vendan",
                "vuelve a poner a la venta el café",
            ),
        },
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
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.product.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=ProductRecoverIn,
    output=ProductOut,
    ai={
        "description": "Make again a product the business no longer holds, with the image of the library it had (run "
        "by the platform when ERPlora's staff recovers the business from a separate copy).",
        "risk": "normal",
    },
)
def recover_product(ctx: OperationContext, data: ProductRecoverIn) -> dict:
    """BASE-F114: a product of a separate copy made again as its screen makes it, all or nothing: the product by
    ``inventory.product.create``, then the image of the library it showed there (INVENTORY-F30), unless the library no
    longer has it; never a photo of its own, deleted with the product (``base.images.from_copy``)."""
    made = create_product(ctx, ProductIn.model_validate(data.model_dump(include=set(ProductIn.model_fields))))
    if image := images.from_copy(ctx, data.image):
        _change_image(ctx, find_product(made.id, None), image)
    return load_product(made.id, ctx.scope)


def _live_categories(category_ids: list[UUID]) -> list[Category]:
    """The live categories of ``category_ids``, held for the write that puts a product in them (see ``held``)."""
    wanted = list(dict.fromkeys(category_ids))
    live = Category.objects.filter(pk__in=wanted, is_deleted=False).order_by("id")
    categories = {category.id: category for category in held(live)}
    if len(categories) != len(wanted):
        raise InvalidPayload(str(CATEGORY_UNKNOWN), code="invalid_field", fields={"category_ids": str(CATEGORY_UNKNOWN)})
    return [categories[category_id] for category_id in wanted]


def _check_pricing_unit(unit: str, pricing_unit: str) -> None:
    if UNIT_SPECS[unit].category != UNIT_SPECS[pricing_unit].category:
        message = str(PRICING_UNIT_MISMATCH)
        raise InvalidPayload(message, code="invalid_field", fields={"pricing_unit": message})


def _same_kind(pricing_unit: str, unit: str) -> str:
    """The pricing unit to keep when the unit changes: the same one if it measures alike, else the new unit."""
    return pricing_unit if UNIT_SPECS[pricing_unit].category == UNIT_SPECS[unit].category else unit


def _save(product: Product, **options) -> None:
    """Save in a savepoint, so that a SKU or an EAN-13 taken by another live product says so."""
    try:
        with atomic():
            product.save(**options)
    except IntegrityError as exc:
        for constraint, (field, message, code) in _PRODUCT_CONSTRAINTS.items():
            if constraint in str(exc):
                raise Conflict(str(message), code=code, fields={field: str(message)}) from exc
        raise


def _link(product: Product, categories: list[Category]) -> None:
    ProductCategory.objects.bulk_create([ProductCategory(product=product, category=category) for category in categories])


def _created_payload(product: Product, categories: list[Category]) -> dict:
    return {
        "id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "category_ids": sorted(str(category.id) for category in categories),
    }
