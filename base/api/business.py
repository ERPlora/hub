"""Route of the business's settings and the hub's context."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries

router = Router()


@bind(router, "base.business.get", "/business")
async def business_get(request):
    return await run_operation(request, queries.hubs.business_get)
