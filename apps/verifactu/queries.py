"""Read operations of the verifactu app, and the read helpers ``services.py`` shares.

Every query runs ``READ ONLY`` (``@operation(kind="query")``) and can be followed live (``live.py``). Lists page
(``limit`` ≤ 100) in a stable order with the id as tie-break. A record is named by its id or by the number of
its invoice (its latest record). What keeps a record from leaving is computed when it is read, from the
configuration, the gateway and the chain's AEAT wait, plus the last attempt's failure kept on the record.
"""

import datetime as dt
from functools import reduce
from operator import and_
from uuid import UUID

from django.conf import settings
from django.db.models import Case, Count, Q, QuerySet, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.invoice.models import Invoice, Issuer
from apps.verifactu import certificates, chain, envelope, gateway, producer
from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Environment,
    Event,
    OwnCertificate,
    Record,
    SendControl,
    wait_reason_text,
)
from apps.verifactu.schemas import (
    AeatRecordListIn,
    AeatRecordOut,
    ByInvoiceIn,
    ByInvoiceOut,
    ChainOut,
    ChainStatusOut,
    ComplianceSummaryOut,
    ConfigOut,
    ContingencyListIn,
    ContingencySummaryOut,
    DiagnosticLastOut,
    EventListIn,
    EventOut,
    EventsOut,
    EventsRecentIn,
    IssuerIn,
    NoInput,
    Page,
    QueueRowOut,
    RecordGetIn,
    RecordListIn,
    RecordOut,
    RecordRowOut,
    RecordsByStatusOut,
    RecordSummaryOut,
)

RECORD_NOT_FOUND = _("Record not found.")
INVOICE_NOT_FOUND = _("Invoice not found.")
#: The waits that are a past attempt's failure, kept on the record (the rest are computed when read).
ATTEMPT_FAILURES = ("unreachable", "refused", "unknown", "aeat_fault", "xml_invalid")
#: Days before its expiry from which the own certificate is announced (VERIFACTU-F34).
EXPIRY_WARNING_DAYS = 30
RECORD_EVENTS_SHOWN = 20
VIEW = "verifactu.view_record"


# ── Shared reads ────────────────────────────────────────────────────────────────────────────────


def config_row() -> Config:
    """The configuration; an unsaved default while nothing was ever saved."""
    return Config.objects.filter(singleton=True).first() or Config()


def issuer_identity() -> tuple[str, str]:
    """Invoicing's issuer: (tax ID, legal name), empty without one."""
    row = Issuer.objects.first()
    return (row.tax_id, row.legal_name) if row else ("", "")


def issuer_configured() -> bool:
    row = Issuer.objects.first()
    return bool(row and row.configured)


def production_open() -> bool:
    """Whether this server lets a business go live (VERIFACTU-F08): only the ``prod`` deployment, and only once ERPlora
    opens it there (``VERIFACTU_PRODUCTION_ENABLED``, under Ioan's supervision); ``pre`` always files in testing."""
    return settings.ERPLORA_ENVIRONMENT == "prod" and bool(
        settings.VERIFACTU_PRODUCTION_ENABLED
    )


def own_certificate() -> OwnCertificate | None:
    """The business's own certificate, its sealed material left unread; ``None`` while none is uploaded."""
    return OwnCertificate.objects.defer("sealed_blob").filter(singleton=True).first()


def own_certificate_blob() -> bytes | None:
    """The sealed material of the own certificate (``certificates.material`` opens it); ``None`` without one."""
    blob = (
        OwnCertificate.objects.filter(singleton=True)
        .values_list("sealed_blob", flat=True)
        .first()
    )
    return bytes(blob) if blob is not None else None


def own_certificate_material(config: Config) -> gateway.Certificate | None:
    """What the gateway presents with on the «own» route (``None`` on ERPlora's, or without a certificate);
    ``certificates.CertificateUnreadable`` when this server's key cannot open it."""
    if config.route != Config.Route.OWN:
        return None
    blob = own_certificate_blob()
    return certificates.material(blob) if blob is not None else None


def own_certificate_readable(config: Config) -> bool:
    try:
        own_certificate_material(config)
    except certificates.CertificateUnreadable:
        return False
    return True


