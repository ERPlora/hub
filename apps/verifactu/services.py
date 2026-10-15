"""Write operations of the verifactu app: one operation = one transaction, with its events in the outbox.

- **Sealing** (``_seal``): the record's chain head (``Chain``, one per issuer and environment) is locked with
  ``select_for_update`` in the record's transaction, so two invoices at once queue, take consecutive sequences
  and never share a previous fingerprint; a refusal rolls the number back. The record copies the invoice's
  figures, computes its fingerprint and its QR and, with the producer's details, builds its XML and validates it
  against the AEAT's schemas: what cannot be declared is never sealed.
- **Sending** (``_send``): per chain, the queue's control row (``SendControl``) is taken with
  ``SKIP LOCKED`` (two passes never send the same chain; sealing never waits for the network), the AEAT's waiting
  time is respected, the chain's unsent records go together in order (≤ 1,000) under one header and the AEAT's
  answer, as the gateway hands it back, settles each one. Nothing is ever taken as accepted without that answer.
- A sealed record is never edited in its figures nor its XML: it is corrected with a new one.

The clock is the Hub's time zone (Madrid in phase 1): ``FechaHoraHusoGenRegistro`` carries its offset.
"""

import base64
import binascii
import copy
import datetime as dt
import hashlib
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import get as get_operation
from live.operations import operation
from live.outbox import record_event

from apps.invoice.models import Invoice
from base import operations as platform
from apps.verifactu import (
    aeat,
    certificates,
    chain,
    envelope,
    events,
    gateway,
    producer,
    representation,
    xsd,
)
from apps.verifactu.envelope import AltaData, AnulacionData, ChainLink, InvoiceRef
from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Environment,
    Event,
    OwnCertificate,
    Record,
    SendControl,
    backoff,
    wait_reason_text,
)
from apps.verifactu.queries import (
    aeat_row,
    blockers,
    can_cancel,
    can_correct,
    chain_out,
    config_out,
    config_row,
    effective_environment,
    find_invoice,
    find_record,
    issuer_configured,
    issuer_identity,
    own_certificate,
    own_certificate_material,
    production_open,
    route_problem,
    saas_unreachable,
    sending_problem,
    summary,
    system_for,
    wait,
)
from apps.verifactu.schemas import (
    AeatQueryIn,
    AeatQueryOut,
    CertificateUploadIn,
    ChainValidateIn,
    ChainValidationOut,
    ConfigOut,
    ConfigSyncIn,
    ConfigSyncOut,
    ConfigUpdateIn,
    ContingencyRetryIn,
    DiagnosticOut,
    NoInput,
    RecordCancelIn,
    RecordCorrectIn,
    RecordCreateIn,
    RecordCreateOut,
    RecordSummaryOut,
    RecordTransmitIn,
    RecoverFromAeatIn,
    RecoverManualIn,
    RepresentationSubmitIn,
    RecoveryOut,
    TestInvoiceOut,
    TransmitOut,
)

IMPOSSIBLE_RECORD = _(
    "This invoice cannot be declared to the AEAT: its amounts do not square (%(detail)s). No record was sealed and no "
    "number of the chain was spent."
)
INVALID_RECORD = _(
    "The record does not pass the AEAT's schema (%(detail)s). No record was sealed and no number of the chain was spent."
)
RECIPIENT_REQUIRED = _(
    "A full or rectifying invoice %(type)s needs the customer's tax ID: it cannot be declared without it."
)
CANNOT_CORRECT = _(
    "This record cannot be corrected: only the last record of a registration the AEAT rejected or accepted with errors can."
)
CANNOT_CANCEL = _(
    "This record cannot be cancelled: only a registration that reached (or will reach) the AEAT and has no cancellation can."
)
NOT_IN_QUEUE = _(
    "This record is not in the queue: it is already in the AEAT, or the AEAT rejected it."
)
SENDING = _("This chain is being sent right now: try again in a moment.")
AEAT_WAIT = _("The AEAT asked to wait: it goes out by itself at %(at)s.")
CANNOT_SEND = _(
    "It cannot be sent now: %(why)s. It stays in the queue and goes out as soon as it can."
)
NO_RECORDS = _("There are no records of that issuer in this environment.")
PENDING_IN_CHAIN = _("The pending records of this chain have to go out first.")
AEAT_REFUSED = _("The AEAT refused the query: %(detail)s")
AEAT_UNREACHABLE = _("The AEAT could not be asked: %(detail)s")
SAME_PAGE = _("it named the same page of records again")
TOO_MANY_PAGES = _("it has more than %(pages)s pages of records")
#: A query's pages followed at most (10,000 records each, §6.4.3): far beyond any business's month.
MAX_QUERY_PAGES = 50
NOTHING_TO_RECOVER = _(
    "The AEAT has no records of that issuer this month: there is nothing to recover."
)
TESTING_ONLY = _("The test invoice is only for the test environment.")
NO_OWN_CERTIFICATE = _(
    "There is no valid certificate loaded: upload it in VeriFactu → Configuration → My certificate."
)
REPRESENTATION_NOT_APPROVED = _(
    "For ERPlora to file in production, ERPlora still has to approve your signed authorisation."
)
PRODUCTION_CLOSED = _(
    "Going live is not open on this server yet: ERPlora opens it when the real submission is ready."
)
ISSUER_MISSING = _("Set up the issuer first in Invoicing → Issuer.")
LIVE_OPTION_UNPAID = _(
    "The live option of VeriFactu is not in your plan: add it in your ERPlora account."
)
HUB_NOT_ACTIVE = _(
    "Your ERPlora account has a pending payment or is suspended: settle it in your ERPlora account to go live."
)
PRODUCTION_HAS_RECORDS = _(
    "It cannot go back to testing: this business already has records in production."
)
CERTIFICATE_STORAGE_UNAVAILABLE = _(
    "This server cannot keep certificates yet: ERPlora has to set its storage key."
)
CERTIFICATE_HOLDER_MISMATCH = _(
    "The certificate belongs to %(holder)s, not to this business's issuer %(issuer)s."
)
CERTIFICATE_EXPIRED = _("The certificate expired on %(date)s: upload a valid one.")
GO_LIVE_FORBIDDEN = _(
    "A demo business cannot go live: it always files in the AEAT's test environment."
)
PLATFORM_FIXED = _(
    "ERPlora's own business files in the AEAT environment of its server: its environment cannot be switched."
)
PLATFORM_ONLY = _("Only ERPlora's own business follows the environment of its server.")
NO_WAY_TO_THE_AEAT = _(
    "Nothing was issued: this business files for real with the AEAT and cannot reach it now: %(why)s. Fix it in "
    "VeriFactu → Settings and try again."
)
#: Why a certificate cannot present to the AEAT (``certificates.CertificateInvalid.code``), in the reader's language.
CERTIFICATE_REFUSALS = {
    "unopenable": _(
        "The file is not a .p12/.pfx certificate that this password opens."
    ),
    "incomplete": _("The file does not hold a certificate and its private key."),
    "no_client_auth": _(
        "The certificate does not allow client authentication, so it cannot connect to the AEAT."
    ),
}
#: Line of the test invoice (VERIFACTU-F11): a fiscal document's text, in the AEAT's language.
TEST_LINE = "Prueba VeriFactu"

CONFIGURE = "verifactu.configure"
TRANSMIT = "verifactu.transmit_record"
CORRECT = "verifactu.correct_record"
CENT = Decimal(1)


def _actor(ctx: OperationContext) -> str:
    actor = ctx.actor
    return str(getattr(actor, "username", None) or actor or "")[:128]


