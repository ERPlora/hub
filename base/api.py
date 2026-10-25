"""Ninja routes of base: each route calls exactly one operation and holds no logic.

Settings › Data's (APP-BASE-2) that read or load a file take it in base64 in their body, more than Django's ceiling for
any other view; both are commands (POST): reading what a file brings writes nothing, but no query string carries it.
"""

from asgiref.sync import sync_to_async
from django.core.files.storage import storages
from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from django.http import HttpResponse

from base import files, queries, services
from base.auth_views import with_language_cookie
from base.request_body import accept_body_up_to
from base.schemas import (
    AccessSettingsUpdateIn,
    AvatarIn,
    BlueprintExportIn,
    BlueprintImportIn,
    BlueprintSourceIn,
    DeviceByIdIn,
    DeviceModeIn,
    DeviceRenameIn,
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
    PinSetIn,
    PreferencesIn,
    ProfileUpdateIn,
)

from base.schemas import ApiKeyCreateIn, ApiKeyIdIn, ApprovalExportIn, ApprovalIn, ApproversIn, BadgeSetIn, PersonIn  # noqa: E402  (APP-BASE-5)

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


# ── The way in (APP-BASE-3) ────────────────────────────────────────────────────────────────────────────────────────


# auth=None: the PIN pad is the door of a browser without a session (its device cookie decides what it shows).
@bind(router, "base.access.door", "/access/door", auth=None)
async def access_door(request):
    return await run_operation(request, queries.access_door)


@bind(router, "base.pin.set", "/me/pin")
async def pin_set(request, data: PinSetIn):
    return await run_operation(request, services.pin_set, data)


@bind(router, "base.device.current", "/device")
async def device_current(request):
    return await run_operation(request, queries.device_current)


@bind(router, "base.device.mode_set", "/device/mode")
async def device_mode_set(request, data: DeviceModeIn):
    return await run_operation(request, services.device_mode_set, data)


@bind(router, "base.device.list", "/devices")
async def device_list(request):
    return await run_operation(request, queries.device_list)


@bind(router, "base.device.rename", "/devices/rename")
async def device_rename(request, data: DeviceRenameIn):
    return await run_operation(request, services.device_rename, data)


@bind(router, "base.device.remove", "/devices/remove")
async def device_remove(request, data: DeviceByIdIn):
    return await run_operation(request, services.device_remove, data)


@bind(router, "base.device.prune", "/devices/prune")
async def device_prune(request):
    return await run_operation(request, services.device_prune)


@bind(router, "base.access.settings", "/access/settings")
async def access_settings(request):
    return await run_operation(request, queries.access_settings_get)


@bind(router, "base.access.settings_update", "/access/settings/update")
async def access_settings_update(request, data: AccessSettingsUpdateIn):
    return await run_operation(request, services.access_settings_update, data)


@bind(router, "base.profile.get", "/me/profile")
async def profile_get(request):
    return await run_operation(request, queries.profile_get)


@bind(router, "base.profile.update", "/me/profile/update")
async def profile_update(request, data: ProfileUpdateIn):
    return await run_operation(request, services.profile_update, data)


# The language applies at once: the answer leaves its cookie, as the login does (base.auth_views._with_language).
@bind(router, "base.profile.preferences_set", "/me/preferences")
async def preferences_set(request, response: HttpResponse, data: PreferencesIn):
    answer = await run_operation(request, services.preferences_set, data)
    with_language_cookie(response, answer.language)
    return answer


#: The photo's body: 2 MB in base64 (2 796 204 characters) and its JSON around it, past Django's 2.5 MB ceiling.
MAX_AVATAR_BODY = 2_900_000


@bind(router, "base.profile.avatar_set", "/me/avatar")
@decorate_view(accept_body_up_to(MAX_AVATAR_BODY))
async def avatar_set(request, data: AvatarIn):
    return await run_operation(request, services.avatar_set, data)


@bind(router, "base.profile.avatar_remove", "/me/avatar/remove")
async def avatar_remove(request):
    return await run_operation(request, services.avatar_remove)


# ── People and permissions: people, roles (APP-BASE-5) ──────────────────────────────────────────────────────────────


@bind(router, "base.person.list", "/people")
async def person_list(request):
    return await run_operation(request, queries.person_list)


@bind(router, "base.person.detail", "/people/detail")
async def person_detail(request, data: Query[PersonIn]):
    return await run_operation(request, queries.person_detail, data)


@bind(router, "base.person.pin_remove", "/people/pin/remove")
async def person_pin_remove(request, data: PersonIn):
    return await run_operation(request, services.person_pin_remove, data)


