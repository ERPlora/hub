"""The queue (``verifactu.contingency.list``): the records not in the AEAT yet, in the order they go out."""

from django.db.models import Q
from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import Record, wait_reason_text
from apps.verifactu.schemas import ContingencyListIn, Page, QueueRowOut

from .reads import VIEW, page


def _queue_row(record: Record) -> dict:
    return {
        "id": record.id,
        "invoice_number": record.invoice_number,
        "record_type": record.record_type,
        "environment": record.environment,
        "attempts": record.attempts,
        "status": record.status,
        # As get_record: a refusal of the gateway waits for a change, never on a timer.
        "next_attempt_at": None
        if record.wait_reason == "refused"
        else record.next_attempt_at,
        "last_error": wait_reason_text(record.wait_reason, record.wait_detail)
        if record.wait_reason
        else "",
        "created_at": record.created_at,
    }


@operation(
    "verifactu.contingency.list",
    kind="query",
    permission=VIEW,
    input=ContingencyListIn,
    output=Page[QueueRowOut],
    ai={
        "description": "The queue: the VeriFactu records that are not in the AEAT yet (pending, or sent without "
        "answer), in the order they go out, with their attempts, next attempt and last error.",
        "asks": {
            "en": (
                "what is queued for the AEAT?",
                "show me the VeriFactu contingency queue",
            ),
            "es": (
                "¿qué registros esperan en la cola de Hacienda?",
                "enséñame la contingencia de VeriFactu",
            ),
        },
    },
)
def list_queue(ctx: OperationContext, data: ContingencyListIn) -> dict:
    queryset = Record.objects.filter(status__in=Record.UNSENT)
    if data.environment:
        queryset = queryset.filter(environment=data.environment)
    if data.search:
        queryset = queryset.filter(
            Q(invoice_number__icontains=data.search)
            | Q(wait_detail__icontains=data.search)
            | Q(wait_reason__icontains=data.search)
        )
    if data.sort:
        prefix = "-" if data.dir == "desc" else ""
        queryset = queryset.order_by(f"{prefix}{data.sort}", f"{prefix}id")
    else:
        queryset = queryset.order_by("environment", "issuer_nif", "sequence", "id")
    return page(queryset, data.limit, data.offset, _queue_row)
