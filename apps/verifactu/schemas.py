"""Input and output schemas of the verifactu app's operations (OpenAPI, live params, 422 per field, and the JSON
Schema of the assistant's tools: every field says what it is).

Made for voice: a record is named by its id or by the **number of its invoice** (``TICKET-2026-000012``: its
latest record); an issuer by its tax ID (by default, Invoicing's issuer). Money is whole cents with a sign; dates
are ISO ``YYYY-MM-DD``.
"""

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    BeforeValidator,
    ConfigDict,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from apps.verifactu import chain
from apps.verifactu.models import Config, Event, OwnCertificate, Record

T = TypeVar("T")

WHICH_RECORD = _("Say which record: its id or the number of its invoice.")
WHICH_INVOICE = _("Say which invoice: its id or its number.")
FINGERPRINT_INVALID = _("The fingerprint must be 64 hexadecimal characters.")
CERTIFICATE_TOO_LARGE = _("The certificate file has to be 1 MB at most.")
#: The largest .p12/.pfx taken (as the screen says, ConfigPage): a larger file is no certificate.
MAX_CERTIFICATE_BYTES = 1024 * 1024
RECORD_ID = "Id of the record."
INVOICE_NUMBER = "Number of the invoice (e.g. TICKET-2026-000012): its latest record."
ISSUER_NIF = "Tax ID of the issuer (Invoicing's issuer when left out)."
SEARCH = "Words to look for."

Direction = Literal["asc", "desc"]
StatusCode = Literal[*Record.Status.values]
TypeCode = Literal[*Record.Type.values]
EnvironmentCode = Literal[*Config.Environment.values]
RouteCode = Literal[*Config.Route.values]
InvoiceTypeCode = Literal["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"]
KindCode = Literal[*Event.Kind.values]
SeverityCode = Literal[*Event.Severity.values]
RepresentationCode = Literal[*Config.Representation.values]


