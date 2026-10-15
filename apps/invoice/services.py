"""Write operations of the invoice app: one operation = one transaction, with its events in the outbox.

Every document goes through ``_issue``: the issuer is copied, the breakdown is audited, the number is
taken from its series with ``UPDATE … RETURNING`` (the row stays locked until the COMMIT, so two
documents of a series queue and a refused one leaves no gap) and the document, its lines and
``invoice.invoice.issued`` are written together. A document is never edited: only ``status`` and
``paid_at`` move (paid, cancelled when rectified whole). The operations that act on a sale or on a
document lock its row first, so a repeated or simultaneous request waits and answers what the first one
did, without spending a number.

The clock is ``_now()``: the business's day is its date in the Hub's time zone (Madrid in phase 1).
"""

import datetime as dt
import logging
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from uuid import UUID

from django.db import DatabaseError
from django.db.models import F
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound
from live.operations import UnknownOperation, operation
from live.operations import get as get_operation
from live.outbox import record_event

from apps.customer.queries import find_customer
from apps.invoice import events, fiscal, platform
from apps.invoice.models import (
    FACTORY_SERIES_NAMES,
    Invoice,
    InvoiceLine,
    InvoiceSeries,
    Issuer,
)
from apps.invoice.queries import (
    document_of_sale,
    find_invoice,
    find_platform_invoice,
    invoice_detail,
    issuer_row,
    platform_answer,
    remaining_of,
    series_row,
    series_started,
)
from apps.invoice.schemas import (
    NAME_MAX,
    TAX_ID_MAX,
    FromRefundIn,
    FromSaleIn,
    FromVoidIn,
    InvoiceCreateIn,
    InvoiceOut,
    IssueOut,
    IssuerIn,
    IssuerOut,
    IssuerSyncIn,
    IssuerSyncOut,
    MarkPaidIn,
    PlatformInvoiceIn,
    PlatformInvoiceOut,
    RectifyIn,
    SeriesCreateIn,
    SeriesOut,
    SeriesUpdateIn,
    SubstituteIn,
    check_tax_id,
)
from apps.sale import pricing
from apps.sale.models import OrderLine, Refund, Sale, Settings
from apps.sale.queries import TICKET_LIMIT, business_country, find_sale
from apps.tax.models import TaxRule
from apps.tax.queries import resolve_category_text, resolve_tax, round_half_up

logger = logging.getLogger(__name__)

ISSUER_MISSING = _(
    "Set up the issuer (the business's legal name, tax ID and address) in Invoicing → Issuer before issuing "
    "documents."
)
RECIPIENT_INCOMPLETE = _(
    "A full invoice needs the customer's name, tax ID and address."
)
FIELD_REQUIRED = _("This field is required.")
TOO_LONG = _(
    "VeriFactu's record holds at most %(max)s characters here: shorten it (on the customer's card)."
)
SERIES_NOT_FOUND = _("This numbering series does not exist.")
SERIES_INACTIVE = _("This series is not active: activate it or choose another one.")
SERIES_NOT_ISSUABLE = _(
    "A manual invoice is numbered in an invoice (F1) or ticket (F2) series."
)
SERIES_EXISTS = _("There is already a series with that code that year.")
SERIES_LOCKED = _(
    "This series has already issued invoices, so its prefix, its format and its next number can no longer "
    "change: the number is part of the VeriFactu chain. Create a new series if you need others."
)
NUMBER_TOO_LONG = _(
    "The numbers of this series would not fit in 60 characters (VeriFactu's limit): shorten the prefix or "
    "the format."
)
SERIES_OTHER_YEAR = _(
    "That series numbers another year: a manual invoice is numbered in a series of this year."
)
TICKET_OVER_LIMIT = _(
    "Above %(limit)s a ticket cannot be issued: issue an invoice (F1) with the customer's details."
)
#: VeriFactu's DescripcionOperacion of a document born of a sale, in the tax agency's language.
SALE_OPERATION = _("Sale %(number)s")
NUMBER_TAKEN = _(
    "The number %(number)s already exists in series %(code)s: give the series a format with the year."
)
CANNOT_MARK_PAID = _(
    "This invoice cannot be marked as paid: only an issued invoice that is not paid yet can be. Nothing was "
    "changed."
)
CANNOT_RECTIFY_RECTIFICATION = _("A rectifying invoice cannot be rectified.")
ALREADY_CANCELLED = _("The invoice is already cancelled.")
SUBSTITUTED = _(
    "This ticket was already replaced by a full invoice: rectify the full invoice."
)
RECTIFY_DATE = _(
    "A rectifying invoice is dated the day it is issued: today, and never earlier than the invoice it "
    "corrects. Nothing was issued. Send it without a date and it will be dated today."
)
NOTHING_LEFT = _("Nothing is left to rectify on this invoice.")
NOT_A_TICKET = _(
    "Only a ticket (simplified invoice) can be replaced by a full invoice."
)
TICKET_CANCELLED = _(
    "This ticket is cancelled: it can no longer be replaced by a full invoice."
)
TICKET_RECTIFIED = _(
    "This ticket already has rectifying invoices: it can no longer be replaced by a full invoice."
)
SALE_NOT_INVOICED = _(
    "The sale %(number)s has no invoice yet: its rectification waits for it."
)
SALE_NOT_VOIDED = _("The sale %(number)s is not voided.")
REFUND_NOT_FOUND = _("That refund does not exist.")
UNKNOWN_CATEGORY = _("There is no tax category «%(category)s».")
NO_TAX_RULE = _("No tax rule applies today to the tax category «%(category)s».")
LINE_UNDERFLOW = _(
    "Line %(line)s: %(quantity)s at that price comes to 0.00, so no invoice was issued."
)
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

#: The code each kind of document is numbered in, and the type a series born for it takes.
TICKET, FULL, RECTIFYING = "TICKET", "FACT", "RECT"
FACTORY_TYPES = {TICKET: "F2", FULL: "F1", RECTIFYING: "R1"}
GENERAL_REGIME = "01"
#: VeriFactu's operation that seals a document's registration record (its WORKBOOK, «Contrato con
#: Facturación»), called by name inside the issue's own transaction.
VERIFACTU_RECORD = "verifactu.record.create"
SEALED, UNAVAILABLE, PENDING = "sealed", "unavailable", "pending"
#: The language a document's own texts are written in for the tax agency (DescripcionOperacion).
FISCAL_LANGUAGE = "es"
DESCRIPTION_MAX_LENGTH = 500
_CENT_HUNDREDTHS = Decimal("0.01")
#: The audit's tolerance for figures copied from an audited document (a substitute, a rectification):
#: only the structure is checked again (subject keys, header = breakdown, sign).
VERBATIM = 10**12