def _event(
    ctx: OperationContext,
    kind: str,
    key: str,
    params: dict,
    *,
    severity: str = "info",
    record=None,
    environment="",
) -> Event:
    event = Event(
        kind=kind,
        severity=severity,
        message_key=key,
        params=params,
        record=record,
        environment=environment,
        actor=_actor(ctx),
    )
    event.search_text = event.compose_search_text()
    event.save()
    return event


def _config(lock: bool = True) -> Config:
    """The configuration row, created on first use."""
    Config.objects.bulk_create([Config(singleton=True)], ignore_conflicts=True)
    queryset = Config.objects.select_for_update() if lock else Config.objects
    return queryset.get(singleton=True)


def _lock_chain(issuer_nif: str, environment: str) -> Chain:
    """The chain's head, locked until the COMMIT (created with its send control on first use)."""
    Chain.objects.bulk_create(
        [Chain(issuer_nif=issuer_nif, environment=environment)], ignore_conflicts=True
    )
    SendControl.objects.bulk_create(
        [SendControl(issuer_nif=issuer_nif, environment=environment)],
        ignore_conflicts=True,
    )
    return Chain.objects.select_for_update().get(
        issuer_nif=issuer_nif, environment=environment
    )


# ── What a record declares ──────────────────────────────────────────────────────────────────────


def _ref(invoice: Invoice | None) -> list[dict]:
    if invoice is None:
        return []
    return [
        {
            "issuer_nif": invoice.issuer_tax_id,
            "number": invoice.number,
            "issue_date": invoice.issue_date.isoformat(),
        }
    ]


def _refs(items: list[dict]) -> tuple:
    return tuple(
        InvoiceRef(
            item["issuer_nif"], item["number"], chain.parse_date(item["issue_date"])
        )
        for item in items
    )


