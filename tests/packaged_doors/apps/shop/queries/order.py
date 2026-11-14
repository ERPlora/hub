from live.operations import INTERNAL, operation

from apps.demo.models import Item

from ..schemas import ItemIn, ItemsOut


@operation("shop.order.list", kind="query", permission=None, input=ItemIn, output=ItemsOut, ai=INTERNAL)
def list_orders(ctx, data):
    return {"names": list(Item.objects.filter(name__startswith=data.name).values_list("name", flat=True))}