def _now() -> dt.datetime:
    return timezone.now()


def _today() -> dt.date:
    return timezone.localdate(_now())


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor or "")[:128]


def _detail(ctx: OperationContext, invoice: Invoice) -> dict:
    with translation.override(ctx.language):
        detail = invoice_detail(invoice)
    # Only the answer of the operation that issued it says what VeriFactu did with it.
    return {**detail, "verifactu_status": getattr(invoice, "verifactu_status", None)}


def _result(
    ctx: OperationContext,
    invoice: Invoice | None,
    *,
    issued: bool,
    already: bool = False,
) -> dict:
    return {
        "issued": issued,
        "already": already,
        "verifactu_status": getattr(invoice, "verifactu_status", None),
        "invoice": _detail(ctx, invoice) if invoice is not None else None,
    }


# ── The issuer ──────────────────────────────────────────────────────────────────────────────────


def _configured_issuer() -> Issuer:
    issuer = Issuer.objects.first()
    if issuer is None or not issuer.configured:
        raise Conflict(str(ISSUER_MISSING), code="invoice.issuer_missing")
    return issuer


def _save_issuer(ctx: OperationContext, data: IssuerIn, **extra) -> Issuer:
    values = {
        "legal_name": data.legal_name,
        "tax_id": data.tax_id,
        "address": data.address,
        "postal_code": data.postal_code,
        "city": data.city,
        "province": data.province,
        "country": data.country,
        "updated_by": actor(ctx),
        **extra,
    }
    issuer, _created = Issuer.objects.update_or_create(singleton=True, defaults=values)
    record_event(ctx, events.ISSUER_UPDATED, {"source": issuer.source})
    return issuer


@operation(
    "invoice.issuer.update",
    kind="command",
    permission="invoice.manage_issuer",
    input=IssuerIn,
    output=IssuerOut,
    ai={
        "description": "Set the issuer of the invoices: the business's legal name, tax ID (a Spanish NIF or CIF is "
        "checked) and address. Every document issued from now on carries it; the ones issued keep theirs.",
        "risk": "high",
    },
)
def update_issuer(ctx: OperationContext, data: IssuerIn) -> dict:
    return issuer_row(_save_issuer(ctx, data, source=Issuer.Source.MANUAL))


@operation(
    "invoice.issuer.sync",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it.
    permission="invoice.sync_issuer",
    input=IssuerSyncIn,
    output=IssuerSyncOut,
    ai={
        "description": "System only: the platform hands over the business's tax identity from the ERPlora account "
        "(the SaaS's photo of the hub) with its version; an older version than the one kept is ignored.",
        "risk": "high",
    },
)
def sync_issuer(ctx: OperationContext, data: IssuerSyncIn) -> dict:
    current = Issuer.objects.select_for_update().first()
    if (
        current is not None
        and current.synced_version is not None
        and data.version <= current.synced_version
    ):
        return {"applied": False, "issuer": issuer_row(current)}
    issuer = _save_issuer(
        ctx,
        data,
        source=Issuer.Source.SAAS,
        synced_version=data.version,
        synced_at=_now(),
    )
    return {"applied": True, "issuer": issuer_row(issuer)}


# ── Series and numbers ──────────────────────────────────────────────────────────────────────────


def series_of_year(
    code: str, year: int, ctx: OperationContext | None = None
) -> InvoiceSeries:
    """The series ``code`` of ``year``, born on first use: it inherits name, type, prefix and format from
    the latest earlier year's (or is a factory one: the code as prefix). ``NotFound`` for an unknown code."""
    existing = InvoiceSeries.objects.filter(code=code, year=year).first()
    if existing is not None:
        return existing
    previous = (
        InvoiceSeries.objects.filter(code=code, year__lt=year).order_by("-year").first()
    )
    if previous is not None:
        values = {
            "name": previous.name,
            "invoice_type": previous.invoice_type,
            "prefix": previous.prefix,
            "format": previous.format,
            "is_active": previous.is_active,
        }
    elif code in FACTORY_TYPES:
        values = {
            "name": FACTORY_SERIES_NAMES[code][0],
            "invoice_type": FACTORY_TYPES[code],
            "prefix": code,
        }
    else:
        raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")
    InvoiceSeries.objects.bulk_create(
        [
            InvoiceSeries(
                code=code, year=year, created_by=actor(ctx) if ctx else "", **values
            )
        ],
        ignore_conflicts=True,
    )
    return InvoiceSeries.objects.get(code=code, year=year)


def _take_number(series: InvoiceSeries) -> tuple[int, str]:
    """The next number of ``series``: its counter raised with ``UPDATE … RETURNING`` (the row stays locked
    until the COMMIT; a rollback gives the number back). A number the series already has is refused."""
    series.current_number = F("current_number") + 1
    series.save(update_fields=["current_number", "updated_at"])
    sequence = series.current_number
    number = fiscal.render_number(
        series.format,
        prefix=series.prefix,
        code=series.code,
        year=series.year,
        seq=sequence,
    )
    if Invoice.objects.filter(series_code=series.code, number=number).exists():
        raise Conflict(
            str(NUMBER_TAKEN) % {"number": number, "code": series.code},
            code="invoice.number_taken",
        )
    return sequence, number


# ── Issuing ─────────────────────────────────────────────────────────────────────────────────────


def _audit(
    closed_entries, tolerance, *, base: int, tax: int, invoice_type: str
) -> None:
    failure = fiscal.audit(
        closed_entries, tolerance, base=base, tax=tax, invoice_type=invoice_type
    )
    if failure is not None:
        raise Conflict(str(AUDIT_MESSAGES[failure.code]), code=failure.code)


def _issue(
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
        issue_date=issue_date or timezone.localdate(now),
        operation_date=operation_date,
        issued_at=now,
        base_amount=base,
        tax_amount=tax,
        total_amount=base + tax,
        tax_breakdown=entries,
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
    record_event(
        ctx,
        events.INVOICE_ISSUED,
        {
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
        },
    )
    invoice.verifactu_status = _seal_in_verifactu(ctx, invoice)
    return invoice


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


def _issuer_copy(issuer: Issuer) -> dict:
    return {
        "issuer_name": issuer.legal_name,
        "issuer_tax_id": issuer.tax_id,
        "issuer_address": issuer.address_line,
        "issuer_country": issuer.country,
    }


def _issuer_of(invoice: Invoice) -> dict:
    return {
        "issuer_name": invoice.issuer_name,
        "issuer_tax_id": invoice.issuer_tax_id,
        "issuer_address": invoice.issuer_address,
        "issuer_country": invoice.issuer_country,
    }


def _recipient_of(invoice: Invoice) -> dict:
    return {
        "customer_id": invoice.customer_id,
        "customer_name": invoice.customer_name,
        "customer_tax_id": invoice.customer_tax_id,
        "customer_address": invoice.customer_address,
        "customer_country": invoice.customer_country,
        "customer_id_type": invoice.customer_id_type,
    }


def _card_address(card) -> str:
    town = " ".join(part for part in (card.postal_code, card.city) if part)
    return ", ".join(part for part in (card.address, town) if part)


def _without_tax_id(recipient: dict, why: str) -> dict:
    """A simplified invoice (F2) needs no recipient: a tax ID that does not check is left out (the name
    stays) instead of leaving the ticket undone, and the log says so."""
    logger.warning("invoice: a ticket goes without its recipient's tax ID (%s)", why)
    return {**recipient, "customer_tax_id": "", "customer_id_type": ""}


def _recipient(data, *, full: bool, fallback_name: str = "", card=None) -> dict:
    """The recipient: what was sent, else the customer card's (named by id or reference). A full invoice
    needs name, tax ID and address (409 with the missing fields); a tax ID taken from the card is checked."""
    if card is None and (
        getattr(data, "customer_id", None) is not None
        or getattr(data, "customer", None)
    ):
        card = find_customer(data.customer_id, data.customer)
    name = (
        data.customer_name
        or (card.company_name or card.name if card else "")
        or fallback_name
    )
    tax_id = data.customer_tax_id or (card.tax_id if card else "")
    address = data.customer_address or (_card_address(card) if card else "")
    country = data.customer_country or (
        card.country if card and card.country != "ES" else ""
    )
    id_type = data.customer_id_type
    refusal = getattr(data, "tax_id_refusal", None)
    if tax_id and not data.customer_tax_id:
        # What the card says is read as what is typed (apps.customer.tax_ids); a refusal names its field.
        try:
            tax_id = check_tax_id(tax_id, country=country, id_type=id_type)
        except ValueError as error:
            refusal = (error.field, str(error))
    if refusal is None and len(tax_id) > TAX_ID_MAX:
        refusal = ("customer_tax_id", str(TOO_LONG) % {"max": TAX_ID_MAX})
    if refusal is not None and full:
        field, message = refusal
        raise InvalidPayload(message, fields={field: message})
    if len(name) > NAME_MAX:
        # A card holds 200 characters; VeriFactu's NombreRazon, 120.
        message = str(TOO_LONG) % {"max": NAME_MAX}
        if full:
            raise InvalidPayload(message, fields={"customer_name": message})
        logger.warning("invoice: a ticket goes without its recipient's name (%s)", message)
        name = ""
    if full:
        missing = [
            field
            for field, value in (
                ("customer_name", name),
                ("customer_tax_id", tax_id),
                ("customer_address", address),
            )
            if not value.strip()
        ]
        if missing:
            raise Conflict(
                str(RECIPIENT_INCOMPLETE),
                code="invoice.recipient_incomplete",
                fields={field: str(FIELD_REQUIRED) for field in missing},
            )
    recipient = {
        "customer": card,
        "customer_name": name,
        "customer_tax_id": tax_id,
        "customer_address": address,
        "customer_country": country,
        "customer_id_type": id_type,
    }
    if refusal is not None:
        return _without_tax_id(recipient, refusal[1])
    return recipient


def _line_values(line: fiscal.Line, **values) -> dict:
    return {
        "tax_rate": line.key.rate,
        "surcharge_rate": line.key.surcharge_rate,
        "base_amount": line.base,
        "tax_amount": line.tax,
        "total_amount": line.total,
        **values,
    }


# ── Manual invoices (INVOICE-F03) ───────────────────────────────────────────────────────────────


def _manual_series(
    data: InvoiceCreateIn, year: int, ctx: OperationContext
) -> InvoiceSeries:
    if data.series_id is not None:
        series = InvoiceSeries.objects.filter(pk=data.series_id).first()
        if series is None:
            raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")
        if series.year != year:
            raise Conflict(
                str(SERIES_OTHER_YEAR),
                code="invoice.series_other_year",
                fields={"series_id": str(SERIES_OTHER_YEAR)},
            )
    elif data.series_code:
        series = series_of_year(data.series_code.strip().upper(), year, ctx)
    else:
        series = InvoiceSeries.objects.filter(
            year=year, is_default=True
        ).first() or series_of_year(FULL, year, ctx)
    if not series.is_active:
        raise Conflict(str(SERIES_INACTIVE), code="invoice.series_inactive")
    if series.invoice_type not in ("F1", "F2"):
        raise Conflict(str(SERIES_NOT_ISSUABLE), code="invoice.series_not_issuable")
    return series


def _rule_key(category_key: str, *, field: str, on: dt.date) -> fiscal.FiscalKey:
    resolution = resolve_tax(category_key=category_key, on=on)
    if resolution is None:
        message = str(NO_TAX_RULE) % {"category": category_key}
        raise Conflict(message, code="invoice.no_tax_rule", fields={field: message})
    return fiscal.FiscalKey(
        tax=resolution.tax_kind,
        regime=resolution.regime_key,
        cls=resolution.operation_class,
        exempt_reason=resolution.exempt_reason,
        rate=resolution.root.rate_pct,
        surcharge_rate=sum(
            (rule.rate_pct for rule in resolution.components[1:]), Decimal(0)
        ),
    )


@operation(
    "invoice.invoice.create",
    kind="command",
    permission="invoice.add_invoice",
    input=InvoiceCreateIn,
    output=InvoiceOut,
    ai={
        "description": "Issue an invoice by hand, dated today and numbered in its series (an invoice F1 needs the "
        "customer's name, tax ID and address; a ticket series issues a simplified F2). Each line: description, "
        "quantity, unit price WITHOUT VAT in cents, and its VAT % or its tax category. The server computes the VAT, "
        "closed once per rate. An issued invoice is never edited: it is corrected with a rectifying invoice.",
        "risk": "high",
    },
)
def create(ctx: OperationContext, data: InvoiceCreateIn) -> dict:
    issuer = _configured_issuer()
    today = _today()
    series = _manual_series(data, today.year, ctx)
    recipient = _recipient(data, full=series.invoice_type == "F1")
    lines, values = [], []
    for index, item in enumerate(data.lines):
        category = ""
        if item.tax_category_key:
            field = f"lines.{index}.tax_category_key"
            category, _matched = resolve_category_text(item.tax_category_key)
            if category is None:
                message = str(UNKNOWN_CATEGORY) % {"category": item.tax_category_key}
                raise InvalidPayload(
                    message,
                    code="invoice.unknown_tax_category",
                    fields={field: message},
                )
            key = _rule_key(category, field=field, on=today)
        else:
            key = fiscal.FiscalKey(
                tax="vat",
                regime=GENERAL_REGIME,
                cls="subject",
                exempt_reason="",
                rate=item.tax_rate,
            )
        base = round_half_up(item.quantity * item.unit_price)
        if item.unit_price > 0 and base == 0:
            message = str(LINE_UNDERFLOW) % {
                "line": index + 1,
                "quantity": item.quantity,
            }
            raise Conflict(
                message,
                code="invoice.line_amount_underflow",
                fields={f"lines.{index}.quantity": message},
            )
        lines.append(
            fiscal.Line(key=key, base=base, tax=0, total=base, category=category)
        )
        values.append(
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": Decimal(item.unit_price),
                "tax_category_key": category,
                "product_id": item.product_id,
            }
        )
    closed = fiscal.close_manual(lines)
    _within_ticket_limit(series, closed.total)
    invoice = _issue(
        ctx,
        series=series,
        invoice_type=series.invoice_type,
        entries=closed.entries,
        lines=[
            _line_values(line, **extra)
            for line, extra in zip(closed.lines, values, strict=True)
        ],
        tolerance=closed.tolerance,
        recipient=recipient,
        issuer=_issuer_copy(issuer),
        operation_date=today,
        source_type=Invoice.Source.MANUAL,
        notes=data.notes,
        description=_operation_text(item.description for item in data.lines),
    )
    return _detail(ctx, invoice)


