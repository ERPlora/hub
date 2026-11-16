from live.operations import INTERNAL, operation

from apps.demo.models import Item

from ..schemas import ItemIn, ItemOut


@operation("shop.order.create", kind="command", permission=None, input=ItemIn, output=ItemOut, ai=INTERNAL)
def create(ctx, data):
    item = Item.objects.create(name=data.name)
    return {"name": item.name}
