"""The printers: how one is found and held, its state, the list, one of them and how it is doing.

A printer's state is read, never stored: inactive; failing when its last failure is newer than its last
paper; waiting when a job of its own has been queued for over a minute; ready otherwise.
"""

import datetime as dt
import uuid

from django.db.models import Count, Min, Q, QuerySet
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.printing.models import Printer, PrintJob
from apps.printing.schemas.fields import Page
from apps.printing.schemas.printers import PrinterListIn, PrinterOut, PrinterRefIn, PrinterStatusOut
from base.ordering import list_order

from .settings import DEFAULT_FIELDS, current_settings
from .waiting import PENDING

#: A job of a printer queued for longer than this makes the printer «waiting».
WAITING_AFTER = dt.timedelta(minutes=1)

NO_PRINTER = _("There is no printer with that name.")


def _as_uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(text))
    except ValueError:
        return None


def first_held(printers: QuerySet[Printer]) -> Printer | None:
    """The first printer of ``printers``, held until this transaction ends with a key-share lock, taken in the
    same read: the admin's deletion waits for it, while another write that names it (a job, a test page, the
    settings) or changes it goes on, so two writes never wait for each other in a circle (a deadlock is a
    500). The ORM has no ``FOR KEY SHARE``: it is appended to the SQL the ORM wrote, and the row still comes
    from the hub's database by the router."""
    sql, params = printers[:1].query.sql_with_params()
    return next(iter(Printer.objects.raw(f"{sql} FOR KEY SHARE", params)), None)


def find_printer(
    printer_id: uuid.UUID | None,
    name: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
    rows: QuerySet[Printer] | None = None,
) -> Printer:
    """The printer named by its id, or by its name (whatever its case; a name may also carry an id). It comes
    from ``rows`` when given (a read: with its queue): one read, so a deletion committed meanwhile is either
    not seen yet or not found, never a row that vanished between two reads. ``lock`` takes it to change it
    (``FOR NO KEY UPDATE``: a write that only names it goes on); ``hold`` takes it to name it (key share)."""
    printers = Printer.objects.all() if rows is None else rows
    if lock:
        printers = printers.select_for_update(no_key=True)
    first = first_held if hold else (lambda found: found.first())
    found = None
    if printer_id is not None:
        found = first(printers.filter(pk=printer_id))
    elif name is not None:
        as_id = _as_uuid(name)
        if as_id is not None:
            found = first(printers.filter(pk=as_id))
        if found is None:
            found = first(printers.annotate(lowered=Lower("name")).filter(lowered=name.strip().lower()))
    if found is None:
        raise NotFound(str(NO_PRINTER), code="printing.printer_not_found")
    return found


def _with_queue(printers: QuerySet[Printer]) -> QuerySet[Printer]:
    return printers.annotate(
        queued=Count("jobs", filter=Q(jobs__status=PrintJob.Status.PENDING)),
        oldest=Min("jobs__created_at", filter=Q(jobs__status=PrintJob.Status.PENDING)),
    )


def printer_state(printer: Printer, oldest_pending: dt.datetime | None, now: dt.datetime) -> str:
    if not printer.is_active:
        return "inactive"
    if printer.last_failed_at and (printer.last_printed_at is None or printer.last_failed_at > printer.last_printed_at):
        return "failing"
    if oldest_pending is not None and now - oldest_pending > WAITING_AFTER:
        return "waiting"
    return "ready"


def printer_row(printer: Printer, now: dt.datetime | None = None) -> dict:
    """A printer as the screens and the assistant read it, with its queue: annotated by the read that found
    it, or read now by a service after its write (the printer locked or just created)."""
    now = now or timezone.now()
    if not hasattr(printer, "queued"):
        printer = _with_queue(Printer.objects.filter(pk=printer.pk)).get()
    return {
        "id": printer.id,
        "name": printer.name,
        "kind": printer.kind,
        "address": printer.address,
        "port": printer.port,
        "paper_width": printer.paper_width,
        "usage": printer.usage,
        "is_active": printer.is_active,
        "target": printer.target,
        "oldest_pending_at": printer.oldest,
        "state": printer_state(printer, printer.oldest, now),
        "pending": printer.queued,
        "last_printed_at": printer.last_printed_at,
        "last_failed_at": printer.last_failed_at,
        "last_error": printer.last_error,
        "created_at": printer.created_at,
    }