def _round(value: Decimal) -> int:
    return int(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _impossible(detail: str) -> Conflict:
    return Conflict(
        str(IMPOSSIBLE_RECORD) % {"detail": detail}, code="verifactu.impossible_record"
    )


def _check_declarable(invoice: Invoice) -> None:
    """VeriFactu's own guard (Invoicing audits first): what cannot be declared is never sealed."""
    entries = invoice.tax_breakdown if isinstance(invoice.tax_breakdown, list) else []
    if not invoice.description.strip():
        raise _impossible("DescripcionOperacion")
    if not entries:
        raise _impossible("Desglose")
    if len(entries) > envelope.MAX_BREAKDOWN_LINES:
        raise _impossible(f"Desglose: {len(entries)} > {envelope.MAX_BREAKDOWN_LINES}")
    tolerance = max(1, invoice.lines.count())
    base = tax = 0
    for entry in entries:
        try:
            line_base = int(entry["base"])
            quota = int(entry.get("quota") or 0)
            surcharge = int(entry.get("surcharge_quota") or 0)
            rate = Decimal(str(entry.get("rate") or "0"))
            surcharge_rate = Decimal(str(entry.get("surcharge_rate") or "0"))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise _impossible("Desglose") from None
        if entry.get("qualification", "subject") != "subject" and (quota or surcharge):
            raise _impossible(
                f"{entry.get('qualification')} {chain.format_amount(quota + surcharge)}"
            )
        for amount, percent in ((quota, rate), (surcharge, surcharge_rate)):
            expected = _round(Decimal(line_base) * percent / 100)
            if abs(amount - expected) > tolerance:
                raise _impossible(
                    f"{chain.format_amount(line_base)} × {chain.format_rate(percent)} % ≠ {chain.format_amount(amount)}"
                )
        base += line_base
        tax += quota + surcharge
    if (base, tax, base + tax) != (
        invoice.base_amount,
        invoice.tax_amount,
        invoice.total_amount,
    ):
        raise _impossible("CuotaTotal / ImporteTotal")
    # The sign (an ordinary document never below zero, a rectifying one never above) is Invoicing's database's
    # own check constraint: it cannot reach here.


def _alta_fields(invoice: Invoice) -> dict:
    """The invoice's figures as the record keeps them (WORKBOOK «Contrato con Facturación»)."""
    return {
        "issuer_nif": invoice.issuer_tax_id,
        "issuer_name": invoice.issuer_name,
        "invoice_number": invoice.number,
        "issue_date": invoice.issue_date,
        "operation_date": invoice.operation_date
        if invoice.operation_date != invoice.issue_date
        else None,
        "invoice_type": invoice.invoice_type,
        "rectification_kind": invoice.rectification_kind
        if invoice.invoice_type in envelope.RECTIFYING_TYPES
        else "",
        "rectified": _ref(invoice.rectifies)
        if invoice.invoice_type in envelope.RECTIFYING_TYPES
        else [],
        "substituted": _ref(invoice.substitutes)
        if invoice.invoice_type == "F3"
        else [],
        "description": invoice.description,
        "recipient_name": invoice.customer_name if invoice.customer_tax_id else "",
        "recipient_tax_id": invoice.customer_tax_id,
        "recipient_country": invoice.customer_country,
        "recipient_id_type": invoice.customer_id_type,
        "tax_breakdown": invoice.tax_breakdown,
        "base_amount": invoice.base_amount,
        "tax_amount": invoice.tax_amount,
        "total_amount": invoice.total_amount,
    }


def _xml_of(record: Record, system: producer.SystemInfo) -> str:
    """The record element, from the record's own frozen figures."""
    previous = None
    if record.previous_fingerprint:
        previous = ChainLink(
            record.previous_issuer_nif or record.issuer_nif,
            record.previous_number,
            record.previous_issue_date,
            record.previous_fingerprint,
        )
    if record.record_type == Record.Type.ANULACION:
        data = AnulacionData(
            record.issuer_nif,
            record.invoice_number,
            record.issue_date,
            record.previous_rejection,
        )
        return envelope.registro_anulacion(
            data,
            previous=previous,
            system=system,
            generated_at=record.generated_at,
            fingerprint=record.fingerprint,
        )
    data = AltaData(
        issuer_nif=record.issuer_nif,
        issuer_name=record.issuer_name,
        number=record.invoice_number,
        issue_date=record.issue_date,
        invoice_type=record.invoice_type,
        description=record.description,
        tax_breakdown=record.tax_breakdown,
        tax_amount=record.tax_amount,
        total_amount=record.total_amount,
        operation_date=record.operation_date,
        rectification_kind=record.rectification_kind,
        rectified=_refs(record.rectified),
        substituted=_refs(record.substituted),
        recipient_name=record.recipient_name,
        recipient_tax_id=record.recipient_tax_id,
        recipient_country=record.recipient_country,
        recipient_id_type=record.recipient_id_type,
        correction=record.correction,
        previous_rejection=record.previous_rejection,
    )
    return envelope.registro_alta(
        data,
        previous=previous,
        system=system,
        generated_at=record.generated_at,
        fingerprint=record.fingerprint,
    )


def _build_xml(record: Record, system: producer.SystemInfo) -> None:
    """Build, validate and freeze the record's XML; ``SchemaError`` / ``UndeclarableRecord`` if it cannot be."""
    xml = _xml_of(record, system)
    xsd.validate_record(
        xml, obligado_name=record.issuer_name, obligado_nif=record.issuer_nif
    )
    record.xml = xml
    record.xml_built_at = timezone.now()


def _seal(ctx: OperationContext, config: Config, record: Record) -> Record:
    """Chain ``record`` (its figures set) in its chain: number, previous link, fingerprint, QR and XML."""
    head = _lock_chain(record.issuer_nif, record.environment)
    now = timezone.now()
    record.sequence = head.sequence + 1
    record.previous_record = head.last_record
    record.previous_issuer_nif = head.last_issuer_nif
    record.previous_number = head.last_number
    record.previous_issue_date = head.last_issue_date
    record.previous_fingerprint = head.last_fingerprint
    record.generated_on = now
    record.generated_at = chain.format_timestamp(timezone.localtime(now))
    record.created_at = now
    record.next_attempt_at = now
    record.created_by = _actor(ctx)
    if record.record_type == Record.Type.ANULACION:
        record.fingerprint = chain.anulacion_hash(
            issuer_nif=record.issuer_nif,
            number=record.invoice_number,
            issue_date=record.issue_date,
            previous_hash=record.previous_fingerprint,
            generated_at=record.generated_at,
        )
        total = record.invoice.total_amount
    else:
        record.fingerprint = chain.alta_hash(
            issuer_nif=record.issuer_nif,
            number=record.invoice_number,
            issue_date=record.issue_date,
            invoice_type=record.invoice_type,
            tax_amount=record.tax_amount,
            total_amount=record.total_amount,
            previous_hash=record.previous_fingerprint,
            generated_at=record.generated_at,
        )
        total = record.total_amount
    record.qr_url = chain.qr_url(
        issuer_nif=record.issuer_nif,
        number=record.invoice_number,
        issue_date=record.issue_date,
        total_amount=total,
        environment=record.environment,
    )
    try:
        # Built and validated when sealed: a record the schema refuses could never leave and would stop its chain.
        _build_xml(record, system_for(ctx))
    except (xsd.SchemaError, envelope.UndeclarableRecord) as error:
        raise Conflict(
            str(INVALID_RECORD) % {"detail": str(error)},
            code="verifactu.invalid_record",
        ) from None
    record.save()
    head.sequence = record.sequence
    head.last_record = record
    head.last_issuer_nif = record.issuer_nif
    head.last_number = record.invoice_number
    head.last_issue_date = record.issue_date
    head.last_fingerprint = record.fingerprint
    head.save()
    if record.record_type == Record.Type.ANULACION:
        key, params = "anulacion_sealed", {"reason_text": record.description}
    else:
        key, params = ("correction_sealed" if record.correction else "alta_sealed"), {}
    _event(
        ctx,
        Event.Kind.RECORD_CREATED,
        key,
        {
            "sequence": record.sequence,
            "invoice_number": record.invoice_number,
            **params,
        },
        record=record,
        environment=record.environment,
    )
    record_event(
        ctx,
        events.RECORD_CREATED,
        {
            "record_id": str(record.id),
            "invoice_id": str(record.invoice_id),
            "invoice_number": record.invoice_number,
            "record_type": record.record_type,
            "sequence": record.sequence,
            "environment": record.environment,
        },
    )
    return record


def _rechazo_previo(corrects: Record) -> str:
    """RechazoPrevio of a correction (Descripción del servicio web VERI*FACTU §9.1.2–§9.1.3): «X» while the AEAT
    holds no registration of the invoice (every alta of it was rejected); «S» when it holds one and what is
    corrected was a later correction it rejected; «N» for the usual correction of a record it holds."""
    held = Record.objects.filter(
        invoice_id=corrects.invoice_id,
        environment=corrects.environment,
        record_type=Record.Type.ALTA,
        status__in=Record.IN_AEAT,
    ).exists()
    if not held:
        return "X"
    return "S" if corrects.status == Record.Status.REJECTED else "N"


def _refuse_without_a_way(config: Config, environment: str) -> None:
    """In production nothing is sealed that can never reach the AEAT (working-rules §15; the old Hub's
    ``enforce_fiscal_road``, HUB-1935): 409 with the route's own code, inside the transaction of the sale or
    invoice, so the document is undone and the series gives its number back. Testing never refuses."""
    if environment != Environment.PRODUCTION:
        return
    problem = route_problem(config, environment)
    if problem:
        raise Conflict(
            str(NO_WAY_TO_THE_AEAT) % {"why": wait_reason_text(problem)},
            code=f"verifactu.{problem}",
        )


def _seal_alta(
    ctx: OperationContext,
    config: Config,
    invoice: Invoice,
    *,
    environment: str,
    corrects: Record | None = None,
    refuse_without_a_way: bool = False,
) -> tuple[Record, bool]:
    """The registration of ``invoice`` (or its correction of ``corrects``); ``(record, already)``. With
    ``refuse_without_a_way``, a new registration in production needs the way to the AEAT."""
    if corrects is None:
        existing = Record.objects.filter(
            invoice=invoice,
            environment=environment,
            record_type=Record.Type.ALTA,
            correction=False,
        ).first()
        if existing is not None:
            return existing, True
    if refuse_without_a_way:
        _refuse_without_a_way(config, environment)
    if (
        invoice.invoice_type in ("F1", "F3", "R1", "R2", "R3", "R4")
        and not invoice.customer_tax_id.strip()
    ):
        raise Conflict(
            str(RECIPIENT_REQUIRED) % {"type": invoice.invoice_type},
            code="verifactu.recipient_required",
        )
    _check_declarable(invoice)
    record = Record(
        record_type=Record.Type.ALTA,
        environment=environment,
        invoice=invoice,
        correction=corrects is not None,
        corrects=corrects,
        previous_rejection=_rechazo_previo(corrects) if corrects is not None else "",
        **_alta_fields(invoice),
    )
    if corrects is None:
        # A second delivery of the same invoice waited for the chain's lock: it answers what the first sealed.
        _lock_chain(record.issuer_nif, environment)
        existing = Record.objects.filter(
            invoice=invoice,
            environment=environment,
            record_type=Record.Type.ALTA,
            correction=False,
        ).first()
        if existing is not None:
            return existing, True
    return _seal(ctx, config, record), False


# ── Sealing operations ──────────────────────────────────────────────────────────────────────────


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
    },
)
def create_record(ctx: OperationContext, data: RecordCreateIn) -> RecordCreateOut:
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
    },
)
def correct_record(ctx: OperationContext, data: RecordCorrectIn) -> RecordCreateOut:
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
    },
)
def cancel_record(ctx: OperationContext, data: RecordCancelIn) -> RecordCreateOut:
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
        # §9.2.2 «anulación por rechazo»: an earlier anulación of the same registration was rejected.
        previous_rejection="S"
        if Record.objects.filter(cancels=target, status=Record.Status.REJECTED).exists()
        else "",
    )
    return RecordCreateOut(record=summary(_seal(ctx, config, record)), already=False)


# ── Sending ─────────────────────────────────────────────────────────────────────────────────────


class _Tally:
    def __init__(self) -> None:
        self.chains = self.sent = self.accepted = self.accepted_with_errors = (
            self.rejected
        ) = self.waiting = 0
        self.reason = ""
        self.detail = ""
        self.changed = False

    def because(self, code: str, detail: str = "") -> None:
        """Why (some of) it did not reach the AEAT, said to whoever asked: never told as a success."""
        self.reason, self.detail = code, detail

    def out(self) -> TransmitOut:
        return TransmitOut(
            chains=self.chains,
            sent=self.sent,
            accepted=self.accepted,
            accepted_with_errors=self.accepted_with_errors,
            rejected=self.rejected,
            waiting=self.waiting,
            reason=self.reason,
            message=wait_reason_text(self.reason, self.detail) if self.reason else "",
        )


def _mark(ctx: OperationContext, records, code: str, detail: str, tally: _Tally) -> int:
    """Records that wait for ``code`` say so (VERIFACTU-F17); a change is told once, not at every pass."""
    queryset = records.exclude(wait_reason=code, wait_detail=detail[:500])
    changed = queryset.update(wait_reason=code, wait_detail=detail[:500])
    if changed:
        tally.changed = True
        _event(
            ctx,
            Event.Kind.DEFERRED,
            "deferred",
            {"count": changed, "reason": code, "detail": detail},
            severity="warning",
        )
    return changed