def _text(max_length: int, *, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


OptionalText = lambda length: Annotated[
    _text(length) | None, BeforeValidator(_blank_to_none)
]  # noqa: E731


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


class NoInput(Schema):
    """No parameters."""


# ── Naming things ───────────────────────────────────────────────────────────────────────────────


class RecordRefIn(Schema):
    """A record, by its id or by the number of its invoice (its latest record)."""

    record_id: UUID | None = Field(None, description=RECORD_ID)
    invoice_number: OptionalText(60) = Field(None, description=INVOICE_NUMBER)

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.record_id is None and not self.invoice_number:
            raise ValueError(str(WHICH_RECORD))
        return self


class IssuerIn(Schema):
    issuer_nif: OptionalText(32) = Field(None, description=ISSUER_NIF)


# ── Outputs ─────────────────────────────────────────────────────────────────────────────────────


class RecordRowOut(Schema):
    id: UUID = Field(description="Id of the record.")
    sequence: int = Field(description="Its number in its chain.")
    record_type: TypeCode = Field(
        description="alta (registration) or anulacion (cancellation)."
    )
    invoice_id: UUID = Field(description="Id of its invoice.")
    invoice_number: str = Field(description="Number of its invoice.")
    issue_date: dt.date = Field(description="Issue date of its invoice.")
    invoice_type: str = Field(
        description="F1, F2, F3 or R1–R5; empty in a cancellation."
    )
    issuer_name: str = Field(description="Issuer's legal name.")
    issuer_nif: str = Field(description="Issuer's tax ID.")
    total_amount: int | None = Field(
        description="Total in cents (none in a cancellation)."
    )
    environment: EnvironmentCode = Field(
        description="testing or production: the AEAT it goes to."
    )
    status: StatusCode = Field(
        description="pending, sent, accepted, accepted_with_errors or rejected."
    )
    correction: bool = Field(description="Whether it is a correction (subsanación).")
    qr_url: str = Field(description="The AEAT's verification link (its QR).")
    created_at: dt.datetime = Field(description="When it was sealed.")


class EventOut(Schema):
    id: UUID = Field(description="Id of the event.")
    created_at: dt.datetime = Field(description="When it happened.")
    kind: KindCode = Field(description="What happened.")
    severity: SeverityCode = Field(
        description="debug, info, warning, error or critical."
    )
    message: str = Field(description="What happened, in the reader's language.")
    record_id: UUID | None = Field(description="The record it is about, if any.")
    invoice_number: str = Field(description="Number of that record's invoice, if any.")


class WaitOut(Schema):
    code: str = Field(description="Why it waits, as a code.")
    message: str = Field(description="Why it waits, in the reader's language.")


class RecordOut(RecordRowOut):
    operation_date: dt.date | None = Field(
        description="Operation date when it is not the issue date."
    )
    rectification_kind: str = Field(
        description="I (by differences) or S in a rectifying invoice."
    )
    rectified: list[dict] = Field(
        description="Invoices it rectifies: issuer_nif, number, issue_date."
    )
    substituted: list[dict] = Field(
        description="Tickets it replaces: issuer_nif, number, issue_date."
    )
    description: str = Field(description="DescripcionOperacion.")
    recipient_name: str = Field(description="Customer's name.")
    recipient_tax_id: str = Field(description="Customer's tax ID.")
    recipient_country: str = Field(description="Customer's country (ISO 3166-1).")
    base_amount: int | None = Field(description="Taxable base in cents.")
    tax_amount: int | None = Field(description="Tax in cents.")
    previous_rejection: str = Field(
        description="RechazoPrevio: X when the AEAT holds no registration of the invoice, S when it holds one and "
        "a later correction was rejected (or an earlier cancellation), N for the usual correction; empty otherwise."
    )
    corrects_id: UUID | None = Field(description="The record this correction corrects.")
    cancels_id: UUID | None = Field(
        description="The registration this cancellation cancels."
    )
    previous_fingerprint: str = Field(
        description="The previous record's fingerprint (empty: first of the chain)."
    )
    previous_number: str = Field(description="The previous record's invoice number.")
    generated_at: str = Field(
        description="FechaHoraHusoGenRegistro, as it entered the fingerprint."
    )
    fingerprint: str = Field(description="Its SHA-256 fingerprint.")
    qr_svg: str = Field(description="The QR as an SVG data URI.")
    envelope: str = Field(
        description="The XML as it travels alone (empty until it can be built)."
    )
    attempts: int = Field(description="Failed sends so far.")
    next_attempt_at: dt.datetime | None = Field(
        description="Next send attempt, while it is in the queue."
    )
    transmitted_at: dt.datetime | None = Field(description="When it was last sent.")
    transmission_id: UUID | None = Field(
        description="Id of the submission that carried it."
    )
    envelope_digest: str = Field(description="SHA-256 of that submission's envelope.")
    incident: bool = Field(
        description="Whether it went out declared as late (Incidencia = S)."
    )
    csv: str = Field(description="The AEAT's CSV.")
    aeat_code: str = Field(description="The AEAT's response code.")
    aeat_message: str = Field(description="The AEAT's response message.")
    waiting: list[WaitOut] = Field(
        description="Why it is not in the AEAT yet (empty when it is, or rejected)."
    )
    can_transmit: bool = Field(description="Whether «Send now» applies.")
    can_correct: bool = Field(description="Whether «Correct» (subsanar) applies.")
    can_cancel: bool = Field(description="Whether «Cancel record» applies.")
    events: list[EventOut] = Field(description="Its latest audit events.")


class RecordSummaryOut(Schema):
    id: UUID = Field(description="Id of the record.")
    invoice_id: UUID = Field(description="Id of its invoice.")
    invoice_number: str = Field(description="Number of its invoice.")
    record_type: TypeCode = Field(description="alta or anulacion.")
    invoice_type: str = Field(description="F1…R5.")
    sequence: int = Field(description="Its number in its chain.")
    environment: EnvironmentCode = Field(description="testing or production.")
    status: StatusCode = Field(description="Its status.")
    fingerprint: str = Field(description="Its fingerprint.")
    qr_url: str = Field(description="The AEAT's verification link.")
    qr_svg: str = Field(description="The QR as an SVG data URI.")
    csv: str = Field(description="The AEAT's CSV, once accepted.")


class RecordCreateOut(Schema):
    record: RecordSummaryOut = Field(description="The record.")
    already: bool = Field(
        description="True when it existed already (nothing new was sealed)."
    )


class ByInvoiceOut(Schema):
    record: RecordSummaryOut | None = Field(
        description="The invoice's latest record, or none."
    )


class QueueRowOut(Schema):
    id: UUID = Field(description="Id of the record.")
    invoice_number: str = Field(description="Number of its invoice.")
    record_type: TypeCode = Field(description="alta or anulacion.")
    environment: EnvironmentCode = Field(description="testing or production.")
    attempts: int = Field(description="Failed sends so far.")
    status: StatusCode = Field(description="pending or sent.")
    next_attempt_at: dt.datetime | None = Field(
        description="Next attempt; none while a refusal of the gateway waits for a change."
    )
    last_error: str = Field(
        description="Why the last attempt did not go, in the reader's language."
    )
    created_at: dt.datetime = Field(description="When it was sealed.")


class TransmitOut(Schema):
    chains: int = Field(description="Chains that were sent.")
    sent: int = Field(description="Records sent.")
    accepted: int = Field(description="Records the AEAT accepted.")
    accepted_with_errors: int = Field(
        description="Records the AEAT accepted with errors."
    )
    rejected: int = Field(description="Records the AEAT rejected.")
    waiting: int = Field(description="Records still waiting.")
    reason: str = Field(
        description="Why nothing could be sent, as a code (empty when it could)."
    )
    message: str = Field(description="That reason in the reader's language.")


class ComplianceSummaryOut(Schema):
    unsent_count: int = Field(
        description="Records not in the AEAT yet (pending or sent without answer)."
    )
    pending_count: int = Field(
        description="Records not accepted: unsent plus rejected."
    )
    rejected_count: int = Field(description="Records the AEAT rejected.")
    accepted_count: int = Field(
        description="Records in the AEAT (accepted, with or without errors)."
    )
    total: int = Field(description="Every record.")
    environment: EnvironmentCode = Field(description="The environment now.")


class StatusCountOut(Schema):
    status: StatusCode = Field(description="A status.")
    label: str = Field(description="Its name in the reader's language.")
    total: int = Field(description="Records in it.")


class RecordsByStatusOut(Schema):
    rows: list[StatusCountOut] = Field(description="One row per status.")


class ContingencySummaryOut(Schema):
    queued_count: int = Field(description="Records in the queue.")
    overdue_count: int = Field(description="Records whose attempt is due now.")
    severity: Literal["ok", "warning", "danger"] = Field(
        description="ok (empty), warning or danger (failing)."
    )


class EventsRecentIn(Schema):
    limit: int = Field(10, ge=1, le=20, description="How many, 1 to 20.")


class EventsOut(Schema):
    rows: list[EventOut] = Field(description="The latest events.")


class AeatRecordOut(Schema):
    id: UUID = Field(description="Id of the row.")
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="testing or production.")
    invoice_number: str = Field(description="Invoice number.")
    issue_date: dt.date | None = Field(description="Issue date.")
    fingerprint: str = Field(description="Fingerprint the AEAT holds.")
    state: str = Field(description="The AEAT's state of it.")
    csv: str = Field(description="CSV, if the AEAT gave it.")
    generated_on: dt.datetime | None = Field(description="When it was generated.")
    queried_at: dt.datetime = Field(description="When the AEAT was asked.")


class ChainOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="testing or production.")
    sequence: int = Field(description="Last sequence given.")
    last_number: str = Field(
        description="Invoice of the last record (or of the anchor)."
    )
    last_issue_date: dt.date | None = Field(description="Its date.")
    last_fingerprint: str = Field(description="Its fingerprint.")
    anchored_at: dt.datetime | None = Field(
        description="When the chain was last anchored (recovery, migration)."
    )
    anchor_source: str = Field(description="aeat or manual.")
    validated_at: dt.datetime | None = Field(description="When it was last validated.")
    valid: bool | None = Field(
        description="The last verdict: intact, broken, or not validated."
    )
    total: int = Field(description="Records the last validation checked.")
    first_invalid_sequence: int | None = Field(description="Where it broke, if it did.")


class ChainStatusOut(Schema):
    issuer_nif: str = Field(
        description="The issuer asked for (Invoicing's by default)."
    )
    environment: EnvironmentCode = Field(description="The environment now.")
    chains: list[ChainOut] = Field(description="That issuer's chains.")


class DiagnosticOut(Schema):
    ran_at: dt.datetime = Field(description="When it ran.")
    environment: EnvironmentCode = Field(description="The environment tested.")
    route: RouteCode = Field(description="The route tested.")
    issuer_ready: bool = Field(description="Invoicing's issuer is set.")
    route_ready: bool = Field(description="The route can file in this environment.")
    gateway_configured: bool = Field(description="This server has ERPlora's gateway.")
    gateway_ready: bool | None = Field(
        description="The gateway's answer: it can present now (none: not asked)."
    )
    gateway_detail: str = Field(description="What the gateway said.")
    can_send: bool = Field(description="Everything is ready to send.")
    reasons: list[WaitOut] = Field(description="What is missing.")


