"""The billing records (``verifactu.record.*``): one sealed for an invoice, corrected or cancelled, sent now,
and reconciled with what the AEAT already holds."""


from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import aeat, events
from apps.verifactu.models import Record
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.records import can_cancel, can_correct, find_invoice, find_record, summary
from apps.verifactu.queries.route import effective_environment
from apps.verifactu.schemas import (
    RecordCancelIn,
    RecordCorrectIn,
    RecordCreateIn,
    RecordCreateOut,
    RecordReconcileIn,
    RecordTransmitIn,
    ReconcileOut,
    TransmitOut,
)

from .aeat_query import _query_aeat
from .sealing import _seal, _seal_alta
from .sending import _send
from .writes import TRANSMIT, _config, _event

CANNOT_CORRECT = _(
    "This record cannot be corrected: only the last record of a registration the AEAT rejected or accepted with errors can."
)
CANNOT_CANCEL = _(
    "This record cannot be cancelled: only a registration that reached (or will reach) the AEAT and has no cancellation can."
)
NOT_IN_QUEUE = _(
    "This record is not in the queue: it is already in the AEAT, or the AEAT rejected it."
)

CORRECT = "verifactu.correct_record"


@operation(
    "verifactu.record.create",
    kind="command",
    permission="verifactu.add_record",
    input=RecordCreateIn,
    output=RecordCreateOut,
    ai={
        "description": "Seal the VeriFactu registration record of an issued invoice (by its id or its number): it is "
        "chained with its fingerprint, gets its QR and waits in the queue to go to the AEAT. It also happens by itself "
        "when an invoice is issued; asking again answers the same record. In production it is refused while the "
        "business has no way to the AEAT (the route's own code), so the sale or invoice is not issued.",
        "risk": "normal",
        "asks": {
            "en": (
                "chain the registration of the last invoice we issued",
                "make the VeriFactu QR an issued invoice is missing",
            ),
            "es": (
                "encadena el registro de la última factura que emitimos, con su sitio en la cola",
                "genera el QR de VeriFactu que le falta a una factura emitida",
            ),
        },
    },
)
def create_record(ctx: OperationContext, data: RecordCreateIn) -> RecordCreateOut:
    refuse_outside_spain(ctx)
    invoice = find_invoice(data.invoice_id, data.number)
    config = _config(lock=False)
    # A person (or an API key) issuing now is refused without a way to the AEAT; the platform's reaction to a
    # document already issued is not: its record is sealed and waits, as the old Hub let the relay deliver a chain
    # already open, rather than the document going undeclared.
    record, already = _seal_alta(
        ctx,
        config,
        invoice,
        environment=effective_environment(ctx, config),
        refuse_without_a_way=ctx.actor != "system",
    )
    return RecordCreateOut(record=summary(record), already=already)


@operation(
    "verifactu.record.correct",
    kind="command",
    permission=CORRECT,
    input=RecordCorrectIn,
    output=RecordCreateOut,
    ai={
        "description": "Correct (subsanar) a registration the AEAT rejected or accepted with errors (by its id or its "
        "invoice's number): a new record of the same invoice, read again, marked as a correction, enters the queue; "
        "the old one is kept as it is. If the invoice itself is wrong, rectify it in Invoicing instead.",
        "risk": "high",
        "asks": {
            "en": (
                "correct the registration the AEAT rejected",
                "fix the registration accepted with errors",
            ),
            "es": (
                "subsana el registro que rechazó la AEAT",
                "corrige el registro aceptado con errores",
            ),
        },
    },
)
def correct_record(ctx: OperationContext, data: RecordCorrectIn) -> RecordCreateOut:
    refuse_outside_spain(ctx)
    target = find_record(data.record_id, data.invoice_number, lock=True)
    if not can_correct(target):
        raise Conflict(str(CANNOT_CORRECT), code="verifactu.cannot_correct")
    config = _config(lock=False)
    invoice = find_invoice(target.invoice_id, None)
    record, _already = _seal_alta(
        ctx, config, invoice, environment=target.environment, corrects=target
    )
    return RecordCreateOut(record=summary(record), already=False)