def _unsent(issuer_nif: str | None = None, environment: str | None = None):
    queryset = Record.objects.filter(status__in=Record.UNSENT)
    if issuer_nif is not None:
        queryset = queryset.filter(issuer_nif=issuer_nif, environment=environment)
    return queryset


def _failed(
    ctx,
    batch,
    code: str,
    detail: str,
    now,
    *,
    status: str | None = None,
    severity: str = "warning",
) -> None:
    for record in batch:
        record.attempts += 1
        record.next_attempt_at = now + backoff(record.attempts)
        record.wait_reason = code
        record.wait_detail = detail[:500]
        if status:
            record.status = status
    _event(
        ctx,
        Event.Kind.DEFERRED,
        "deferred",
        {"count": len(batch), "reason": code, "detail": detail},
        severity=severity,
        record=batch[0] if len(batch) == 1 else None,
        environment=batch[0].environment,
    )


def _settle(ctx, batch, answer: aeat.SubmissionAnswer, now, tally: _Tally) -> None:
    """Each record of ``batch`` takes the AEAT's verdict on it; one the answer does not name stays «sent»."""
    verdicts: dict[tuple[str, str], list[aeat.LineVerdict]] = {}
    for line in answer.lines:
        verdicts.setdefault((line.operation.lower(), line.number), []).append(line)
    accepted = []
    for record in batch:
        found = verdicts.get((record.record_type, record.invoice_number))
        if not found:
            record.status = Record.Status.SENT
            record.attempts += 1
            record.next_attempt_at = now + backoff(record.attempts)
            record.wait_reason = "unknown"
            continue
        line = found.pop(0)
        record.status = line.status
        record.aeat_code = line.code[:16]
        record.aeat_message = line.message[:1000]
        record.wait_reason = record.wait_detail = ""
        if line.status in Record.IN_AEAT:
            record.csv = answer.csv[:64]
        notice = {
            "record_id": str(record.id),
            "invoice_number": record.invoice_number,
            "status": line.status,
            "code": line.code,
            "message": line.message,
            "environment": record.environment,
        }
        if line.status == Record.Status.ACCEPTED:
            tally.accepted += 1
            accepted.append(record)
        elif line.status == Record.Status.ACCEPTED_WITH_ERRORS:
            tally.accepted_with_errors += 1
            _event(
                ctx,
                Event.Kind.ACCEPTED_WITH_ERRORS,
                "accepted_with_errors",
                notice,
                severity="warning",
                record=record,
                environment=record.environment,
            )
            record_event(ctx, events.RECORD_ACCEPTED_WITH_ERRORS, notice)
        else:
            tally.rejected += 1
            _event(
                ctx,
                Event.Kind.FAILED,
                "rejected",
                notice,
                severity="error",
                record=record,
                environment=record.environment,
            )
            record_event(ctx, events.RECORD_REJECTED, notice)
    if accepted:
        _event(
            ctx,
            Event.Kind.ACCEPTED,
            "accepted",
            {
                "count": len(accepted),
                "csv": answer.csv,
                "environment": accepted[0].environment,
            },
            record=accepted[0] if len(accepted) == 1 else None,
            environment=accepted[0].environment,
        )


def _send_chain(
    ctx,
    config: Config,
    system,
    issuer_nif: str,
    environment: str,
    tally: _Tally,
    *,
    force: bool,
    strict: bool,
) -> None:
    now = timezone.now()
    problem = sending_problem(config, environment)
    certificate = None
    if not problem:
        try:
            certificate = own_certificate_material(config)
        except certificates.CertificateUnreadable:
            problem = "own_certificate_unreadable"
    if problem:
        if strict:
            raise Conflict(
                str(CANNOT_SEND) % {"why": wait_reason_text(problem)},
                code=f"verifactu.{problem}",
            )
        tally.waiting += _unsent(issuer_nif, environment).count()
        tally.reason = problem
        _mark(ctx, _unsent(issuer_nif, environment), problem, "", tally)
        return
    SendControl.objects.bulk_create(
        [SendControl(issuer_nif=issuer_nif, environment=environment)],
        ignore_conflicts=True,
    )
    control = (
        SendControl.objects.select_for_update(skip_locked=True)
        .filter(issuer_nif=issuer_nif, environment=environment)
        .first()
    )
    if control is None:
        if strict:
            raise Conflict(str(SENDING), code="verifactu.sending")
        return
    if control.next_send_at and control.next_send_at > now:
        if strict:
            at = timezone.localtime(control.next_send_at).strftime("%H:%M:%S")
            raise Conflict(str(AEAT_WAIT) % {"at": at}, code="verifactu.aeat_wait")
        tally.waiting += _unsent(issuer_nif, environment).count()
        return
    batch = list(
        _unsent(issuer_nif, environment)
        .select_for_update()
        .order_by("sequence")[: envelope.MAX_RECORDS]
    )
    if not batch or (not force and batch[0].next_attempt_at > now):
        tally.waiting += len(batch)
        return
    try:
        for record in batch:
            if not record.xml:
                _build_xml(record, system)
        whole = envelope.submission(
            obligado_name=batch[0].issuer_name,
            obligado_nif=issuer_nif,
            registros=[record.xml for record in batch],
            representative=(
                (producer.MANUFACTURER["NombreRazon"], producer.MANUFACTURER["NIF"])
                if config.route == Config.Route.ERPLORA
                else None
            ),
            incident=any(
                record.attempts
                or record.wait_reason
                or record.status == Record.Status.SENT
                for record in batch
            ),
        )
        xsd.validate(whole)
    except (xsd.SchemaError, envelope.UndeclarableRecord) as error:
        # A defect of ours: the chain stops loudly instead of sending what the AEAT would refuse.
        if strict:
            raise Conflict(
                str(INVALID_RECORD) % {"detail": str(error)},
                code="verifactu.invalid_record",
            ) from None
        # Told once, as every wait: a pass a minute repeats nothing while the defect stays the same.
        tally.because("xml_invalid", str(error))
        if _mark(ctx, _unsent(issuer_nif, environment), "xml_invalid", str(error), tally):
            _event(
                ctx,
                Event.Kind.FAILED,
                "xml_invalid",
                {"invoice_number": batch[0].invoice_number, "detail": str(error)},
                severity="critical",
            )
        tally.waiting += len(batch)
        return
    incident = "<sum1:Incidencia>S</sum1:Incidencia>" in whole
    reply = gateway.submit(
        hub=ctx.scope.key,
        nif=issuer_nif,
        environment=environment,
        route=config.route,
        envelope=whole,
        certificate=certificate,
    )
    transmission = uuid.uuid7()
    digest = hashlib.sha256(whole.encode("utf-8")).hexdigest()
    for record in batch:
        record.transmitted_at = now
        record.transmission_id = transmission
        record.envelope_digest = digest
        record.incident = incident
    tally.changed = True
    if reply.kind in (gateway.ANSWERED, gateway.UNKNOWN):
        # It reached (or may have reached) the AEAT; a refusal of the gateway or no connection never left.
        tally.chains += 1
        tally.sent += len(batch)
    if reply.kind == gateway.ANSWERED:
        try:
            answer = aeat.parse_submission(reply.aeat_body)
        except aeat.UnreadableAnswer as error:
            if reply.aeat_status == 200:
                _failed(
                    ctx, batch, "unknown", str(error), now, status=Record.Status.SENT
                )
                tally.because("unknown", str(error))
            else:
                detail = f"AEAT HTTP {reply.aeat_status}"
                _failed(ctx, batch, "unreachable", detail, now)
                tally.because("unreachable", detail)
            tally.waiting += len(batch)
        else:
            if answer.fault_code:
                # A fault refuses the SENDING, not its records: the AEAT evaluated none of them, so none is
                # «rejected» (a correction of a record it never saw would carry a wrong RechazoPrevio). They
                # wait with the attempt spent; a permanent fault (4102/4104/4116) is told as critical, since
                # sending it again unchanged will not help.
                detail = f"{answer.fault_code}: {answer.fault_message}"
                _failed(
                    ctx,
                    batch,
                    "aeat_fault",
                    detail,
                    now,
                    severity="critical" if answer.permanent_fault else "warning",
                )
                tally.because("aeat_fault", detail)
                tally.waiting += len(batch)
            else:
                _settle(ctx, batch, answer, now, tally)
                tally.waiting += sum(
                    1 for record in batch if record.status in Record.UNSENT
                )
            if answer.wait_seconds is not None:
                control.wait_seconds = answer.wait_seconds
                control.next_send_at = now + dt.timedelta(
                    seconds=answer.wait_seconds
                )
    elif reply.kind == gateway.REFUSED:
        detail = f"{reply.code}: {reply.message}"
        _failed(ctx, batch, "refused", detail, now)
        tally.because("refused", detail)
        tally.waiting += len(batch)
    elif reply.kind == gateway.UNKNOWN:
        _failed(ctx, batch, "unknown", reply.message, now, status=Record.Status.SENT)
        tally.because("unknown", reply.message)
        tally.waiting += len(batch)
    else:
        _failed(ctx, batch, "unreachable", reply.message, now)
        tally.because("unreachable", reply.message)
        tally.waiting += len(batch)
    control.last_sent_at = now
    control.save()
    Record.objects.bulk_update(
        batch,
        [
            "status",
            "attempts",
            "next_attempt_at",
            "wait_reason",
            "wait_detail",
            "transmitted_at",
            "transmission_id",
            "envelope_digest",
            "incident",
            "csv",
            "aeat_code",
            "aeat_message",
            "xml",
            "xml_built_at",
            "updated_at",
        ],
    )
    record_event(
        ctx,
        events.RECORD_TRANSMITTED,
        {
            "record_ids": [str(record.id) for record in batch],
            "transmission_id": str(transmission),
            "environment": environment,
        },
    )