def _operation_text(parts) -> str:
    """VeriFactu's DescripcionOperacion of a manual invoice: its concepts, at most 500 characters."""
    return ", ".join(parts)[:DESCRIPTION_MAX_LENGTH]


def _sale_operation(sale: Sale) -> str:
    """VeriFactu's DescripcionOperacion of a document born of ``sale``, in the tax agency's language."""
    with translation.override(FISCAL_LANGUAGE):
        return str(SALE_OPERATION) % {"number": sale.number}


def _within_ticket_limit(series: InvoiceSeries, total: int) -> None:
    """A ticket (F2) up to the till's own limit (RD 1619/2012 art. 4; Sales' ``TICKET_LIMIT``)."""
    limit = TICKET_LIMIT.get(business_country())
    if series.invoice_type == "F2" and limit is not None and total > limit:
        raise Conflict(
            str(TICKET_OVER_LIMIT) % {"limit": f"{limit / 100:.2f} €"},
            code="invoice.ticket_over_limit",
        )


# ── The invoice of a sale (INVOICE-F01, F02, F06) ───────────────────────────────────────────────


def _sale_key(line, rules: dict) -> fiscal.FiscalKey:
    """The fiscal key a sale line was charged with: its frozen root rule and its components."""
    components = line.tax_components or []
    main = Decimal(str(components[0]["rate_pct"])) if components else line.tax_rate
    surcharge = sum((Decimal(str(c["rate_pct"])) for c in components[1:]), Decimal(0))
    rule = rules.get(line.tax_rule_id)
    if rule is None:
        return fiscal.FiscalKey(
            tax="vat",
            regime=GENERAL_REGIME,
            cls="subject",
            exempt_reason="",
            rate=main,
            surcharge_rate=surcharge,
        )
    exempt = (
        rule.exempt_reason.upper()
        if rule.operation_class == TaxRule.OperationClass.EXEMPT
        else ""
    )
    return fiscal.FiscalKey(
        tax=rule.tax_type or "vat",
        regime=rule.regime_key or GENERAL_REGIME,
        cls=rule.operation_class,
        exempt_reason=exempt,
        rate=main,
        surcharge_rate=surcharge,
    )


def _undiscounted(sale_line, order_line: OrderLine | None) -> int:
    """What a charged line was worth at its own price before any discount, in the sale's price mode (with
    or without VAT); a comp or a line a voucher pays was worth nothing to begin with."""
    if sale_line.is_gift or sale_line.voucher_session_id is not None:
        return 0
    if order_line is not None:
        ratio = pricing.price_ratio(
            sale_line.quantity,
            (order_line.unit_factor_num, order_line.unit_factor_den),
            (order_line.pricing_factor_num, order_line.pricing_factor_den),
            sale_line.price_quantity,
        )
    else:
        ratio = Fraction(sale_line.quantity) / Fraction(sale_line.price_quantity)
    return pricing.line_amount(sale_line.unit_price, ratio)


def _net_price(
    line: fiscal.Line, quantity: Decimal, undiscounted: int, *, tax_included: bool
) -> tuple[Decimal, int]:
    """The unit price WITHOUT VAT and before any discount (cents with two decimals) and the discount
    without VAT of a charged line (RD 1619/2012 art. 6.1.f): what it was worth at its own price, without
    VAT in the same proportion the line was charged (or by its key's rates when it came to nothing)."""
    charged = line.total if tax_included else line.base
    if undiscounted <= charged:
        return (Decimal(line.base) / quantity).quantize(_CENT_HUNDREDTHS, ROUND_HALF_UP), 0
    if not tax_included:
        net = Decimal(undiscounted)
    elif line.total:
        net = Decimal(undiscounted) * Decimal(line.base) / Decimal(line.total)
    else:
        rates = Decimal(100) + line.key.rate + line.key.surcharge_rate
        net = Decimal(undiscounted) * Decimal(100) / rates
    unit = (net / quantity).quantize(_CENT_HUNDREDTHS, ROUND_HALF_UP)
    return unit, max(round_half_up(quantity * unit) - line.base, 0)


