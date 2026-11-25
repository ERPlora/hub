"""Printers (PRINTING-F03, F04): a printer of the business is added and changed by its name, with a connection
the app understands; one that leaves takes no queued job with it."""

import ipaddress
import re

from django.db import IntegrityError
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import Printer, PrintJob, Settings
from apps.printing.queries.job_printer import job_printer
from apps.printing.queries.jobs import actor
from apps.printing.queries.printers import find_printer, printer_row
from apps.printing.queries.settings import DEFAULT_FIELDS, current_settings
from apps.printing.schemas.printers import PrinterIn, PrinterOut, PrinterUpdateIn
from apps.printing.services.writes import _queued

DEFAULT_PORT = 9100

PRINTER_EXISTS = _("There is already a printer with that name.")
BAD_HOST = _("Type a valid IP or network name (for example 192.168.1.100).")
BAD_PORT = _("The port goes from 1 to 65535.")
PORT_ONLY_NETWORK = _("Only a network printer has a port.")
BAD_MAC = _("Type the MAC as AA:BB:CC:DD:EE:FF.")
BAD_QUEUE = _("Type the print queue's name as the system gives it (no spaces, slashes or #).")
SYSTEM_NO_ADDRESS = _("The system printer is the computer's own: it has no address.")
SYSTEM_RECEIPTS = _("The system printer prints A4 pages: give it the Receipt role.")

_HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_MAC = re.compile(r"^[0-9A-Fa-f]{1,2}([:-])[0-9A-Fa-f]{1,2}(\1[0-9A-Fa-f]{1,2}){4}$")
_QUEUE_FORBIDDEN = re.compile(r"[ \t/#\x00-\x1f\x7f]")
#: The longest OS print queue name the app accepts (``CUPS_MAX_QUEUE_NAME``).
MAX_QUEUE_NAME = 127


def _host_ok(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return bool(_HOSTNAME.match(host))
    return True


def _normalize_mac(mac: str) -> str:
    return ":".join(part.zfill(2) for part in re.split(r"[:-]", mac.upper()))


def _connection(kind: str, address: str, port: int | None, usage: str) -> tuple[str, int | None]:  # noqa: C901
    """The address and port a printer of ``kind`` keeps, normalized; a 422 at the field that is wrong.

    The rules are the app's (``discovery::parse_print_target``): a network printer is ``<ip>:<port>``, a
    Bluetooth one a MAC, a USB one the name of an OS print queue; the system printer has none.
    """
    address = address.strip()
    if kind == Printer.Kind.NETWORK:
        if not _host_ok(address):
            raise InvalidPayload(str(BAD_HOST), fields={"address": str(BAD_HOST)})
        port = DEFAULT_PORT if port is None else port
        if not 1 <= port <= 65535:
            raise InvalidPayload(str(BAD_PORT), fields={"port": str(BAD_PORT)})
        return address, port
    if port is not None:
        raise InvalidPayload(str(PORT_ONLY_NETWORK), fields={"port": str(PORT_ONLY_NETWORK)})
    if kind == Printer.Kind.BLUETOOTH:
        if not _MAC.match(address):
            raise InvalidPayload(str(BAD_MAC), fields={"address": str(BAD_MAC)})
        return _normalize_mac(address), None
    if kind == Printer.Kind.USB:
        if not address or address.startswith("-") or len(address.encode()) > MAX_QUEUE_NAME or _QUEUE_FORBIDDEN.search(address):
            raise InvalidPayload(str(BAD_QUEUE), fields={"address": str(BAD_QUEUE)})
        return address, None
    if address:
        raise InvalidPayload(str(SYSTEM_NO_ADDRESS), fields={"address": str(SYSTEM_NO_ADDRESS)})
    if usage != "receipt":
        raise InvalidPayload(str(SYSTEM_RECEIPTS), fields={"usage": str(SYSTEM_RECEIPTS)})
    return "", None


def _name_taken(name: str, *, but: Printer | None = None) -> bool:
    others = Printer.objects.annotate(lowered=Lower("name")).filter(lowered=name.lower())
    if but is not None:
        others = others.exclude(pk=but.pk)
    return others.exists()


def _refuse_taken_name() -> Conflict:
    return Conflict(str(PRINTER_EXISTS), code="printing.printer_exists", fields={"name": str(PRINTER_EXISTS)})


@operation(
    "printing.printer.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.manage_settings",
    input=PrinterIn,
    output=PrinterOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add a new printer called Kitchen 2 on 192.168.1.50",
                "add a receipt printer",
                "connect a bluetooth printer for labels",
            ),
            "es": (
                "añade una impresora nueva llamada Cocina 2 con la IP 192.168.1.50",
                "da de alta una impresora de tickets para la caja",
                "conecta una impresora bluetooth para etiquetas",
            ),
        },
        "description": "Add a printer of the business: its name (Till, Kitchen), its connection (network with its IP and "
        "port 9100, bluetooth with its MAC, usb with the name of the computer's print queue, or system for the "
        "computer's A4 printer), its paper (80 or 58 mm) and what it prints (receipt, kitchen, bar or label). Two "
        "printers never share a name.",
        "risk": "normal",
    },
)
def create_printer(ctx: OperationContext, data: PrinterIn) -> dict:
    address, port = _connection(data.kind, data.address, data.port, data.usage)
    if _name_taken(data.name):
        raise _refuse_taken_name()
    try:
        with atomic():
            printer = Printer.objects.create(
                name=data.name,
                kind=data.kind,
                address=address,
                port=port,
                paper_width=data.paper_width,
                usage=data.usage,
                is_active=data.is_active,
                created_by=actor(ctx),
            )
    except IntegrityError:
        raise _refuse_taken_name() from None
    record_event(ctx, events.PRINTER_CREATED, {"id": str(printer.id)})
    return printer_row(printer)


