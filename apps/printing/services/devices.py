"""The devices that print (PRINTING-F18): set up from the device itself, seen while they are there, and changed or
retired from any device."""


from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import PrintDevice, Printer
from apps.printing.queries.device_reads import active_devices, device_row, find_device, this_device_key
from apps.printing.queries.jobs import actor
from apps.printing.schemas.devices import (
    DeviceOut,
    DeviceRefIn,
    DeviceRegisterIn,
    DeviceSeenIn,
    DeviceSeenOut,
    DeviceUpdateIn,
)
from apps.printing.services.writes import MANAGE_SETTINGS

DEVICE_UNKNOWN = _("Set a device up from the device itself: this request does not say which device it is.")
CHOOSE_PRINTERS = _("Choose the printers this device reaches.")
NOT_ACTIVE_PRINTERS = _("Choose active printers of this business.")


def _reached_printers(ids: list) -> list[Printer]:
    """The active printers of the business named by ``ids``; a 422 at ``printers`` if none or one is not."""
    if not ids:
        raise InvalidPayload(str(CHOOSE_PRINTERS), fields={"printers": str(CHOOSE_PRINTERS)})
    found = list(Printer.objects.filter(pk__in=ids, is_active=True))
    if len(found) != len(set(ids)):
        raise InvalidPayload(str(NOT_ACTIVE_PRINTERS), fields={"printers": str(NOT_ACTIVE_PRINTERS)})
    return found


@operation(
    "printing.device.register",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SETTINGS,
    input=DeviceRegisterIn,
    output=DeviceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "enroll this station as the one that prints",
                "this counter's station will take the print jobs",
            ),
            "es": (
                "deja este equipo encargado de la impresión de los tickets",
                "este equipo se encargará de los trabajos de impresión",
            ),
        },
        "description": "Set up the device the person is using to print, with its name and the printers it reaches: from "
        "then on it prints their jobs with anybody's session. Only from the device itself (it says which device it is); "
        "setting up a retired device again brings it back.",
        "risk": "high",
    },
)
def register_device(ctx: OperationContext, data: DeviceRegisterIn) -> dict:
    key = this_device_key(ctx)
    if key is None:
        raise InvalidPayload(str(DEVICE_UNKNOWN), code="printing.device_required")
    printers = _reached_printers(data.printers)
    device = PrintDevice.objects.select_for_update().filter(key=key).first()
    if device is None:
        try:
            with atomic():
                device = PrintDevice.objects.create(key=key, name=data.name, registered_by=actor(ctx))
        except IntegrityError:
            device = PrintDevice.objects.select_for_update().get(key=key)
    # Set up from the device in hand: it is there (a re-registration counts as news).
    device.name, device.retired_at, device.retired_by, device.last_seen_at = data.name, None, "", timezone.now()
    device.save(update_fields=["name", "retired_at", "retired_by", "last_seen_at"])
    device.printers.set(printers)
    record_event(ctx, events.DEVICE_REGISTERED, {"id": str(device.id)})
    return device_row(device, key)


# Not an assistant tool: /ws/print's hello and beats, the device's own.
@operation(
    "printing.device.seen",
    kind="command",
    permission="printing.print",
    input=DeviceSeenIn,
    output=DeviceSeenOut,
    ai=INTERNAL,
)
def see_device(ctx: OperationContext, data: DeviceSeenIn) -> dict:
    """The device's presence: base's /ws/print runs it at the hello and at the beats of a device that prints
    (``print_presence`` of this app), as the device's user, so ``printing.print`` is all it asks — whoever is signed in
    at the till prints. The device set up with that id (not retired) is there now; anything else is not, and nothing is
    set up by being there. No event: every device beats every 30 s, and the bell reads the clock instead
    (``bell_refresh_every``). No route, no API key and no assistant: the id never travels in a URL."""
    seen = active_devices().filter(key=PrintDevice.key_of(data.device)).update(last_seen_at=timezone.now())
    return {"seen": seen > 0}


@operation(
    "printing.device.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SETTINGS,
    input=DeviceUpdateIn,
    output=DeviceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the name and the printers of the Bar 2 station",
                "make this station reach the kitchen printer too",
            ),
            "es": (
                "cambia el nombre del equipo de impresión Barra 2",
                "haz que este equipo también llegue a la impresora de cocina",
            ),
        },
        "description": "Rename a device that prints, or change the printers it reaches, by its registration id "
        "(printing.device.list). From any device.",
        "risk": "high",
    },
)
def update_device(ctx: OperationContext, data: DeviceUpdateIn) -> dict:
    device = find_device(data.device_id, lock=True)
    if data.name is not None:
        device.name = data.name
        device.save(update_fields=["name"])
    if data.printers is not None:
        device.printers.set(_reached_printers(data.printers))
    record_event(ctx, events.DEVICE_UPDATED, {"id": str(device.id)})
    return device_row(device, this_device_key(ctx))


@operation(
    "printing.device.retire",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SETTINGS,
    input=DeviceRefIn,
    output=DeviceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "retire the Bar 2 station for good",
                "that station was lost, take it out of service",
            ),
            "es": (
                "retira el dispositivo Barra 2, ya no está",
                "el equipo de la barra se ha perdido: retíralo",
            ),
        },
        "description": "Retire a device that prints (a till replaced or lost), by its registration id: it takes, confirms "
        "and fails no job any more, and printing from it does not set it up again. Its jobs in hand go back to the "
        "queue when their time to answer runs out.",
        "risk": "high",
    },
)
def retire_device(ctx: OperationContext, data: DeviceRefIn) -> dict:
    device = find_device(data.device_id, lock=True)
    device.retired_at, device.retired_by = timezone.now(), actor(ctx)
    device.save(update_fields=["retired_at", "retired_by"])
    record_event(ctx, events.DEVICE_RETIRED, {"id": str(device.id)})
    return device_row(device, this_device_key(ctx))
