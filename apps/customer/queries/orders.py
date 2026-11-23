"""Which card an open order is for (CUSTOMER-F19)."""

from uuid import UUID

from apps.customer.models import OrderLink


def linked_customer_id(order_id: UUID) -> UUID | None:
    """The live card linked to the order, if any: a deleted, merged or erased one is nobody's customer any more."""
    link = OrderLink.objects.filter(order_id=order_id, customer__deleted_at__isnull=True).first()
    return link.customer_id if link else None
