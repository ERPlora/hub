"""What a price or a rule points at in another app, named as that app names it."""

from live.context import OperationContext
from live.operations import operation

from apps.customer.queries import find_group
from apps.inventory import queries as inventory_queries
from apps.pricing.queries.other_apps import call_service
from apps.pricing.schemas import CatalogRecordOut, CatalogRefIn


@operation(
    "pricing.catalog.get",
    kind="query",
    permission="pricing.view",
    input=CatalogRefIn,
    output=CatalogRecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what group is behind the partners' one?",
                "what is the real name of the group behind that identifier?",
                "name the identifier this one points at",
            ),
            "es": (
                "¿qué grupo hay detrás de la de socios?",
                "¿cómo se llama de verdad el grupo de ese identificador?",
                "¿a qué apunta ese identificador y cómo se llama?",
            ),
        },
        "description": "Name by its id the service, the category or the customer group a price list, a price or a "
        "rule points at, as Services, Inventory or Customers name it (a service needs its permission in Services)."
    },
)
def get_catalog_record(ctx: OperationContext, data: CatalogRefIn) -> dict:
    if data.service_id is not None:
        record = call_service(ctx, data.service_id, None)
    elif data.category_id is not None:
        record = inventory_queries.reads.find_category(data.category_id, None)
    else:
        record = find_group(data.customer_group_id, None)
    return {"id": record.id, "name": record.name}