@bind(router, "base.person.badge_set", "/people/badge")
async def person_badge_set(request, data: BadgeSetIn):
    return await run_operation(request, services.person_badge_set, data)


@bind(router, "base.person.badge_remove", "/people/badge/remove")
async def person_badge_remove(request, data: PersonIn):
    return await run_operation(request, services.person_badge_remove, data)


@bind(router, "base.role.list", "/roles")
async def role_list(request):
    return await run_operation(request, queries.role_list)


# ── People and permissions: the business's API keys (APP-BASE-5) ───────────────────────────────────────────────────


@bind(router, "base.api_key.list", "/keys")
async def api_key_list(request):
    return await run_operation(request, queries.api_key_list)


@bind(router, "base.api_key.create", "/keys")
async def api_key_create(request, data: ApiKeyCreateIn):
    return await run_operation(request, services.api_key_create, data)


@bind(router, "base.api_key.rotate", "/keys/rotate")
async def api_key_rotate(request, data: ApiKeyIdIn):
    return await run_operation(request, services.api_key_rotate, data)


@bind(router, "base.api_key.revoke", "/keys/revoke")
async def api_key_revoke(request, data: ApiKeyIdIn):
    return await run_operation(request, services.api_key_revoke, data)


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────


@bind(router, "base.approval.list", "/approvals")
async def approval_list(request):
    return await run_operation(request, queries.approval_list)


@bind(router, "base.approval.export", "/approvals/export")
async def approval_export(request, data: Query[ApprovalExportIn]):
    return await run_operation(request, queries.approval_export, data)


@bind(router, "base.approval.approvers", "/approvals/approvers")
async def approval_approvers(request, data: Query[ApproversIn]):
    return await run_operation(request, queries.approval_approvers, data)


@bind(router, "base.approval.approve", "/approvals")
async def approval_approve(request, data: ApprovalIn):
    return await run_operation(request, services.approval_approve, data)


# ── People and permissions: the API's documentation (APP-BASE-5) ───────────────────────────────────────────────────
from base.schemas import ApiDocSettingsUpdateIn  # noqa: E402


@bind(router, "base.api_doc.get", "/api-docs")
async def api_doc_get(request):
    return await run_operation(request, queries.api_doc_get)


@bind(router, "base.api_doc.settings", "/api-docs/settings")
async def api_doc_settings(request):
    return await run_operation(request, queries.api_doc_settings)


@bind(router, "base.api_doc.settings_update", "/api-docs/settings/update")
async def api_doc_settings_update(request, data: ApiDocSettingsUpdateIn):
    return await run_operation(request, services.api_doc_settings_update, data)


# ── Assistant (APP-BASE-9) ──────────────────────────────────────────────────────────────────────────────────────

from base import assistant  # noqa: E402 - the assistant's block keeps its imports with it
from base.schemas import AssistantReportIn, AssistantTranscribeIn, AssistantTurnIn  # noqa: E402

#: A turn's body: the conversation and the attachments of its last question, in base64 (the gateway takes 32 MB).
MAX_ASSISTANT_TURN_BODY = 32 * 1024 * 1024
#: A dictation: 2 MB of audio in base64 and its JSON around it.
MAX_ASSISTANT_AUDIO_BODY = 3_000_000


# The 200 is a stream (text/event-stream) of the turn's frames (base/assistant.py ``turn_frames``), not the JSON of
# its operation's output, which is what the stream is made of.
@bind(router, "base.assistant.turn", "/assistant/turn")
@decorate_view(accept_body_up_to(MAX_ASSISTANT_TURN_BODY))
async def assistant_turn(request, data: AssistantTurnIn):
    plan = await run_operation(request, services.assistant_turn, data)
    return assistant.turn_response(request, plan.model_dump(mode="json"))


@bind(router, "base.assistant.usage", "/assistant/usage")
async def assistant_usage(request):
    return await run_operation(request, queries.assistant_usage)


@bind(router, "base.assistant.report", "/assistant/report")
async def assistant_report(request, data: AssistantReportIn):
    return await run_operation(request, services.assistant_report, data)


@bind(router, "base.assistant.transcribe", "/assistant/transcribe")
@decorate_view(accept_body_up_to(MAX_ASSISTANT_AUDIO_BODY))
async def assistant_transcribe(request, data: AssistantTranscribeIn):
    return await run_operation(request, services.assistant_transcribe, data)


# ── Locations (round 2026-10-24b, multi-location) ──────────────────────────────────────────────────────────────────


@bind(router, "base.location.list", "/locations")
async def location_list(request):
    return await run_operation(request, queries.location_list)