@operation(
    "verifactu.record.cancel",
    kind="command",
    permission=CORRECT,
    input=RecordCancelIn,
    output=RecordCreateOut,
    ai={
        "description": "Cancel the registration of an invoice issued BY ERROR (by the record's id or the invoice's "
        "number), with the reason: a chained cancellation record (RegistroAnulacion) is sealed and sent. A refund or "
        "a correction is never this: it is a rectifying invoice in Invoicing. The invoice stays in Invoicing.",
        "risk": "high",
        "asks": {
            "en": (
                "cancel the VeriFactu registration of an invoice issued by mistake",
                "cancel the registration of an invoice we should not have issued",
            ),
            "es": (
                "anula el registro de una factura que se emitió por error",
                "anula en Hacienda la factura que emitimos sin querer",
                "esa factura fue una equivocación, anula su registro",
            ),
        },
    },
)
def cancel_record(ctx: OperationContext, data: RecordCancelIn) -> RecordCreateOut:
    refuse_outside_spain(ctx)
    target = find_record(data.record_id, data.invoice_number, lock=True)
    if target.record_type != Record.Type.ALTA:
        target = target.cancels or target
    if not can_cancel(target):
        raise Conflict(str(CANNOT_CANCEL), code="verifactu.cannot_cancel")
    config = _config(lock=False)
    record = Record(
        record_type=Record.Type.ANULACION,
        environment=target.environment,
        invoice=target.invoice,
        cancels=target,
        issuer_nif=target.issuer_nif,
        issuer_name=target.issuer_name,
        invoice_number=target.invoice_number,
        issue_date=target.issue_date,
        description=data.reason,
        # «Anulación por rechazo» (the AEAT's web service description, section 9.2.2): an earlier anulación of the
        # same registration was rejected.
        previous_rejection="S"
        if Record.objects.filter(cancels=target, status=Record.Status.REJECTED).exists()
        else "",
    )
    return RecordCreateOut(record=summary(_seal(ctx, config, record)), already=False)


@operation(
    "verifactu.record.transmit",
    kind="command",
    permission=TRANSMIT,
    input=RecordTransmitIn,
    output=TransmitOut,
    ai={
        "description": "Send a VeriFactu record to the AEAT now (by its id or its invoice's number), with the earlier "
        "pending ones of its chain, through ERPlora's gateway, respecting the AEAT's waiting time. It is never taken as "
        "accepted without the AEAT's answer; without the gateway it stays in the queue.",
        "risk": "high",
        "asks": {
            "en": (
                "send VeriFactu entry 12 to the AEAT now",
                "file that queued registration with the AEAT",
            ),
            "es": (
                "manda a la AEAT el registro 12 con sus anteriores",
                "remite a Hacienda ese registro que espera",
            ),
        },
    },
)
def transmit_record(ctx: OperationContext, data: RecordTransmitIn) -> TransmitOut:
    refuse_outside_spain(ctx)
    record = find_record(data.record_id, data.invoice_number)
    if record.status not in Record.UNSENT:
        raise Conflict(str(NOT_IN_QUEUE), code="verifactu.not_in_queue")
    return _send(ctx, only=record).out()


@operation(
    "verifactu.record.reconcile",
    kind="command",
    permission=TRANSMIT,
    input=RecordReconcileIn,
    output=ReconcileOut,
    ai={
        "description": "Ask the AEAT, through ERPlora's gateway, whether it already holds a record of the VeriFactu "
        "queue (by its id or its invoice's number; typically one sent without an answer). Only when it holds that very "
        "record (same fingerprint) does it leave the queue as registered; otherwise nothing changes and it is sent "
        "again. Nothing the AEAT does not hold ever leaves the queue.",
        "risk": "high",
        "asks": {
            "en": (
                "reconcile VeriFactu entry 12 with the AEAT",
                "ask the AEAT whether it holds that unanswered filing",
            ),
            "es": (
                "concilia con la AEAT el registro 12 que no tuvo respuesta",
                "mira en Hacienda si consta el registro que nunca tuvo respuesta",
            ),
        },
    },
)
def reconcile_record(ctx: OperationContext, data: RecordReconcileIn) -> ReconcileOut:
    refuse_outside_spain(ctx)
    found = find_record(data.record_id, data.invoice_number)
    if found.status not in Record.UNSENT:
        raise Conflict(str(NOT_IN_QUEUE), code="verifactu.not_in_queue")
    config = _config(lock=False)
    # The AEAT files a record under the period of its invoice's issue date; it is asked before the row is locked,
    # so a pass of the queue never waits on the gateway.
    held = aeat.held_as(
        _query_aeat(
            ctx,
            config,
            found.issuer_nif,
            found.environment,
            found.issue_date.year,
            found.issue_date.month,
        ),
        found.issuer_nif,
        found.invoice_number,
        found.fingerprint,
    )
    record = find_record(found.id, None, lock=True)
    if held is None or record.status not in Record.UNSENT:
        return ReconcileOut(held=False, record=summary(record))
    record.status = held
    record.wait_reason = record.wait_detail = ""
    record.save(update_fields=["status", "wait_reason", "wait_detail", "updated_at"])
    notice = {
        "record_id": str(record.id),
        "invoice_number": record.invoice_number,
        "status": held,
        "environment": record.environment,
    }
    _event(
        ctx,
        held,
        "record_reconciled",
        notice,
        severity="warning" if held == Record.Status.ACCEPTED_WITH_ERRORS else "info",
        record=record,
        environment=record.environment,
    )
    record_event(ctx, events.RECORD_RECONCILED, notice)
    return ReconcileOut(held=True, record=summary(record))
