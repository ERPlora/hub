"""The records of VeriFactu: their rows, the record with everything, and what creates, corrects, cancels, sends and
reconciles one."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, model_validator

from apps.verifactu import card_names
from apps.verifactu.schemas.events import EventOut
from apps.verifactu.schemas.fields import (
    SEARCH,
    CorrectionStatusCode,
    Direction,
    EnvironmentCode,
    InvoiceTypeCode,
    OptionalText,
    PageIn,
    RecordRefIn,
    StatusCode,
    TypeCode,
    WaitOut,
    _text,
)


WHICH_INVOICE = _("Say which invoice: its id or its number.")


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
        description="Total in cents (none in a cancellation).", json_schema_extra={"money": True}
    )
    environment: EnvironmentCode = Field(
        description="testing or production: the AEAT it goes to."
    )
    status: StatusCode = Field(
        description="pending, sent, accepted, accepted_with_errors or rejected."
    )
    correction: bool = Field(description="Whether it is a correction (subsanación).")
    correction_status: CorrectionStatusCode = Field(
        description="A registration the AEAT rejected or accepted with errors: pending (not corrected yet) or corrected "
        "(a newer record corrects it: corrected_by_id); not_applicable for every other record."
    )
    corrected_by_id: UUID | None = Field(
        description="The record that corrects this one (its subsanación); none while it is not corrected."
    )
    qr_url: str = Field(description="The AEAT's verification link (its QR).")
    created_at: dt.datetime = Field(description="When it was sealed.")


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
    base_amount: int | None = Field(description="Taxable base in cents.", json_schema_extra={"money": True})
    tax_amount: int | None = Field(description="Tax in cents.", json_schema_extra={"money": True})
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
        None, description="Total of at least this many cents.", json_schema_extra={"money": True}
    )
    total_amount_to: int | None = Field(
        None, description="Total of at most this many cents.", json_schema_extra={"money": True}
    )
    correction_status: Literal["pending", "corrected"] | None = Field(
        None,
        description="Only the registrations the AEAT rejected or accepted with errors that are not corrected yet "
        "(pending) or that a newer record already corrects (corrected).",
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


class RecordCreateIn(Schema):
    """The issued invoice (also the payload of ``invoice.invoice.issued``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    invoice_id: UUID | None = Field(None, description="Id of the issued invoice.", json_schema_extra=card_names.AN_INVOICE)
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


class RecordReconcileIn(RecordRefIn):
    """A record of the queue to ask the AEAT about."""


class ReconcileOut(Schema):
    held: bool = Field(
        description="True when the AEAT already held this very record (same fingerprint): it left the queue."
    )
    record: RecordSummaryOut = Field(description="The record, with its status now.")