def _send(ctx: OperationContext, *, only: Record | None = None) -> _Tally:
    """One pass of the queue (VERIFACTU-F15, F20, F21), or the chain of ``only`` now (VERIFACTU-F25)."""
    tally = _Tally()
    config = _config(lock=False)
    strict = only is not None
    scope = _unsent(only.issuer_nif, only.environment) if strict else _unsent()
    for code in blockers(config, only.environment if strict else config.environment):
        if code == "gateway_unavailable":
            if strict:
                raise Conflict(
                    str(CANNOT_SEND) % {"why": wait_reason_text(code)},
                    code=f"verifactu.{code}",
                )
            tally.reason = code
            tally.waiting = scope.count()
            _mark(ctx, scope, code, "", tally)
            return tally
    system = system_for(ctx)
    keys = list(scope.order_by().values_list("issuer_nif", "environment").distinct())
    for issuer_nif, environment in sorted(keys):
        _send_chain(
            ctx,
            config,
            system,
            issuer_nif,
            environment,
            tally,
            force=strict,
            strict=strict,
        )
    return tally


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
    },
)
def transmit_record(ctx: OperationContext, data: RecordTransmitIn) -> TransmitOut:
    record = find_record(data.record_id, data.invoice_number)
    if record.status not in Record.UNSENT:
        raise Conflict(str(NOT_IN_QUEUE), code="verifactu.not_in_queue")
    return _send(ctx, only=record).out()


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
    },
)
def retry_record(ctx: OperationContext, data: ContingencyRetryIn) -> RecordSummaryOut:
    record = find_record(data.record_id, data.invoice_number, lock=True)
    if record.status not in Record.UNSENT:
        raise Conflict(str(NOT_IN_QUEUE), code="verifactu.not_in_queue")
    now = timezone.now()
    _unsent(record.issuer_nif, record.environment).filter(
        sequence__lte=record.sequence
    ).update(next_attempt_at=now)
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


# ── The chain ───────────────────────────────────────────────────────────────────────────────────


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


def _anchor(
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


def _query_page(
    ctx: OperationContext,
    config: Config,
    nif: str,
    name: str,
    environment: str,
    year: int,
    month: int,
    represented: bool,
    after: InvoiceRef | None,
    certificate: gateway.Certificate | None,
) -> aeat.QueryPage:
    """One page of the AEAT's records of ``nif`` in a month (after ``after``), asked through the gateway."""
    try:
        body = envelope.query(
            obligado_nif=nif,
            obligado_name=name,
            year=year,
            month=month,
            represented=represented,
            after=after,
        )
        xsd.validate_query(body)
    except (envelope.UndeclarableRecord, xsd.SchemaError) as error:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(error)},
            code="verifactu.aeat_unreachable",
        ) from None
    reply = gateway.query(
        hub=ctx.scope.key,
        nif=nif,
        environment=environment,
        route=config.route,
        envelope=body,
        certificate=certificate,
    )
    if reply.kind != gateway.ANSWERED:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": reply.message or reply.code},
            code="verifactu.aeat_unreachable",
        )
    try:
        return aeat.parse_query(reply.aeat_body)
    except aeat.AeatFault as fault:
        raise Conflict(
            str(AEAT_REFUSED) % {"detail": fault.message}, code="verifactu.aeat_refused"
        ) from None
    except aeat.UnreadableAnswer as error:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(error)},
            code="verifactu.aeat_unreachable",
        ) from None


def _query_aeat(
    ctx, config: Config, nif: str, environment: str, year: int, month: int
) -> list[aeat.QueriedRecord]:
    """Ask the AEAT, through the gateway, for the records of ``nif`` in a month; replace the last photo."""
    if not gateway.configured():
        raise Conflict(
            str(CANNOT_SEND) % {"why": wait_reason_text("gateway_unavailable")},
            code="verifactu.gateway_unavailable",
        )
    try:
        certificate = own_certificate_material(config)
    except certificates.CertificateUnreadable:
        raise Conflict(
            str(CANNOT_SEND) % {"why": wait_reason_text("own_certificate_unreadable")},
            code="verifactu.own_certificate_unreadable",
        ) from None
    latest_name = (
        Record.objects.filter(issuer_nif=nif)
        .order_by("-created_at")
        .values_list("issuer_name", flat=True)
        .first()
    )
    name = latest_name or issuer_identity()[1]
    represented = (
        config.route == Config.Route.ERPLORA
        and nif.upper() != producer.MANUFACTURER["NIF"]
    )
    records: list[aeat.QueriedRecord] = []
    after = None
    for _page in range(MAX_QUERY_PAGES):
        page = _query_page(
            ctx, config, nif, name, environment, year, month, represented, after, certificate
        )
        records.extend(page.records)
        if not page.more:
            break
        if page.after == after:
            raise Conflict(
                str(AEAT_UNREACHABLE) % {"detail": str(SAME_PAGE)},
                code="verifactu.aeat_unreachable",
            )
        after = page.after
    else:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(TOO_MANY_PAGES) % {"pages": MAX_QUERY_PAGES}},
            code="verifactu.aeat_unreachable",
        )
    now = timezone.now()
    AeatRecord.objects.filter(issuer_nif=nif, environment=environment).delete()
    AeatRecord.objects.bulk_create(
        [
            AeatRecord(
                issuer_nif=item.issuer_nif or nif,
                environment=environment,
                invoice_number=item.number,
                issue_date=item.issue_date,
                fingerprint=chain.normalize_hash(item.fingerprint),
                state=item.state[:40],
                csv=item.csv[:64],
                generated_on=item.generated_at,
                queried_at=now,
            )
            for item in records
        ]
    )
    _event(
        ctx,
        Event.Kind.AEAT_QUERIED,
        "aeat_queried",
        {"issuer_nif": nif, "count": len(records)},
        environment=environment,
    )
    record_event(ctx, events.AEAT_QUERIED, {"issuer_nif": nif, "count": len(records)})
    return records


