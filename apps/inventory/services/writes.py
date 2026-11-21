"""What more than one write of the inventory app shares: the system's own permission, who wrote a row, the
checks that run before anything is written (a tax category, a quantity on its unit's step, a service that has no
stock), and the events of a product's link to a category and of a changed product."""

from decimal import Decimal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.outbox import record_event

from apps.inventory.models import ACTOR_MAX_LENGTH, fits_unit, increment_of, Product
from apps.inventory.queries.exports import quantity_text
from apps.inventory.queries.reads import held
from apps.tax.models import TaxCategory

TAX_CATEGORY_UNKNOWN = _("This tax category does not exist in Taxes.")

OFF_GRID = _("The quantity does not respect the step allowed for this unit: use multiples of %(step)s.")

SERVICE_HAS_NO_STOCK = _("A service has no stock.")

#: Run only by the platform (events.py): no role holds it, so no person and no API key reaches it.
SYSTEM = "inventory.system"


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _tax_category(key: str, field: str = "tax_category_key") -> TaxCategory:
    """The active tax category of ``key``, held for the write that names it (see ``held``)."""
    tax_category = next(iter(held(TaxCategory.objects.filter(key=key, is_active=True)[:1])), None)
    if tax_category is None:
        raise InvalidPayload(str(TAX_CATEGORY_UNKNOWN), code="invalid_field", fields={field: str(TAX_CATEGORY_UNKNOWN)})
    return tax_category


def _check_grid(qty: Decimal, unit: str, field: str) -> None:
    if not fits_unit(qty, unit):
        message = str(OFF_GRID) % {"step": f"{quantity_text(increment_of(unit))} {unit}"}
        raise Conflict(message, code="inventory.off_grid_quantity", fields={field: message})


def _service_has_no_stock(field: str) -> Conflict:
    return Conflict(str(SERVICE_HAS_NO_STOCK), code="inventory.service_has_no_stock", fields={field: str(SERVICE_HAS_NO_STOCK)})


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
