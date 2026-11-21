"""Routes of who is signed in and of the Home."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries

router = Router()


# auth=None: an anonymous visitor gets ``user: null`` (and the SPA sends it to the login).
@bind(router, "base.session.me", "/me", auth=None)
async def session_me(request):
    return await run_operation(request, queries.sessions.session_me)


@bind(router, "base.setup.status", "/home/setup")
async def setup_status(request):
    return await run_operation(request, queries.home.setup_status)


@bind(router, "base.widget.list", "/home/widgets")
async def widget_list(request):
    return await run_operation(request, queries.home.widget_list)


@bind(router, "base.bell.counters", "/home/bell")
async def bell_counters(request):
    return await run_operation(request, queries.home.bell_counters)


@bind(router, "base.notice.list", "/home/notices")
async def notice_list(request):
    return await run_operation(request, queries.home.notice_list)
