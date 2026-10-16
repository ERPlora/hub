"""Read operations of the printing app (``READ ONLY``), and the helpers its services share.

A printer's state is read, never stored: inactive; failing when its last failure is newer than its last
paper; waiting when a job of its own has been queued for over a minute; ready otherwise. A job sent to a
device and unanswered past its 90 s lease is «stale»: it can be retried or cancelled, and the next claim
puts it back in the queue (services.py).
"""

import datetime as dt
import uuid

from django.db.models import Count, Min, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.printing.models import Printer, PrintJob, Settings, Usage
from apps.printing.schemas import (
    EmptyIn,
    JobListIn,
    JobOut,
    JobSummaryOut,
    Page,
    PrinterListIn,
    PrinterOut,
    PrinterRefIn,
    PrinterStatusOut,
    SettingsOut,
)

#: Hand-outs a job gets before it fails (the old hub's ``MAX_ATTEMPTS``).
MAX_ATTEMPTS = 5
#: How long a device has to answer for a job it took (the old hub's ``DEFAULT_LEASE_SECONDS``).
LEASE = dt.timedelta(seconds=90)
#: A job of a printer queued for longer than this makes the printer «waiting».
WAITING_AFTER = dt.timedelta(minutes=1)
#: The functions, in the order the screens and the summary show them.
USAGES = [usage.value for usage in Usage]
#: The settings' field of each function's printer.
DEFAULT_FIELDS = {usage: f"{usage}_printer" for usage in USAGES}

NO_PRINTER = _("There is no printer with that name.")
NO_JOB = _("There is no print job with that id or number.")

PENDING = Q(status=PrintJob.Status.PENDING)


def actor(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:128]


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


def current_settings() -> Settings:
    """The business's settings, or the factory ones (unsaved) when it never saved them."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    return {
        "print_receipt_on_sale": settings.print_receipt_on_sale,
        "open_drawer_on_sale": settings.open_drawer_on_sale,
        "receipt_copies": settings.receipt_copies,
        **{f"{field}_id": getattr(settings, f"{field}_id") for field in DEFAULT_FIELDS.values()},
        # The factory values are an unsaved row: they were never saved.
        "updated_at": None if settings._state.adding else settings.updated_at,
    }


@operation(
    "printing.settings.get",
    kind="query",
    permission="printing.view_settings",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Get the printing settings: whether the receipt prints and the drawer opens by itself at checkout, "
        "the receipt copies and the printer chosen for each function (receipts, kitchen, bar, labels). The receipt's "
        "header and footer are not here: they are Sales' settings."
    },
)
def get_settings(ctx: OperationContext, data: EmptyIn) -> dict:
    return settings_row(current_settings())


# ── Printers ──────────────────────────────────────────────────────────────────────────────────────


def _as_uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(text))
    except ValueError:
        return None


def find_printer(printer_id: uuid.UUID | None, name: str | None, *, lock: bool = False) -> Printer:
    """The printer named by its id, or by its name (whatever its case; a name may also carry an id)."""
    printers = Printer.objects.select_for_update() if lock else Printer.objects.all()
    found = None
    if printer_id is not None:
        found = printers.filter(pk=printer_id).first()
    elif name is not None:
        as_id = _as_uuid(name)
        if as_id is not None:
            found = printers.filter(pk=as_id).first()
        if found is None:
            found = printers.annotate(lowered=Lower("name")).filter(lowered=name.strip().lower()).first()
    if found is None:
        raise NotFound(str(NO_PRINTER), code="printing.printer_not_found")
    return found


def _with_queue(printers):
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
    """A printer as the screens and the assistant read it, with its queue (annotated or read now)."""
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
    key = _PRINTER_SORT[params.sort]
    ordered = (key.desc() if params.dir == "desc" else key.asc()) if not isinstance(key, str) else key
    if isinstance(key, str) and params.dir == "desc":
        ordered = f"-{key}"
    tie = "-id" if params.dir == "desc" else "id"
    page = _with_queue(printers).order_by(ordered, tie)[params.offset : params.offset + params.limit]
    now = timezone.now()
    return {"rows": [printer_row(p, now) for p in page], "total": total, "limit": params.limit, "offset": params.offset}


@operation(
    "printing.printer.get",
    kind="query",
    permission="printing.view_settings",
    input=PrinterRefIn,
    output=PrinterOut,
    expose_api=True,
    ai={"description": "Get one printer by its id or its name («the kitchen one» → Kitchen), with its state."},
)
def get_printer(ctx: OperationContext, params: PrinterRefIn) -> dict:
    return printer_row(find_printer(params.printer_id, params.printer))


@operation(
    "printing.printer.status",
    kind="query",
    permission="printing.view_settings",
    input=PrinterRefIn,
    output=PrinterStatusOut,
    expose_api=True,
    ai={
        "description": "How a printer is doing, by its name or id: its state, how many of its jobs wait and since when, "
        "how many a device has and how many failed, when it last printed, its last error and whether it is the printer "
        "of its function. «Is the kitchen printer working?»"
    },
)
def printer_status(ctx: OperationContext, params: PrinterRefIn) -> dict:
    printer = find_printer(params.printer_id, params.printer)
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


# ── Jobs ──────────────────────────────────────────────────────────────────────────────────────────


def is_stale(job: PrintJob, now: dt.datetime) -> bool:
    """Sent to a device and unanswered past its lease."""
    return job.status == PrintJob.Status.SENT and job.leased_until is not None and job.leased_until < now


def retryable(job: PrintJob, now: dt.datetime) -> bool:
    """Queued (it goes to the printer of its function now), failed, or sent with no answer."""
    return job.status in (PrintJob.Status.PENDING, PrintJob.Status.FAILED) or is_stale(job, now)


def cancellable(job: PrintJob, now: dt.datetime) -> bool:
    return job.status in (PrintJob.Status.PENDING, PrintJob.Status.FAILED) or is_stale(job, now)


def job_row(job: PrintJob, now: dt.datetime | None = None) -> dict:
    now = now or timezone.now()
    return {
        "id": job.id,
        "job_key": job.job_key,
        "kind": job.kind,
        "document_type": job.document_type,
        "reference": job.reference,
        "format": job.format,
        "usage": job.usage,
        "printer_id": job.printer_id,
        "printer_name": job.printer.name if job.printer_id else None,
        "copies": job.copies,
        "open_drawer": job.open_drawer,
        "status": job.status,
        "attempts": job.attempts,
        "leased_until": job.leased_until,
        "stale": is_stale(job, now),
        "retryable": retryable(job, now),
        "cancellable": cancellable(job, now),
        "device": job.device,
        "last_error": job.last_error,
        "source_app": job.source_app,
        "created_at": job.created_at,
        "created_by": job.created_by,
        "sent_at": job.sent_at,
        "printed_at": job.printed_at,
        "failed_at": job.failed_at,
        "retried_at": job.retried_at,
        "retried_by": job.retried_by,
        "cancelled_at": job.cancelled_at,
        "cancelled_by": job.cancelled_by,
        "cancel_reason": job.cancel_reason,
    }


def find_job(job_id: uuid.UUID | None, reference: str | None, *, lock: bool = False) -> PrintJob:
    """The job named by its id, or the newest one of a document's number."""
    jobs = PrintJob.objects.select_for_update() if lock else PrintJob.objects.select_related("printer")
    if job_id is not None:
        found = jobs.filter(pk=job_id).first()
    else:
        found = jobs.filter(reference__iexact=reference).order_by("-created_at", "-id").first()
    if found is None:
        raise NotFound(str(NO_JOB), code="printing.job_not_found")
    return found


