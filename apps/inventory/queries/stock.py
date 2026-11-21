"""The inventory panel's figures (``inventory.stock.get_summary``)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from live.context import OperationContext
from live.operations import operation

from apps.inventory.models import Product
from apps.inventory.queries.products import tracks_stock_expression
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas.stock import SummaryIn, SummaryOut


@operation(
    "inventory.stock.get_summary",
    kind="query",
    permission="inventory.view_product",
    input=SummaryIn,
    output=SummaryOut,
    expose_api=True,
    ai={
        "description": "The inventory's figures: articles with stock control, in stock, out of stock, low on "
        "stock, without cost, the stock's value at cost and the number of active products.",
        "asks": {
            "en": (
                "how is my inventory doing?",
                "how much is my stock worth?",
                "give me the inventory figures: how many products are out of stock",
            ),
            "es": (
                "¿cómo va mi inventario?",
                "¿cuánto vale mi stock?",
                "¿cuántos productos se han quedado sin existencias?",
            ),
        },
    },
)
def get_summary(ctx: OperationContext, data: SummaryIn) -> dict:
    """The panel's figures over the active articles with stock control; a negative balance never subtracts."""
    tracked = Q(tracks=True)
    in_stock = tracked & Q(stock__gt=0)
    value = ExpressionWrapper(
        F("cost") * F("stock"),
        output_field=DecimalField(max_digits=32, decimal_places=3),
    )
    figures = (
        Product.objects.filter(is_deleted=False, is_active=True)
        .annotate(tracks=tracks_stock_expression(current_settings()))
        .aggregate(
            active_products=Count("id"),
            products_tracked=Count("id", filter=tracked),
            products_in_stock=Count("id", filter=in_stock),
            products_out_of_stock=Count("id", filter=tracked & Q(stock__lte=0)),
            products_low_stock=Count(
                "id", filter=tracked & Q(stock__lte=F("low_stock_threshold"))
            ),
            products_without_cost=Count("id", filter=tracked & Q(cost__lte=0)),
            value=Sum(value, filter=in_stock),
        )
    )
    total = figures.pop("value") or Decimal("0")
    return {
        **figures,
        "stock_value": int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }
