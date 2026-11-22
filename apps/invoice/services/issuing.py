"""The one way every document is issued: audited, numbered, written with its lines and its notice, and sealed in
VeriFactu inside the same transaction.
"""

import datetime as dt

from django.db import DatabaseError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation
from live.operations import get as get_operation
from live.outbox import record_event

from apps.invoice import events, fiscal
from apps.invoice.models import Invoice, InvoiceLine, InvoiceSeries
from apps.invoice.services.numbering import _take_number
from apps.invoice.services.writes import _now, actor, logger
from base.business import business_zone

#: The audit's refusals (``fiscal.audit``), by code.
AUDIT_MESSAGES = {
    "invoice.tax_quota_mismatch": _(
        "The tax quota does not match its base and rate, so no invoice was issued. Charging one amount and "
        "declaring another breaks the tax agency's cross-check."
    ),
    "invoice.totals_mismatch": _(
        "The invoice's total does not add up to its own lines, so nothing was issued."
    ),
    "invoice.quota_on_non_subject_class": _(
        "An exempt, not subject or reverse-charge line carries a tax quota, so no invoice was issued: only a "
        "subject operation may declare a quota."
    ),
    "invoice.negative_total": _(
        "An ordinary invoice cannot add up below zero. To give an amount back, issue a rectifying invoice."
    ),
}


GENERAL_REGIME = "01"


#: VeriFactu's operation that seals a document's registration record (its WORKBOOK, «Contrato con
#: Facturación»), called by name inside the issue's own transaction.
VERIFACTU_RECORD = "verifactu.record.create"


SEALED, UNAVAILABLE, PENDING = "sealed", "unavailable", "pending"


#: The audit's tolerance for figures copied from an audited document (a substitute, a rectification):
#: only the structure is checked again (subject keys, header = breakdown, sign).
VERBATIM = 10**12


def _audit(
    closed_entries, tolerance, *, base: int, tax: int, invoice_type: str
) -> None:
    failure = fiscal.audit(
        closed_entries, tolerance, base=base, tax=tax, invoice_type=invoice_type
    )
    if failure is not None:
        raise Conflict(str(AUDIT_MESSAGES[failure.code]), code=failure.code)


def _issue(  # noqa: PLR0913
    ctx: OperationContext,
    *,
    series: InvoiceSeries,
    invoice_type: str,
    entries: list[dict],
    lines: list[dict],
    tolerance: dict,
    recipient: dict,
    issuer: dict,
    operation_date: dt.date,
    source_type: str,
    currency: str,
    status: str = Invoice.Status.ISSUED,
    paid_at: dt.datetime | None = None,
    numbered: tuple[int, str] | None = None,
    issue_date: dt.date | None = None,
    **links,
) -> Invoice:
    """Audits, numbers and writes a document with its lines, and records ``invoice.invoice.issued``. A document
    numbered elsewhere (ERPlora's own invoice: ``numbered`` and its ``issue_date``) takes nothing from its series."""
    base = sum(item["base"] for item in entries)
    tax = sum(item["quota"] + item["surcharge_quota"] for item in entries)
    _audit(entries, tolerance, base=base, tax=tax, invoice_type=invoice_type)
    now = _now()
    sequence, number = numbered if numbered is not None else _take_number(series)
    invoice = Invoice.objects.create(
        invoice_type=invoice_type,
        series=series,
        series_code=series.code,
        year=series.year,
        sequence=sequence,
        number=number,
        issue_date=issue_date or timezone.localdate(now, business_zone()),
        operation_date=operation_date,
        issued_at=now,
        base_amount=base,
        tax_amount=tax,
        total_amount=base + tax,
        tax_breakdown=entries,
        currency=currency,
        source_type=source_type,
        status=status,
        paid_at=paid_at,
        created_by=actor(ctx),
        **issuer,
        **recipient,
        **links,
    )
    InvoiceLine.objects.bulk_create(
        [
            InvoiceLine(invoice=invoice, position=position, **line)
            for position, line in enumerate(lines, start=1)
        ]
    )
    record_event(ctx, events.INVOICE_ISSUED, _issued_notice(invoice))
    invoice.verifactu_status = _seal_in_verifactu(ctx, invoice)
    return invoice


def _issued_notice(invoice: Invoice) -> dict:
    """The payload of ``invoice.invoice.issued`` (WORKBOOK, «Lo que avisa»)."""
    return {
        "invoice_id": str(invoice.id),
        "number": invoice.number,
        "series": invoice.series_code,
        "invoice_type": invoice.invoice_type,
        "total": invoice.total_amount,
        "source_type": invoice.source_type,
        "sale_id": str(invoice.source_sale_id) if invoice.source_sale_id else None,
        # Where it comes from, so Sales links a document issued later (by the outbox) to its write.
        "source": {
            "type": invoice.source_type,
            "sale_id": str(invoice.source_sale_id) if invoice.source_sale_id else None,
            "refund_id": str(invoice.source_refund_id)
            if invoice.source_refund_id
            else None,
            "void": invoice.source_type == Invoice.Source.VOID,
        },
        "rectifies_id": str(invoice.rectifies_id) if invoice.rectifies_id else None,
        "substitutes_id": str(invoice.substitutes_id)
        if invoice.substitutes_id
        else None,
    }


def _seal_in_verifactu(ctx: OperationContext, invoice: Invoice) -> str:
    """Asks VeriFactu, by name and with the issuer's own session, for the registration record of
    ``invoice`` inside this transaction (in its savepoint), so the record is made when the document is
    (RD 1007/2023): «sealed» in the same commit; «unavailable» when VeriFactu is not in this business (the
    document goes without a record); «pending» only for a transient database error (its reaction to
    ``invoice.invoice.issued`` seals it later). Any refusal of VeriFactu (409 ``verifactu.*``, 403) is
    deterministic — it would fail again — so it is not swallowed: it undoes the whole issue and the series
    gives its number back. A programming error is never swallowed either."""
    try:
        record = get_operation(VERIFACTU_RECORD)
    except UnknownOperation:
        return UNAVAILABLE
    try:
        record(ctx, record.input.model_validate({"invoice_id": str(invoice.id)}))
    except AppInactive:
        return UNAVAILABLE
    except DatabaseError as error:
        logger.warning(
            "invoice: VeriFactu could not seal %s now (%s); its reaction to the notice will",
            invoice.number,
            type(error).__name__,
        )
        return PENDING
    return SEALED


def _line_values(line: fiscal.Line, **values) -> dict:
    return {
        "tax_rate": line.key.rate,
        "surcharge_rate": line.key.surcharge_rate,
        "base_amount": line.base,
        "tax_amount": line.tax,
        "total_amount": line.total,
        **values,
    }
