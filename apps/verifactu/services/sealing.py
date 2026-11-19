"""What a record declares and how it is sealed: the invoice's figures checked, its XML built and validated
against the AEAT's schemas, and the record chained under the head of its issuer's chain."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.outbox import record_event

from apps.invoice.models import Invoice
from apps.verifactu import chain, envelope, events, producer, xsd
from apps.verifactu.envelope import AltaData, AnulacionData, ChainLink, InvoiceRef
from apps.verifactu.models import Config, Environment, Event, Record, wait_reason_text
from apps.verifactu.queries.route import route_problem, system_for

from .writes import _actor, _event, _lock_chain

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
NO_WAY_TO_THE_AEAT = _(
    "Nothing was issued: this business files for real with the AEAT and cannot reach it now: %(why)s. Fix it in "
    "VeriFactu → Settings and try again."
)

CENT = Decimal(1)


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


def _fingerprint_of(record: Record) -> str:
    """The fingerprint of a chained record from its own fields: what sealing writes and chain validation checks."""
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
    record.fingerprint = _fingerprint_of(record)
    if record.record_type == Record.Type.ANULACION:
        total = record.invoice.total_amount
    else:
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
    """RechazoPrevio of a correction (the AEAT's «Descripción del servicio web VERI*FACTU», sections 9.1.2 and
    9.1.3): «X» while the AEAT holds no registration of the invoice (every alta of it was rejected); «S» when it holds
    one and what is corrected was a later correction it rejected; «N» for the usual correction of a record it holds."""
    held = Record.objects.filter(
        invoice_id=corrects.invoice_id,
        environment=corrects.environment,
        record_type=Record.Type.ALTA,
        status__in=Record.IN_AEAT,
    ).exists()
    if not held:
        return "X"
    return "S" if corrects.status == Record.Status.REJECTED else "N"


def _refuse_without_a_way(config: Config, environment: str, scope: Scope) -> None:
    """In production nothing is sealed that can never reach the AEAT: 409 with the route's own code, inside the
    transaction of the sale or invoice, so the document is undone and the series gives its number back. Testing never
    refuses."""
    if environment != Environment.PRODUCTION:
        return
    problem = route_problem(config, environment, scope)
    if problem:
        raise Conflict(
            str(NO_WAY_TO_THE_AEAT) % {"why": wait_reason_text(problem)},
            code=f"verifactu.{problem}",
        )


def _seal_alta(  # noqa: PLR0913
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
        _refuse_without_a_way(config, environment, ctx.scope)
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
