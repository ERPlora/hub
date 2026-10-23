"""Ninja routes of base: each route calls exactly one operation and holds no logic."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries

router = Router(tags=["base"])


# auth=None: an anonymous visitor gets ``user: null`` (and the SPA sends it to the login).
@bind(router, "base.session.me", "/me", auth=None)
async def session_me(request):
    return await run_operation(request, queries.session_me)


@bind(router, "base.setup.status", "/home/setup")
async def setup_status(request):
    return await run_operation(request, queries.setup_status)


@bind(router, "base.widget.list", "/home/widgets")
async def widget_list(request):
    return await run_operation(request, queries.widget_list)


@bind(router, "base.bell.counters", "/home/bell")
async def bell_counters(request):
    return await run_operation(request, queries.bell_counters)


@bind(router, "base.notice.list", "/home/notices")
async def notice_list(request):
    return await run_operation(request, queries.notice_list)


# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────


@bind(router, "base.app.list", "/apps")
async def app_list(request):
    return await run_operation(request, queries.app_list)


@bind(router, "base.plan.usage", "/system/plan")
async def plan_usage(request):
    return await run_operation(request, queries.plan_usage)
