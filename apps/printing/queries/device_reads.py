"""A device set up to print (PRINTING-F18), as the reads and the writes share it, without operations: the key of the
one that asks, the live ones, one by its id and how the screens read it."""

import datetime as dt
import uuid

from django.db.models import QuerySet
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound

from apps.printing.models import PrintDevice

#: A device set up here is there while its last news is this recent: its hello or a beat on base's /ws/print, asking for
#: a job or being set up from it (the old hub's ``HOST_TTL_SECONDS``: three missed beats of 30 s).
SEEN_WITHIN = dt.timedelta(seconds=90)

NO_DEVICE = _("There is no device set up to print with that id.")

#: The header the SPA names its device with (``@erplora/ui``'s ``DEVICE_ID_HEADER``), on every request and stream.
DEVICE_HEADER = "X-Device-Id"


def this_device_key(ctx: OperationContext) -> str | None:
    """The key of the device the caller uses, from the request's ``X-Device-Id``; none without one (the assistant,
    an API key, the worker)."""
    request = ctx.request
    headers = getattr(request, "headers", None)
    device_id = (headers.get(DEVICE_HEADER) or "").strip() if headers is not None else ""
    return PrintDevice.key_of(device_id) if device_id else None


def active_devices() -> QuerySet[PrintDevice]:
    return PrintDevice.objects.filter(retired_at__isnull=True)


def find_device(device_id: uuid.UUID, *, lock: bool = False) -> PrintDevice:
    devices = active_devices().select_for_update() if lock else active_devices()
    found = devices.filter(pk=device_id).first()
    if found is None:
        raise NotFound(str(NO_DEVICE), code="printing.device_not_found")
    return found


def device_row(device: PrintDevice, this_key: str | None) -> dict:
    """A device as the screens read it: its printers by name, and whether it is the one asking. Never its key."""
    prefetched = "printers" in getattr(device, "_prefetched_objects_cache", {})
    printers = device.printers.all() if prefetched else device.printers.order_by(Lower("name"), "id")
    return {
        "id": device.id,
        "name": device.name,
        "printers": [
            {"id": printer.id, "name": printer.name, "usage": printer.usage, "is_active": printer.is_active}
            for printer in printers
        ],
        "registered_at": device.registered_at,
        "registered_by": device.registered_by,
        "last_seen_at": device.last_seen_at,
        "this_device": this_key is not None and device.key == this_key,
    }