_PRINTER_SORT = {"name": Lower("name"), "usage": "usage", "kind": "kind", "created_at": "created_at"}


@operation(
    "printing.printer.list",
    kind="query",
    permission="printing.view_settings",
    input=PrinterListIn,
    output=Page[PrinterOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what printers do I have?",
                "show me the printers of the business",
                "which printers are inactive?",
            ),
            "es": (
                "¿qué impresoras tengo?",
                "enséñame las impresoras del negocio",
                "¿qué impresoras hay de cocina?",
            ),
        },
        "description": "List the business's printers by name, with their connection, address, paper, function "
        "(receipt, kitchen, bar, label), whether they are active and their state (ready, waiting, failing, inactive). "
        "Search by name or address; filter by function, connection or active."
    },
)
def list_printers(ctx: OperationContext, params: PrinterListIn) -> dict:
    printers = Printer.objects.all()
    if params.search:
        printers = printers.filter(Q(name__icontains=params.search) | Q(address__icontains=params.search))
    if params.usage:
        printers = printers.filter(usage=params.usage)
    if params.kind:
        printers = printers.filter(kind=params.kind)
    if params.is_active is not None:
        printers = printers.filter(is_active=params.is_active)
    total = printers.count()
    order = list_order(_PRINTER_SORT[params.sort], descending=params.dir == "desc")
    page = _with_queue(printers).order_by(*order)[params.offset : params.offset + params.limit]
    now = timezone.now()
    return {"rows": [printer_row(p, now) for p in page], "total": total, "limit": params.limit, "offset": params.offset}


@operation(
    "printing.printer.get",
    kind="query",
    permission="printing.view_settings",
    input=PrinterRefIn,
    output=PrinterOut,
    expose_api=True,
    ai={
        "description": "Get one printer by its id or its name («the kitchen one» → Kitchen), with its state.",
        "asks": {
            "en": (
                "tell me about the kitchen printer",
                "what IP does the Till printer have?",
            ),
            "es": (
                "háblame de la impresora de cocina",
                "¿qué IP tiene la impresora de la caja?",
                "¿de qué papel es la impresora Caja 2?",
            ),
        },
    },
)
def get_printer(ctx: OperationContext, params: PrinterRefIn) -> dict:
    return printer_row(find_printer(params.printer_id, params.printer, rows=_with_queue(Printer.objects.all())))


@operation(
    "printing.printer.status",
    kind="query",
    permission="printing.view_settings",
    input=PrinterRefIn,
    output=PrinterStatusOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the kitchen printer working?",
                "why is the Till printer not printing?",
                "when did the bar printer last print?",
            ),
            "es": (
                "¿funciona la impresora de cocina?",
                "¿por qué no imprime la impresora de la caja?",
                "¿cuándo imprimió por última vez la de la barra?",
            ),
        },
        "description": "How a printer is doing, by its name or id: its state, how many of its jobs wait and since when, "
        "how many a device has and how many failed, when it last printed, its last error and whether it is the printer "
        "of its function. «Is the kitchen printer working?»"
    },
)
def printer_status(ctx: OperationContext, params: PrinterRefIn) -> dict:
    printer = find_printer(params.printer_id, params.printer, rows=_with_queue(Printer.objects.all()))
    jobs = PrintJob.objects.filter(printer=printer).aggregate(
        pending=Count("id", filter=PENDING),
        oldest=Min("created_at", filter=PENDING),
        sent=Count("id", filter=Q(status=PrintJob.Status.SENT)),
        failed=Count("id", filter=Q(status=PrintJob.Status.FAILED)),
    )
    settings = current_settings()
    return {
        "printer": printer_row(printer),
        "is_default": getattr(settings, f"{DEFAULT_FIELDS[printer.usage]}_id") == printer.id,
        "pending": jobs["pending"],
        "oldest_pending_at": jobs["oldest"],
        "sent": jobs["sent"],
        "failed": jobs["failed"],
    }
