"""The product categories (INVENTORY-F06, F07): create, edit, delete and bring back from a separate copy."""

from django.utils import timezone
from django.utils.text import slugify
from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import Category, Product, ProductCategory
from apps.inventory.queries.categories import load_category
from apps.inventory.queries.reads import find_category, held
from apps.inventory.schemas.categories import CategoryIn, CategoryOut, CategoryPatchIn, CategoryRecoverIn
from apps.inventory.schemas.fields import CategoryRefIn, DeletedOut
from apps.inventory.services.writes import SYSTEM, _actor, _next_category_order, _record_link, _tax_category


@operation(
    "inventory.category.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.add_category",
    input=CategoryIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Create a product category; its slug is made from the name when not given.",
        "risk": "normal",
        "asks": {
            "en": (
                "create a category called Desserts",
                "add a new family for the till: Wines",
            ),
            "es": (
                "crea una categoría que se llame Postres",
                "añade una familia nueva para el TPV: Vinos",
            ),
        },
    },
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    return load_category(_new_category(ctx, data).id)


@operation(
    "inventory.category.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=CategoryRecoverIn,
    output=CategoryOut,
    ai={
        "description": "Bring a deleted category back as a new one, with the deleted products it had back in it (run "
        "by the platform when ERPlora's staff recovers the business from a separate copy).",
        "risk": "normal",
    },
)
def recover_category(ctx: OperationContext, data: CategoryRecoverIn) -> dict:
    """INVENTORY-F07: the category created as its screen creates it, and each of ``product_ids`` the business still
    holds deleted put back in it, so that restoring it (INVENTORY-F34) brings it back inside. A live product stays as
    the business keeps it."""
    category = _new_category(ctx, data)
    for product in held(Product.objects.filter(pk__in=data.product_ids, is_deleted=True).order_by("id")):
        ProductCategory.objects.create(product=product, category=category)
        _record_link(ctx, events.PRODUCT_CATEGORIZED, product.id, category.id)
    return load_category(category.id)


def _new_category(ctx: OperationContext, data: CategoryIn) -> Category:
    tax_category = _tax_category(data.tax_category_key) if data.tax_category_key else None
    category = Category.objects.create(
        **data.model_dump(include=CategoryIn.model_fields.keys() - {"slug", "order", "tax_category_key"}),
        slug=data.slug or slugify(data.name),
        order=_next_category_order() if data.order is None else data.order,
        tax_category=tax_category,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    record_event(ctx, events.CATEGORY_CREATED, {"id": str(category.id), "name": category.name})
    return category


@operation(
    "inventory.category.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_category",
    input=CategoryPatchIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Change a category, named by its id or name; what is not sent (icon, colour, order, "
        "description) is kept.",
        "risk": "normal",
        "check": "inventory.category.get",
        "asks": {
            "en": (
                "rename the Drinks category to Beverages",
                "change the colour of the Desserts family",
            ),
            "es": (
                "renombra la categoría Bebidas a Refrescos",
                "cámbiale el color a la familia Postres",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.delete_category",
    input=CategoryRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a category, named by its id or name: its products stay, only unlinked from it.",
        "risk": "high",
        "check": "inventory.category.get",
        "asks": {
            "en": (
                "delete the Desserts category",
                "remove the family Wines from the till",
            ),
            "es": (
                "borra la categoría Postres",
                "quita la familia Vinos del TPV",
            ),
        },
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
