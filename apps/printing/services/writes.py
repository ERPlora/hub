"""What the printing writes share: the permission of whoever sets up the printers and the devices, and the nudge every
write that puts a job in the queue records."""


from live.context import OperationContext
from live.outbox import record_event

from apps.printing import events
from apps.printing.models import PrintJob

#: Who sets up the printers sets up the devices that print for them, and pairs one by printing from it.
MANAGE_SETTINGS = "printing.manage_settings"


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
