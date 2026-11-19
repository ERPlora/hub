"""Routes of the way in: the PIN pad, the PIN, the devices, the access settings and the profile."""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from django.http import HttpResponse

from base import queries, services
from base.auth_views import with_language_cookie
from base.request_body import accept_body_up_to
from base.schemas.access import AccessSettingsUpdateIn
from base.schemas.devices import DeviceByIdIn, DeviceModeIn, DeviceRenameIn, PinSetIn
from base.schemas.profile import AvatarIn, PreferencesIn, ProfileUpdateIn

router = Router()


# auth=None: the PIN pad is the door of a browser without a session (its device cookie decides what it shows).
@bind(router, "base.access.door", "/access/door", auth=None)
async def access_door(request):
    return await run_operation(request, queries.access.access_door)


@bind(router, "base.pin.set", "/me/pin")
async def pin_set(request, data: PinSetIn):
    return await run_operation(request, services.devices.pin_set, data)


@bind(router, "base.device.current", "/device")
async def device_current(request):
    return await run_operation(request, queries.devices.device_current)


@bind(router, "base.device.mode_set", "/device/mode")
async def device_mode_set(request, data: DeviceModeIn):
    return await run_operation(request, services.devices.device_mode_set, data)


@bind(router, "base.device.list", "/devices")
async def device_list(request):
    return await run_operation(request, queries.devices.device_list)


@bind(router, "base.device.detail", "/devices/detail")
async def device_detail(request, data: Query[DeviceByIdIn]):
    return await run_operation(request, queries.devices.device_detail, data)


@bind(router, "base.device.rename", "/devices/rename")
async def device_rename(request, data: DeviceRenameIn):
    return await run_operation(request, services.devices.device_rename, data)


@bind(router, "base.device.remove", "/devices/remove")
async def device_remove(request, data: DeviceByIdIn):
    return await run_operation(request, services.devices.device_remove, data)


@bind(router, "base.device.prune", "/devices/prune")
async def device_prune(request):
    return await run_operation(request, services.devices.device_prune)


@bind(router, "base.access.settings", "/access/settings")
async def access_settings(request):
    return await run_operation(request, queries.access.access_settings_get)


@bind(router, "base.access.settings_update", "/access/settings/update")
async def access_settings_update(request, data: AccessSettingsUpdateIn):
    return await run_operation(request, services.profile.access_settings_update, data)


@bind(router, "base.profile.get", "/me/profile")
async def profile_get(request):
    return await run_operation(request, queries.profile.profile_get)


@bind(router, "base.profile.update", "/me/profile/update")
async def profile_update(request, data: ProfileUpdateIn):
    return await run_operation(request, services.profile.profile_update, data)


# The language applies at once: the answer leaves its cookie, as the login does (base.auth_views._with_language).
@bind(router, "base.profile.preferences_set", "/me/preferences")
async def preferences_set(request, response: HttpResponse, data: PreferencesIn):
    answer = await run_operation(request, services.profile.preferences_set, data)
    with_language_cookie(response, answer.language)
    return answer


#: The photo's body: 2 MB in base64 (2 796 204 characters) and its JSON around it, past Django's 2.5 MB ceiling.
MAX_AVATAR_BODY = 2_900_000


@bind(router, "base.profile.avatar_set", "/me/avatar")
@decorate_view(accept_body_up_to(MAX_AVATAR_BODY))
async def avatar_set(request, data: AvatarIn):
    return await run_operation(request, services.profile.avatar_set, data)


@bind(router, "base.profile.avatar_remove", "/me/avatar/remove")
async def avatar_remove(request):
    return await run_operation(request, services.profile.avatar_remove)
