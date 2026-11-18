"""The billing records (``verifactu.record.*``): the list, one record and an invoice's, and what can be done
to a record. A record is named by its id or by the number of its invoice (its latest record)."""

from uuid import UUID

from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.invoice.models import Invoice
from apps.verifactu import chain, envelope
from apps.verifactu.models import Record
from apps.verifactu.schemas import (
    ByInvoiceIn,
    ByInvoiceOut,
    Page,
    RecordGetIn,
    RecordListIn,
    RecordOut,
    RecordRowOut,
    RecordSummaryOut,
)

from .country import outside_spain
from .events import event_out
from .reads import VIEW, page
from .route import config_row, waiting_of

RECORD_NOT_FOUND = _("Record not found.")
INVOICE_NOT_FOUND = _("Invoice not found.")
RECORD_EVENTS_SHOWN = 20


def find_record(
    record_id: UUID | None, invoice_number: str | None, *, lock: bool = False
) -> Record:
    """A record by its id, or the latest record of the invoice with that number; ``NotFound`` otherwise."""
    queryset = Record.objects.all()
    if lock:
        queryset = queryset.select_for_update()
    if record_id is not None:
        found = queryset.filter(pk=record_id).first()
    else:
        found = (
            queryset.filter(invoice_number=invoice_number)
            .order_by("-created_at", "-id")
            .first()
        )
    if found is None:
        raise NotFound(str(RECORD_NOT_FOUND))
    return found


def find_invoice(invoice_id: UUID | None, number: str | None) -> Invoice:
    """An issued invoice by its id or its number; ``NotFound`` otherwise."""
    queryset = Invoice.objects.select_related("rectifies", "substitutes")
    if invoice_id is not None:
        found = queryset.filter(pk=invoice_id).first()
    else:
        found = queryset.filter(number=number).order_by("-issued_at", "-id").first()
    if found is None:
        raise NotFound(str(INVOICE_NOT_FOUND))
    return found


def single_envelope(record: Record) -> str:
    """The record as it travels alone (empty until its XML is built)."""
    if not record.xml:
        return ""
    return envelope.submission(
        obligado_name=record.issuer_name,
        obligado_nif=record.issuer_nif,
        registros=[record.xml],
    )


def summary(record: Record) -> RecordSummaryOut:
    return RecordSummaryOut(
        id=record.id,
        invoice_id=record.invoice_id,
        invoice_number=record.invoice_number,
        record_type=record.record_type,
        invoice_type=record.invoice_type,
        sequence=record.sequence,
        environment=record.environment,
        status=record.status,
        fingerprint=record.fingerprint,
        qr_url=record.qr_url,
        qr_svg=chain.qr_svg_data_uri(record.qr_url),
        csv=record.csv,
    )


def _row(record: Record, corrected_by: UUID | None) -> dict:
    return {
        "id": record.id,
        "sequence": record.sequence,
        "record_type": record.record_type,
        "invoice_id": record.invoice_id,
        "invoice_number": record.invoice_number,
        "issue_date": record.issue_date,
        "invoice_type": record.invoice_type,
        "issuer_name": record.issuer_name,
        "issuer_nif": record.issuer_nif,
        "total_amount": record.total_amount,
        "environment": record.environment,
        "status": record.status,
        "correction": record.correction,
        "correction_status": correction_status(record, corrected_by),
        "corrected_by_id": corrected_by,
        "qr_url": record.qr_url,
        "created_at": record.created_at,
    }


CORRECTABLE = (Record.Status.REJECTED, Record.Status.ACCEPTED_WITH_ERRORS)


def correctable(record: Record) -> bool:
    """A registration the AEAT rejected or accepted with errors: what «Correct» acts on (VERIFACTU-F24)."""
    return record.record_type == Record.Type.ALTA and record.status in CORRECTABLE


def can_correct(record: Record) -> bool:
    """A correctable registration not corrected yet (VERIFACTU-F24)."""
    return correctable(record) and not Record.objects.filter(corrects=record).exists()


