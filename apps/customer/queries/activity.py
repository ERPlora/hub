"""A card's timeline: its notes and what the apps wrote on it, newest first."""

from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import Activity
from apps.customer.queries.reads import find_customer, page
from apps.customer.schemas.activity import ActivityListIn, ActivityPage
from base.text_search import contains_text


@operation(
    "customer.activity.list",
    kind="query",
    permission="customer.view",
    input=ActivityListIn,
    output=ActivityPage,
    ai=AI(
        "Lists a customer's activity history, newest first: notes, purchases, voids, consent decisions, merges and "
        "other apps' entries.",
        asks={
            "en": (
                "what's been going on with Pedro?",
                "show Lucía's history",
                "has anything happened with Javier lately?",
            ),
            "es": ("¿qué ha pasado con Pedro últimamente?", "enséñame el historial de Lucía"),
        },
    ),
)
def list_activity(ctx: OperationContext, params: ActivityListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    entries = Activity.objects.filter(customer=customer)
    if params.search:
        entries = entries.filter(contains_text(params.search, "text", "title"))
    return page(entries.order_by("-created_at", "-id"), params)