class DiagnosticLastOut(Schema):
    result: DiagnosticOut | None = Field(description="The last test, or none.")


class ProducerOut(Schema):
    name: str = Field(description="NombreRazon of the producer.")
    nif: str = Field(description="NIF of the producer.")
    system_name: str = Field(description="NombreSistemaInformatico.")
    system_id: str = Field(description="IdSistemaInformatico.")
    version: str = Field(description="Version installed.")
    installation: str = Field(description="NumeroInstalacion.")
    only_verifactu: str = Field(description="TipoUsoPosibleSoloVerifactu.")
    multi_ot: str = Field(description="TipoUsoPosibleMultiOT.")
    multiple_ot: str = Field(
        description="IndicadorMultiplesOT (always S: ERPlora serves several taxpayers)."
    )


class CertificateOut(Schema):
    loaded: bool = Field(description="An own certificate is loaded in this Hub.")
    holder: str = Field(description="Its holder.")
    holder_tax_id: str = Field(description="Its holder's tax ID.")
    kind: Literal["", *OwnCertificate.Kind.values] = Field(
        description="seal, representative, personal or unknown; empty without one."
    )
    uploaded_at: dt.datetime | None = Field(description="When it was uploaded.")
    expires_at: dt.datetime | None = Field(description="When it expires.")
    expires_in_days: int | None = Field(description="Days left (negative: expired).")


DocumentName = Literal[
    "signed_model", "id_copy", "signature_sample", "representation_proof"
]


class RepresentationSubmissionOut(Schema):
    """The last authorisation sent from this Hub: what was sent, never its content."""

    version: int = Field(description="Its number at ERPlora.")
    submitted_at: dt.datetime | None = Field(description="When ERPlora received it.")
    document_type: Literal["dni", "nie"] = Field(
        description="The signer's identity document: dni or nie."
    )
    documents: list[DocumentName] = Field(
        description="The documents sent: signed_model, id_copy, signature_sample, representation_proof."
    )


