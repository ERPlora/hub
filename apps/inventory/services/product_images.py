"""The image a product shows (INVENTORY-F30, F31): one of the shared library or a photo of its own
(``base.images``)."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.inventory import events
from apps.inventory.models import Product
from apps.inventory.queries.products import load_product
from apps.inventory.queries.reads import find_product
from apps.inventory.schemas.product_images import ProductImageIn, ProductImageUploadIn
from apps.inventory.schemas.products import ProductOut
from apps.inventory.services.writes import _actor, _product_payload
from base import images

#: Where a product's own photos are kept under its hub's prefix: the folder ``public_media`` serves (apps.py).
PHOTOS = "inventory/products/"


@operation(
    "inventory.product.set_image",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.change_product",
    input=ProductImageIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Set the image («foto») a product shows on the till and in its lists («ponle foto al café con "
        "leche»), named by its id, SKU or name: an image of ERPlora's shared library by its reference (catalog:<folder>/<name>, from "
        "inventory.product.suggest_image or base.catalog_image.search), or empty to show none (its initials).",
        "risk": "normal",
        "check": "inventory.product.get",
        "asks": {
            "en": (
                "put an image on the latte",
                "set the image of the croissant",
                "remove the image of the tea",
            ),
            "es": (
                "ponle una imagen al café con leche",
                "pon una imagen al cruasán",
                "quita la imagen del producto té",
            ),
        },
    },
)
def set_image(ctx: OperationContext, data: ProductImageIn) -> dict:
    """INVENTORY-F30: an image of the library or none; anything else (a photo of its own too, which only its upload
    writes) is refused before anything changes. The photo of its own it let go is deleted once this is saved."""
    product = find_product(data.id, data.product, lock=True)
    images.check(ctx, data.image)
    _change_image(ctx, product, data.image)
    return load_product(product.id, ctx.scope)


@operation(
    "inventory.product.upload_image",
    kind="command",
    permission="inventory.change_product",
    input=ProductImageUploadIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Not an assistant tool (it takes the photo the person picks in the product's form): keeps a "
        "photo of the product, a JPG, PNG or WebP of 2 MB at most, as its image.",
        "risk": "normal",
    },
)
def upload_image(ctx: OperationContext, data: ProductImageUploadIn) -> dict:
    """INVENTORY-F31: the photo becomes a 512 × 512 WebP of its own (``base.images``), within the plan's space, and
    takes the place of the one the product had, which is deleted once this is saved."""
    webp = images.to_webp(images.decode(data.data_base64, language=ctx.language), language=ctx.language)
    product = find_product(data.id, data.product, lock=True)
    _change_image(ctx, product, images.keep_photo(ctx, PHOTOS, webp))
    return load_product(product.id, ctx.scope)


def _change_image(ctx: OperationContext, product: Product, image: str) -> None:
    """Show ``image`` on ``product`` (no change, no event); the photo of its own it let go is deleted once saved."""
    if product.image == image:
        return
    previous = product.image
    product.image = image
    product.updated_by = _actor(ctx)
    product.save(update_fields=["image", "updated_by", "updated_at"])
    record_event(ctx, events.PRODUCT_UPDATED, _product_payload(product))
    images.let_go(ctx, previous)
