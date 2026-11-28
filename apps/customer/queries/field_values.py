"""Every value the live cards keep in their custom fields, with the card and the field by name: what a backup of the
business carries of them (``apps.customer.blueprint``). The card shows its own values in its detail."""

from django.db.models import F
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.customer.models import Customer, CustomFieldValue
from apps.customer.queries.reads import page
from apps.customer.schemas.custom_fields import FieldValuePage
from apps.customer.schemas.fields import PageIn


@operation(
    "customer.field_value.list",
    kind="query",
    permission="customer.export",
    input=PageIn,
    output=FieldValuePage,
    ai=INTERNAL,
)
def list_field_values(ctx: OperationContext, params: PageIn) -> dict:
    values = (
        CustomFieldValue.objects.filter(customer__in=Customer.objects.live(), field__is_active=True)
        .annotate(
            customer_name=F("customer__name"),
            phone=F("customer__phone"),
            email=F("customer__email"),
            field_name=F("field__name"),
        )
        .order_by("customer__name", "customer_id", "field__sort_order", "field__name", "id")
    )
    found = page(values, params)
    found["rows"] = [
        {"customer": row.customer_name, "phone": row.phone, "email": row.email, "field": row.field_name, "value": row.value}
        for row in found["rows"]
    ]
    return found
