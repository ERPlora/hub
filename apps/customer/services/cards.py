"""A customer's card: creating it and updating it (CUSTOMER-F01, F04)."""

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import Customer
from apps.customer.queries.cards import load_detail
from apps.customer.queries.reads import find_customer
from apps.customer.schemas.cards import CustomerDetailOut, CustomerIn, CustomerPatchIn
from apps.customer.services.field_values import _apply_field_values, _validated_field_values
from apps.customer.services.writes import _changes, _e164

#: The fields a patch may clear by sending ``null``.
NULLABLE = frozenset({"birthday", "anniversary"})


@operation(
    "customer.customer.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=CustomerIn,
    output=CustomerDetailOut,
    ai=AI(
        "Creates a new customer; only the name is required. The phone is saved in international format "
        "(+34600111222), a number without prefix read in the business's country; one that is not a phone of its "
        "country is refused.",
        asks={
            "en": (
                "add Ana as a customer, her number is 600 111 222",
                "new client: Marta López",
                "save Luis with his email luis@gmail.com",
            ),
            "es": (
                "apúntame a Ana con su teléfono 600 111 222",
                "da de alta a la clienta Marta López",
                "nueva clienta: Lucía, lucia@gmail.com",
                "crea un cliente que se llama Luis",
            ),
        },
    ),
)
def create_customer(ctx: OperationContext, data: CustomerIn) -> dict:
    values = data.model_dump()
    values["phone"] = _e164(values["phone"], ctx)
    customer = Customer.objects.create(**values)
    record_event(ctx, events.CUSTOMER_CREATED, {"id": str(customer.id)})
    return load_detail(customer)


@operation(
    "customer.customer.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=CustomerPatchIn,
    output=CustomerDetailOut,
    ai=AI(
        "Updates a customer's card, by its id or its name, phone or email: only the fields sent change, and "
        "with field_values its custom fields too, in one write: required fields must end up filled and values must "
        "match their type, or nothing is saved.",
        asks={
            "en": ("change Marta's email", "Luis has a new number: 611 222 333", "update Carmen's address"),
            "es": (
                "cámbiale el email a Marta",
                "Luis tiene móvil nuevo: 611 222 333",
                "pon que Carmen vive en Valencia",
            ),
        },
    ),
)
def update_customer(ctx: OperationContext, data: CustomerPatchIn) -> dict:
    customer = find_customer(ctx, data.id, data.customer, lock=True)
    sent = {
        field: value
        for field, value in data.model_dump(
            exclude_unset=True, exclude={"id", "customer", "field_values"}
        ).items()
        if value is not None or field in NULLABLE
    }
    if "phone" in sent:
        sent["phone"] = _e164(sent["phone"], ctx)
    kept = (
        _validated_field_values(customer, data.field_values)
        if data.field_values is not None
        else {}
    )
    changes = _changes(customer, sent)
    for field, value in changes.items():
        setattr(customer, field, value)
    values_changed = _apply_field_values(customer, kept)
    if changes or values_changed:
        customer.save(update_fields=[*changes, "updated_at"])
        record_event(ctx, events.CUSTOMER_UPDATED, {"id": str(customer.id)})
    return load_detail(customer)
