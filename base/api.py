"""Ninja routes of base: each route calls exactly one operation and holds no logic.

Settings › Data's (APP-BASE-2) that read or load a file take it in base64 in their body, more than Django's ceiling for
any other view; both are commands (POST): reading what a file brings writes nothing, but no query string carries it.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from django.http import HttpResponse

from base import queries, services
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
    HubResetIn,
    ImportUndoIn,
    PinSetIn,
    PreferencesIn,
    ProfileUpdateIn,
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