class RepresentationStepOut(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    at: dt.datetime = Field(description="When it happened.")
    version: int | None = Field(description="The authorisation's number, when sent from here.")
    reason: str = Field(description="The reviewer's note.")


class RepresentationOut(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    updated_at: dt.datetime | None = Field(description="When it last changed.")
    reason: str = Field(description="The reviewer's note.")
    linked: bool = Field(
        False,
        description="ERPlora's account has linked this business: the authorisation can be sent from here.",
    )
    company: bool = Field(
        False,
        description="Invoicing's issuer is a company: who signs for it and the proof of representation are asked.",
    )
    submission: RepresentationSubmissionOut | None = Field(
        None, description="The last authorisation sent from this Hub."
    )
    history: list[RepresentationStepOut] = Field(
        default_factory=list, description="Its steps, newest first."
    )


class ConfigOut(Schema):
    environment: EnvironmentCode = Field(description="testing or production.")
    route: RouteCode = Field(
        description="erplora (ERPlora files for you) or own (your certificate)."
    )
    production_since: dt.datetime | None = Field(description="When it went live.")
    production_open: bool = Field(description="This server lets a business go live.")
    can_go_back: bool = Field(
        description="It can go back to testing (no production record yet)."
    )
    gateway_configured: bool = Field(description="This server has ERPlora's gateway.")
    issuer_nif: str = Field(description="Invoicing's issuer tax ID.")
    issuer_name: str = Field(description="Invoicing's issuer legal name.")
    producer: ProducerOut = Field(description="SistemaInformatico.")
    declaration_version: str = Field(
        description="Version of the responsible declaration."
    )
    declaration_url: str = Field(description="Where to read it.")
    account_url: str = Field(
        description="The ERPlora account, where the signed authorisation is managed."
    )
    own_certificate: CertificateOut = Field(
        description="The own certificate uploaded in this Hub (never its material)."
    )
    representation: RepresentationOut = Field(
        description="The signed authorisation, as the account says."
    )
    synced_at: dt.datetime | None = Field(
        description="When the account last sent its data."
    )
    route_ready: bool = Field(description="The route can file in this environment.")
    route_ready_for_production: bool = Field(
        description="The route could carry the records to the AEAT of production: ERPlora's with the signed "
        "authorisation approved, or the business's own valid certificate (what the business has to do, whatever "
        "this server lacks)."
    )
    reasons: list[WaitOut] = Field(description="What keeps records from leaving now.")
    issue_blocker: WaitOut | None = Field(
        description="Why new sales and invoices are refused now (production without a way to the AEAT); "
        "none when they are not."
    )
    live_blockers: list[WaitOut] = Field(
        description="What keeps the business from going live now (empty when it can)."
    )


class ChainValidationOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="The chain's environment.")
    valid: bool = Field(description="Every fingerprint recomputes and chains.")
    total: int = Field(description="Records checked.")
    first_invalid_sequence: int | None = Field(description="Where it breaks.")


class AeatQueryOut(Schema):
    count: int = Field(description="Records the AEAT returned.")
    rows: list[AeatRecordOut] = Field(description="Those records.")


class RecoveryOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="The chain's environment.")
    sequence: int = Field(
        description="The chain's last sequence (the next record takes the following one)."
    )
    invoice_number: str = Field(description="The invoice the chain continues after.")
    fingerprint: str = Field(description="The fingerprint the next record chains to.")
    found: int = Field(description="Records the AEAT returned (0 for a manual anchor).")


class TestInvoiceOut(Schema):
    invoice_id: UUID = Field(description="Id of the test invoice.")
    number: str = Field(description="Its number.")
    record: RecordSummaryOut = Field(description="Its record.")


class ConfigSyncOut(Schema):
    applied: bool = Field(description="False when an equal or newer version was kept.")
    version: int | None = Field(description="The version kept.")


# ── Inputs ──────────────────────────────────────────────────────────────────────────────────────


class RecordListIn(PageIn):
    """The records, the last sealed first unless sorted otherwise."""

    search: OptionalText(120) = Field(
        None, description=SEARCH + " Invoice number, sequence, issuer's name or tax ID."
    )
    status: StatusCode | None = Field(None, description="Only this status.")
    record_type: TypeCode | None = Field(
        None, description="Only alta or only anulacion."
    )
    invoice_type: InvoiceTypeCode | None = Field(
        None, description="Only this invoice type."
    )
    environment: EnvironmentCode | None = Field(
        None, description="Only testing or only production."
    )
    issue_date_from: dt.date | None = Field(
        None, description="Invoices issued on this day or later."
    )
    issue_date_to: dt.date | None = Field(
        None, description="Invoices issued on this day or earlier."
    )
    total_amount_from: int | None = Field(
        None, description="Total of at least this many cents."
    )
    total_amount_to: int | None = Field(
        None, description="Total of at most this many cents."
    )
    sort: (
        Literal[
            "created_at",
            "sequence",
            "invoice_number",
            "issue_date",
            "invoice_type",
            "issuer_name",
            "total_amount",
            "environment",
            "status",
        ]
        | None
    ) = Field(None, description="Column to sort by (the last sealed first by default).")
    dir: Direction = Field("desc", description="asc or desc.")


class RecordGetIn(RecordRefIn):
    """A record with everything: its invoice, its chain, its QR, its XML, its answer and why it waits."""


