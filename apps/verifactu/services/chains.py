"""The chains of an issuer (``verifactu.chain.*``): checked fingerprint by fingerprint, and continued from the
last record of another application or from the last one the AEAT holds."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import aeat, chain, events
from apps.verifactu.models import Chain, Event, Record
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.route import config_row, issuer_identity
from apps.verifactu.schemas import ChainValidateIn, ChainValidationOut, RecoverFromAeatIn, RecoverManualIn, RecoveryOut

from .aeat_query import _query_aeat
from .sending import _unsent
from .writes import CONFIGURE, _event, _lock_chain

NO_RECORDS = _("There are no records of that issuer in this environment.")
PENDING_IN_CHAIN = _("The pending records of this chain have to go out first.")
NOTHING_TO_RECOVER = _(
    "The AEAT has no records of that issuer this month: there is nothing to recover."
)


def _fingerprint_of(record: Record) -> str:
    if record.record_type == Record.Type.ANULACION:
        return chain.anulacion_hash(
            issuer_nif=record.issuer_nif,
            number=record.invoice_number,
            issue_date=record.issue_date,
            previous_hash=record.previous_fingerprint,
            generated_at=record.generated_at,
        )
    return chain.alta_hash(
        issuer_nif=record.issuer_nif,
        number=record.invoice_number,
        issue_date=record.issue_date,
        invoice_type=record.invoice_type,
        tax_amount=record.tax_amount,
        total_amount=record.total_amount,
        previous_hash=record.previous_fingerprint,
        generated_at=record.generated_at,
    )


@operation(
    "verifactu.chain.validate",
    kind="command",
    permission="verifactu.view_record",
    input=ChainValidateIn,
    output=ChainValidationOut,
    ai={
        "description": "Verify the VeriFactu chain of an issuer (Invoicing's by default) in the current environment: "
        "every record's SHA-256 fingerprint is recomputed and must carry the previous one's. It repairs nothing and "
        "does not re-audit amounts.",
        "risk": "normal",
        "asks": {
            "en": (
                "check that the fingerprint chain is not broken",
                "verify every fingerprint of the VeriFactu chain",
            ),
            "es": (
                "comprueba que cada huella enlaza con la anterior y la cadena no está rota",
                "valida la cadena recalculando todas las huellas",
            ),
        },
    },
)
def validate_chain(ctx: OperationContext, data: ChainValidateIn) -> ChainValidationOut:
    nif = data.issuer_nif or issuer_identity()[0]
    environment = config_row().environment
    records = list(
        Record.objects.filter(issuer_nif=nif, environment=environment).order_by(
            "sequence"
        )
    )
    if not records:
        raise Conflict(str(NO_RECORDS), code="verifactu.no_records")
    first_invalid = None
    previous = None
    for record in records:
        linked = (
            record.previous_fingerprint == previous.fingerprint
            and record.previous_record_id == previous.id
            if record.previous_record_id is not None and previous is not None
            else record.previous_record_id is None
        )
        if not linked or _fingerprint_of(record) != record.fingerprint:
            first_invalid = record.sequence
            break
        previous = record
    valid = first_invalid is None
    head = _lock_chain(nif, environment)
    head.validated_at = timezone.now()
    head.validation_valid = valid
    head.validation_total = len(records)
    head.validation_first_invalid = first_invalid
    head.save()
    params = {
        "issuer_nif": nif,
        "total": len(records),
        "first_invalid_sequence": first_invalid,
    }
    if valid:
        _event(
            ctx, Event.Kind.CHAIN_VALID, "chain_valid", params, environment=environment
        )
    else:
        _event(
            ctx,
            Event.Kind.CHAIN_BROKEN,
            "chain_broken",
            params,
            severity="critical",
            environment=environment,
        )
    record_event(
        ctx,
        events.CHAIN_VALIDATED,
        {**params, "environment": environment, "valid": valid},
    )
    return ChainValidationOut(
        issuer_nif=nif,
        environment=environment,
        valid=valid,
        total=len(records),
        first_invalid_sequence=first_invalid,
    )


def _anchor(  # noqa: PLR0913
    ctx,
    nif: str,
    environment: str,
    *,
    number: str,
    issue_date,
    fingerprint: str,
    issuer_nif: str,
    source: str,
) -> Chain:
    if _unsent(nif, environment).exists():
        raise Conflict(str(PENDING_IN_CHAIN), code="verifactu.pending_in_chain")
    head = _lock_chain(nif, environment)
    head.last_record = None
    head.last_issuer_nif = issuer_nif
    head.last_number = number
    head.last_issue_date = issue_date
    head.last_fingerprint = fingerprint
    head.anchored_at = timezone.now()
    head.anchor_source = source
    head.save()
    return head


@operation(
    "verifactu.chain.recover_manual",
    kind="command",
    permission=CONFIGURE,
    input=RecoverManualIn,
    output=RecoveryOut,
    ai={
        "description": "Continue the VeriFactu chain of another application (a migration): the next record chains to "
        "the given last fingerprint (64 hex), invoice number and issue date. Only during a migration, and only with no "
        "pending records.",
        "risk": "high",
        "asks": {
            "en": (
                "carry on the chain from our previous software's last fingerprint",
                "we migrated: chain on from the old program's last invoice",
            ),
            "es": (
                "sigue la cadena desde la última huella del programa de antes",
                "tras la migración, encadena desde la última factura del software anterior",
            ),
        },
    },
)
def recover_manual(ctx: OperationContext, data: RecoverManualIn) -> RecoveryOut:
    nif = data.issuer_nif or issuer_identity()[0]
    environment = config_row().environment
    head = _anchor(
        ctx,
        nif,
        environment,
        number=data.invoice_number,
        issue_date=data.issue_date,
        fingerprint=data.fingerprint,
        issuer_nif=nif,
        source="manual",
    )
    _event(
        ctx,
        Event.Kind.CHAIN_RECOVERED,
        "chain_continued_manually",
        {"issuer_nif": nif, "invoice_number": data.invoice_number},
        severity="warning",
        environment=environment,
    )
    record_event(
        ctx,
        events.CHAIN_RECOVERED,
        {
            "issuer_nif": nif,
            "environment": environment,
            "sequence": head.sequence,
            "source": "manual",
        },
    )
    return RecoveryOut(
        issuer_nif=nif,
        environment=environment,
        sequence=head.sequence,
        invoice_number=data.invoice_number,
        fingerprint=data.fingerprint,
        found=0,
    )


@operation(
    "verifactu.chain.recover_from_aeat",
    kind="command",
    permission=CONFIGURE,
    input=RecoverFromAeatIn,
    output=RecoveryOut,
    ai={
        "description": "After restoring a backup: anchor the VeriFactu chain of an issuer (Invoicing's by default) on the "
        "last record the AEAT holds this month, asked through ERPlora's gateway. Only with no pending records.",
        "risk": "high",
        "asks": {
            "en": (
                "rebuild the chain from what the AEAT holds",
                "re-anchor the VeriFactu chain on the AEAT's last entry",
            ),
            "es": (
                "reconstruye la cadena con lo último que tenga Hacienda",
                "recupera la cadena de VeriFactu desde la AEAT tras la copia",
            ),
        },
    },
)
def recover_from_aeat(ctx: OperationContext, data: RecoverFromAeatIn) -> RecoveryOut:
    refuse_outside_spain(ctx)
    config = config_row()
    nif = data.issuer_nif or issuer_identity()[0]
    if _unsent(nif, config.environment).exists():
        raise Conflict(str(PENDING_IN_CHAIN), code="verifactu.pending_in_chain")
    today = timezone.localdate()
    records = _query_aeat(ctx, config, nif, config.environment, today.year, today.month)
    latest = aeat.latest(records)
    if latest is None:
        raise Conflict(str(NOTHING_TO_RECOVER), code="verifactu.nothing_to_recover")
    fingerprint = chain.normalize_hash(latest.fingerprint)
    head = _anchor(
        ctx,
        nif,
        config.environment,
        number=latest.number,
        issue_date=latest.issue_date,
        fingerprint=fingerprint,
        issuer_nif=latest.issuer_nif or nif,
        source="aeat",
    )
    _event(
        ctx,
        Event.Kind.CHAIN_RECOVERED,
        "chain_recovered_from_aeat",
        {"issuer_nif": nif, "invoice_number": latest.number, "found": len(records)},
        severity="warning",
        environment=config.environment,
    )
    record_event(
        ctx,
        events.CHAIN_RECOVERED,
        {
            "issuer_nif": nif,
            "environment": config.environment,
            "sequence": head.sequence,
            "source": "aeat",
        },
    )
    return RecoveryOut(
        issuer_nif=nif,
        environment=config.environment,
        sequence=head.sequence,
        invoice_number=latest.number,
        fingerprint=fingerprint,
        found=len(records),
    )