def certificate_valid(now: dt.datetime | None = None) -> bool:
    """Whether an own certificate is uploaded and has not expired."""
    now = now or timezone.now()
    return OwnCertificate.objects.filter(singleton=True, expires_at__gt=now).exists()


def route_problem(config: Config, environment: str) -> str:
    """Why the chosen route cannot file in ``environment`` (a wait code), or ``""``: the own route needs its valid
    certificate; in production, ERPlora's route needs the approved authorisation, and either needs the live option of
    the plan (VERIFACTU-F08)."""
    if config.route == Config.Route.OWN:
        if not certificate_valid():
            return "own_certificate_missing"
    elif (
        environment == Environment.PRODUCTION
        and config.representation_status != Config.Representation.APPROVED
    ):
        return "representation_not_approved"
    if environment == Environment.PRODUCTION and not config.live_paid:
        return "live_option_unpaid"
    return ""


def live_problems(config: Config) -> list[str]:
    """Everything that keeps this business from going live now (VERIFACTU-F08), as codes; empty when it can. The
    server's own opening (``production_open``) and Invoicing's issuer are told apart."""
    found = []
    problem = route_problem(config, Environment.PRODUCTION)
    if problem and problem != "live_option_unpaid":
        found.append(problem)
    if not config.live_paid:
        found.append("live_option_unpaid")
    if config.hub_status != Config.HubStatus.ACTIVE:
        found.append("hub_not_active")
    return found


def system_for(config: Config, ctx: OperationContext) -> producer.SystemInfo | None:
    """``SistemaInformatico`` of this installation, or ``None`` while the account has not said everything."""
    return producer.system_info(
        version=producer.running_version(),
        installation=ctx.scope.key,
        multiple_taxpayers=config.multiple_taxpayers,
    )


def blockers(config: Config, environment: str) -> list[str]:
    """What keeps every record of ``environment`` from leaving now, as wait codes."""
    found = []
    if not gateway.configured():
        found.append("gateway_unavailable")
    if config.multiple_taxpayers not in producer.YES_NO:
        found.append("producer_facts_missing")
    problem = route_problem(config, environment)
    if problem:
        found.append(problem)
    elif not own_certificate_readable(config):
        found.append("own_certificate_unreadable")
    return found


def wait(code: str, detail: str = "", at: str = "") -> dict:
    return {"code": code, "message": wait_reason_text(code, detail, at)}


def _local_time(moment: dt.datetime) -> str:
    return timezone.localtime(moment).strftime("%H:%M:%S")


def waiting_of(record: Record, config: Config) -> list[dict]:
    """Why ``record`` is not in the AEAT yet; empty when it is, or when the AEAT rejected it."""
    if record.status not in Record.UNSENT:
        return []
    reasons = [wait(code) for code in blockers(config, record.environment)]
    control = SendControl.objects.filter(
        issuer_nif=record.issuer_nif, environment=record.environment
    ).first()
    if control and control.next_send_at and control.next_send_at > timezone.now():
        reasons.append(wait("aeat_wait", at=_local_time(control.next_send_at)))
    if record.wait_reason in ATTEMPT_FAILURES:
        reasons.append(wait(record.wait_reason, record.wait_detail))
    return reasons


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


def _row(record: Record) -> dict:
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
        "qr_url": record.qr_url,
        "created_at": record.created_at,
    }


def event_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        created_at=event.created_at,
        kind=event.kind,
        severity=event.severity,
        message=event.message(),
        record_id=event.record_id,
        invoice_number=event.record.invoice_number if event.record_id else "",
    )


def can_correct(record: Record) -> bool:
    """A registration the AEAT rejected or accepted with errors, not corrected yet (VERIFACTU-F24)."""
    return (
        record.record_type == Record.Type.ALTA
        and record.status
        in (Record.Status.REJECTED, Record.Status.ACCEPTED_WITH_ERRORS)
        and not Record.objects.filter(corrects=record).exists()
    )


