"""The customer tags as their list shows them, with how many live cards have each (CUSTOMER-F28)."""

from django.db.models import QuerySet
from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import CustomerTag
from apps.customer.queries.reads import _customer_count, _ordered, page
from apps.customer.schemas.tags import TagListIn, TagPage
from base.text_search import contains_text


def _tags() -> QuerySet:
    """The tags as their list shows them, with how many live cards have each."""
    return CustomerTag.objects.annotate(customer_count=_customer_count("customers"))


@operation(
    "customer.tag.list",
    kind="query",
    permission="customer.view",
    input=TagListIn,
    output=TagPage,
    ai=AI(
        "Lists the customer tags with how many customers have each, active and inactive.",
        asks={
            "en": ("which tags do we have?", "how many clients are tagged vegan?"),
            "es": ("¿qué etiquetas usamos?", "¿cuántos clientes llevan la etiqueta habitual?"),
        },
    ),
)
def list_tags(ctx: OperationContext, params: TagListIn) -> dict:
    tags = _tags()
    if params.search:
        tags = tags.filter(contains_text(params.search, "name"))
    filters = {"is_active": params.is_active, "color": params.color}
    tags = tags.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(tags, params.sort, params.descending), params)