@operation(
    "invoice.invoice.create_from_sale",
    kind="command",
    permission="invoice.add_invoice",
    input=FromSaleIn,
    output=IssueOut,
    ai={
        "description": "Issue the fiscal document of a charged sale (by its id or its number of the day): its ticket "
        "(F2) or, if it was charged as an invoice, its full invoice (F1) with the customer's data. Read from the sale "
        "itself, born paid. It is also what happens by itself after every charge; asking again issues nothing.",
        "risk": "high",
    },
)
def create_from_sale(ctx: OperationContext, data: FromSaleIn) -> dict:
    sale = find_sale(data.sale_id, data.sale, lock=True)
    existing = Invoice.objects.filter(
        source_sale=sale, source_type=Invoice.Source.SALE
    ).first()
    if existing is not None:
        return _result(ctx, existing, issued=False, already=True)
    issuer = _configured_issuer()
    full = sale.document_type == Settings.DocumentType.INVOICE
    sale_lines = list(sale.lines.order_by("position", "id"))
    rules = TaxRule.objects.in_bulk(
        {line.tax_rule_id for line in sale_lines if line.tax_rule_id}
    )
    lines = [
        fiscal.Line(
            key=_sale_key(line, rules),
            base=line.net_amount,
            tax=line.tax_amount,
            total=line.line_total,
            category=line.tax_category_key,
        )
        for line in sale_lines
    ]
    closed = fiscal.close_charged(lines, tax_included=sale.tax_included)
    if closed.total != sale.total:
        raise Conflict(
            str(AUDIT_MESSAGES["invoice.totals_mismatch"]),
            code="invoice.totals_mismatch",
        )
    recipient = _recipient(
        data,
        full=full,
        fallback_name=sale.customer_name,
        card=sale.customer,
    )
    series = series_of_year(FULL if full else TICKET, _today().year, ctx)
    order_lines = OrderLine.objects.in_bulk(
        {line.order_line_id for line in sale_lines if line.order_line_id}
    )
    values = []
    for line, sale_line in zip(closed.lines, sale_lines, strict=True):
        unit, discount = _net_price(
            line,
            sale_line.quantity,
            _undiscounted(sale_line, order_lines.get(sale_line.order_line_id)),
            tax_included=sale.tax_included,
        )
        values.append(
            _line_values(
                line,
                description=sale_line.name,
                quantity=sale_line.quantity,
                unit_price=unit,
                discount_amount=discount,
                tax_category_key=sale_line.tax_category_key,
                product_id=sale_line.product_id,
                sale_line_id=sale_line.id,
            )
        )
    invoice = _issue(
        ctx,
        series=series,
        invoice_type="F1" if full else "F2",
        entries=closed.entries,
        lines=values,
        tolerance=closed.tolerance,
        recipient=recipient,
        issuer=_issuer_copy(issuer),
        operation_date=sale.business_day,
        source_type=Invoice.Source.SALE,
        source_sale=sale,
        status=Invoice.Status.PAID,
        paid_at=sale.created_at,
        currency=sale.currency,
        description=_sale_operation(sale),
    )
    return _result(ctx, invoice, issued=True)


# ── A full invoice for a ticket (INVOICE-F04, F05) ──────────────────────────────────────────────


@operation(
    "invoice.invoice.substitute",
    kind="command",
    permission="invoice.add_invoice",
    input=SubstituteIn,
    output=IssueOut,
    ai={
        "description": "The customer asks for the full invoice of their ticket: issue a full invoice (F3) that replaces "
        "the ticket (by its number), with the customer's name, tax ID and address (or their card) and the ticket's "
        "very figures. The ticket is not touched. A ticket has one; asking again answers it without issuing another.",
        "risk": "high",
    },
)
def substitute(ctx: OperationContext, data: SubstituteIn) -> dict:
    ticket = find_invoice(data.invoice_id, data.number, lock=True)
    if ticket.invoice_type != "F2":
        raise Conflict(str(NOT_A_TICKET), code="invoice.not_a_ticket")
    existing = Invoice.objects.filter(substitutes=ticket).first()
    if existing is not None:
        return _result(ctx, existing, issued=False, already=True)
    if ticket.status == Invoice.Status.CANCELLED:
        raise Conflict(str(TICKET_CANCELLED), code="invoice.already_cancelled")
    if ticket.rectifications.exists():
        raise Conflict(str(TICKET_RECTIFIED), code="invoice.ticket_rectified")
    recipient = _recipient(data, full=True)
    _configured_issuer()
    series = series_of_year(FULL, _today().year, ctx)
    invoice = _issue(
        ctx,
        series=series,
        invoice_type="F3",
        entries=list(ticket.tax_breakdown),
        lines=[
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": line.discount_amount,
                "tax_rate": line.tax_rate,
                "surcharge_rate": line.surcharge_rate,
                "tax_category_key": line.tax_category_key,
                "base_amount": line.base_amount,
                "tax_amount": line.tax_amount,
                "total_amount": line.total_amount,
                "product_id": line.product_id,
                "sale_line_id": line.sale_line_id,
            }
            for line in ticket.lines.order_by("position", "id")
        ],
        tolerance={fiscal.key_of(item): VERBATIM for item in ticket.tax_breakdown},
        recipient=recipient,
        issuer=_issuer_of(ticket),
        operation_date=ticket.operation_date,
        source_type=Invoice.Source.SUBSTITUTION,
        source_sale=ticket.source_sale,
        substitutes=ticket,
        status=ticket.status,
        paid_at=ticket.paid_at,
        currency=ticket.currency,
        description=ticket.description,
    )
    return _result(ctx, invoice, issued=True)


# ── Rectifying (INVOICE-F07–F10) ────────────────────────────────────────────────────────────────


def _rectify(
    ctx: OperationContext,
    original: Invoice,
    *,
    amount: int,
    reason: str,
    invoice_type: str,
    source_type: str,
    operation_date: dt.date,
    line_description: str,
    source_refund: Refund | None = None,
    returned: dict[fiscal.FiscalKey, tuple[int, str]] | None = None,
) -> Invoice:
    """Issues the rectification by differences of ``amount`` cents of what is left of ``original``: the
    whole original negated (header, breakdown and lines) when nothing rectified it yet and the amount is
    its total; else what is left prorated key by key — over the keys of the articles ``returned`` (their
    worth and their text, per key) when a refund brings them back — with one line per key at its own
    rate. The original is cancelled when nothing is left of it, and ``invoice.invoice.rectified`` says so."""
    previous = list(original.rectifications.all())
    whole = not previous and amount == original.total_amount
    if whole:
        entries = fiscal.negate(original.tax_breakdown)
        lines = [
            {
                "description": line.description,
                "quantity": -line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": -line.discount_amount,
                "tax_rate": line.tax_rate,
                "surcharge_rate": line.surcharge_rate,
                "tax_category_key": line.tax_category_key,
                "base_amount": -line.base_amount,
                "tax_amount": -line.tax_amount,
                "total_amount": -line.total_amount,
                "product_id": line.product_id,
                "sale_line_id": line.sale_line_id,
            }
            for line in original.lines.order_by("position", "id")
        ]
    else:
        left = fiscal.remaining(
            original.tax_breakdown, [item.tax_breakdown for item in previous]
        )
        weights = (
            [returned.get(fiscal.key_of(item), (0, ""))[0] for item in left]
            if returned
            else None
        )
        entries = [
            item
            for item in fiscal.prorate(left, amount, weights)
            if fiscal.gross_of(item) or item["base"]
        ]
        lines = [_key_line(item, line_description, returned) for item in entries]
    series = series_of_year(RECTIFYING, _today().year, ctx)
    rectification = _issue(
        ctx,
        series=series,
        invoice_type=invoice_type,
        entries=entries,
        lines=lines,
        tolerance={fiscal.key_of(item): VERBATIM for item in entries},
        recipient=_recipient_of(original),
        issuer=_issuer_of(original),
        operation_date=operation_date,
        source_type=source_type,
        source_sale=original.source_sale,
        source_refund=source_refund,
        rectifies=original,
        rectification_kind=Invoice.RectificationKind.DIFFERENCES,
        description=reason[:500],
        currency=original.currency,
    )
    left_over = remaining_of(original)
    if left_over == 0 and original.status != Invoice.Status.CANCELLED:
        original.status = Invoice.Status.CANCELLED
        original.save(update_fields=["status", "updated_at"])
    record_event(
        ctx,
        events.INVOICE_RECTIFIED,
        {
            "invoice_id": str(original.id),
            "number": original.number,
            "status": original.status,
            "rectification_id": str(rectification.id),
            "rectification_number": rectification.number,
            "remaining": left_over,
        },
    )
    return rectification