@operation(
    "verifactu.aeat.query",
    kind="command",
    permission=TRANSMIT,
    input=AeatQueryIn,
    output=AeatQueryOut,
    ai={
        "description": "Ask the AEAT which records of an issuer (Invoicing's by default) it holds in a month (this one "
        "by default), through ERPlora's gateway; the answer replaces the last photo. It does not touch the chain.",
        "risk": "high",
    },
)
def query_aeat(ctx: OperationContext, data: AeatQueryIn) -> AeatQueryOut:
    config = config_row()
    today = timezone.localdate()
    nif = data.issuer_nif or issuer_identity()[0]
    records = _query_aeat(
        ctx,
        config,
        nif,
        config.environment,
        data.year or today.year,
        data.month or today.month,
    )
    rows = AeatRecord.objects.filter(
        issuer_nif=nif, environment=config.environment
    ).order_by("-generated_on", "-id")
    return AeatQueryOut(count=len(records), rows=[aeat_row(row) for row in rows])


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
    },
)
def recover_from_aeat(ctx: OperationContext, data: RecoverFromAeatIn) -> RecoveryOut:
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


# ── Connection test and test invoice ────────────────────────────────────────────────────────────


@operation(
    "verifactu.diagnostic.run",
    kind="command",
    permission=TRANSMIT,
    input=NoInput,
    output=DiagnosticOut,
    ai={
        "description": "Test whether this business can send VeriFactu records now, presenting nothing to the AEAT: the "
        "issuer, the producer's details, the route and, with ERPlora's gateway, its own answer.",
        "risk": "normal",
    },
)
def run_diagnostic(ctx: OperationContext, data: NoInput) -> DiagnosticOut:
    config = config_row()
    nif = issuer_identity()[0]
    codes = blockers(config, config.environment)
    gateway_ready, gateway_detail = None, ""
    if gateway.configured() and "own_certificate_unreadable" not in codes:
        reply = gateway.probe(
            hub=ctx.scope.key,
            nif=nif,
            environment=config.environment,
            route=config.route,
            certificate=own_certificate_material(config),
        )
        gateway_ready = reply.kind == gateway.ANSWERED and reply.ready
        gateway_detail = reply.message or reply.code
        if not gateway_ready:
            codes.append("refused")
    details = {"refused": gateway_detail}
    result = {
        "ran_at": timezone.now(),
        "environment": config.environment,
        "route": config.route,
        "issuer_ready": issuer_configured(),
        "route_ready": not route_problem(config, config.environment),
        "gateway_configured": gateway.configured(),
        "gateway_ready": gateway_ready,
        "gateway_detail": gateway_detail,
        "can_send": not codes and issuer_configured(),
        "reasons": [{"code": code, "detail": details.get(code, "")} for code in codes],
    }
    stored = {**result, "ran_at": result["ran_at"].isoformat()}
    if result["can_send"]:
        key, params = "connection_ok", {"environment": config.environment}
    else:
        first = codes[0] if codes else "issuer"
        key, params = (
            "connection_blocked",
            {
                "environment": config.environment,
                "reason": first,
                "detail": details.get(first, ""),
            },
        )
    _event(
        ctx,
        Event.Kind.CONNECTION_TEST,
        key,
        {**params, "result": stored},
        severity="info" if result["can_send"] else "warning",
    )
    record_event(ctx, events.DIAGNOSTIC_RUN, {"can_send": result["can_send"]})
    return DiagnosticOut(
        **{
            **result,
            "reasons": [
                wait(item["code"], item["detail"]) for item in result["reasons"]
            ],
        }
    )


@operation(
    "verifactu.test_invoice.create",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=TestInvoiceOut,
    ai={
        "description": "Create the VeriFactu test invoice (only in the test environment): a real ticket (F2) of one line "
        "«Prueba VeriFactu», 1.00 € plus 21 % VAT, issued by Invoicing in its TICKET series, and its record.",
        "risk": "high",
    },
)
def create_test_invoice(ctx: OperationContext, data: NoInput) -> TestInvoiceOut:
    config = _config(lock=False)
    environment = effective_environment(ctx, config)
    if environment != Environment.TESTING:
        raise Conflict(str(TESTING_ONLY), code="verifactu.testing_only")
    issue = get_operation("invoice.invoice.create")
    invoice_out = issue(
        ctx,
        issue.input.model_validate(
            {
                "series_code": "TICKET",
                "lines": [
                    {
                        "description": TEST_LINE,
                        "quantity": "1",
                        "unit_price": 100,
                        "tax_rate": "21",
                    }
                ],
            }
        ),
    )
    invoice = find_invoice(invoice_out.id, None)
    record, _already = _seal_alta(ctx, config, invoice, environment=environment)
    return TestInvoiceOut(
        invoice_id=invoice.id, number=invoice.number, record=summary(record)
    )


# ── Configuration ───────────────────────────────────────────────────────────────────────────────


def _changed(
    ctx, config: Config, key: str, params: dict | None = None, *, fields: list[str]
) -> None:
    config.updated_by = _actor(ctx)
    config.save()
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        params or {},
        environment=config.environment,
    )
    record_event(ctx, events.CONFIG_CHANGED, {"fields": fields})


def _route_refusal(config: Config, route: str, environment: str) -> Conflict | None:
    """Why ``route`` cannot file in ``environment`` (VERIFACTU-F04, F08), as the refusal to raise."""
    probe = copy.copy(config)
    probe.route = route
    problem = route_problem(probe, environment)
    if problem == "own_certificate_missing":
        return Conflict(str(NO_OWN_CERTIFICATE), code="verifactu.no_own_certificate")
    if problem == "representation_not_approved":
        return Conflict(
            str(REPRESENTATION_NOT_APPROVED),
            code="verifactu.representation_not_approved",
        )
    if problem == "live_option_unpaid":
        return Conflict(str(LIVE_OPTION_UNPAID), code="verifactu.live_option_unpaid")
    return None


@operation(
    "verifactu.config.update",
    kind="command",
    permission=CONFIGURE,
    input=ConfigUpdateIn,
    output=ConfigOut,
    ai={
        "description": "Choose who files the VeriFactu records: «erplora» (ERPlora files on the business's behalf with "
        "its seal; in production it needs the approved signed authorisation) or «own» (the business's own certificate, "
        "uploaded in VeriFactu → Configuration).",
        "risk": "high",
    },
)
def update_config(ctx: OperationContext, data: ConfigUpdateIn) -> ConfigOut:
    config = _config()
    refusal = _route_refusal(config, data.route, config.environment)
    if refusal is not None:
        raise refusal
    if config.route != data.route:
        config.route = data.route
        _changed(
            ctx,
            config,
            "route_own" if data.route == Config.Route.OWN else "route_erplora",
            fields=["route"],
        )
    return config_out(config, ctx)


