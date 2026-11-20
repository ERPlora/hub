"""The queue (``verifactu.contingency.*``): its pass now, as the scheduled task runs it every minute, and a
record put out with the next one."""


from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import events
from apps.verifactu.models import Event, Record
from apps.verifactu.queries.records import find_record, summary
from apps.verifactu.schemas.contingency import ContingencyRetryIn, TransmitOut
from apps.verifactu.schemas.fields import NoInput
from apps.verifactu.schemas.records import RecordSummaryOut

from .records import NOT_IN_QUEUE
from .sending import _back_in_the_queue, _send, _unsent
from .writes import TRANSMIT, _event


@operation(
    "verifactu.contingency.process",
    kind="command",
    permission=TRANSMIT,
    input=NoInput,
    output=TransmitOut,
    ai={
        "description": "Process the VeriFactu queue now: every chain whose turn has come goes to the AEAT in order, "
        "declared as late when it failed before. It is what the scheduled task does every minute.",
        "risk": "high",
        "asks": {
            "en": (
                "process the VeriFactu queue",
                "send everything due in the queue to the AEAT",
            ),
            "es": (
                "procesa la cola de envíos de VeriFactu",
                "despacha a Hacienda todo lo que toque de la contingencia",
            ),
        },
    },
)
def process_queue(ctx: OperationContext, data: NoInput) -> TransmitOut:
    tally = _send(ctx)
    by_a_person = ctx.actor != "system"
    if tally.sent or tally.changed or by_a_person:
        counts = {
            "sent": tally.sent,
            "accepted": tally.accepted + tally.accepted_with_errors,
            "rejected": tally.rejected,
            "waiting": tally.waiting,
        }
        # The scheduled pass every minute leaves a line only when it sent something.
        if tally.sent or by_a_person:
            _event(ctx, Event.Kind.QUEUE_PROCESSED, "queue_processed", counts)
        record_event(ctx, events.CONTINGENCY_PROCESSED, counts)
    return tally.out()


@operation(
    "verifactu.contingency.retry",
    kind="command",
    permission=TRANSMIT,
    input=ContingencyRetryIn,
    output=RecordSummaryOut,
    ai={
        "description": "Put a record of the VeriFactu queue (by its id or its invoice's number) out with the next pass, "
        "with the earlier ones of its chain; its attempts are kept.",
        "risk": "high",
        "asks": {
            "en": (
                "retry VeriFactu entry 12 on the next round",
                "push that stuck registration out of the queue sooner",
            ),
            "es": (
                "reintenta el registro 12 en la próxima pasada",
                "adelanta el envío del registro que espera en la cola",
            ),
        },
    },
)
def retry_record(ctx: OperationContext, data: ContingencyRetryIn) -> RecordSummaryOut:
    record = find_record(data.record_id, data.invoice_number, lock=True)
    if record.status not in Record.UNSENT:
        raise Conflict(str(NOT_IN_QUEUE), code="verifactu.not_in_queue")
    now = timezone.now()
    earlier = _unsent(record.issuer_nif, record.environment).filter(
        sequence__lte=record.sequence
    )
    _back_in_the_queue(earlier)
    earlier.update(next_attempt_at=now)
    _event(
        ctx,
        Event.Kind.QUEUE_RETRIED,
        "queue_retried",
        {"invoice_number": record.invoice_number},
        record=record,
        environment=record.environment,
    )
    record_event(ctx, events.CONTINGENCY_RETRIED, {"record_id": str(record.id)})
    record.refresh_from_db()
    return summary(record)