def can_cancel(record: Record) -> bool:
    """A registration that is (or will be) in the AEAT and has no live cancellation (VERIFACTU-F30)."""
    return (
        record.record_type == Record.Type.ALTA
        and record.status != Record.Status.REJECTED
        and not Record.objects.filter(cancels=record)
        .exclude(status=Record.Status.REJECTED)
        .exists()
    )


def config_out(config: Config, ctx: OperationContext) -> ConfigOut:
    nif, name = issuer_identity()
    system = system_for(config, ctx)
    now = timezone.now()
    certificate = own_certificate()
    expires = certificate.expires_at if certificate else None
    return ConfigOut(
        environment=config.environment,
        route=config.route,
        production_since=config.production_since,
        production_open=production_open(),
        can_go_back=not Record.objects.filter(
            environment=Environment.PRODUCTION
        ).exists(),
        gateway_configured=gateway.configured(),
        issuer_nif=nif,
        issuer_name=name,
        producer={
            "name": producer.MANUFACTURER["NombreRazon"],
            "nif": producer.MANUFACTURER["NIF"],
            "system_name": producer.MANUFACTURER["NombreSistemaInformatico"],
            "system_id": producer.MANUFACTURER["IdSistemaInformatico"],
            "version": producer.running_version(),
            "installation": ctx.scope.key,
            "only_verifactu": producer.MANUFACTURER["TipoUsoPosibleSoloVerifactu"],
            "multi_ot": producer.MANUFACTURER["TipoUsoPosibleMultiOT"],
            "multiple_ot": system.multiple_ot if system else "",
        },
        declaration_version=producer.DECLARATION_VERSION,
        declaration_url=producer.declaration_url(),
        account_url=settings.SAAS_URL.rstrip("/"),
        own_certificate={
            "loaded": certificate is not None,
            "holder": certificate.holder if certificate else "",
            "holder_tax_id": certificate.holder_tax_id if certificate else "",
            "kind": certificate.kind if certificate else "",
            "uploaded_at": certificate.uploaded_at if certificate else None,
            "expires_at": expires,
            "expires_in_days": (expires - now).days if expires else None,
        },
        representation={
            "status": config.representation_status,
            "updated_at": config.representation_updated_at,
            "reason": config.representation_reason,
        },
        synced_at=config.synced_at,
        route_ready=not route_problem(config, config.environment),
        reasons=[wait(code) for code in blockers(config, config.environment)],
        live_blockers=[wait(code) for code in live_problems(config)],
    )


def page(queryset: QuerySet, limit: int, offset: int, convert) -> dict:
    return {
        "rows": [convert(item) for item in queryset[offset : offset + limit]],
        "total": queryset.count(),
        "limit": limit,
        "offset": offset,
    }


def _words(text: str | None) -> list[str]:
    return [word for word in (text or "").split() if word]


# ── Operations ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "verifactu.config.get",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "VeriFactu's configuration: the environment (testing or production), the sending route (ERPlora "
        "files for the business, or its own certificate), the own certificate uploaded here (holder and expiry, never "
        "its material), the signed authorisation's state as the ERPlora account says, the software producer's details, the responsible declaration, and what keeps "
        "records from leaving now."
    },
)
def get_config(ctx: OperationContext, data: NoInput) -> ConfigOut:
    return config_out(config_row(), ctx)


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
        "rejected), record type, invoice type, environment, issue date and total in cents."
    },
)
def list_records(ctx: OperationContext, data: RecordListIn) -> dict:
    queryset = Record.objects.all()
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
    column = SORTS[data.sort or "created_at"]
    prefix = "-" if data.dir == "desc" else ""
    queryset = queryset.order_by(f"{prefix}{column}", f"{prefix}id")
    return page(queryset, data.limit, data.offset, _row)


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
        "(CSV, code, message), its attempts and why it is not in the AEAT yet."
    },
)
def get_record(ctx: OperationContext, data: RecordGetIn) -> RecordOut:
    record = find_record(data.record_id, data.invoice_number)
    config = config_row()
    events = record.events.select_related("record").order_by("-created_at", "-id")[
        :RECORD_EVENTS_SHOWN
    ]
    return RecordOut(
        **_row(record),
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
        next_attempt_at=record.next_attempt_at
        if record.status in Record.UNSENT
        else None,
        transmitted_at=record.transmitted_at,
        transmission_id=record.transmission_id,
        envelope_digest=record.envelope_digest,
        incident=record.incident,
        csv=record.csv,
        aeat_code=record.aeat_code,
        aeat_message=record.aeat_message,
        waiting=waiting_of(record, config),
        can_transmit=record.status in Record.UNSENT,
        can_correct=can_correct(record),
        can_cancel=can_cancel(record),
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
        "its status, for the ticket or the invoice; none when the invoice has no record yet."
    },
)
def by_invoice(ctx: OperationContext, data: ByInvoiceIn) -> ByInvoiceOut:
    record = (
        Record.objects.filter(invoice_id=data.invoice_id)
        .order_by("-created_at", "-id")
        .first()
    )
    return ByInvoiceOut(record=summary(record) if record else None)