class ByInvoiceIn(Schema):
    invoice_id: UUID = Field(description="Id of the invoice.")


class ContingencyListIn(PageIn):
    search: OptionalText(120) = Field(
        None, description=SEARCH + " Invoice number or the last error."
    )
    environment: EnvironmentCode | None = Field(
        None, description="Only testing or only production."
    )
    sort: Literal["next_attempt_at", "invoice_number", "attempts", "status", "created_at"] | None = Field(
        None, description="Column to sort by (the order they go out by default)."
    )
    dir: Direction = Field("asc", description="asc or desc.")


class EventListIn(PageIn):
    search: OptionalText(120) = Field(
        None, description=SEARCH + " In the type or the message, in Spanish or English."
    )
    kind: KindCode | None = Field(None, description="Only this type.")
    severity: SeverityCode | None = Field(None, description="Only this severity.")
    date_from: dt.date | None = Field(None, description="On this day or later.")
    date_to: dt.date | None = Field(None, description="On this day or earlier.")
    sort: Literal["created_at", "kind", "severity"] | None = Field(
        None, description="Column to sort by (the newest first by default)."
    )
    dir: Direction = Field("desc", description="asc or desc.")


#: How the AEAT's query names the state of a record it holds (``EstadoRegistro`` of RespuestaConsultaLR.xsd).
AeatStateCode = Literal["Correcto", "AceptadoConErrores", "Anulado"]


class AeatRecordListIn(PageIn):
    """The last photo of the AEAT, the last generated first unless sorted otherwise."""

    search: OptionalText(120) = Field(
        None, description=SEARCH + " Invoice number, fingerprint or CSV."
    )
    state: AeatStateCode | None = Field(None, description="Only this state at the AEAT.")
    issue_date_from: dt.date | None = Field(
        None, description="Invoices issued on this day or later."
    )
    issue_date_to: dt.date | None = Field(
        None, description="Invoices issued on this day or earlier."
    )
    sort: Literal["generated_on", "invoice_number", "issue_date", "fingerprint", "state", "csv", "queried_at"] | None = Field(
        None, description="Column to sort by (the last generated first by default)."
    )
    dir: Direction = Field("desc", description="asc or desc.")


