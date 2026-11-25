"""The print queue: who acts in it, one job as the screens read it, the list and one job.

A job sent to a device and unanswered past its 90 s lease is «stale»: it can be retried or cancelled, and the next claim
puts it back in the queue (services/claims.py).
"""

import datetime as dt
import uuid

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.printing.models import PrintJob
from apps.printing.schemas.fields import Page
from apps.printing.schemas.jobs import JobDetailOut, JobListIn, JobOut, JobRefIn
from base.ordering import list_order
from base.queries.people import actor_name

#: Hand-outs a job gets before it fails (the old hub's ``MAX_ATTEMPTS``).
MAX_ATTEMPTS = 5
#: How long a device has to answer for a job it took (the old hub's ``DEFAULT_LEASE_SECONDS``).
LEASE = dt.timedelta(seconds=90)

NO_JOB = _("There is no print job with that id or number.")


def actor(ctx: OperationContext) -> str:
    """Who acts, as a colleague reads it in the print queue: never their e-mail address."""
    return actor_name(ctx.actor)[:128]


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
        "asks": {
            "en": (
                "what is in the print queue?",
                "which print jobs failed today?",
                "show me the pending prints",
            ),
            "es": (
                "¿qué hay en la cola de impresión?",
                "¿qué impresiones han fallado hoy?",
                "enséñame las impresiones pendientes",
            ),
        },
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
    page = jobs.order_by(*list_order(params.sort, descending=params.dir == "desc"))[
        params.offset : params.offset + params.limit
    ]
    now = timezone.now()
    return {"rows": [job_row(job, now) for job in page], "total": total, "limit": params.limit, "offset": params.offset}


def job_label(job: PrintJob, language: str) -> str:
    """How the queue titles ``job`` in ``language``: its document and its number («Receipt T-000123»), or what it is
    when it has none («Open the drawer»), as the Jobs screen's ``jobTitle``."""
    with translation.override(language):
        what = str(job.get_document_type_display() if job.kind == PrintJob.Kind.DOCUMENT else job.get_kind_display())
    return f"{what} {job.reference}" if job.reference else what


@operation(
    "printing.job.get",
    kind="query",
    permission="printing.view_settings",
    input=JobRefIn,
    output=JobDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what happened to the print job of ticket T-000123?",
                "did ticket T-000123 print?",
            ),
            "es": (
                "¿qué pasó con la impresión del ticket T-000123?",
                "¿se imprimió el ticket T-000123?",
                "dime el estado de la impresión de la factura F-000045",
            ),
        },
        "description": "Get one print job by its id or by its document's number («T-000123»: its newest job), titled as "
        "the queue titles it, with its state, printer, attempts, last error and who retried or cancelled it."
    },
)
def get_job(ctx: OperationContext, params: JobRefIn) -> dict:
    job = find_job(params.job_id, params.reference)
    return {**job_row(job), "label": job_label(job, ctx.language)}
