"""Ninja route of the Home's health row: it calls ``base.health.list`` and holds no logic. ``config/api.py`` mounts it."""

from live.ninja import bind, run_operation
from ninja import Router

from base.queries import health

router = Router(tags=["base"])


@bind(router, "base.health.list", "/home/health")
async def health_list(request):
    return await run_operation(request, health.health_list)
