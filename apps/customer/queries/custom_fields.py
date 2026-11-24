"""The custom fields of the cards as their list shows them (CUSTOMER-F29)."""

from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import CustomField
from apps.customer.queries.reads import _ordered, page
from apps.customer.schemas.custom_fields import FieldListIn, FieldPage


@operation(
    "customer.field.list",
    kind="query",
    permission="customer.view",
    input=FieldListIn,
    output=FieldPage,
    ai=AI(
        "Lists the custom fields defined for the customers' cards, with their type, options and whether they are "
        "required.",
        asks={
            "en": ("what custom fields do we have?", "which extra fields are on the customer card?"),
            "es": ("¿qué campos extra tiene la ficha?", "¿qué datos pedimos a los clientes además del nombre?"),
        },
    ),
)
def list_fields(ctx: OperationContext, params: FieldListIn) -> dict:
    fields = CustomField.objects.all()
    if params.search:
        fields = fields.filter(name__icontains=params.search)
    filters = {
        "field_type": params.field_type,
        "is_required": params.is_required,
        "is_active": params.is_active,
    }
    fields = fields.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(fields, params.sort, params.descending), params)