def _key_line(
    item: dict, description: str, returned: dict | None
) -> dict:
    """The line of one key of a rectification by differences: its base as the price, at its own rate,
    named by the articles of that key that came back (else by ``description``)."""
    key = fiscal.key_of(item)
    text = (returned or {}).get(key, (0, ""))[1] or description
    return {
        "description": text[:255],
        "quantity": Decimal("-1"),
        "unit_price": Decimal(-item["base"]),
        "discount_amount": 0,
        "tax_rate": key.rate,
        "surcharge_rate": key.surcharge_rate,
        "base_amount": item["base"],
        "tax_amount": item["quota"] + item["surcharge_quota"],
        "total_amount": fiscal.gross_of(item),
    }


def _rectifying_type(original: Invoice, chosen: str | None = None) -> str:
    """R5 for a ticket; for a full invoice the type chosen, R1 by default (a refund is art. 80 Two)."""
    return "R5" if original.is_simplified else (chosen or "R1")


@operation(
    "invoice.invoice.rectify",
    kind="command",
    permission="invoice.rectify_invoice",
    input=RectifyIn,
    output=IssueOut,
    ai={
        "description": "Rectify an invoice (by its number) with a mandatory reason: a rectifying invoice dated today in "
        "this year's RECT series negates what is left of it, and the original is cancelled. Type R1 by default (R2–R4 "
        "to choose; a ticket is always R5). Do not send a date: any other day than today is refused. Money is given "
        "back in Sales, not here.",
        "risk": "high",
    },
)
def rectify(ctx: OperationContext, data: RectifyIn) -> dict:
    original = find_invoice(data.invoice_id, data.number, lock=True)
    if original.is_rectification:
        raise Conflict(
            str(CANNOT_RECTIFY_RECTIFICATION),
            code="invoice.cannot_rectify_rectification",
        )
    if original.status == Invoice.Status.CANCELLED:
        raise Conflict(str(ALREADY_CANCELLED), code="invoice.already_cancelled")
    if Invoice.objects.filter(substitutes=original).exists():
        raise Conflict(str(SUBSTITUTED), code="invoice.substituted")
    today = _today()
    if (
        data.issue_date is not None and data.issue_date != today
    ) or original.issue_date > today:
        raise Conflict(
            str(RECTIFY_DATE),
            code="invoice.rectify_date_not_allowed",
            fields={"issue_date": str(RECTIFY_DATE)},
        )
    left_over = remaining_of(original)
    if left_over <= 0:
        raise Conflict(str(NOTHING_LEFT), code="invoice.nothing_left")
    rectification = _rectify(
        ctx,
        original,
        amount=left_over,
        reason=data.reason,
        invoice_type=_rectifying_type(original, data.rectification_type),
        source_type=Invoice.Source.RECTIFICATION,
        operation_date=original.operation_date,
        line_description=data.reason,
    )
    return _result(ctx, rectification, issued=True)


def _sale_document(sale: Sale) -> Invoice:
    """The document in force of ``sale``, locked; a 409 to retry while it has none (INVOICE-F06)."""
    document = document_of_sale(sale.id)
    if document is None:
        raise Conflict(
            str(SALE_NOT_INVOICED) % {"number": sale.number},
            code="invoice.sale_not_invoiced",
        )
    return Invoice.objects.select_for_update().get(pk=document.pk)


def _quantity_text(quantity: Decimal) -> str:
    """«2», «0.25»: a quantity without the zeros its three decimals add."""
    return f"{quantity.normalize():f}"


def _refund_concept(refund: Refund) -> str:
    """What came back: «2 × Shampoo, 1 × Wax», or the reason of a refund of money only."""
    returned = [
        f"{_quantity_text(item.quantity)} × {item.sale_line.name}"
        for item in refund.lines.select_related("sale_line").order_by(
            "sale_line__position", "id"
        )
    ]
    return ", ".join(returned) or refund.reason


def _returned_by_key(refund: Refund) -> dict[fiscal.FiscalKey, tuple[int, str]] | None:
    """The articles a refund brings back, per fiscal key: what they were charged (their share of their
    line) and their text («2 × Shampoo»); ``None`` for a refund of money only."""
    items = list(
        refund.lines.select_related("sale_line").order_by("sale_line__position", "id")
    )
    if not items:
        return None
    rules = TaxRule.objects.in_bulk(
        {item.sale_line.tax_rule_id for item in items if item.sale_line.tax_rule_id}
    )
    weights: dict[fiscal.FiscalKey, int] = {}
    texts: dict[fiscal.FiscalKey, list[str]] = {}
    for item in items:
        line = item.sale_line
        key = _sale_key(line, rules)
        weights[key] = weights.get(key, 0) + round_half_up(
            Decimal(line.line_total) * item.quantity / line.quantity
        )
        texts.setdefault(key, []).append(
            f"{_quantity_text(item.quantity)} × {line.name}"
        )
    return {key: (weights[key], ", ".join(texts[key])) for key in weights}


