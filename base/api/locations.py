"""Route of the business's locations."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries

router = Router()


@bind(router, "base.location.list", "/locations")
async def location_list(request):
    return await run_operation(request, queries.hubs.location_list)
