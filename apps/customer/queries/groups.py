"""The customer groups as their list shows them, with how many live cards are in each (CUSTOMER-F27)."""

from django.db.models import Q, QuerySet
from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import CustomerGroup
from apps.customer.queries.reads import _customer_count, _ordered, page
from apps.customer.schemas.groups import GroupListIn, GroupPage


def _groups() -> QuerySet:
    """The groups as their list shows them, with how many live cards are in each."""
    return CustomerGroup.objects.annotate(customer_count=_customer_count("customers"))


@operation(
    "customer.group.list",
    kind="query",
    permission="customer.view",
    input=GroupListIn,
    output=GroupPage,
    ai=AI(
        "Lists the customer groups with how many customers are in each, active and inactive.",
        asks={
            "en": ("what customer groups are there?", "how many people are in the VIP group?"),
            "es": ("¿qué grupos tenemos?", "¿cuánta gente hay en el grupo VIP?"),
        },
    ),
)
def list_groups(ctx: OperationContext, params: GroupListIn) -> dict:
    groups = _groups()
    if params.search:
        groups = groups.filter(
            Q(name__icontains=params.search) | Q(description__icontains=params.search)
        )
    filters = {
        "is_active": params.is_active,
        "color": params.color,
        "customer_count__gte": params.customers_min,
        "customer_count__lte": params.customers_max,
    }
    groups = groups.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(groups, params.sort, params.descending), params)
