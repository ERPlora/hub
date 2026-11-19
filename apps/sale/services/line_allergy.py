"""Marking the customer's allergy on a line of an open check before it is sent to the kitchen."""

from live.context import OperationContext
from live.operations import AI, operation

from apps.sale.schemas.line_allergy import OrderSetLineAllergyIn
from apps.sale.schemas.orders import OrderOut
from apps.sale.services.orders import _open_order, _out, _pending_line, _touch


@operation(
    "sale.order.set_line_allergy",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetLineAllergyIn,
    output=OrderOut,
    ai=AI(
        description="Mark the customer's allergy on a line of an open check not sent to the kitchen yet: all the "
        "allergens the person it is for must not eat, of the fourteen; an empty list takes it off. The kitchen gets it "
        "with the dish, and the check says which of them the dish contains. Resolve the check with "
        "sale.order.list(search=...) and its line with sale.order.get; never ask for order_id or line_id.",
        risk="normal",
        asks={
            "en": (
                "the burger on table 4 is for someone allergic to gluten",
                "mark a milk and egg allergy on the dessert",
                "take the allergy off the salad, it was a mistake",
            ),
            "es": (
                "la hamburguesa de la mesa 4 es para un alérgico al gluten",
                "el cliente del postre tiene alergia a la leche y al huevo",
                "desmarca la alergia de la ensalada, que era un error",
            ),
        },
    ),
)
def set_line_allergy(ctx: OperationContext, data: OrderSetLineAllergyIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id)
    if line.allergy != data.allergy:
        line.allergy = data.allergy
        line.save(update_fields=["allergy", "updated_at"])
        _touch(ctx, order)
    return _out(order)
