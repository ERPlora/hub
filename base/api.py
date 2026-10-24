"""Ninja routes of base: each route calls exactly one operation and holds no logic.

Settings › Data's (APP-BASE-2) that read or load a file take it in base64 in their body, more than Django's ceiling for
any other view; both are commands (POST): reading what a file brings writes nothing, but no query string carries it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from base import queries, services
from base.request_body import accept_body_up_to
from base.schemas import (
    BlueprintExportIn,
    BlueprintImportIn,
    BlueprintSourceIn,
    FailedEventDiscardIn,
    FailedEventIn,
    FailedEventListIn,
    HubResetIn,
    ImportUndoIn,
)

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


# ── Data: blueprints, imports and reset (APP-BASE-2) ──
#: The upload's body: 5 MB of zip in base64 (6 990 508 characters) and its JSON around it.
MAX_BLUEPRINT_BODY = 7_100_000


@bind(router, "base.blueprint.list", "/settings/data/blueprints")
async def blueprint_list(request):
    return await run_operation(request, queries.blueprint_list)


@bind(router, "base.blueprint.inspect", "/settings/data/blueprints/inspect")
@decorate_view(accept_body_up_to(MAX_BLUEPRINT_BODY))
async def blueprint_inspect(request, data: BlueprintSourceIn):
    return await run_operation(request, services.blueprint_inspect, data)


@bind(router, "base.blueprint.import", "/settings/data/blueprints/import")
@decorate_view(accept_body_up_to(MAX_BLUEPRINT_BODY))
async def blueprint_import(request, data: BlueprintImportIn):
    return await run_operation(request, services.blueprint_import, data)


@bind(router, "base.blueprint.export", "/settings/data/export")
async def blueprint_export(request, data: Query[BlueprintExportIn]):
    return await run_operation(request, queries.blueprint_export, data)


@bind(router, "base.import.list", "/settings/data/imports")
async def import_list(request):
    return await run_operation(request, queries.import_list)


@bind(router, "base.import.undo", "/settings/data/imports/undo")
async def import_undo(request, data: ImportUndoIn):
    return await run_operation(request, services.import_undo, data)


@bind(router, "base.dataset.list", "/settings/data/datasets")
async def dataset_list(request):
    return await run_operation(request, queries.dataset_list)


@bind(router, "base.hub.reset", "/settings/data/reset")
async def hub_reset(request, data: HubResetIn):
    return await run_operation(request, services.hub_reset, data)


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