def corrections_of(record) -> QuerySet:
    """The id of the newest record that corrects ``record`` (a record or an ``OuterRef``), as a one-row query."""
    return (
        Record.objects.filter(corrects=record)
        .order_by("-created_at", "-id")
        .values_list("id", flat=True)[:1]
    )


def with_corrections(queryset: QuerySet) -> QuerySet:
    """Each record with ``corrected_by``, the id of the record that corrects it, in the same SELECT: no query per
    row of a list."""
    return queryset.annotate(corrected_by=Subquery(corrections_of(OuterRef("pk"))))


def correction_status(record: Record, corrected_by: UUID | None) -> str:
    """Where a correctable registration stands: ``pending`` or ``corrected``; ``not_applicable`` for any other."""
    if not correctable(record):
        return "not_applicable"
    return "corrected" if corrected_by else "pending"


def can_cancel(record: Record) -> bool:
    """A registration that is (or will be) in the AEAT and has no live cancellation (VERIFACTU-F30)."""
    return (
        record.record_type == Record.Type.ALTA
        and record.status != Record.Status.REJECTED
        and not Record.objects.filter(cancels=record)
        .exclude(status=Record.Status.REJECTED)
        .exists()
    )


SORTS = {
    "created_at": "created_at",
    "sequence": "sequence",
    "invoice_number": "invoice_number",
    "issue_date": "issue_date",
    "invoice_type": "invoice_type",
    "issuer_name": "issuer_name",
    "total_amount": "total_amount",
    "environment": "environment",
    "status": "status",
}


@operation(
    "verifactu.record.list",
    kind="query",
    permission=VIEW,
    input=RecordListIn,
    output=Page[RecordRowOut],
    expose_api=True,
    ai={
        "description": "List the VeriFactu billing records, the last sealed first: search by invoice number, "
        "#sequence, issuer's name or tax ID; filter by status (pending, sent, accepted, accepted_with_errors, "
        "rejected), record type, invoice type, environment, issue date and total in cents. Each row says whether a "
        "registration the AEAT rejected or accepted with errors is already corrected (correction_status corrected, "
        "corrected_by_id the record that corrects it) or still to correct (pending); correction_status=pending lists "
        "only the ones still to correct, correction_status=corrected only the corrected ones.",
        "asks": {
            "en": (
                "list the VeriFactu registrations sealed in October",
                "which rejected registrations still need correcting?",
            ),
            "es": (
                "lista los registros de VeriFactu de octubre",
                "¿qué registros rechazados quedan por subsanar?",
            ),
        },
    },
)
def list_records(ctx: OperationContext, data: RecordListIn) -> dict:  # noqa: C901
    queryset = with_corrections(Record.objects.all())
    text = (data.search or "").strip()
    if text.startswith("#") and text[1:].isdigit():
        queryset = queryset.filter(sequence=int(text[1:]))
    elif text:
        match = (
            Q(invoice_number__icontains=text)
            | Q(issuer_name__icontains=text)
            | Q(issuer_nif__icontains=text)
        )
        if text.isdigit():
            match |= Q(sequence=int(text))
        queryset = queryset.filter(match)
    for field in ("status", "record_type", "invoice_type", "environment"):
        value = getattr(data, field)
        if value:
            queryset = queryset.filter(**{field: value})
    if data.issue_date_from:
        queryset = queryset.filter(issue_date__gte=data.issue_date_from)
    if data.issue_date_to:
        queryset = queryset.filter(issue_date__lte=data.issue_date_to)
    if data.total_amount_from is not None:
        queryset = queryset.filter(total_amount__gte=data.total_amount_from)
    if data.total_amount_to is not None:
        queryset = queryset.filter(total_amount__lte=data.total_amount_to)
    if data.correction_status:
        queryset = queryset.filter(
            record_type=Record.Type.ALTA,
            status__in=CORRECTABLE,
            corrected_by__isnull=data.correction_status == "pending",
        )
    column = SORTS[data.sort or "created_at"]
    prefix = "-" if data.dir == "desc" else ""
    queryset = queryset.order_by(f"{prefix}{column}", f"{prefix}id")
    return page(
        queryset,
        data.limit,
        data.offset,
        lambda record: _row(record, record.corrected_by),
    )


