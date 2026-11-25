"""The device that prints, through base's /ws/print (PRINTING-F18): it takes the oldest job of the printers it
reaches, confirms it or reports its failure; a lease that runs out puts the job back in the queue."""


from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, PermissionDenied
from live.operations import atomic, operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import PrintDevice, Printer, PrintJob
from apps.printing.queries.device_reads import active_devices
from apps.printing.queries.jobs import LEASE, MAX_ATTEMPTS, actor, find_job, job_row
from apps.printing.schemas import JobAckOut, JobClaimIn, JobClaimOut, JobCompleteIn, JobFailIn
from apps.printing.services.writes import MANAGE_SETTINGS, _queued

NOT_YOURS = _("That job is not this device's: another device or another hand-out has it now.")
NO_ANSWER = _("No answer from the device.")
DEVICE_NOT_SET_UP = _(
    "This device is not set up to print here: someone who manages the printers sets it up in Printing → Devices."
)
PRINTER_NOT_ON_DEVICE = _(
    "This device does not print for %(printers)s: someone who manages the printers adds it to the device."
)
DEVICE_NUMBER = _("Device %(number)s")

#: Documents whose copies after the first are duplicates, never a second original (RD 1619/2012 art. 14.4).
FISCAL_PAPERS = ("receipt", "invoice")


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


def _claiming_device(ctx: OperationContext, device_id: str, printers: list[Printer], now) -> PrintDevice:
    """The device set up with ``device_id``, which must print for every printer it names. Whoever sets up the
    printers pairs it by asking: a device new here is set up, a printer it does not reach yet is added; with no
    active printer named there is nothing to pair it with. Anybody else is refused (403), and so is a retired
    device: retiring it was a decision, not something a claim undoes."""
    key = PrintDevice.key_of(device_id)
    device = PrintDevice.objects.select_for_update().filter(key=key).first()
    pairs = ctx.has(MANAGE_SETTINGS)
    if (device is None and not (pairs and printers)) or (device is not None and device.retired_at is not None):
        raise PermissionDenied(str(DEVICE_NOT_SET_UP), code="printing.device_not_registered")
    new = device is None
    if new:
        device, new = _paired_device(ctx, key)
    reached = set(device.printers.values_list("id", flat=True))
    missing = [printer for printer in printers if printer.id not in reached]
    if missing:
        if not pairs:
            names = ", ".join(f"«{printer.name}»" for printer in missing)
            raise PermissionDenied(str(PRINTER_NOT_ON_DEVICE) % {"printers": names}, code="printing.printer_not_on_device")
        device.printers.add(*missing)
        if not new:
            record_event(ctx, events.DEVICE_UPDATED, {"id": str(device.id)})
    device.last_seen_at = now
    device.save(update_fields=["last_seen_at"])
    return device


def _paired_device(ctx: OperationContext, key: str) -> tuple[PrintDevice, bool]:
    """A device paired by printing from it, named «Device N» until somebody renames it; whether it is new (two
    of its first claims at once pair it once: the second finds the first one's)."""
    with translation.override(ctx.language):
        name = str(DEVICE_NUMBER) % {"number": PrintDevice.objects.count() + 1}
    try:
        with atomic():
            device = PrintDevice.objects.create(key=key, name=name, registered_by=actor(ctx))
    except IntegrityError:
        return PrintDevice.objects.select_for_update().get(key=key), False
    record_event(ctx, events.DEVICE_REGISTERED, {"id": str(device.id)})
    return device, True


def _holds(job: PrintJob, device_id: str) -> bool:
    """Whether the device set up with ``device_id`` (and not retired) is the one that took ``job``."""
    if job.print_device_id is None:
        return False
    return active_devices().filter(pk=job.print_device_id, key=PrintDevice.key_of(device_id)).exists()


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.print",
    input=JobClaimIn,
    output=JobClaimOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "take the next print job for this device",
                "this device is ready to print the oldest job",
            ),
            "es": (
                "este equipo recoge el siguiente trabajo de impresión",
                "que este puesto coja el trabajo de impresión más antiguo",
            ),
        },
        "description": "For the device that prints (base's /ws/print): take the oldest queued job of the printers this "
        "device reaches, or one with no printer of their function. It is marked sent for 90 s; without an answer it "
        "goes back to the queue. Not for a person.",
        "risk": "high",
    },
)
def claim_job(ctx: OperationContext, data: JobClaimIn) -> dict:
    now = timezone.now()
    printers = {p.id: p for p in Printer.objects.filter(pk__in=data.printers, is_active=True)}
    # First who asks, before anything moves: a refusal leaves the queue as it was.
    device = _claiming_device(ctx, data.device, list(printers.values()), now)
    _reclaim_expired(ctx, now)
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
    job.print_device, job.device = device, device.name
    job.save(update_fields=["status", "attempts", "leased_until", "sent_at", "print_device", "device", "printer"])
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
            "leased_until": job.leased_until,
        }
    }


@operation(
    "printing.job.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.print",
    input=JobCompleteIn,
    output=JobAckOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "this device confirms the job came out on paper",
                "the print job is done on this device",
            ),
            "es": (
                "este dispositivo dice que el trabajo de impresión ya salió en papel",
                "el trabajo de impresión ya está hecho en este equipo",
            ),
        },
        "description": "For the device that prints: confirm a job came out on paper, saying which device and which "
        "hand-out. Confirming twice is one confirmation; a late confirmation of the device that took it is taken even "
        "if the job went back to the queue (the paper did come out). Another device: refused. Not for a person.",
        "risk": "high",
    },
)
def complete_job(ctx: OperationContext, data: JobCompleteIn) -> dict:
    job = find_job(data.job_id, None, lock=True)
    if not _holds(job, data.device) or data.attempt > job.attempts:
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.print",
    input=JobFailIn,
    output=JobAckOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "this device reports the print job did not come out",
                "the printer ran out of paper on this job",
            ),
            "es": (
                "este equipo avisa de que el trabajo no salió impreso",
                "la impresora se quedó sin papel en este trabajo",
            ),
        },
        "description": "For the device that prints: say a job did not come out, with the device's error, the device "
        "and the hand-out it answers. It goes back to the queue, and fails after its fifth hand-out. Another device or "
        "another hand-out: refused. Not for a person.",
        "risk": "high",
    },
)
def fail_job(ctx: OperationContext, data: JobFailIn) -> dict:
    job = find_job(data.job_id, None, lock=True)
    if not _holds(job, data.device) or job.attempts != data.attempt:
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
