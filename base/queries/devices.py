"""The devices of the business: the one in use, the list and one device (``base.device.*``)."""

from typing import Any

from django.db.models import Max
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, operation

from base import access
from base.models import SessionOwner, TrustedDevice
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas import DeviceByIdIn, DeviceCurrentIn, DeviceCurrentOut, DeviceListIn, DeviceListOut, DeviceOut


def device_of(request: HttpRequest | None, *, for_update: bool = False) -> TrustedDevice | None:
    """The hub's device this browser's cookie names, or ``None`` (no request or cookie, or a device the hub does not
    know: never one in which nobody entered with an account, nor one that was removed)."""
    token = request.COOKIES.get(access.DEVICE_COOKIE, "") if request is not None else ""
    if not token:
        return None
    devices = TrustedDevice.objects.select_for_update() if for_update else TrustedDevice.objects
    return devices.filter(token_digest=access.token_digest(token)).first()


def device_of_entry(request: HttpRequest) -> TrustedDevice | None:
    """The device an entry of this request was made on: the token it just left (a new device's) or the cookie's."""
    token = getattr(request, access.DEVICE_TOKEN_ATTR, None)
    if token:
        return TrustedDevice.objects.filter(token_digest=access.token_digest(token)).first()
    return device_of(request)


@operation(
    "base.device.current",
    kind="query",
    permission=VIEW_HOME,
    input=DeviceCurrentIn,
    output=DeviceCurrentOut,
    ai=AI(
        description="Says whether the device the person is using is shared (a till: PIN, a shift) or personal.",
        asks={
            "en": ("is this a shared device?", "what mode is this device in?", "does this device ask for a PIN?"),
            "es": ("¿este aparato es de uso compartido?", "¿este dispositivo pide PIN?"),
        },
    ),
)
def device_current(ctx: OperationContext, data: DeviceCurrentIn) -> dict[str, Any]:
    """«This device» of Settings › General: the mode of the browser that asks, and whether the hub knows it
    (someone entered with an account from it). An unknown one reads as shared, the strict mode."""
    device = device_of(ctx.request)
    if device is None:
        return {"known": False, "mode": access.SHARED, "mode_set_by": "", "mode_set_at": None}
    return {"known": True, "mode": device.mode, "mode_set_by": device.mode_set_by, "mode_set_at": device.mode_set_at}


@operation(
    "base.device.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DeviceListIn,
    output=DeviceListOut,
    ai=AI(
        description=(
            "Lists the devices someone entered this hub from: name, browser, shared or personal, whether it has a "
            "session open now and until when, who entered last and when, and which ones nobody used in 30 days."
        ),
        asks={
            "en": (
                "which devices are signed in to the business?",
                "list the tablets and computers",
                "which devices haven't been used in a month?",
            ),
            "es": ("lista las tablets y ordenadores del negocio", "¿qué aparatos llevan un mes sin usarse?"),
        },
    ),
)
def device_list(ctx: OperationContext, data: DeviceListIn) -> dict[str, Any]:
    """«Devices» of Settings › General: never a device's token, which is its proof."""
    rows = _device_rows(ctx, list(TrustedDevice.objects.order_by("-last_entry_at")))
    return {"devices": rows, "unused": sum(row["unused"] for row in rows)}


@operation(
    "base.device.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DeviceByIdIn,
    output=DeviceOut,
    ai=AI(
        description=(
            "Reads one device someone entered this hub from, by its id, as the devices list shows it: its name first."
        ),
        asks={
            "en": ("show me the kitchen tablet's details", "who used the bar device last?"),
            "es": (
                "¿quién entró el último en el dispositivo de la barra?",
                "¿quién usó por última vez el ordenador de la oficina?",
            ),
        },
    ),
)
def device_detail(ctx: OperationContext, data: DeviceByIdIn) -> dict[str, Any]:
    """One device of «Devices», as its row: what the assistant's card names a device by."""
    device = TrustedDevice.objects.filter(pk=data.id).first()
    if device is None:
        raise NotFound(gettext("That device is no longer registered here. Refresh the list."))
    return _device_rows(ctx, [device])[0]


def _device_rows(ctx: OperationContext, devices: list[TrustedDevice]) -> list[dict[str, Any]]:
    """``devices`` as «Devices» lists them, with whether each has a session open now and until when."""
    now = timezone.now()
    here = device_of(ctx.request)
    until = dict(
        SessionOwner.objects.filter(host=ctx.scope.key, device_id__in=[d.pk for d in devices], session__expire_date__gt=now)
        .values("device_id")
        .annotate(until=Max("session__expire_date"))
        .values_list("device_id", "until")
    )
    return [
        {
            "id": device.pk,
            "name": device.name,
            "agent": device.agent,
            "mode": device.mode,
            "current": here is not None and device.pk == here.pk,
            "in_use": device.pk in until,
            "session_until": until.get(device.pk),
            "last_entry_at": device.last_entry_at,
            "last_user": device.last_user_label,
            "created_at": device.created_at,
            "unused": _unused(device, here, now),
        }
        for device in devices
    ]


def _unused(device: TrustedDevice, here: TrustedDevice | None, now) -> bool:
    return (here is None or device.pk != here.pk) and device.last_entry_at < now - access.UNUSED_AFTER


def unused_devices(here: TrustedDevice | None):
    """The devices «Remove the unused» removes: nobody entered on them in 30 days, never the one in hand."""
    old = TrustedDevice.objects.filter(last_entry_at__lt=timezone.now() - access.UNUSED_AFTER)
    return old.exclude(pk=here.pk) if here is not None else old
