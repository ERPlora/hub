"""How long the queue keeps a job (PRINTING-F20): the platform's hourly prune forgets the jobs that ended 30 days ago."""

import datetime as dt
import logging

from django.db.models.functions import Coalesce
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import PrintJob
from apps.printing.schemas.fields import EmptyIn
from apps.printing.schemas.jobs import PruneOut

# Named after the package, not this module, so the prune's log lines keep the logger name they are filtered by.
logger = logging.getLogger("apps.printing.services")

#: Run only by the platform (the scheduled prune): no role is given it, and it has no route.
SYSTEM = "printing.system"
#: How long the queue keeps a job after it ended — printed, cancelled or failed (PRINTING-F20).
KEEP_FINISHED = dt.timedelta(days=30)
#: The most jobs one prune deletes: an hourly run never holds the queue for long.
PRUNE_BATCH = 500


# Not an assistant tool: a scheduled task of the platform.
@operation("printing.job.prune", kind="command", permission=SYSTEM, input=EmptyIn, output=PruneOut, ai=INTERNAL)
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
