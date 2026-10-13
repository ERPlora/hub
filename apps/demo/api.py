"""Ninja routes of the demo app: each route calls exactly one operation and holds no logic.

No path parameters: the item's ``id`` travels in the input (query string on GET, body on POST),
because a route takes one parameter, the operation's input.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.demo import queries, services
from apps.demo.schemas import ByIdIn, ItemIn, ItemListIn, ItemPatchIn, LineIn

router = Router(tags=["demo"])


@bind(router, "demo.item.list", "/demo/items")
async def item_list(request, params: Query[ItemListIn]):
    return await run_operation(request, queries.list_items, params)


@bind(router, "demo.item.detail", "/demo/items/detail")
async def item_detail(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.item_detail, params)


@bind(router, "demo.item.stats", "/demo/items/stats")
async def item_stats(request):
    return await run_operation(request, queries.item_stats)


@bind(router, "demo.item.create", "/demo/items", status=201)
async def item_create(request, data: ItemIn):
    return await run_operation(request, services.create_item, data)


@bind(router, "demo.item.update", "/demo/items/update")
async def item_update(request, data: ItemPatchIn):
    return await run_operation(request, services.update_item, data)


@bind(router, "demo.item.delete", "/demo/items/delete")
async def item_delete(request, data: ByIdIn):
    return await run_operation(request, services.delete_item, data)


@bind(router, "demo.item.add_line", "/demo/items/add_line")
async def item_add_line(request, data: LineIn):
    return await run_operation(request, services.add_line, data)
