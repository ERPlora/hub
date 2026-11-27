"""A product's barcode label (INVENTORY-F25), printed through Printing's queue."""

from decimal import Decimal

from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, PermissionDenied
from live.operations import UnknownOperation, get, operation

from apps.inventory.queries.reads import find_product
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.labels import PrintLabelOut
from base import operations as platform

LABEL_QUEUE_UNAVAILABLE = _("The print queue is not available here: print the label from the browser.")
SKU_NOT_BARCODE = _(
    "This SKU cannot be turned into a barcode: use letters without accents, digits and signs."
)


@operation(
    "inventory.product.print_label",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="inventory.view_product",
    input=ProductRefIn,
    output=PrintLabelOut,
    expose_api=True,
    ai={
        "description": "Print the barcode label of a product (its name, its SKU as the code and its price) on the "
        "printer of the label function, named by its id, SKU or name; each call prints one label. When the answer "
        "says no device that prints that printer is on, say it stays in the queue until a device set up in Printing › "
        "Devices prints it, never that it was printed.",
        "risk": "normal",
        "check": "inventory.product.get",
        "asks": {
            "en": (
                "print a label for the coffee",
                "I need the barcode label of the croissant",
            ),
            "es": (
                "imprime una etiqueta del café",
                "necesito la etiqueta con el código de barras del cruasán",
            ),
        },
    },
)
def print_label(ctx: OperationContext, data: ProductRefIn) -> dict:
    """INVENTORY-F25: Printing's queue takes the label (PRINTING-F12); a person who cannot reach it gets
    ``inventory.label_queue_unavailable`` and nothing queued, so the screen prints from the browser."""
    product = find_product(data.id, data.product)
    currency = platform.business_currency(ctx.scope)
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
                        "price": float(Decimal(product.price).scaleb(-get_currency_precision(currency))),
                    },
                    "currency": currency,
                    "source_app": "inventory",
                    "source_ref": product.sku,
                }
            ),
        )
    except (UnknownOperation, AppInactive, PermissionDenied):
        raise Conflict(str(LABEL_QUEUE_UNAVAILABLE), code="inventory.label_queue_unavailable") from None
    return {"job_id": queued.job.id, "printer_name": queued.job.printer_name, "waits_for_device": queued.waits_for_device}
