"""Ninja routes of base: each route calls exactly one operation and holds no logic."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base import queries, services
from base.schemas import FailedEventDiscardIn, FailedEventIn, FailedEventListIn

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


# ── System (APP-BASE-7) ────────────────────────────────────────────────────────────────────────────────────────


@bind(router, "base.system.status", "/system/status")
async def system_status(request):
    return await run_operation(request, queries.system_status)


@bind(router, "base.event.list", "/system/events")
async def event_list(request):
    return await run_operation(request, queries.event_list)


@bind(router, "base.failed_event.list", "/system/failed-events")
async def failed_event_list(request, params: Query[FailedEventListIn]):
    return await run_operation(request, queries.failed_event_list, params)


@bind(router, "base.failed_event.retry", "/system/failed-events/retry")
async def failed_event_retry(request, data: FailedEventIn):
    return await run_operation(request, services.failed_event_retry, data)


@bind(router, "base.failed_event.retry_all", "/system/failed-events/retry_all")
async def failed_event_retry_all(request):
    return await run_operation(request, services.failed_event_retry_all)


@bind(router, "base.failed_event.discard", "/system/failed-events/discard")
async def failed_event_discard(request, data: FailedEventDiscardIn):
    return await run_operation(request, services.failed_event_discard, data)