@operation(
    "printing.job.list",
    kind="query",
    permission="printing.view_settings",
    input=JobListIn,
    output=Page[JobOut],
    expose_api=True,
    ai={
        "description": "List the print queue, newest first: each job's document and number, function, printer, state "
        "(pending, sent, done, failed, cancelled), attempts, last error and who retried or cancelled it. Filter by "
        "state, function or printer; search by the document's number («T-000123»)."
    },
)
def list_jobs(ctx: OperationContext, params: JobListIn) -> dict:
    jobs = PrintJob.objects.select_related("printer")
    if params.search:
        jobs = jobs.filter(reference__icontains=params.search)
    if params.status:
        jobs = jobs.filter(status=params.status)
    if params.usage:
        jobs = jobs.filter(usage=params.usage)
    if params.printer_id:
        jobs = jobs.filter(printer_id=params.printer_id)
    total = jobs.count()
    sign = "-" if params.dir == "desc" else ""
    page = jobs.order_by(f"{sign}{params.sort}", f"{sign}id")[params.offset : params.offset + params.limit]
    now = timezone.now()
    return {"rows": [job_row(job, now) for job in page], "total": total, "limit": params.limit, "offset": params.offset}


@operation(
    "printing.job.summary",
    kind="query",
    permission="printing.view_settings",
    input=EmptyIn,
    output=JobSummaryOut,
    expose_api=True,
    ai={
        "description": "How printing is going, by function (receipts, kitchen, bar, labels): its active printers, the "
        "one chosen in the settings, how many jobs wait and since when, how many a device has and how many failed."
    },
)
def job_summary(ctx: OperationContext, data: EmptyIn) -> dict:
    counts = {
        row["usage"]: row
        for row in PrintJob.objects.values("usage").annotate(
            pending=Count("id", filter=PENDING),
            oldest=Min("created_at", filter=PENDING),
            sent=Count("id", filter=Q(status=PrintJob.Status.SENT)),
            failed=Count("id", filter=Q(status=PrintJob.Status.FAILED)),
        )
    }
    printers = {
        row["usage"]: row["n"]
        for row in Printer.objects.filter(is_active=True).values("usage").annotate(n=Count("id"))
    }
    settings = current_settings()
    usages = []
    for usage in USAGES:
        row = counts.get(usage, {})
        chosen = getattr(settings, DEFAULT_FIELDS[usage]) if getattr(settings, f"{DEFAULT_FIELDS[usage]}_id") else None
        usages.append(
            {
                "usage": usage,
                "printers": printers.get(usage, 0),
                "default_printer": chosen.name if chosen else None,
                "pending": row.get("pending", 0),
                "oldest_pending_at": row.get("oldest"),
                "sent": row.get("sent", 0),
                "failed": row.get("failed", 0),
            }
        )
    return {
        "usages": usages,
        "pending": sum(row["pending"] for row in usages),
        "sent": sum(row["sent"] for row in usages),
        "failed": sum(row["failed"] for row in usages),
    }
