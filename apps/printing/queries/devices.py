"""The devices that print (PRINTING-F18): the list, one of them, the one that says hello and who covers a function."""

from django.db.models import Prefetch
from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.printing.models import PrintDevice, Printer
from apps.printing.schemas.devices import (
    CoverageIn,
    CoverageOut,
    DeviceGetIn,
    DeviceGetOut,
    DeviceListIn,
    DeviceOut,
    DeviceRefIn,
)
from apps.printing.schemas.fields import Page
from base.queries.devices import ended_by_the_device_limit

from .device_reads import active_devices, device_row, find_device, this_device_key
from .waiting import coverage, stalled

#: The printers of a device, by name, read with it.
_BY_NAME = Prefetch("printers", queryset=Printer.objects.order_by(Lower("name"), "id"))


@operation(
    "printing.device.list",
    kind="query",
    permission="printing.view_settings",
    input=DeviceListIn,
    output=Page[DeviceOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which stations are registered, and when were they last seen?",
                "list the stations and when each was last seen",
            ),
            "es": (
                "¿desde qué equipos se imprime en el negocio?",
                "¿qué equipos están dados de alta y cuándo se vieron por última vez?",
            ),
        },
        "description": "List the devices set up to print, by name: the printers each one reaches and prints for, who set "
        "it up and when it was last seen (connected to print, or asked for a job). Only these devices print; their own "
        "ids are never shown."
    },
)
def list_devices(ctx: OperationContext, params: DeviceListIn) -> dict:
    devices = active_devices()
    total = devices.count()
    page = devices.prefetch_related(_BY_NAME).order_by(Lower("name"), "id")[params.offset : params.offset + params.limit]
    key, signed_out = this_device_key(ctx), frozenset(ended_by_the_device_limit())
    rows = [device_row(device, key, signed_out) for device in page]
    return {"rows": rows, "total": total, "limit": params.limit, "offset": params.offset}


@operation(
    "printing.device.detail",
    kind="query",
    permission="printing.view_settings",
    input=DeviceRefIn,
    output=DeviceOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "tell me about the Bar 2 station: what does it reach and when was it last seen?",
                "when did the Bar 2 station last report in?",
            ),
            "es": (
                "háblame del equipo Barra 2: a qué llega y cuándo se vio por última vez",
                "¿quién configuró el equipo Barra 2 para imprimir?",
            ),
        },
        "description": "Get one device set up to print by its registration id (printing.device.list): its name, the "
        "printers it reaches and prints for, who set it up and when it was last seen. A retired one is not there."
    },
)
def get_device_detail(ctx: OperationContext, params: DeviceRefIn) -> dict:
    return device_row(find_device(params.device_id), this_device_key(ctx))


# Not an assistant tool: /ws/print's hello, the device's own.
@operation(
    "printing.device.get",
    kind="query",
    permission="printing.print",
    input=DeviceGetIn,
    output=DeviceGetOut,
    ai=INTERNAL,
)
def get_device(ctx: OperationContext, params: DeviceGetIn) -> dict:
    """For base's /ws/print, at the hello: the device set up with the id it says, with its printers, or whether it
    was retired (the session that pairs a device new here does not pair a retired one). No route (the id never
    travels in a URL), no API key and no assistant."""
    key = PrintDevice.key_of(params.device)
    device = PrintDevice.objects.prefetch_related(_BY_NAME).filter(key=key).first()
    if device is None or device.retired_at is not None:
        return {"device": None, "retired": device is not None}
    return {"device": device_row(device, key), "retired": False}


@operation(
    "printing.device.coverage",
    kind="query",
    permission="printing.view_settings",
    input=CoverageIn,
    output=CoverageOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "does every function have a station set up, or are jobs waiting for nobody?",
                "is anybody covering the kitchen orders?",
            ),
            "es": (
                "¿tiene cada función un equipo dado de alta o hay trabajos esperando a nadie?",
                "¿hay alguien cubriendo los pedidos de cocina?",
            ),
        },
        "description": "Whether a function (receipt, kitchen, bar, label) has a device set up to print it, on or not, and "
        "how many of its jobs have waited a minute or more with no device on to print them (none set up for them, or "
        "the one set up gave no news in the last 90 s). «Is anybody printing the kitchen orders?»"
    },
)
def device_coverage(ctx: OperationContext, params: CoverageIn) -> dict:
    """The Home's «Set up your printer» (``configured`` of the receipts) and the bell's «Nothing is printing» (``count``)."""
    configured, _unattended = coverage([params.usage])[params.usage]
    return {"usage": params.usage, "configured": configured, "count": stalled([params.usage])[params.usage]}