def _refuse_on_the_platform_hub(ctx: OperationContext) -> None:
    """ERPlora's own hub files where its deployment does (``queries.effective_environment``): no switch moves it."""
    if platform.is_platform_hub(ctx.scope):
        raise Conflict(str(PLATFORM_FIXED), code="verifactu.platform_fixed")


@operation(
    "verifactu.config.go_live",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Go live: from now on every VeriFactu record goes to the real AEAT. It needs the server opened for "
        "it by ERPlora, a business that is not a demo, Invoicing's issuer, a route ready for production (the own valid certificate, or ERPlora's "
        "approved signed authorisation with the live option in the plan) and an active ERPlora account; it cannot "
        "go back once a production record is sealed.",
        "risk": "high",
    },
)
def go_live(ctx: OperationContext, data: NoInput) -> ConfigOut:
    _refuse_on_the_platform_hub(ctx)
    config = _config()
    if config.environment == Environment.PRODUCTION:
        return config_out(config, ctx)
    if not production_open():
        raise Conflict(str(PRODUCTION_CLOSED), code="verifactu.production_closed")
    if platform.is_demo_hub(ctx.scope):
        raise Conflict(str(GO_LIVE_FORBIDDEN), code="verifactu.go_live_forbidden")
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    refusal = _route_refusal(config, config.route, Environment.PRODUCTION)
    if refusal is not None:
        raise refusal
    if config.hub_status != Config.HubStatus.ACTIVE:
        raise Conflict(str(HUB_NOT_ACTIVE), code="verifactu.hub_not_active")
    config.environment = Environment.PRODUCTION
    config.production_since = timezone.now()
    _changed(ctx, config, "went_live", fields=["environment"])
    return config_out(config, ctx)


@operation(
    "verifactu.config.back_to_testing",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Go back to the AEAT's test environment; only while no VeriFactu record was sealed in production.",
        "risk": "high",
    },
)
def back_to_testing(ctx: OperationContext, data: NoInput) -> ConfigOut:
    _refuse_on_the_platform_hub(ctx)
    config = _config()
    if config.environment == Environment.TESTING:
        return config_out(config, ctx)
    if Record.objects.filter(environment=Environment.PRODUCTION).exists():
        raise Conflict(
            str(PRODUCTION_HAS_RECORDS), code="verifactu.production_has_records"
        )
    config.environment = Environment.TESTING
    config.production_since = None
    _changed(ctx, config, "back_to_testing", fields=["environment"])
    return config_out(config, ctx)


def _certificate_event(ctx, key: str, row: OwnCertificate) -> None:
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        {
            "holder": row.holder,
            "holder_tax_id": row.holder_tax_id,
            "expires_on": timezone.localtime(row.expires_at).date().isoformat(),
        },
        environment=config_row().environment,
    )
    record_event(ctx, events.CONFIG_CHANGED, {"fields": ["own_certificate"]})


@operation(
    "verifactu.certificate.upload",
    kind="command",
    permission=CONFIGURE,
    input=CertificateUploadIn,
    output=ConfigOut,
    ai={
        "description": "Upload the business's own certificate (.p12/.pfx in base64, with its password) to file its "
        "VeriFactu records with it (the «own» route). It must belong to Invoicing's issuer, allow client "
        "authentication and be in force; it replaces the one uploaded before and is kept encrypted, never shown again.",
        "risk": "high",
    },
)
def upload_certificate(ctx: OperationContext, data: CertificateUploadIn) -> ConfigOut:
    if not certificates.storage_available():
        raise Conflict(
            str(CERTIFICATE_STORAGE_UNAVAILABLE),
            code="verifactu.certificate_storage_unavailable",
        )
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    try:
        p12 = base64.b64decode(
            "".join(data.p12_base64.get_secret_value().split()), validate=True
        )
    except (binascii.Error, ValueError):
        p12 = b""
    password = data.password.get_secret_value()
    try:
        facts = certificates.inspect(p12, password)
    except certificates.CertificateInvalid as invalid:
        raise Conflict(
            str(CERTIFICATE_REFUSALS[invalid.code]), code="verifactu.certificate_invalid"
        ) from None
    if facts.expires_at <= timezone.now():
        raise Conflict(
            str(CERTIFICATE_EXPIRED)
            % {"date": timezone.localtime(facts.expires_at).date().isoformat()},
            code="verifactu.certificate_invalid",
        )
    issuer = issuer_identity()[0].strip().upper()
    if facts.holder_tax_id != issuer:
        raise Conflict(
            str(CERTIFICATE_HOLDER_MISMATCH)
            % {"holder": facts.holder_tax_id or facts.holder, "issuer": issuer},
            code="verifactu.certificate_holder_mismatch",
        )
    row, _created = OwnCertificate.objects.update_or_create(
        singleton=True,
        defaults={
            "holder": facts.holder[:200],
            "holder_tax_id": facts.holder_tax_id,
            "kind": facts.kind,
            "expires_at": facts.expires_at,
            "uploaded_at": timezone.now(),
            "uploaded_by": _actor(ctx),
            "sealed_blob": certificates.seal(p12, password),
        },
    )
    _certificate_event(ctx, "certificate_uploaded", row)
    return config_out(config_row(), ctx)


@operation(
    "verifactu.certificate.remove",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Remove the business's own certificate from this Hub. With the «own» route, records wait in the "
        "queue until another certificate is uploaded or ERPlora files for the business.",
        "risk": "high",
    },
)
def remove_certificate(ctx: OperationContext, data: NoInput) -> ConfigOut:
    row = own_certificate()
    if row is not None:
        OwnCertificate.objects.filter(pk=row.pk).delete()
        _certificate_event(ctx, "certificate_removed", row)
    return config_out(config_row(), ctx)


@operation(
    "verifactu.config.sync",
    kind="command",
    permission="verifactu.sync_config",
    input=ConfigSyncIn,
    output=ConfigSyncOut,
    ai={
        "description": "System only: the platform hands over the ERPlora account's VeriFactu block (the signed "
        "authorisation's state, whether the plan includes the live option, the business's status) with its version; "
        "an equal or older version is ignored.",
        "risk": "high",
    },
)
def sync_config(ctx: OperationContext, data: ConfigSyncIn) -> ConfigSyncOut:
    config = _config()
    if config.synced_version is not None and data.version <= config.synced_version:
        return ConfigSyncOut(applied=False, version=config.synced_version)
    if data.hub_id is not None:
        config.hub_id = data.hub_id
    if data.representation is not None:
        if data.representation.status != config.representation_status:
            _representation_step(ctx, config, data.representation)
        config.representation_status = data.representation.status
        config.representation_updated_at = data.representation.updated_at
        config.representation_reason = data.representation.reason
    if data.live_paid is not None:
        config.live_paid = data.live_paid
    if data.hub_status is not None:
        config.hub_status = data.hub_status
    config.synced_version = data.version
    config.synced_at = timezone.now()
    _changed(
        ctx, config, "account_synced", {"version": data.version}, fields=["account"]
    )
    return ConfigSyncOut(applied=True, version=data.version)


# ── ERPlora's own hub (PLAN-SAAS §4) ───────────────────────────────────────────────────────────────────────────