@operation(
    "invoice.invoice.rectify_from_refund",
    kind="command",
    permission="invoice.rectify_invoice",
    input=FromRefundIn,
    output=IssueOut,
    ai={
        "description": "Issue the rectifying invoice of a refund of the Sales app (by the refund's id): what the refund "
        "gave back, prorated over what is left of the sale's invoice (by differences); the refund that closes the sale "
        "takes exactly what is left and cancels the invoice. It also happens by itself after every refund; asking "
        "again issues nothing.",
        "risk": "high",
    },
)
def rectify_from_refund(ctx: OperationContext, data: FromRefundIn) -> dict:
    refund = Refund.objects.filter(pk=data.refund_id).first()
    if refund is None:
        raise NotFound(str(REFUND_NOT_FOUND), code="invoice.refund_not_found")
    sale = find_sale(refund.sale_id, None, lock=True)
    existing = Invoice.objects.filter(source_refund=refund).first()
    if existing is not None:
        return _result(ctx, existing, issued=False, already=True)
    original = _sale_document(sale)
    left_over = remaining_of(original)
    returned_until_now = sum(
        item.total
        for item in sale.refunds.all()
        if (item.created_at, item.id.int) <= (refund.created_at, refund.id.int)
    )
    closes = returned_until_now >= sale.total
    amount = left_over if closes else min(refund.total, left_over)
    if amount <= 0:
        return _result(ctx, None, issued=False)
    rectification = _rectify(
        ctx,
        original,
        amount=amount,
        reason=refund.reason,
        invoice_type=_rectifying_type(original),
        source_type=Invoice.Source.REFUND,
        operation_date=timezone.localdate(refund.created_at),
        line_description=_refund_concept(refund),
        source_refund=refund,
        returned=None if closes else _returned_by_key(refund),
    )
    return _result(ctx, rectification, issued=True)


@operation(
    "invoice.invoice.rectify_from_void",
    kind="command",
    permission="invoice.rectify_invoice",
    input=FromVoidIn,
    output=IssueOut,
    ai={
        "description": "Issue the rectifying invoice of a voided sale (by the sale's id): the whole of what is left of "
        "its ticket negated (R5; R1 if the ticket was replaced by a full invoice), with the void's reason. It also "
        "happens by itself after every void; asking again issues nothing.",
        "risk": "high",
    },
)
def rectify_from_void(ctx: OperationContext, data: FromVoidIn) -> dict:
    sale = find_sale(data.sale_id, None, lock=True)
    if sale.status != Sale.Status.VOIDED:
        raise Conflict(
            str(SALE_NOT_VOIDED) % {"number": sale.number},
            code="invoice.sale_not_voided",
        )
    existing = Invoice.objects.filter(
        source_sale=sale, source_type=Invoice.Source.VOID
    ).first()
    if existing is not None:
        return _result(ctx, existing, issued=False, already=True)
    original = _sale_document(sale)
    left_over = remaining_of(original)
    if left_over <= 0:
        return _result(ctx, None, issued=False)
    rectification = _rectify(
        ctx,
        original,
        amount=left_over,
        reason=sale.void_reason,
        invoice_type=_rectifying_type(original),
        source_type=Invoice.Source.VOID,
        operation_date=timezone.localdate(sale.voided_at or _now()),
        line_description=sale.void_reason,
    )
    return _result(ctx, rectification, issued=True)


# ── Paying (INVOICE-F19) ────────────────────────────────────────────────────────────────────────


@operation(
    "invoice.invoice.mark_paid",
    kind="command",
    permission="invoice.add_invoice",
    input=MarkPaidIn,
    output=InvoiceOut,
    ai={
        "description": "Mark an issued invoice (by its number) as paid now. No amount changes, no payment method is "
        "kept and the till is not touched; a paid, cancelled or rectifying invoice is refused.",
        "risk": "normal",
    },
)
def mark_paid(ctx: OperationContext, data: MarkPaidIn) -> dict:
    invoice = find_invoice(data.invoice_id, data.number, lock=True)
    if invoice.is_rectification or invoice.status != Invoice.Status.ISSUED:
        raise Conflict(str(CANNOT_MARK_PAID), code="invoice.cannot_mark_paid")
    invoice.status = Invoice.Status.PAID
    invoice.paid_at = _now()
    invoice.save(update_fields=["status", "paid_at", "updated_at"])
    record_event(
        ctx,
        events.INVOICE_PAID,
        {
            "invoice_id": str(invoice.id),
            "number": invoice.number,
            "paid_at": invoice.paid_at.isoformat(),
        },
    )
    return _detail(ctx, invoice)


# ── Series (INVOICE-F12, F13) ───────────────────────────────────────────────────────────────────


def _check_number(*, prefix: str, format: str, code: str, year: int, blame: str) -> None:
    """Every number of the series must be a VeriFactu ``NumSerieFactura`` (60 printable ASCII
    characters at most, with its widest sequence); a 422 under the field the request changed."""
    if not fiscal.number_fits(format, prefix=prefix, code=code, year=year):
        raise InvalidPayload(str(NUMBER_TOO_LONG), fields={blame: str(NUMBER_TOO_LONG)})


def _demote_defaults(year: int, keep: UUID | None = None) -> None:
    InvoiceSeries.objects.filter(year=year, is_default=True).exclude(pk=keep).update(
        is_default=False
    )


@operation(
    "invoice.series.create",
    kind="command",
    permission="invoice.manage_series",
    input=SeriesCreateIn,
    output=SeriesOut,
    ai={
        "description": "Create a numbering series: code, name, type (F1–F3, R1–R5), year, prefix (default: the code), "
        "optional number format and the number its first document takes. Sales number in TICKET, FACT and RECT; "
        "another code serves manual invoices. Marking it default demotes the default series of its year.",
        "risk": "normal",
    },
)
def create_series(ctx: OperationContext, data: SeriesCreateIn) -> dict:
    if InvoiceSeries.objects.filter(code=data.code, year=data.year).exists():
        raise Conflict(
            str(SERIES_EXISTS),
            code="invoice.series_exists",
            fields={"code": str(SERIES_EXISTS)},
        )
    _check_number(
        prefix=data.prefix or data.code,
        format=data.format,
        code=data.code,
        year=data.year,
        blame="format" if data.format else "prefix",
    )
    if data.is_default:
        _demote_defaults(data.year)
    series = InvoiceSeries.objects.create(
        code=data.code,
        name=data.name,
        invoice_type=data.invoice_type,
        year=data.year,
        prefix=data.prefix or data.code,
        format=data.format,
        current_number=data.next_number - 1,
        is_active=data.is_active,
        is_default=data.is_default,
        created_by=actor(ctx),
        updated_by=actor(ctx),
    )
    record_event(
        ctx,
        events.SERIES_CREATED,
        {"id": str(series.id), "code": series.code, "year": series.year},
    )
    return series_row(series)


