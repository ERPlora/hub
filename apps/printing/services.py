"""Write operations of the printing app: one operation = one transaction, with its events in the outbox.

The queue's state machine is the old hub's (``print_queue.rs``): a job waits ``pending``; a device takes
it (``claim``: ``sent``, one more hand-out, a 90 s lease) with ``SELECT … FOR UPDATE SKIP LOCKED``, so two
devices never take the same one; the device confirms it (``done``) or reports its failure (back to
``pending``, or ``failed`` after 5 hand-outs); a lease that runs out puts it back in the queue at the next
claim. A person retries a failed (or unanswered) job or cancels it, stamped. A job that ended (printed,
cancelled or failed) is forgotten 30 days later by the hourly prune, the platform's own (PRINTING-F20).

Every app that prints calls ``printing.job.create`` by name inside its own transaction; the job is the
structured document the app's renderer paints, never bytes (PLAN-HUB §5; hub#501).
"""

import datetime as dt
import ipaddress
import logging
import re
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Coalesce, Lower
from django.template.loader import render_to_string
from django.utils import timezone, translation
from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from live.operations import UnknownOperation, operation
from live.operations import get as operation_named
from live.outbox import record_event

from apps.printing import documents, events
from apps.printing.models import Printer, PrintJob, Settings
from apps.printing.queries import (
    DEFAULT_FIELDS,
    LEASE,
    MAX_ATTEMPTS,
    actor,
    cancellable,
    current_settings,
    find_job,
    find_printer,
    first_held,
    is_stale,
    job_row,
    printer_row,
    retryable,
    settings_row,
)
from apps.printing.schemas import (
    EmptyIn,
    JobAckOut,
    JobCancelIn,
    JobClaimIn,
    JobClaimOut,
    JobCompleteIn,
    JobCreateIn,
    JobCreateOut,
    JobFailIn,
    JobOut,
    JobRefIn,
    PrinterIn,
    PrinterOut,
    PrinterRefIn,
    PrinterUpdateIn,
    PruneOut,
    SettingsOut,
    SettingsPatchIn,
)

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9100
#: Run only by the platform (the scheduled prune): no role is given it, and it has no route.
SYSTEM = "printing.system"
#: How long the queue keeps a job after it ended — printed, cancelled or failed (PRINTING-F20).
KEEP_FINISHED = dt.timedelta(days=30)
#: The most jobs one prune deletes: an hourly run never holds the queue for long.
PRUNE_BATCH = 500

PRINTER_EXISTS = _("There is already a printer with that name.")
BAD_HOST = _("Type a valid IP or network name (for example 192.168.1.100).")
BAD_PORT = _("The port goes from 1 to 65535.")
PORT_ONLY_NETWORK = _("Only a network printer has a port.")
BAD_MAC = _("Type the MAC as AA:BB:CC:DD:EE:FF.")
BAD_QUEUE = _("Type the print queue's name as the system gives it (no spaces, slashes or #).")
SYSTEM_NO_ADDRESS = _("The system printer is the computer's own: it has no address.")
SYSTEM_RECEIPTS = _("The system printer prints A4 pages: give it the Receipt role.")
NOT_ITS_FUNCTION = _("That printer does not have this role.")
DEFAULT_INACTIVE = _("That printer is inactive.")
TEST_INACTIVE = _("That printer is inactive: activate it to test it.")
JOB_PRINTER_INACTIVE = _("That printer is inactive: activate it or print on another one.")
JOB_PRINTER_INCOMPATIBLE = _(
    "That printer cannot print this paper: A4 pages go to the system printer and receipts to a receipt printer."
)
NOT_RETRYABLE = _(
    "Only a queued or failed job, or a sent one with no answer, goes back to the queue; this one is %(status)s."
)
NOT_YOURS = _("That job is not this device's: another device or another hand-out has it now.")
NOT_CANCELLABLE = _("A job that is printing or has printed is not cancelled; this one is %(status)s.")
NO_ANSWER = _("No answer from the device.")
TEST_PAGE = _("Test page")

#: The amounts' currency when the caller does not say (the one Sales charges in until the Hub keeps its own).
DEFAULT_CURRENCY = "EUR"
#: Documents whose copies after the first are duplicates, never a second original (RD 1619/2012 art. 14.4).
FISCAL_PAPERS = ("receipt", "invoice")

_HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")
_MAC = re.compile(r"^[0-9A-Fa-f]{1,2}([:-])[0-9A-Fa-f]{1,2}(\1[0-9A-Fa-f]{1,2}){4}$")
_QUEUE_FORBIDDEN = re.compile(r"[ \t/#\x00-\x1f\x7f]")
#: The longest OS print queue name the app accepts (``CUPS_MAX_QUEUE_NAME``).
MAX_QUEUE_NAME = 127


# ── Printers ──────────────────────────────────────────────────────────────────────────────────────


def _host_ok(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return bool(_HOSTNAME.match(host))
    return True


def _normalize_mac(mac: str) -> str:
    return ":".join(part.zfill(2) for part in re.split(r"[:-]", mac.upper()))


def _connection(kind: str, address: str, port: int | None, usage: str) -> tuple[str, int | None]:
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
    permission="printing.manage_settings",
    input=PrinterIn,
    output=PrinterOut,
    expose_api=True,
    ai={
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
        with transaction.atomic():
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
    permission="printing.manage_settings",
    input=PrinterUpdateIn,
    output=PrinterOut,
    expose_api=True,
    ai={
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
        with transaction.atomic():
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
        job.printer = _resolve_printer(job.usage, job.format, settings)
        job.save(update_fields=["printer"])
        _queued(ctx, job)


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with transaction.atomic():
            return Settings.objects.create(updated_by=actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


def _chosen_printer(field: str, ref: str | None, usage: str) -> Printer | None:
    """The printer chosen for ``usage`` (by id or name): one of its own and active; ``None`` clears it. It is
    held until the settings that name it are saved: a deletion waits for them."""
    if ref is None:
        return None
    try:
        printer = find_printer(None, ref, hold=True)
    except NotFound as missing:  # said at the field the person filled
        raise InvalidPayload(missing.message, fields={field: missing.message}) from None
    if printer.usage != usage:
        raise InvalidPayload(str(NOT_ITS_FUNCTION), fields={field: str(NOT_ITS_FUNCTION)})
    if not printer.is_active:
        raise InvalidPayload(str(DEFAULT_INACTIVE), fields={field: str(DEFAULT_INACTIVE)})
    return printer


@operation(
    "printing.settings.update",
    kind="command",
    permission="printing.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change how the business prints, field by field: print the receipt by itself at checkout, open the "
        "drawer with it, receipt copies (1 to 3), and the printer of each function by its name («the kitchen orders go "
        "to Kitchen 2»; null = the first active one of that function). What is not sent is kept.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True)
    values: dict = {}
    for field, value in sent.items():
        usage = next((u for u, f in DEFAULT_FIELDS.items() if f == field), None)
        if usage is not None:
            values[field] = _chosen_printer(field, value, usage)
        elif value is not None:
            values[field] = value
    changes = {field: value for field, value in values.items() if getattr(settings, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)


# ── The queue ─────────────────────────────────────────────────────────────────────────────────────


def _resolve_printer(usage: str, paper: str, settings: Settings) -> Printer | None:
    """The printer of ``usage`` for ``paper``: the settings' choice, else the first active one by name. It is
    held until the job that names it is saved: a deletion waits for it, and one deleted before is passed over."""
    printers = Printer.objects.filter(is_active=True)
    printers = printers.filter(kind=Printer.Kind.SYSTEM) if paper == PrintJob.Format.A4 else printers.exclude(kind=Printer.Kind.SYSTEM)
    chosen_id = getattr(settings, f"{DEFAULT_FIELDS[usage]}_id")
    chosen = first_held(printers.filter(pk=chosen_id)) if chosen_id else None
    return chosen or first_held(printers.filter(usage=usage).order_by(Lower("name"), "id"))


def _queued(ctx: OperationContext, job: PrintJob) -> None:
    record_event(
        ctx,
        events.JOB_QUEUED,
        {
            "id": str(job.id),
            "usage": job.usage,
            "printer_id": str(job.printer_id) if job.printer_id else None,
            "kind": job.kind,
        },
    )


def _status_label(job: PrintJob) -> str:
    return str(PrintJob.Status(job.status).label).lower()


def _given_printer(ref: str, paper: str) -> Printer:
    """The printer a job is sent to by its name or id, held until the job is saved: a deletion waits for it."""
    printer = find_printer(None, ref, hold=True)
    if not printer.is_active:
        raise Conflict(str(JOB_PRINTER_INACTIVE), code="printing.printer_inactive")
    if printer.format != paper:
        raise Conflict(str(JOB_PRINTER_INCOMPATIBLE), code="printing.printer_incompatible")
    return printer


def _stamped(ctx: OperationContext, data: JobCreateIn) -> dict:
    """The document with the envelope the paper needs when the caller left it out: its language (the
    caller's) and, but on a generic document (which prints every key), its money scale (hub#1159, #2129)."""
    document = dict(data.document)
    if data.format != PrintJob.Format.RECEIPT:
        return document
    document.setdefault("locale", ctx.language)
    if data.document_type != "generic":
        document.setdefault("decimals", get_currency_precision(data.currency or DEFAULT_CURRENCY))
    return document


def _business_name(ctx: OperationContext) -> str:
    """The business's legal name as Invoicing keeps it, by its operation; empty when Invoicing is not here,
    not on, not set up or not open to this person (the test page then says «ERPlora»)."""
    try:
        issuer = operation_named("invoice.issuer.get")
        found = issuer(ctx, issuer.input.model_validate({}))
    except (UnknownOperation, OperationError):
        return ""
    return found.legal_name


def _new_job(ctx: OperationContext, **values) -> PrintJob:
    """Writes the job unless its key is already in the queue (two at once write one)."""
    try:
        with transaction.atomic():
            return PrintJob.objects.create(created_by=actor(ctx), **values)
    except IntegrityError:
        existing = PrintJob.objects.filter(job_key=values["job_key"]).first()
        if existing is None:
            raise
        existing.duplicate = True
        return existing


@operation(
    "printing.job.create",
    kind="command",
    permission="printing.print",
    input=JobCreateIn,
    output=JobCreateOut,
    expose_api=True,
    ai={
        "description": "Print a document: put it in the print queue, where the device next to its printer prints it. "
        "The document is structured (a receipt: business_name, receipt_id, items [{name, quantity, total}], totals, "
        "payment; a barcode label: product_name, barcode, price) and goes to the printer of its function, or to a "
        "printer named («print it on Kitchen»). The same job_key twice is one job.",
        "risk": "normal",
    },
)
def create_job(ctx: OperationContext, data: JobCreateIn) -> dict:
    # An A4 page carries its own content: the receipt printer's checks are for the structured document.
    problem = documents.problems(data.document_type if data.format == "receipt" else "generic", data.document)
    if problem:
        raise InvalidPayload(problem, fields={"document": problem})
    job_key = data.job_key or f"job-{uuid.uuid7()}"
    existing = PrintJob.objects.select_related("printer").filter(job_key=job_key).first()
    if existing is not None:
        return {"job": job_row(existing), "duplicate": True, "skipped": None}
    settings = current_settings()
    usage = data.usage or documents.default_usage(data.document_type)
    if data.printer is not None:
        printer = _given_printer(data.printer, data.format)
    else:
        printer = _resolve_printer(usage, data.format, settings)
    reference = (data.source_ref or documents.reference(data.document))[:64]
    document = _stamped(ctx, data)
    common = {
        "job_key": job_key,
        "usage": usage,
        "printer": printer,
        "reference": reference,
        "source_app": data.source_app or "",
    }
    skipped = None
    if data.automatic and not settings.print_receipt_on_sale:
        skipped = "print_on_sale_off"
        if not settings.open_drawer_on_sale:
            return {"job": None, "duplicate": False, "skipped": skipped}
        # The receipt stays in the drawer's printer's tray: only the kick travels.
        job = _new_job(ctx, kind=PrintJob.Kind.DRAWER, open_drawer=True, **common)
    else:
        # An A4 page prints once (a copy would be a second original); a receipt takes the settings' copies.
        if data.format == PrintJob.Format.A4:
            copies = 1
        else:
            copies = data.copies or (settings.receipt_copies if data.document_type == "receipt" else 1)
        job = _new_job(
            ctx,
            kind=PrintJob.Kind.DOCUMENT,
            document_type=data.document_type,
            document=document,
            html=data.html or "",
            format=data.format,
            copies=copies,
            open_drawer=data.automatic and settings.open_drawer_on_sale,
            **common,
        )
    if getattr(job, "duplicate", False):
        return {"job": job_row(job), "duplicate": True, "skipped": None}
    _queued(ctx, job)
    return {"job": job_row(job), "duplicate": False, "skipped": skipped}


@operation(
    "printing.printer.test",
    kind="command",
    permission="printing.print",
    input=PrinterRefIn,
    output=JobOut,
    expose_api=True,
    ai={
        "description": "Print a test page on a printer, named by its name or id («test the kitchen printer»): the device "
        "next to it prints the sheet with the printer's address and the time, or an A4 page on the system printer.",
        "risk": "normal",
    },
)
def test_printer(ctx: OperationContext, data: PrinterRefIn) -> dict:
    # Held until its test page is saved: a deletion waits for it.
    printer = find_printer(data.printer_id, data.printer, hold=True)
    if not printer.is_active:
        raise Conflict(str(TEST_INACTIVE), code="printing.printer_inactive")
    # Read before any write of this command (a query runs READ ONLY).
    business_name = _business_name(ctx)
    page = {"locale": ctx.language, **({"business_name": business_name} if business_name else {})}
    html = ""
    if printer.format == PrintJob.Format.A4:
        with translation.override(ctx.language):
            html = render_to_string(
                "printing/test_page.html",
                {
                    "printer": printer.name,
                    "business": business_name or "ERPlora",
                    "when": timezone.localtime(),
                    "language": ctx.language,
                },
            )
    job = _new_job(
        ctx,
        job_key=f"test-{uuid.uuid7()}",
        kind=PrintJob.Kind.TEST_PAGE,
        document=page,
        html=html,
        format=printer.format,
        usage=printer.usage,
        printer=printer,
        reference=printer.name[:64],
    )
    _queued(ctx, job)
    return job_row(job)


# ── The device that prints (base's /ws/print) ─────────────────────────────────────────────────────


def _reclaim_expired(ctx: OperationContext, now) -> None:
    """Jobs whose device never answered go back to the queue, or fail after their last hand-out."""
    expired = PrintJob.objects.select_for_update(skip_locked=True).filter(
        status=PrintJob.Status.SENT, leased_until__lt=now
    )
    for job in expired:
        job.leased_until = None
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.failed_at, job.last_error = PrintJob.Status.FAILED, now, str(NO_ANSWER)
            job.save(update_fields=["status", "leased_until", "failed_at", "last_error"])
            record_event(ctx, events.JOB_FAILED, {"id": str(job.id), "final": True})
        else:
            job.status = PrintJob.Status.PENDING
            job.save(update_fields=["status", "leased_until"])
            _queued(ctx, job)


def _copy_of(job: PrintJob) -> dict | None:
    """What the copies after the first print: a receipt or an invoice marked duplicate, never a second
    original (RD 1619/2012 art. 14.4; the renderer prints «DUPLICADO» with ``duplicate``); anything else as is."""
    if job.copies < 2:
        return None
    if job.document_type in FISCAL_PAPERS:
        return {**job.document, "duplicate": True}
    return job.document


@operation(
    "printing.job.claim",
    kind="command",
    permission="printing.print",
    input=JobClaimIn,
    output=JobClaimOut,
    expose_api=True,
    ai={
        "description": "For the device that prints (base's /ws/print): take the oldest queued job of the printers this "
        "device reaches, or one with no printer of their function. It is marked sent for 90 s; without an answer it "
        "goes back to the queue. Not for a person.",
        "risk": "high",
    },
)
def claim_job(ctx: OperationContext, data: JobClaimIn) -> dict:
    now = timezone.now()
    _reclaim_expired(ctx, now)
    printers = {p.id: p for p in Printer.objects.filter(pk__in=data.printers, is_active=True)}
    if not printers:
        return {"job": None}
    mine = Q()
    for printer in printers.values():
        mine |= Q(printer=printer) | Q(printer__isnull=True, usage=printer.usage, format=printer.format)
    job = (
        PrintJob.objects.select_for_update(skip_locked=True)
        .filter(mine, status=PrintJob.Status.PENDING)
        .order_by("created_at", "id")
        .first()
    )
    if job is None:
        return {"job": None}
    if job.printer_id is None:
        job.printer = next(p for p in printers.values() if p.usage == job.usage and p.format == job.format)
    printer = printers[job.printer_id]
    job.status = PrintJob.Status.SENT
    job.attempts += 1
    job.leased_until = now + LEASE
    job.sent_at = now
    job.device = data.device
    job.save(update_fields=["status", "attempts", "leased_until", "sent_at", "device", "printer"])
    record_event(ctx, events.JOB_CLAIMED, {"id": str(job.id), "printer_id": str(printer.id)})
    return {
        "job": {
            "id": job.id,
            "kind": job.kind,
            "printer_id": printer.id,
            "target": printer.target,
            "paper_width": printer.paper_width,
            "document_type": job.document_type,
            "document": job.document,
            "format": job.format,
            "html": job.html,
            "copies": job.copies,
            "copy_document": _copy_of(job),
            "open_drawer": job.open_drawer,
            "attempts": job.attempts,
        }
    }


@operation(
    "printing.job.complete",
    kind="command",
    permission="printing.print",
    input=JobCompleteIn,
    output=JobAckOut,
    expose_api=True,
    ai={
        "description": "For the device that prints: confirm a job came out on paper, saying which device and which "
        "hand-out. Confirming twice is one confirmation; a late confirmation of the device that took it is taken even "
        "if the job went back to the queue (the paper did come out). Another device: refused. Not for a person.",
        "risk": "high",
    },
)
def complete_job(ctx: OperationContext, data: JobCompleteIn) -> dict:
    job = find_job(data.job_id, None, lock=True)
    if job.device != data.device or data.attempt > job.attempts:
        raise Conflict(str(NOT_YOURS), code="printing.job_not_yours")
    if job.status == PrintJob.Status.DONE:
        return {"confirmed": True, "job": job_row(job)}
    # Its lease ran out and it went back to the queue, but the paper came out: taken, never printed twice.
    if job.status not in (PrintJob.Status.SENT, PrintJob.Status.PENDING):
        return {"confirmed": False, "job": job_row(job)}
    now = timezone.now()
    job.status, job.printed_at, job.leased_until = PrintJob.Status.DONE, now, None
    # RGPD: printed, the job keeps its number and its trail, not the customer's paper.
    job.document, job.html = {}, ""
    job.save(update_fields=["status", "printed_at", "leased_until", "document", "html"])
    Printer.objects.filter(pk=job.printer_id).update(last_printed_at=now)
    record_event(ctx, events.JOB_PRINTED, {"id": str(job.id)})
    return {"confirmed": True, "job": job_row(job)}


@operation(
    "printing.job.fail",
    kind="command",
    permission="printing.print",
    input=JobFailIn,
    output=JobAckOut,
    expose_api=True,
    ai={
        "description": "For the device that prints: say a job did not come out, with the device's error, the device "
        "and the hand-out it answers. It goes back to the queue, and fails after its fifth hand-out. Another device or "
        "another hand-out: refused. Not for a person.",
        "risk": "high",
    },
)
def fail_job(ctx: OperationContext, data: JobFailIn) -> dict:
    job = find_job(data.job_id, None, lock=True)
    if job.device != data.device or job.attempts != data.attempt:
        raise Conflict(str(NOT_YOURS), code="printing.job_not_yours")
    if job.status != PrintJob.Status.SENT:
        return {"confirmed": False, "job": job_row(job)}
    now = timezone.now()
    final = job.attempts >= MAX_ATTEMPTS
    job.status = PrintJob.Status.FAILED if final else PrintJob.Status.PENDING
    job.last_error, job.leased_until = data.error, None
    if final:
        job.failed_at = now
    job.save(update_fields=["status", "last_error", "leased_until", "failed_at"])
    Printer.objects.filter(pk=job.printer_id).update(last_failed_at=now, last_error=data.error)
    record_event(ctx, events.JOB_FAILED, {"id": str(job.id), "final": final})
    return {"confirmed": True, "job": job_row(job)}


# ── PRINTING-F14 Retry and cancel ─────────────────────────────────────────────────────────────────


@operation(
    "printing.job.retry",
    kind="command",
    permission="printing.manage_jobs",
    input=JobRefIn,
    output=JobOut,
    expose_api=True,
    ai={
        "description": "Send a queued or failed print job (or a sent one with no answer) back to the queue, named by its id or "
        "the number of its document («retry ticket T-000123»): its attempts start again, and if its printer is no "
        "longer active it goes to the printer of its function now.",
        "risk": "normal",
    },
)
def retry_job(ctx: OperationContext, data: JobRefIn) -> dict:
    job = find_job(data.job_id, data.reference, lock=True)
    now = timezone.now()
    if not retryable(job, now):
        raise Conflict(str(NOT_RETRYABLE) % {"status": _status_label(job)}, code="printing.job_not_retryable")
    if job.printer_id is None or not Printer.objects.filter(pk=job.printer_id, is_active=True).exists():
        job.printer = _resolve_printer(job.usage, job.format, current_settings())
    job.status, job.attempts, job.leased_until = PrintJob.Status.PENDING, 0, None
    job.retried_at, job.retried_by = now, actor(ctx)
    job.save(update_fields=["status", "attempts", "leased_until", "retried_at", "retried_by", "printer"])
    record_event(ctx, events.JOB_RETRIED, {"id": str(job.id)})
    _queued(ctx, job)
    return job_row(job)


@operation(
    "printing.job.cancel",
    kind="command",
    permission="printing.manage_jobs",
    input=JobCancelIn,
    output=JobOut,
    expose_api=True,
    ai={
        "description": "Cancel a print job that is queued, failed or sent with no answer, named by its id or the "
        "number of its document, with an optional reason. It is not printed and stays in the queue with who, when "
        "and why. A job a printer is printing or has printed is not cancelled.",
        "risk": "normal",
    },
)
def cancel_job(ctx: OperationContext, data: JobCancelIn) -> dict:
    job = find_job(data.job_id, data.reference, lock=True)
    now = timezone.now()
    if not cancellable(job, now):
        raise Conflict(str(NOT_CANCELLABLE) % {"status": _status_label(job)}, code="printing.job_not_cancellable")
    job.status, job.leased_until = PrintJob.Status.CANCELLED, None
    job.cancelled_at, job.cancelled_by, job.cancel_reason = now, actor(ctx), data.reason
    # RGPD: it will never print; it keeps its number and its trail, not the customer's paper.
    job.document, job.html = {}, ""
    job.save(update_fields=["status", "leased_until", "cancelled_at", "cancelled_by", "cancel_reason", "document", "html"])
    record_event(ctx, events.JOB_CANCELLED, {"id": str(job.id)})
    return job_row(job)


# ── PRINTING-F20 How long the queue keeps a job ───────────────────────────────────────────────────


@operation("printing.job.prune", kind="command", permission=SYSTEM, input=EmptyIn, output=PruneOut)
def prune_jobs(ctx: OperationContext, data: EmptyIn) -> dict:
    """Deletes the jobs that ended over ``KEEP_FINISHED`` ago (the oldest first, ``PRUNE_BATCH`` at most).
    A job still waiting or sent is never touched; a deleted job's key can be queued again."""
    cutoff = timezone.now() - KEEP_FINISHED
    finished = (PrintJob.Status.DONE, PrintJob.Status.CANCELLED, PrintJob.Status.FAILED)
    doomed = list(
        PrintJob.objects.filter(status__in=finished)
        .annotate(ended=Coalesce("printed_at", "cancelled_at", "failed_at", "created_at"))
        .filter(ended__lt=cutoff)
        .order_by("ended", "id")
        .values_list("pk", flat=True)[:PRUNE_BATCH]
    )
    if doomed:
        PrintJob.objects.filter(pk__in=doomed).delete()
        # Counted: a silent prune cannot be told from lost data the day somebody looks for an old job.
        logger.info("printing: deleted %d finished jobs older than %d days", len(doomed), KEEP_FINISHED.days)
        record_event(ctx, events.JOB_PRUNED, {"count": len(doomed)})
    return {"count": len(doomed)}

