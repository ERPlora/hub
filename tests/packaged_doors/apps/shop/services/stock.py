from live.operations import INTERNAL, operation

from apps.demo.models import Item

from ..schemas import ItemIn, ItemOut


@operation("shop.stock.remove", kind="command", permission=None, input=ItemIn, output=ItemOut, ai=INTERNAL)
def remove(ctx, data):
    Item.objects.filter(name=data.name).delete()
    return {"name": data.name}
