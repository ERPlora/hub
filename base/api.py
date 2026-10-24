"""Ninja routes of base: each route calls exactly one operation and holds no logic.

Settings › Data's (APP-BASE-2) that read or load a file take it in base64 in their body, more than Django's ceiling for
any other view; both are commands (POST): reading what a file brings writes nothing, but no query string carries it.
"""

from asgiref.sync import sync_to_async
from django.core.files.storage import storages
from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from base import files, queries, services
from base.request_body import accept_body_up_to
from base.schemas import (
    BlueprintExportIn,
    BlueprintImportIn,
    BlueprintSourceIn,
    FailedEventDiscardIn,
    FailedEventIn,
    FailedEventListIn,
    FileDeleteIn,
    FileFolderCreateIn,
    FileListIn,
    FileMoveIn,
    FileReadIn,
    FileRenameIn,
    FileUploadIn,
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


# ── Business settings and the hub's context (APP-BASE-6) ──


@bind(router, "base.business.get", "/business")
async def business_get(request):
    return await run_operation(request, queries.business_get)


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


# ── Files (APP-BASE-8) ─────────────────────────────────────────────────────────────────────────────────────────
#: An upload's body: 25 MB of file in base64 (34 952 536 characters) and its JSON around it.
MAX_FILE_BODY = 35_100_000


@bind(router, "base.file.list", "/files")
async def file_list(request, params: Query[FileListIn]):
    return await run_operation(request, queries.file_list, params)


@bind(
    router,
    "base.file.read",
    "/files/raw",
    openapi_extra={
        "responses": {
            200: {
                "description": "The file's bytes (an attachment unless `inline` and safe to show), or the operation's "
                "JSON when only JSON is accepted.",
                "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
            }
        }
    },
)
async def file_read(request, params: Query[FileReadIn]):
    described = await run_operation(request, queries.file_read, params)
    if request.headers.get("Accept", "").strip() == "application/json":
        return described
    return await sync_to_async(files.file_response)(
        storages["hub_files"], request.hub.id, described.model_dump(), inline=params.inline
    )


@bind(router, "base.file.upload", "/files/upload")
@decorate_view(accept_body_up_to(MAX_FILE_BODY))
async def file_upload(request, data: FileUploadIn):
    return await run_operation(request, services.file_upload, data)


@bind(router, "base.file.create_folder", "/files/folder")
async def file_create_folder(request, data: FileFolderCreateIn):
    return await run_operation(request, services.file_create_folder, data)


@bind(router, "base.file.rename", "/files/rename")
async def file_rename(request, data: FileRenameIn):
    return await run_operation(request, services.file_rename, data)


@bind(router, "base.file.move", "/files/move")
async def file_move(request, data: FileMoveIn):
    return await run_operation(request, services.file_move, data)


@bind(router, "base.file.delete", "/files/delete")
async def file_delete(request, data: FileDeleteIn):
    return await run_operation(request, services.file_delete, data)
