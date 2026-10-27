"""Read operations of the printing app (``READ ONLY``), and the helpers its services share.

A printer's state is read, never stored: inactive; failing when its last failure is newer than its last
paper; waiting when a job of its own has been queued for over a minute; ready otherwise. A job sent to a
device and unanswered past its 90 s lease is «stale»: it can be retried or cancelled, and the next claim
puts it back in the queue (services.py).
"""

import datetime as dt
import uuid

from django.conf import settings as django_settings
from django.db.models import Case, Count, IntegerField, Min, Prefetch, Q, QuerySet, Value, When
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, system_context
from live.errors import NotFound
from live.operations import get as operation_named
from live.operations import operation

from apps.printing.models import PrintDevice, Printer, PrintJob, Settings, Usage
from base.business import currency_of
from base.operations import is_platform_hub
from apps.printing.schemas import (
    CoverageIn,
    CoverageOut,
    DeviceGetIn,
    DeviceGetOut,
    DeviceListIn,
    DeviceOut,
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
NO_DEVICE = _("There is no device set up to print with that id.")

PENDING = Q(status=PrintJob.Status.PENDING)
#: Receipt paper before the computer's printer, the order a job of a function finds its printer in.
_SYSTEM_LAST = Case(When(kind=Printer.Kind.SYSTEM, then=Value(1)), default=Value(0), output_field=IntegerField())


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


# ── The business's currency ─────────────────────────────────────────────────────────────────────

#: What tells the business's currency: its country's, from this hub's registry, never asking erplora.com (APP-BASE-6).
BUSINESS = "base.business.get"


def business_currency(ctx: OperationContext) -> str:
    """The currency of ``ctx``'s business (ISO 4217), the one a receipt whose caller does not say is in, as
    ``base.business.get`` reads it. Read as the platform: an API key holds only the permission of what it prints, and
    every person of the hub may see it anyway. ERPlora's own hub has no business on erplora.com (phase 1: no registry
    row, ``create_platform_hub``): its papers keep the currency of its issuer's country, as its sales and invoices do."""
    if is_platform_hub(ctx.scope):
        return currency_of(django_settings.PLATFORM_ISSUER_COUNTRY)
    business = operation_named(BUSINESS)
    return business(system_context(ctx.scope), business.input()).currency


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


def current_settings() -> Settings:
    """The business's settings, or the factory ones (unsaved) when it never saved them. The printer chosen
    for each function comes in the same read: one deleted meanwhile is either still there or already
    cleared, never one left to load that is gone."""
    return Settings.objects.select_related(*DEFAULT_FIELDS.values()).first() or Settings()


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
    return printer_row(find_printer(params.printer_id, params.printer, rows=_with_queue(Printer.objects.all())))


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
    active: dict[str, list[Printer]] = {}
    # Receipt paper first, then the computer's printer; by name within each, as a job is sent (services.py).
    for printer in Printer.objects.filter(is_active=True).order_by(_SYSTEM_LAST, Lower("name"), "id"):
        active.setdefault(printer.usage, []).append(printer)
    settings = current_settings()
    usages = []
    for usage in USAGES:
        row = counts.get(usage, {})
        chosen = getattr(settings, DEFAULT_FIELDS[usage])
        mine = active.get(usage, [])
        prints_on = chosen if chosen is not None and chosen.is_active else (mine[0] if mine else None)
        usages.append(
            {
                "usage": usage,
                "printers": len(mine),
                "default_printer": chosen.name if chosen else None,
                "prints_on": prints_on.name if prints_on else None,
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


# ── The devices that print (PRINTING-F18) ────────────────────────────────────────────────────────

#: The header the SPA names its device with (``@erplora/ui``'s ``DEVICE_ID_HEADER``), on every request and stream.
DEVICE_HEADER = "X-Device-Id"
#: The printers of a device, by name, read with it.
_BY_NAME = Prefetch("printers", queryset=Printer.objects.order_by(Lower("name"), "id"))


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


@operation(
    "printing.device.list",
    kind="query",
    permission="printing.view_settings",
    input=DeviceListIn,
    output=Page[DeviceOut],
    expose_api=True,
    ai={
        "description": "List the devices set up to print, by name: the printers each one reaches and prints for, who set "
        "it up and when it last asked for a job. Only these devices print; their own ids are never shown."
    },
)
def list_devices(ctx: OperationContext, params: DeviceListIn) -> dict:
    devices = active_devices()
    total = devices.count()
    page = devices.prefetch_related(_BY_NAME).order_by(Lower("name"), "id")[params.offset : params.offset + params.limit]
    key = this_device_key(ctx)
    return {"rows": [device_row(device, key) for device in page], "total": total, "limit": params.limit, "offset": params.offset}


@operation("printing.device.get", kind="query", permission="printing.print", input=DeviceGetIn, output=DeviceGetOut)
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
        "description": "Whether a function (receipt, kitchen, bar, label) has a device set up to print it, and how many of "
        "its jobs wait that no device set up here can print. «Is anybody printing the kitchen orders?»"
    },
)
def device_coverage(ctx: OperationContext, params: CoverageIn) -> dict:
    """The Home's «Set up your printer» (``covered`` of the receipts) and the bell's «Nothing is printing» (``count``).

    A device set up here prints the active printers it reaches: the jobs of those printers, and the jobs of a function
    no printer took yet on the paper of one of them (``printing.job.claim``). Set up is enough, as the old hub's
    registration for a station: a device off right now is not a step undone. Only waiting jobs count: one a device has
    is that device's, and one that ended waits for nobody.
    """
    reached = Printer.objects.filter(is_active=True, devices__in=active_devices())
    mine = reached.filter(usage=params.usage)
    paper = {
        PrintJob.Format.RECEIPT: mine.exclude(kind=Printer.Kind.SYSTEM).exists(),
        PrintJob.Format.A4: mine.filter(kind=Printer.Kind.SYSTEM).exists(),
    }
    takeable = Q(printer__in=reached)
    for paper_format, any_reached in paper.items():
        if any_reached:
            takeable |= Q(printer__isnull=True, format=paper_format)
    jobs = PrintJob.objects.filter(PENDING, usage=params.usage).aggregate(
        waiting=Count("id"), takeable=Count("id", filter=takeable)
    )
    return {
        "usage": params.usage,
        "covered": paper[PrintJob.Format.RECEIPT],
        "count": jobs["waiting"] - jobs["takeable"],
    }