@operation(
    "invoice.series.update",
    kind="command",
    permission="invoice.manage_series",
    input=SeriesUpdateIn,
    output=SeriesOut,
    ai={
        "description": "Change a numbering series (by its id): name, active, default and, only while it has numbered "
        "nothing, its prefix, its format and its next number. Code, type, year and the counter never change.",
        "risk": "normal",
    },
)
def update_series(ctx: OperationContext, data: SeriesUpdateIn) -> dict:
    series = InvoiceSeries.objects.select_for_update().filter(pk=data.series_id).first()
    if series is None:
        raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")
    wanted = {
        "name": data.name,
        "prefix": data.prefix,
        "format": data.format,
        "is_active": data.is_active,
        "is_default": data.is_default,
    }
    if data.next_number is not None:
        wanted["current_number"] = data.next_number - 1
    changes = {
        field: value
        for field, value in wanted.items()
        if value is not None and getattr(series, field) != value
    }
    frozen = sorted(set(changes) & {"prefix", "format", "current_number"})
    if frozen and series_started(series):
        field_names = [
            "next_number" if field == "current_number" else field for field in frozen
        ]
        raise Conflict(
            str(SERIES_LOCKED),
            code="invoice.series_locked",
            fields={f: str(SERIES_LOCKED) for f in field_names},
        )
    if "prefix" in changes or "format" in changes:
        _check_number(
            prefix=changes.get("prefix", series.prefix) or series.code,
            format=changes.get("format", series.format),
            code=series.code,
            year=series.year,
            blame="prefix" if "prefix" in changes else "format",
        )
    if changes.get("is_default"):
        _demote_defaults(series.year, keep=series.id)
    for field, value in changes.items():
        setattr(series, field, value)
    series.updated_by = actor(ctx)
    series.save()
    if changes:
        record_event(
            ctx,
            events.SERIES_UPDATED,
            {
                "id": str(series.id),
                "code": series.code,
                "year": series.year,
                "fields": sorted(
                    "next_number" if field == "current_number" else field
                    for field in changes
                ),
            },
        )
    return series_row(series)


# ── ERPlora's own invoices (its platform hub, PLAN-SAAS §4) ─────────────────────────────────────────────────────

PLATFORM_ORIGINAL_UNKNOWN = _(
    "The invoice this credit note rectifies (%(number)s) was never issued here: it has to arrive first."
)
#: The SaaS's number (``ERP-2026-00123``): the platform hub's series prints the same, though it never counts one.
PLATFORM_FORMAT = "{prefix}-{year}-{seq:05d}"
PLATFORM_SERIES_TYPES = {"ERP": "F1", "ERPR": "R1"}


def _platform_series(ctx: OperationContext, code: str, year: int) -> InvoiceSeries:
    """The series ``code`` of ``year``, born on first use with the SaaS's format, and its row locked until the
    COMMIT: two deliveries of the same invoice queue here, and the second finds what the first wrote."""
    InvoiceSeries.objects.bulk_create(
        [
            InvoiceSeries(
                code=code,
                year=year,
                name="ERPlora",
                invoice_type=PLATFORM_SERIES_TYPES[code],
                prefix=code,
                format=PLATFORM_FORMAT,
                created_by=actor(ctx),
            )
        ],
        ignore_conflicts=True,
    )
    return InvoiceSeries.objects.select_for_update().get(code=code, year=year)


def _platform_refusal(refused: platform.PlatformBodyRefused) -> Exception:
    if refused.code == "invoice.platform_recipient_required":
        return Conflict(refused.message, code=refused.code)
    if refused.code == "invoice.platform_original_unknown":
        return NotFound(refused.message, code=refused.code)
    return InvalidPayload(refused.message, code=refused.code)


@operation(
    "invoice.invoice.issue_platform",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it; /internal/platform/invoices calls it.
    permission="invoice.issue_platform",
    input=PlatformInvoiceIn,
    output=PlatformInvoiceOut,
    ai={
        "description": "System only: ERPlora's platform hub issues an invoice of ERPlora to a customer as the SaaS posts "
        "it (its number, date, payer, lines and tax treatment), with its VeriFactu record in the same transaction. "
        "Posting the same invoice again answers what it has.",
        "risk": "high",
    },
)
def issue_platform(ctx: OperationContext, data: PlatformInvoiceIn) -> dict:
    existing = find_platform_invoice(data.id)
    if existing is not None:
        return platform_answer(ctx, existing, already=True)
    body = data.model_dump(mode="json")
    issued_on = data.issued_on
    series = _platform_series(ctx, data.series, issued_on.year)
    # A second delivery waited for the series' lock: it answers what the first issued.
    existing = find_platform_invoice(data.id)
    if existing is not None:
        return platform_answer(ctx, existing, already=True)
    original = None
    if data.rectifies is not None:
        original = find_platform_invoice(data.rectifies.id, lock=True)
        if original is None:
            message = str(PLATFORM_ORIGINAL_UNKNOWN) % {"number": data.rectifies.number}
            raise NotFound(message, code="invoice.platform_original_unknown")
    try:
        fields = platform.to_invoice_fields(
            body,
            issuer=_issuer_copy(_configured_issuer()),
            original_type=original.invoice_type if original is not None else None,
        )
    except platform.PlatformBodyRefused as refused:
        raise _platform_refusal(refused) from None
    values = fields["invoice"]
    if Invoice.objects.filter(series_code=values["series_code"], number=values["number"]).exists():
        raise Conflict(
            str(NUMBER_TAKEN) % {"number": values["number"], "code": values["series_code"]},
            code="invoice.number_taken",
        )
    links = {"rectifies": original} if original is not None else {}
    invoice = _issue(
        ctx,
        series=series,
        invoice_type=values["invoice_type"],
        entries=values["tax_breakdown"],
        lines=fields["lines"],
        tolerance=fields["tolerance"],
        recipient={key: values[key] for key in values if key.startswith("customer_")},
        issuer={key: values[key] for key in values if key.startswith("issuer_")},
        operation_date=values["operation_date"],
        source_type=Invoice.Source.RECTIFICATION if original is not None else Invoice.Source.MANUAL,
        numbered=(values["sequence"], values["number"]),
        issue_date=values["issue_date"],
        description=values["description"],
        notes=values["notes"],
        currency=values["currency"],
        rectification_kind=values["rectification_kind"],
        platform_ref=data.id,
        language=data.language,
        **links,
    )
    if original is not None:
        left_over = remaining_of(original)
        if left_over == 0 and original.status != Invoice.Status.CANCELLED:
            original.status = Invoice.Status.CANCELLED
            original.save(update_fields=["status", "updated_at"])
        record_event(
            ctx,
            events.INVOICE_RECTIFIED,
            {
                "invoice_id": str(original.id),
                "number": original.number,
                "status": original.status,
                "rectification_id": str(invoice.id),
                "rectification_number": invoice.number,
                "remaining": left_over,
            },
        )
    return platform_answer(ctx, invoice)