def _queue_row(record: Record) -> dict:
    return {
        "id": record.id,
        "invoice_number": record.invoice_number,
        "record_type": record.record_type,
        "environment": record.environment,
        "attempts": record.attempts,
        "status": record.status,
        "next_attempt_at": record.next_attempt_at,
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
        "answer), in the order they go out, with their attempts, next attempt and last error."
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


@operation(
    "verifactu.event.list",
    kind="query",
    permission=VIEW,
    input=EventListIn,
    output=Page[EventOut],
    ai={
        "description": "VeriFactu's audit events, newest first, each message in the reader's language: search by the "
        "words shown (in Spanish or English), filter by type, severity and day."
    },
)
def list_events(ctx: OperationContext, data: EventListIn) -> dict:
    queryset = Event.objects.select_related("record")
    words = _words(data.search)
    if words:
        queryset = queryset.filter(
            reduce(and_, (Q(search_text__icontains=word.lower()) for word in words))
        )
    if data.kind:
        queryset = queryset.filter(kind=data.kind)
    if data.severity:
        queryset = queryset.filter(severity=data.severity)
    if data.date_from:
        queryset = queryset.filter(created_at__date__gte=data.date_from)
    if data.date_to:
        queryset = queryset.filter(created_at__date__lte=data.date_to)
    prefix = "-" if data.dir == "desc" else ""
    column = data.sort or "created_at"
    # Severity sorts by weight (debug → critical ascending), not alphabetically.
    if column == "severity":
        weight = Case(*(When(severity=code, then=index) for index, code in enumerate(Event.Severity.values)))
        queryset = queryset.annotate(weight=weight).order_by(f"{prefix}weight", "-created_at", "-id")
    else:
        queryset = queryset.order_by(f"{prefix}{column}", f"{prefix}id")
    return page(queryset, data.limit, data.offset, event_out)


@operation(
    "verifactu.stats.compliance_summary",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ComplianceSummaryOut,
    expose_api=True,
    ai={
        "description": "How many VeriFactu records are not in the AEAT yet, rejected, accepted and in total: whether "
        "everything reached the AEAT."
    },
)
def compliance_summary(ctx: OperationContext, data: NoInput) -> ComplianceSummaryOut:
    counts = dict(Record.objects.values_list("status").annotate(total=Count("id")))
    unsent = sum(counts.get(status, 0) for status in Record.UNSENT)
    rejected = counts.get(Record.Status.REJECTED, 0)
    return ComplianceSummaryOut(
        unsent_count=unsent,
        pending_count=unsent + rejected,
        rejected_count=rejected,
        accepted_count=sum(counts.get(status, 0) for status in Record.IN_AEAT),
        total=sum(counts.values()),
        environment=config_row().environment,
    )


@operation(
    "verifactu.stats.records_by_status",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=RecordsByStatusOut,
    ai={"description": "How many VeriFactu records are in each status."},
)
def records_by_status(ctx: OperationContext, data: NoInput) -> RecordsByStatusOut:
    counts = dict(Record.objects.values_list("status").annotate(total=Count("id")))
    return RecordsByStatusOut(
        rows=[
            {"status": status, "label": str(label), "total": counts.get(status, 0)}
            for status, label in Record.Status.choices
        ]
    )


@operation(
    "verifactu.stats.contingency_summary",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ContingencySummaryOut,
    ai={
        "description": "The queue in short: how many records wait, how many are due now, and whether it is failing."
    },
)
def contingency_summary(ctx: OperationContext, data: NoInput) -> ContingencySummaryOut:
    queued = Record.objects.filter(status__in=Record.UNSENT)
    count = queued.count()
    failing = queued.filter(attempts__gt=0).exists()
    return ContingencySummaryOut(
        queued_count=count,
        overdue_count=queued.filter(next_attempt_at__lte=timezone.now()).count(),
        severity="ok" if count == 0 else ("danger" if failing else "warning"),
    )


@operation(
    "verifactu.stats.events_recent",
    kind="query",
    permission=VIEW,
    input=EventsRecentIn,
    output=EventsOut,
    ai={"description": "The latest VeriFactu audit events."},
)
def events_recent(ctx: OperationContext, data: EventsRecentIn) -> EventsOut:
    events = Event.objects.select_related("record").order_by("-created_at", "-id")[
        : data.limit
    ]
    return EventsOut(rows=[event_out(event) for event in events])


def aeat_row(row: AeatRecord) -> dict:
    return {
        "id": row.id,
        "issuer_nif": row.issuer_nif,
        "environment": row.environment,
        "invoice_number": row.invoice_number,
        "issue_date": row.issue_date,
        "fingerprint": row.fingerprint,
        "state": row.state,
        "csv": row.csv,
        "generated_on": row.generated_on,
        "queried_at": row.queried_at,
    }


@operation(
    "verifactu.aeat_record.list",
    kind="query",
    permission=VIEW,
    input=AeatRecordListIn,
    output=Page[AeatRecordOut],
    ai={
        "description": "The last photo of what the AEAT holds (from the last «Query AEAT»), the newest first."
    },
)
def list_aeat_records(ctx: OperationContext, data: AeatRecordListIn) -> dict:
    return page(
        AeatRecord.objects.order_by("-generated_on", "-id"),
        data.limit,
        data.offset,
        aeat_row,
    )


def chain_out(head: Chain) -> ChainOut:
    return ChainOut(
        issuer_nif=head.issuer_nif,
        environment=head.environment,
        sequence=head.sequence,
        last_number=head.last_number,
        last_issue_date=head.last_issue_date,
        last_fingerprint=head.last_fingerprint,
        anchored_at=head.anchored_at,
        anchor_source=head.anchor_source,
        validated_at=head.validated_at,
        valid=head.validation_valid,
        total=head.validation_total,
        first_invalid_sequence=head.validation_first_invalid,
    )


@operation(
    "verifactu.chain.status",
    kind="query",
    permission=VIEW,
    input=IssuerIn,
    output=ChainStatusOut,
    ai={
        "description": "The VeriFactu chains of an issuer (Invoicing's issuer by default): last sequence, last "
        "fingerprint, anchors and the last validation's verdict."
    },
)
def chain_status(ctx: OperationContext, data: IssuerIn) -> ChainStatusOut:
    nif = data.issuer_nif or issuer_identity()[0]
    chains = Chain.objects.filter(issuer_nif=nif).order_by("environment")
    return ChainStatusOut(
        issuer_nif=nif,
        environment=config_row().environment,
        chains=[chain_out(head) for head in chains],
    )


@operation(
    "verifactu.diagnostic.last",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=DiagnosticLastOut,
    ai={"description": "The result of the last VeriFactu connection test, or none."},
)
def last_diagnostic(ctx: OperationContext, data: NoInput) -> DiagnosticLastOut:
    event = (
        Event.objects.filter(kind=Event.Kind.CONNECTION_TEST)
        .order_by("-created_at", "-id")
        .first()
    )
    if event is None or "result" not in event.params:
        return DiagnosticLastOut(result=None)
    result = dict(event.params["result"])
    # The reasons in the reader's language, from their codes.
    result["reasons"] = [
        wait(item["code"], item.get("detail", "")) for item in result.get("reasons", [])
    ]
    return DiagnosticLastOut(result=result)