@operation(
    "verifactu.record.get",
    kind="query",
    permission=VIEW,
    input=RecordGetIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "description": "One VeriFactu record, by its id or by its invoice's number (e.g. TICKET-2026-000012): its "
        "invoice's figures, its chain (sequence, fingerprint, previous one), its QR link, its XML, the AEAT's answer "
        "(CSV, code, message), its attempts and why it is not in the AEAT yet.",
        "asks": {
            "en": (
                "give me the XML and fingerprint of VeriFactu entry 12",
                "why has the AEAT not taken VeriFactu entry 12?",
            ),
            "es": (
                "dame el XML y la huella del registro 12",
                "¿qué respondió Hacienda al registro 12?",
            ),
        },
    },
)
def get_record(ctx: OperationContext, data: RecordGetIn) -> RecordOut:
    record = find_record(data.record_id, data.invoice_number)
    corrected_by = corrections_of(record).first()
    config = config_row()
    # Outside Spain it never goes out: no next attempt, and nothing to send, correct or cancel (each would be refused).
    spanish = not outside_spain(ctx.scope)
    events = record.events.select_related("record").order_by("-created_at", "-id")[
        :RECORD_EVENTS_SHOWN
    ]
    return RecordOut(
        **_row(record, corrected_by),
        operation_date=record.operation_date,
        rectification_kind=record.rectification_kind,
        rectified=record.rectified,
        substituted=record.substituted,
        description=record.description,
        recipient_name=record.recipient_name,
        recipient_tax_id=record.recipient_tax_id,
        recipient_country=record.recipient_country,
        base_amount=record.base_amount,
        tax_amount=record.tax_amount,
        previous_rejection=record.previous_rejection,
        corrects_id=record.corrects_id,
        cancels_id=record.cancels_id,
        previous_fingerprint=record.previous_fingerprint,
        previous_number=record.previous_number,
        generated_at=record.generated_at,
        fingerprint=record.fingerprint,
        qr_svg=chain.qr_svg_data_uri(record.qr_url),
        envelope=single_envelope(record),
        attempts=record.attempts,
        # A refusal of the gateway waits for a change, never on a timer (services.sending._send_chain).
        next_attempt_at=record.next_attempt_at
        if spanish and record.status in Record.UNSENT and record.wait_reason != "refused"
        else None,
        transmitted_at=record.transmitted_at,
        transmission_id=record.transmission_id,
        envelope_digest=record.envelope_digest,
        incident=record.incident,
        csv=record.csv,
        aeat_code=record.aeat_code,
        aeat_message=record.aeat_message,
        waiting=waiting_of(record, config, ctx.scope),
        can_transmit=spanish and record.status in Record.UNSENT,
        can_correct=spanish
        and correction_status(record, corrected_by) == "pending",
        can_cancel=spanish and can_cancel(record),
        events=[event_out(event) for event in events],
    )


@operation(
    "verifactu.record.by_invoice",
    kind="query",
    permission=VIEW,
    input=ByInvoiceIn,
    output=ByInvoiceOut,
    expose_api=True,
    ai={
        "description": "The VeriFactu record of an invoice (by the invoice's id): its QR link and image, its CSV and "
        "its status, for the ticket or the invoice; none when the invoice has no record yet.",
        "asks": {
            "en": (
                "what QR does invoice F-2026-0007 carry?",
                "get me the VeriFactu registration of this invoice",
            ),
            "es": (
                "¿qué QR lleva la factura F-2026-0007?",
                "dame el registro de VeriFactu de esta factura",
            ),
        },
    },
)
def by_invoice(ctx: OperationContext, data: ByInvoiceIn) -> ByInvoiceOut:
    # Outside Spain no record is ever sent: the invoice carries no VeriFactu receipt, as with the app off.
    if outside_spain(ctx.scope):
        return ByInvoiceOut(record=None)
    record = (
        Record.objects.filter(invoice_id=data.invoice_id)
        .order_by("-created_at", "-id")
        .first()
    )
    return ByInvoiceOut(record=summary(record) if record else None)
