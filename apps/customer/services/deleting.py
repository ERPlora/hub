"""A card deleted (CUSTOMER-F07): it leaves every list and keeps its data."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.fields import CustomerRefIn, DeletedOut


@operation(
    "customer.customer.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.delete",
    input=CustomerRefIn,
    output=DeletedOut,
    ai=AI(
        "Deletes a customer's card: it leaves every list, the till and the phone lookup, but keeps its data, "
        "purchases and orders (erasing personal data is customer.customer.erase). Repeating it on a card already "
        "gone answers well.",
        risk="high",
        asks={
            "en": ("delete this customer", "remove Pedro from my clients"),
            "es": ("borra a este cliente", "elimina la ficha de Pedro", "quita a Ana de clientes"),
        },
    ),
)
def delete_customer(ctx: OperationContext, data: CustomerRefIn) -> dict:
    customer = find_customer(ctx, data.id, data.customer, lock=True, live=False)
    if customer.deleted_at is None:
        customer.deleted_at = timezone.now()
        customer.is_active = False
        customer.save(update_fields=["deleted_at", "is_active", "updated_at"])
    record_event(ctx, events.CUSTOMER_DELETED, {"id": str(customer.id)})
    return {"id": customer.id}
