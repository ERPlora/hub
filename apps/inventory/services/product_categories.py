"""A product put in or taken out of a category (INVENTORY-F08)."""

from live.context import OperationContext
from live.operations import operation

from apps.inventory import events
from apps.inventory.models import ProductCategory
from apps.inventory.queries.reads import find_category, find_product
from apps.inventory.schemas.product_categories import ProductCategoryIn, ProductCategoryLinkOut
from apps.inventory.services.writes import _record_link


@operation(
    "inventory.product_category.add",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_product",
    input=ProductCategoryIn,
    output=ProductCategoryLinkOut,
    expose_api=True,
    ai={
        "description": "Put a product in a category so that the till groups it there.",
        "risk": "normal",
        "check": "inventory.product_category.check",
        "asks": {
            "en": (
                "put the coffee in the Breakfasts category",
                "classify the croissant as bakery",
                "move the tea to the drinks family",
            ),
            "es": (
                "clasifica el café en la categoría Desayunos",
                "mete el cruasán en la familia Bollería",
                "clasifica el té en la categoría Bebidas",
            ),
        },
    },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_product",
    input=ProductCategoryIn,
    output=ProductCategoryLinkOut,
    expose_api=True,
    ai={
        "description": "Take a product out of a category.",
        "risk": "normal",
        "check": "inventory.product_category.check",
        "asks": {
            "en": (
                "take the coffee out of the drinks category",
                "unclassify the croissant from bakery",
            ),
            "es": (
                "saca el café de la categoría bebidas",
                "quita el cruasán de la familia Bollería",
            ),
        },
    },
)
def remove_product_category(ctx: OperationContext, data: ProductCategoryIn) -> dict:
    product = find_product(data.product_id, data.product, lock=True)
    category = find_category(data.category_id, data.category)
    removed, _ = ProductCategory.objects.filter(product=product, category=category).delete()
    if removed:
        _record_link(ctx, events.PRODUCT_UNCATEGORIZED, product.id, category.id)
    return {"product_id": product.id, "category_id": category.id, "changed": bool(removed)}