class RecordCreateIn(Schema):
    """The issued invoice (also the payload of ``invoice.invoice.issued``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    invoice_id: UUID | None = Field(None, description="Id of the issued invoice.")
    number: OptionalText(60) = Field(
        None,
        title=gettext_noop("Invoice number"),
        description="Number of the issued invoice, instead of its id.",
    )

    @model_validator(mode="after")
    def _one_of_them(self):
        if self.invoice_id is None and not self.number:
            raise ValueError(str(WHICH_INVOICE))
        return self


class RecordCorrectIn(RecordRefIn):
    """A rejected or accepted-with-errors registration to correct with a new record."""


class RecordCancelIn(RecordRefIn):
    reason: _text(500, min_length=1) = Field(
        description="Why the invoice was issued by error."
    )


class RecordTransmitIn(RecordRefIn):
    """A record to send now, with the earlier ones of its chain."""


class ContingencyRetryIn(RecordRefIn):
    """A record of the queue to put out with the next pass."""


class RecordReconcileIn(RecordRefIn):
    """A record of the queue to ask the AEAT about."""


class ReconcileOut(Schema):
    held: bool = Field(
        description="True when the AEAT already held this very record (same fingerprint): it left the queue."
    )
    record: RecordSummaryOut = Field(description="The record, with its status now.")


class ChainValidateIn(IssuerIn):
    """The chain of an issuer in the current environment."""


class AeatQueryIn(IssuerIn):
    year: int | None = Field(
        None,
        ge=2024,
        le=2999,
        title=gettext_noop("Year"),
        description="Year (this one by default).",
    )
    month: int | None = Field(
        None,
        ge=1,
        le=12,
        title=gettext_noop("Month"),
        description="Month, 1 to 12 (this one by default).",
    )


class RecoverFromAeatIn(IssuerIn):
    """Anchor the chain on the last record the AEAT holds this month."""


class RecoverManualIn(IssuerIn):
    fingerprint: str = Field(
        description="The last fingerprint of the previous application, 64 hexadecimal characters."
    )
    invoice_number: _text(60, min_length=1) = Field(description="Its invoice number.")
    issue_date: dt.date = Field(description="Its invoice's issue date (YYYY-MM-DD).")

    @field_validator("fingerprint", mode="before")
    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        text = chain.normalize_hash(value) if isinstance(value, str) else ""
        if not chain.is_valid_hash(text):
            raise ValueError(str(FINGERPRINT_INVALID))
        return text


class CertificateUploadIn(Schema):
    """The business's own certificate (VERIFACTU-F02): kept sealed in the hub's database, never shown again."""

    p12_base64: SecretStr = Field(
        title=gettext_noop("Business certificate (.p12 / .pfx)"),
        description="The .p12/.pfx file of the certificate, in base64 (at most 1 MB).",
    )
    password: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Certificate password"),
        description="The certificate's password.",
    )

    @field_validator("p12_base64")
    @classmethod
    def _at_most_one_mb(cls, value: SecretStr) -> SecretStr:
        """Measured on the base64 itself, before anything is decoded: what it would decode to."""
        text = "".join(value.get_secret_value().split())
        size = len(text) * 3 // 4 - (len(text) - len(text.rstrip("=")))
        if size > MAX_CERTIFICATE_BYTES:
            raise ValueError(str(CERTIFICATE_TOO_LARGE))
        return value


class ConfigUpdateIn(Schema):
    route: RouteCode = Field(
        description="erplora (ERPlora files for you) or own (your certificate)."
    )


class RepresentationIn(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    updated_at: dt.datetime | None = Field(None, description="When it last changed.")
    reason: _text(500) = Field("", description="The reviewer's note.")


class ConfigSyncIn(Schema):
    """The ERPlora account's block of the hub's photo (WORKBOOK «Contrato con el SaaS»). Any other key is ignored,
    never refused: the SaaS still sends the retired ``live_paid`` until it stops (PLAN §30, expand/contract)."""

    model_config = ConfigDict(extra="ignore")

    version: int = Field(
        ge=0, description="The photo's version; an equal or older one is ignored."
    )
    hub_id: UUID | None = Field(
        None, description="The business's id in ERPlora (the photo's path)."
    )
    representation: RepresentationIn | None = Field(
        None, description="The signed authorisation's state."
    )
    hub_status: Literal["active", "past_due", "suspended"] | None = Field(
        None, description="The business's commercial status."
    )


class RepresentationSubmitIn(Schema):
    """The signed representation authorisation (Anexo I of Convenio 17) and its documents, each a PDF in base64 of
    5 MB at most. Who owes the tax is Invoicing's issuer; a self-employed business signs itself."""

    signer_tax_id: _text(16) = Field(
        "",
        title=gettext_noop("ID number of the person signing"),
        description="Tax ID (DNI or NIE) of whoever signs; for a self-employed business, left empty: its own.",
    )
    signer_name: _text(200) = Field(
        "",
        title=gettext_noop("Full name of the person signing"),
        description="Full name of whoever signs; for a self-employed business, left empty: its own.",
    )
    signer_document_type: Literal["dni", "nie"] = Field(
        title=gettext_noop("Identity document"),
        description="The signer's identity document: dni or nie.",
    )
    signed_model_base64: SecretStr = Field(
        title=gettext_noop("Signed model"),
        description="The official model, signed by hand and scanned or with AutoFirma: a PDF in base64.",
    )
    id_copy_base64: SecretStr = Field(
        title=gettext_noop("Copy of the identity document"),
        description="Copy of the signer's identity document: a PDF in base64.",
    )
    signature_sample_base64: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Signature sample"),
        description="A sheet with the signer's handwritten signature, required with a NIE: a PDF in base64.",
    )
    representation_proof_base64: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Proof of representation"),
        description="The document that names who may sign for a company, required for one: a PDF in base64.",
    )


class RepresentationModelOut(Schema):
    filename: str = Field(description="The file's name.")
    content_type: str = Field(description="The file's type: application/pdf.")
    content_base64: str = Field(
        description="The official model (Anexo I of Convenio 17) with Invoicing's issuer written in, a PDF in base64."
    )
