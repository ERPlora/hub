"""A person retries a queued, failed or unanswered job, or cancels it, stamped (PRINTING-F14)."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import Printer, PrintJob
from apps.printing.queries import actor, cancellable, current_settings, find_job, job_row, retryable
from apps.printing.queries.job_printer import job_printer
from apps.printing.schemas import JobCancelIn, JobOut, JobRefIn
from apps.printing.services.writes import _queued

NOT_RETRYABLE = _(
    "Only a queued or failed job, or a sent one with no answer, goes back to the queue; this one is %(status)s."
)
NOT_CANCELLABLE = _("A job that is printing or has printed is not cancelled; this one is %(status)s.")


def _status_label(job: PrintJob) -> str:
    return str(PrintJob.Status(job.status).label).lower()


@operation(
    "printing.job.retry",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.manage_jobs",
    input=JobRefIn,
    output=JobOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "retry the failed print of ticket T-000123",
                "print that failed ticket again",
                "reprint the stuck job",
            ),
            "es": (
                "reintenta la impresión fallida del ticket T-000123",
                "vuelve a mandar a imprimir ese ticket que falló",
                "reenvía la impresión atascada a la cola",
            ),
        },
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
        job.printer = job_printer(job.usage, job.format, current_settings())
    job.status, job.attempts, job.leased_until = PrintJob.Status.PENDING, 0, None
    job.retried_at, job.retried_by = now, actor(ctx)
    job.save(update_fields=["status", "attempts", "leased_until", "retried_at", "retried_by", "printer"])
    record_event(ctx, events.JOB_RETRIED, {"id": str(job.id)})
    _queued(ctx, job)
    return job_row(job)


@operation(
    "printing.job.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="printing.manage_jobs",
    input=JobCancelIn,
    output=JobOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel the print job of ticket T-000123",
                "do not print that queued document",
                "drop the stuck print from the queue",
            ),
            "es": (
                "cancela la impresión del ticket T-000123",
                "no imprimas ese documento que está en cola",
                "saca de la cola la impresión atascada",
            ),
        },
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
