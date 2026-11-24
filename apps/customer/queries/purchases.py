"""A card's purchases (CUSTOMER-F23), the cards whose figures disagree with them, and whether the business holds
any."""

from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from live.context import OperationContext
from live.operations import AI, operation

from apps.customer.models import Customer, Purchase
from apps.customer.queries.reads import _ordered, find_customer, page
from apps.customer.schemas.purchases import DivergencePage, DivergencesIn, PurchaseListIn, PurchasePage
from apps.customer.search import normalize

from . import contact


@operation(
    "customer.purchase.list",
    kind="query",
    permission="customer.view",
    input=PurchaseListIn,
    output=PurchasePage,
    ai=AI(
        "Paginated purchase history of a customer: each sale with its amount in cents, currency and status (paid or "
        "voided); voided ones are kept.",
        asks={
            "en": ("what has Sara bought?", "how much has Pedro spent with us?", "show Ana's purchases"),
            "es": ("¿qué ha comprado Sara?", "¿cuánto se ha gastado Pedro con nosotros?", "las compras de Ana"),
        },
    ),
)
def list_purchases(ctx: OperationContext, params: PurchaseListIn) -> dict:
    customer = find_customer(ctx, params.customer_id, params.customer)
    purchases = Purchase.objects.filter(customer=customer)
    if params.search:
        purchases = purchases.filter(sale_id__icontains=params.search.strip())
    filters = {
        "status": params.status,
        "recorded_at__date__gte": params.recorded_from,
        "recorded_at__date__lte": params.recorded_to,
    }
    purchases = purchases.filter(
        **{lookup: value for lookup, value in filters.items() if value is not None}
    )
    return page(_ordered(purchases, params.sort, params.descending), params)


@operation(
    "customer.purchase.divergences",
    kind="query",
    permission="customer.view",
    input=DivergencesIn,
    output=DivergencePage,
    ai=AI(
        "Reconciliation audit: the customers whose purchase count or spend disagree with their purchase history. "
        "Empty means healthy.",
        asks={
            "en": ("check the customer spend figures for mismatches", "are the customers' spend totals right?"),
            "es": ("revisa si cuadra el gasto de cada cliente", "¿está bien calculado el gasto de los clientes?"),
        },
    ),
)
def purchase_divergences(ctx: OperationContext, params: DivergencesIn) -> dict:
    confirmed = Q(purchases__status=Purchase.Status.CONFIRMED)
    # The spend is what was paid minus what came back (refund lines carry a negative amount).
    spent = confirmed | Q(purchases__status=Purchase.Status.REFUNDED)
    cards = Customer.objects.live().annotate(
        ledger_purchases=Count("purchases", filter=confirmed),
        ledger_spent=Coalesce(
            Sum("purchases__amount", filter=spent),
            Value(0),
            output_field=IntegerField(),
        ),
    )
    cards = cards.exclude(
        total_purchases=F("ledger_purchases"), total_spent=F("ledger_spent")
    )
    term = normalize(params.search or "")
    if term:
        cards = contact.searched(ctx, cards, term)
    return page(cards.order_by("name", "id"), params)


def keeps_fiscal_documents() -> bool:
    """Whether this database holds the card sales of its customers (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Purchase.objects.exists()
