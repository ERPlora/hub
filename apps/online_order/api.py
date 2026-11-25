"""Ninja routes of Online orders: each route calls exactly one operation and holds no logic."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.online_order import queries, services
from apps.online_order.schemas import TableCodeListIn
from apps.table.schemas import TableRefIn

router = Router(tags=["online_order"])


@bind(router, "online_order.qr_code.list", "/online_order/qr_codes")
async def qr_code_list(request, params: Query[TableCodeListIn]):
    return await run_operation(request, queries.list_qr_codes, params)


@bind(router, "online_order.qr_code.regenerate", "/online_order/qr_codes/regenerate")
async def qr_code_regenerate(request, data: TableRefIn):
    return await run_operation(request, services.regenerate_qr_code, data)
