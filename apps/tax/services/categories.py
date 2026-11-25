"""The writes of tax categories, and the category a write names (TAX-F02)."""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import TaxCategory
from apps.tax.queries.categories import CATEGORY_NOT_FOUND, category_row
from apps.tax.queries.naming import category_by_reference
from apps.tax.schemas.categories import CategoryIn, CategoryOut

CATEGORY_EXISTS = _("There is already a tax category with that key.")


@operation(
    "tax.category.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=CategoryIn,
    output=CategoryOut,
    ai={
        "asks": {
            "en": (
                "create a tax category for books",
                "add a VAT category called Takeaway food",
                "new tax category product.flowers named Flowers",
            ),
            "es": (
                "da de alta una categoría fiscal para los libros",
                "añade una categoría de IVA que se llame Comida para llevar",
                "nueva categoría de impuestos product.flores con el nombre Flores",
            ),
        },
        "description": "Create a tax category with its key (the one products and services link to, such as "
        "product.books) and its name. It brings no rate: create its rule next.",
        "risk": "normal",
    },
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    try:
        with atomic():
            category = TaxCategory.objects.create(**data.model_dump())
    except IntegrityError:  # the key is the only unique field
        raise Conflict(
            CATEGORY_EXISTS,
            code="tax.category_exists",
            fields={"key": str(CATEGORY_EXISTS)},
        ) from None
    record_event(
        ctx, events.CATEGORY_CREATED, {"id": str(category.id), "key": category.key}
    )
    return category_row(category)


def _category(reference: str, field: str = "tax_category_key") -> TaxCategory:
    category = category_by_reference(reference)
    if category is None:
        raise InvalidPayload(
            str(CATEGORY_NOT_FOUND),
            code="invalid_field",
            fields={field: str(CATEGORY_NOT_FOUND)},
        )
    return category