@operation(
    "printing.printer.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.manage_settings",
    input=PrinterUpdateIn,
    output=PrinterOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the IP, the paper and the name of the Caja 2 printer",
                "rename the Till printer to Front desk",
                "switch the kitchen printer to 58 mm paper",
                "deactivate the old bar printer",
            ),
            "es": (
                "cambia la IP, el papel y el nombre de la impresora Caja 2",
                "renombra la impresora de la caja como Recepción",
                "pon la impresora de cocina con papel de 58 mm",
                "desactiva la impresora de la barra",
            ),
        },
        "description": "Change a printer, named by its name or id: its name, connection, address, port, paper or "
        "function, or deactivate it (it takes no new jobs) and activate it again. A printer is never deleted. A "
        "printer that changes function stops being the chosen one of its old function.",
        "risk": "normal",
    },
)
def update_printer(ctx: OperationContext, data: PrinterUpdateIn) -> dict:
    printer = find_printer(data.printer_id, data.printer, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude={"printer_id", "printer"})
    kind = sent.get("kind") or printer.kind
    usage = sent.get("usage") or printer.usage
    if {"kind", "address", "port", "usage"} & set(sent):
        address = sent.get("address", printer.address)
        port = sent["port"] if "port" in sent else (printer.port if kind == Printer.Kind.NETWORK else None)
        if kind == Printer.Kind.SYSTEM and "address" not in sent:
            address = ""
        sent["address"], sent["port"] = _connection(kind, address, port, usage)
    if sent.get("name") is not None and _name_taken(sent["name"], but=printer):
        raise _refuse_taken_name()
    changes = {field: value for field, value in sent.items() if value is not None or field == "port"}
    changes = {field: value for field, value in changes.items() if getattr(printer, field) != value}
    if not changes:
        return printer_row(printer)
    old_usage = printer.usage
    for field, value in changes.items():
        setattr(printer, field, value)
    try:
        with atomic():
            printer.save(update_fields=[*changes, "updated_at"])
    except IntegrityError:
        raise _refuse_taken_name() from None
    if "usage" in changes:
        # It no longer prints its old function: it cannot stay the chosen printer of it.
        Settings.objects.filter(**{DEFAULT_FIELDS[old_usage]: printer}).update(
            **{DEFAULT_FIELDS[old_usage]: None}, updated_by=actor(ctx), updated_at=timezone.now()
        )
    if {"is_active", "usage", "kind"} & set(changes):
        _release_queue(ctx, printer, usage_changed="usage" in changes)
    record_event(ctx, events.PRINTER_UPDATED, {"id": str(printer.id), "fields": sorted(changes)})
    return printer_row(printer)


def _release_queue(ctx: OperationContext, printer: Printer, *, usage_changed: bool) -> None:
    """Its queued jobs it can no longer print go to the printer of their function now, or wait for one."""
    settings = current_settings()
    for job in PrintJob.objects.select_for_update().filter(printer=printer, status=PrintJob.Status.PENDING):
        keeps = printer.is_active and printer.format == job.format and not (usage_changed and printer.usage != job.usage)
        if keeps:
            continue
        job.printer = job_printer(job.usage, job.format, settings)
        job.save(update_fields=["printer"])
        _queued(ctx, job)