@operation(
    "verifactu.config.follow_deployment",
    kind="command",
    # Declared by no role: only the system holds it (``manage.py create_platform_hub``).
    permission="verifactu.follow_deployment",
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "System only: ERPlora's own business takes the AEAT environment of its server (prod: production; "
        "pre: testing), the one its records file in anyway; refused for any other business.",
        "risk": "high",
    },
)
def follow_deployment(ctx: OperationContext, data: NoInput) -> ConfigOut:
    if not platform.is_platform_hub(ctx.scope):
        raise Conflict(str(PLATFORM_ONLY), code="verifactu.platform_only")
    config = _config()
    environment = effective_environment(ctx, config)
    if config.environment == environment:
        return config_out(config, ctx)
    if environment == Environment.TESTING and Record.objects.filter(
        environment=Environment.PRODUCTION
    ).exists():
        raise Conflict(
            str(PRODUCTION_HAS_RECORDS), code="verifactu.production_has_records"
        )
    config.environment = environment
    went_live = environment == Environment.PRODUCTION
    config.production_since = timezone.now() if went_live else None
    _changed(
        ctx,
        config,
        "went_live" if went_live else "back_to_testing",
        fields=["environment"],
    )
    return config_out(config, ctx)


# ── The signed authorisation (VERIFACTU-F05, F06) ───────────────────────────────────────────────

SIGNER_REQUIRED = _("Fill in the name and ID number of the person signing.")
SIGNED_MODEL_REQUIRED = _("Attach the signed form.")
SIGNED_MODEL_NOT_PDF = _(
    "The signed form has to be a PDF: scan it or sign it with AutoFirma."
)
ID_COPY_REQUIRED = _("Attach a copy of the identity document.")
SIGNATURE_SAMPLE_REQUIRED = _(
    "With a NIE we also need a sample of the handwritten signature."
)
REPRESENTATION_PROOF_REQUIRED = _(
    "Attach the document that proves you may sign for the company."
)
DOCUMENT_TOO_LARGE = _("Each file has to be 5 MB at most.")
DOCUMENT_NOT_PDF = _("Each file has to be a PDF.")
REPRESENTATION_INCOMPLETE = _("The authorisation cannot be sent as it is.")
REPRESENTATION_REFUSED = _("ERPlora did not take the authorisation as it is.")
HUB_UNREGISTERED = _(
    "ERPlora has not linked this business yet. Try again in a few minutes."
)
#: The documents in the order the SaaS checks them: (this input's field, the contract's name).
REPRESENTATION_DOCUMENTS = (
    ("signed_model_base64", "signed_model"),
    ("id_copy_base64", "id_copy"),
    ("signature_sample_base64", "signature_sample"),
    ("representation_proof_base64", "representation_proof"),
)


def _representation_step(ctx: OperationContext, config: Config, data) -> None:
    """Leave in the audit trail the authorisation's new state, as the photo says it."""
    at = data.updated_at or timezone.now()
    key = (
        "representation_under_review"
        if data.status == Config.Representation.SUBMITTED
        else f"representation_{data.status}"
    )
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        {"at": at, "note": data.reason},
        environment=config.environment,
    )


def _representation_payload(
    data: RepresentationSubmitIn, taxpayer_tax_id: str, taxpayer_name: str
) -> dict:
    """The contract's body, or ``InvalidPayload`` naming every broken rule with the first one's code: the SaaS's
    own rules and codes (the old Hub's ``validate``), checked before anything crosses the network."""
    problems: list[tuple[str, str, str]] = []
    company = representation.is_legal_person_nif(taxpayer_tax_id)
    signer_tax_id = representation.normalise_nif(data.signer_tax_id)
    signer_name = data.signer_name
    if not company and not signer_tax_id and not signer_name:
        # A self-employed business signs itself: its signer is the taxpayer, not a second person.
        signer_tax_id = representation.normalise_nif(taxpayer_tax_id)
        signer_name = taxpayer_name
    if not signer_tax_id:
        problems.append(("signer_tax_id", "fiscal.signer_required", SIGNER_REQUIRED))
    if not signer_name:
        problems.append(("signer_name", "fiscal.signer_required", SIGNER_REQUIRED))
    required = {
        "signed_model": ("fiscal.signed_model_required", SIGNED_MODEL_REQUIRED),
        "id_copy": ("fiscal.id_copy_required", ID_COPY_REQUIRED),
    }
    if data.signer_document_type == "nie":
        # Many foreign identity documents carry no printed signature to compare against.
        required["signature_sample"] = (
            "fiscal.signature_sample_required",
            SIGNATURE_SAMPLE_REQUIRED,
        )
    if company:
        # A company signs through whoever its deeds name: the model's note (2).
        required["representation_proof"] = (
            "fiscal.representation_proof_required",
            REPRESENTATION_PROOF_REQUIRED,
        )
    documents: dict[str, str | None] = {}
    for field, name in REPRESENTATION_DOCUMENTS:
        value = getattr(data, field).get_secret_value().strip()
        documents[name] = None
        if not value:
            if name in required:
                problems.append((field, *required[name]))
            continue
        problem = representation.document_problem(value)
        if problem == "too_large":
            problems.append((field, "fiscal.document_too_large", DOCUMENT_TOO_LARGE))
        elif problem == "not_pdf" and name == "signed_model":
            problems.append((field, "fiscal.signed_model_not_pdf", SIGNED_MODEL_NOT_PDF))
        elif problem == "not_pdf":
            problems.append((field, "fiscal.document_not_pdf", DOCUMENT_NOT_PDF))
        else:
            documents[name] = value
    if problems:
        raise InvalidPayload(
            str(REPRESENTATION_INCOMPLETE),
            code=problems[0][1],
            fields={field: str(message) for field, _code, message in problems},
        )
    return {
        "taxpayer_tax_id": taxpayer_tax_id,
        "taxpayer_name": taxpayer_name,
        "signer_tax_id": signer_tax_id,
        "signer_name": signer_name,
        "signer_document_type": data.signer_document_type,
        "documents": documents,
    }


@operation(
    "verifactu.representation.submit",
    kind="command",
    permission=CONFIGURE,
    input=RepresentationSubmitIn,
    output=ConfigOut,
    ai={
        "description": "Send the signed representation authorisation (Anexo I of the AEAT's Convenio 17) for ERPlora "
        "to file on the business's behalf: the signed model and a copy of the signer's identity document, plus a "
        "signature sample with a NIE and the proof of representation for a company, each a PDF of 5 MB at most. "
        "A person at ERPlora reviews it; until then it is under review. This Hub keeps none of the documents.",
        "risk": "high",
    },
)
def submit_representation(
    ctx: OperationContext, data: RepresentationSubmitIn
) -> ConfigOut:
    hub_id = config_row().hub_id
    if hub_id is None:
        raise Conflict(str(HUB_UNREGISTERED), code="verifactu.hub_unregistered")
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    payload = _representation_payload(data, *issuer_identity())
    try:
        result = representation.submit(
            hub_id, payload, language=ctx.language or "en"
        )
    except representation.RepresentationRefused as refused:
        raise InvalidPayload(
            refused.message or str(REPRESENTATION_REFUSED),
            code=refused.code,
            fields=refused.fields or None,
        ) from None
    except representation.HubUnknown:
        raise Conflict(
            str(HUB_UNREGISTERED), code="verifactu.hub_unregistered"
        ) from None
    except representation.SaasUnreachable:
        raise saas_unreachable() from None
    # Locked only now: nothing is held while the documents travel.
    config = _config()
    submitted_at = result.submitted_at or timezone.now()
    if config.representation_status != Config.Representation.APPROVED:
        # The account's photo says it too; until then the Hub knows it is under review. An approved one stays in
        # force (and keeps filing) until a person approves the new one.
        config.representation_status = Config.Representation.SUBMITTED
        config.representation_updated_at = submitted_at
        config.representation_reason = ""
    _changed(
        ctx,
        config,
        "representation_submitted",
        {
            "version": result.version,
            "submitted_at": submitted_at,
            "document_type": data.signer_document_type,
            "documents": [name for name, value in payload["documents"].items() if value],
        },
        fields=["representation"],
    )
    return config_out(config, ctx)
