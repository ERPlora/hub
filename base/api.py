"""Ninja routes of base: each route calls exactly one operation and holds no logic."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries, services
from base.schemas import PinSetIn

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


# ── The way in (APP-BASE-3) ────────────────────────────────────────────────────────────────────────────────────────


# auth=None: the PIN pad is the door of a browser without a session (its device cookie decides what it shows).
@bind(router, "base.access.door", "/access/door", auth=None)
async def access_door(request):
    return await run_operation(request, queries.access_door)


@bind(router, "base.pin.set", "/me/pin")
async def pin_set(request, data: PinSetIn):
    return await run_operation(request, services.pin_set, data)
