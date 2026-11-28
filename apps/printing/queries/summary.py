"""How printing is going, by function: its printers, its queue and what nobody is there to print."""

from django.db.models import Count, Min, Q
from live.context import OperationContext
from live.operations import operation

from apps.printing.models import PrintJob
from apps.printing.schemas.fields import EmptyIn
from apps.printing.schemas.jobs import JobSummaryOut

from .device_reads import this_device_key
from .job_printer import active_printers, prints_on
from .settings import DEFAULT_FIELDS, USAGES, current_settings
from .waiting import PENDING, coverage, signed_out_usages, stalled


@operation(
    "printing.job.summary",
    kind="query",
    permission="printing.view_settings",
    input=EmptyIn,
    output=JobSummaryOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how is printing going?",
                "is any print job stuck?",
                "is the print queue healthy?",
            ),
            "es": (
                "¿cómo va la cola de impresión?",
                "¿hay alguna impresión atascada?",
                "¿se están imprimiendo los pedidos de cocina?",
            ),
        },
        "description": "How printing is going, by function (receipts, kitchen, bar, labels): its active printers, the "
        "one chosen in the settings, how many jobs wait and since when, how many a device has, how many failed, how "
        "many have waited a minute with no device on to print them, and whether the device set up for it lost its "
        "session because someone entered on another device and the plan covers no more devices at a time."
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
    # The receipt goes to the printer of the till that looks, when it has one of its own (PRINTING-F22).
    active, settings, device = active_printers(), current_settings(), this_device_key(ctx)
    reach, stuck, signed_out = coverage(USAGES), stalled(USAGES), signed_out_usages(USAGES)
    usages = []
    for usage in USAGES:
        row = counts.get(usage, {})
        chosen = getattr(settings, DEFAULT_FIELDS[usage])
        mine = active.get(usage, [])
        printing_on = prints_on(usage, chosen, mine, device)
        usages.append(
            {
                "usage": usage,
                "printers": len(mine),
                "default_printer": chosen.name if chosen else None,
                "prints_on": printing_on.name if printing_on else None,
                "pending": row.get("pending", 0),
                "oldest_pending_at": row.get("oldest"),
                "sent": row.get("sent", 0),
                "failed": row.get("failed", 0),
                "unattended": reach[usage][1],
                "stalled": stuck[usage],
                "signed_out": usage in signed_out,
            }
        )
    return {
        "usages": usages,
        "pending": sum(row["pending"] for row in usages),
        "sent": sum(row["sent"] for row in usages),
        "failed": sum(row["failed"] for row in usages),
    }
