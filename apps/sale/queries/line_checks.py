"""What a new line of a product names, read before the assistant's card of the write that adds it (SALE-F20, BASE-F97):
the product, found as the write finds it. Words that fit no product, or several, are refused at once and the person
never sees a card for them: the model hears the words, and looks the product up or asks which one."""

from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.sale.queries.order_lines import catalog_product
from apps.sale.schemas.lines import ProductLineIn
from apps.sale.schemas.records import LineProductOut


@operation(
    "sale.order_line.check",
    kind="query",
    permission="sale.add_sale",
    input=ProductLineIn,
    output=LineProductOut,
    ai=INTERNAL,
)
def check_line(ctx: OperationContext, data: ProductLineIn) -> dict:
    """The product ``sale.order.add_line`` adds a line of."""
    product = catalog_product(ctx, data)
    return {"id": product.id, "name": product.name}
