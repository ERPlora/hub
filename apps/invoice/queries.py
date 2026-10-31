"""Read operations of the invoice app (``READ ONLY``), and how a document is read.

``invoice_row`` and ``invoice_detail`` are the one way a document becomes an output: the lists, the
detail, the document of a sale and every write (services.py) answer with them, so what the screen
shows and what the assistant reads never drift apart; the same for ``series_row`` and ``issuer_row``.
``document_of_sale`` finds the document in force of a sale (its full invoice when its ticket was
replaced). ``render_document`` writes the printable A4 document (``templates/invoice/invoice.html``)
in the reader's language.
"""

import datetime as dt
from decimal import Decimal

from babel.numbers import format_decimal, format_percent, get_currency_precision
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Sum, Window
from django.db.models.functions import Coalesce, Lag
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import AppInactive, Conflict, NotFound
from live.operations import UnknownOperation, operation
from live.operations import get as get_operation

from apps.invoice import fiscal
from apps.invoice.models import (
    FACTORY_SERIES_NAMES,
    Invoice,
    InvoiceLine,
    InvoiceSeries,
    Issuer,
)
from apps.invoice.schemas import (
    AllocationPage,
    AllocationsIn,
    BySourceIn,
    BySourceOut,
    DocumentIn,
    DocumentOut,
    GapPage,
    GapsIn,
    InvoiceGetIn,
    InvoiceListIn,
    InvoiceOut,
    InvoicePage,
    IssuerGetIn,
    IssuerOut,
    LineDefaultsIn,
    LineDefaultsOut,
    NumberingStatusIn,
    NumberingStatusOut,
    PlatformDocumentOut,
    PlatformHealthIn,
    PlatformHealthOut,
    PlatformInvoiceOut,
    PlatformRefIn,
    RectificationPreviewIn,
    RectificationPreviewOut,
    RefundGetIn,
    RefundOut,
    SeriesDetailOut,
    SeriesListIn,
    SeriesPage,
    SeriesPeekIn,
    SeriesPeekOut,
)
from apps.sale.models import Refund
from apps.sale.queries import find_sale
from apps.tax.queries import business_tax_kind, resolve_tax
from base.business import money_text

INVOICE_NOT_FOUND = _("Invoice not found.")
SERIES_NOT_FOUND = _("This numbering series does not exist.")
REFUND_NOT_FOUND = _("That refund does not exist.")

# Texts of the printed document (and its titles), in the reader's language.
DOC_INVOICE = _("Invoice")
DOC_SIMPLIFIED = _("Simplified invoice")
DOC_RECTIFYING = _("Rectifying invoice")
DOC_COPY = _("Copy")
TAX_VAT = _("VAT")
TAX_SURCHARGE = _("Equivalence surcharge")
# «Exento» and «No sujeto», as the invoice's screen says them, not taxes' «Exenta» and «No sujeta».
TAX_EXEMPT = pgettext_lazy("invoice", "Exempt")
TAX_EXEMPT_CAUSE = _("Exempt (%(cause)s)")
TAX_NOT_SUBJECT = pgettext_lazy("invoice", "Not subject")
TAX_REVERSE_CHARGE = _("Reverse charge")
RECTIFIES_NOTE = _("Rectifies invoice %(number)s. Reason: %(reason)s")
RECTIFIES_NOTE_NO_REASON = _("Rectifies invoice %(number)s.")
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

#: The code each kind of document is numbered in, and the type a series born for it takes.
TICKET, FULL, RECTIFYING = "TICKET", "FACT", "RECT"
FACTORY_TYPES = {TICKET: "F2", FULL: "F1", RECTIFYING: "R1"}


# ── Rows ────────────────────────────────────────────────────────────────────────────────────────


def with_links(invoices):
    """The queryset with what a row says about its links (the rectified number, a replaced ticket)."""
    return invoices.select_related("rectifies").annotate(
        substituted_flag=Exists(Invoice.objects.filter(substitutes=OuterRef("pk"))),
        rectification_count=Count("rectifications", distinct=True),
    )


def _flags(invoice: Invoice, *, substituted: bool, rectified: bool) -> dict:
    """What can still be done to a document: the row and the detail ask the same questions."""
    ordinary = not invoice.is_rectification
    return {
        "substituted": substituted,
        "can_mark_paid": ordinary and invoice.status == Invoice.Status.ISSUED,
        "can_rectify": ordinary
        and invoice.status != Invoice.Status.CANCELLED
        and not substituted,
        "can_substitute": invoice.invoice_type == "F2"
        and invoice.status != Invoice.Status.CANCELLED
        and not substituted
        and not rectified,
    }


def invoice_row(invoice: Invoice) -> dict:
    """An ``InvoiceRowOut`` (best through ``with_links``)."""
    substituted = getattr(invoice, "substituted_flag", None)
    if substituted is None:
        substituted = invoice.substitutions.exists()
    count = getattr(invoice, "rectification_count", None)
    rectified = invoice.rectifications.exists() if count is None else count > 0
    return {
        "id": invoice.id,
        "number": invoice.number,
        "invoice_type": invoice.invoice_type,
        "series_code": invoice.series_code,
        "year": invoice.year,
        "issue_date": invoice.issue_date,
        "issued_at": invoice.issued_at,
        "customer_name": invoice.customer_name,
        "customer_tax_id": invoice.customer_tax_id,
        "base_amount": invoice.base_amount,
        "tax_amount": invoice.tax_amount,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "currency_decimals": get_currency_precision(invoice.currency),
        "status": invoice.status,
        "source_type": invoice.source_type,
        "rectifies_id": invoice.rectifies_id,
        "rectifies_number": invoice.rectifies.number if invoice.rectifies_id else "",
        **_flags(invoice, substituted=substituted, rectified=rectified),
    }


def _link(invoice: Invoice | None) -> dict | None:
    if invoice is None:
        return None
    return {
        "id": invoice.id,
        "number": invoice.number,
        "invoice_type": invoice.invoice_type,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "total_amount": invoice.total_amount,
    }


def _line(line: InvoiceLine) -> dict:
    return {
        "id": line.id,
        "position": line.position,
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
    }


def remaining_of(invoice: Invoice) -> int:
    """What is left of a document after its rectifications (a rectification has nothing left)."""
    if invoice.is_rectification:
        return 0
    taken = invoice.rectifications.aggregate(total=Coalesce(Sum("total_amount"), 0))[
        "total"
    ]
    return invoice.total_amount + taken


def _loaded(invoice: Invoice) -> Invoice:
    return (
        Invoice.objects.select_related("rectifies", "substitutes", "source_sale")
        .prefetch_related(
            Prefetch("lines", queryset=InvoiceLine.objects.order_by("position", "id")),
            Prefetch(
                "rectifications", queryset=Invoice.objects.order_by("issued_at", "id")
            ),
        )
        .get(pk=invoice.pk)
    )


def invoice_detail(invoice: Invoice) -> dict:
    """An ``InvoiceOut``: the document with its lines, its breakdown and its links."""
    invoice = _loaded(invoice)
    substituted_by = Invoice.objects.filter(substitutes=invoice).first()
    rectifications = list(invoice.rectifications.all())
    row = invoice_row(invoice)
    row.update(
        _flags(
            invoice,
            substituted=substituted_by is not None,
            rectified=bool(rectifications),
        )
    )
    return {
        **row,
        "series_id": invoice.series_id,
        "sequence": invoice.sequence,
        "operation_date": invoice.operation_date,
        "issuer_name": invoice.issuer_name,
        "issuer_tax_id": invoice.issuer_tax_id,
        "issuer_address": invoice.issuer_address,
        "issuer_country": invoice.issuer_country,
        "customer_id": invoice.customer_id,
        "customer_address": invoice.customer_address,
        "customer_country": invoice.customer_country,
        "customer_id_type": invoice.customer_id_type,
        "description": invoice.description,
        "notes": invoice.notes,
        "tax_breakdown": invoice.tax_breakdown,
        "rectification_kind": invoice.rectification_kind,
        "sale_id": invoice.source_sale_id,
        "sale_number": invoice.source_sale.number if invoice.source_sale_id else "",
        "refund_id": invoice.source_refund_id,
        "rectifies": _link(invoice.rectifies),
        "substitutes": _link(invoice.substitutes),
        "substituted_by": _link(substituted_by),
        "rectifications": [_link(item) for item in rectifications],
        "remaining": remaining_of(invoice),
        "paid_at": invoice.paid_at,
        "created_by": invoice.created_by,
        "lines": [_line(line) for line in invoice.lines.all()],
    }


def find_invoice(invoice_id, number: str | None, *, lock: bool = False) -> Invoice:
    """The document named by its id or its number; ``NotFound`` when there is none."""
    invoices = Invoice.objects.select_for_update() if lock else Invoice.objects.all()
    if invoice_id is not None:
        invoice = invoices.filter(pk=invoice_id).first()
    else:
        invoice = (
            invoices.filter(number=(number or "").strip())
            .order_by("-issued_at", "-id")
            .first()
        )
    if invoice is None:
        raise NotFound(str(INVOICE_NOT_FOUND), code="invoice.not_found")
    return invoice


def document_of_sale(sale_id) -> Invoice | None:
    """The document in force of a sale: the one it was invoiced with, or the full invoice (F3) that
    replaced its ticket. ``None`` while it has none."""
    born = Invoice.objects.filter(
        source_sale_id=sale_id, source_type=Invoice.Source.SALE
    ).first()
    if born is None:
        return None
    return Invoice.objects.filter(substitutes=born).first() or born


def series_started(series: InvoiceSeries) -> bool:
    """The series numbered a document: its prefix, format and next number are frozen (the number is part of
    the VeriFactu chain). A series that starts at a later number, to continue another system, has not until its
    first document. A list annotates it as ``started``; a single series asks."""
    started = getattr(series, "started", None)
    if started is None:
        started = Invoice.objects.filter(series=series).exists()
    return started


def series_row(series: InvoiceSeries) -> dict:
    """A ``SeriesOut``: the series and the number its next document will carry."""
    return {
        "id": series.id,
        "code": series.code,
        "name": series.name,
        "display_name": series.display_name,
        "invoice_type": series.invoice_type,
        "year": series.year,
        "prefix": series.prefix,
        "format": series.format,
        "current_number": series.current_number,
        "next_number": fiscal.render_number(
            series.format,
            prefix=series.prefix,
            code=series.code,
            year=series.year,
            seq=series.current_number + 1,
        ),
        "format_locked": series_started(series),
        "is_active": series.is_active,
        "is_default": series.is_default,
    }


def issuer_row(issuer: Issuer | None) -> dict:
    """An ``IssuerOut``; an empty one while nothing is set up."""
    updated = issuer.updated_at if issuer is not None else None
    issuer = issuer or Issuer(legal_name="", tax_id="", address="")
    return {
        "configured": issuer.configured,
        "legal_name": issuer.legal_name,
        "tax_id": issuer.tax_id,
        "address": issuer.address,
        "postal_code": issuer.postal_code,
        "city": issuer.city,
        "province": issuer.province,
        "country": issuer.country,
        "address_line": issuer.address_line,
        "source": issuer.source,
        "synced_version": issuer.synced_version,
        "synced_at": issuer.synced_at,
        "updated_at": updated,
    }


# ── Invoices ────────────────────────────────────────────────────────────────────────────────────


#: A sort column → its ordering; every one ends with the newest first, then the id.
_SORTS = {
    "issued_at": ["issued_at"],
    "issue_date": ["issue_date", "issued_at"],
    "number": ["series_code", "year", "sequence"],
    "customer_name": ["customer_name"],
    "total_amount": ["total_amount"],
    "status": ["status"],
    "invoice_type": ["invoice_type"],
    "series_code": ["series_code", "year", "sequence"],
}


def _ordering(sort: str, direction: str) -> list:
    columns = [
        F(column).desc() if direction == "desc" else F(column).asc()
        for column in _SORTS[sort]
    ]
    tie = (
        [F("issued_at").desc(), F("id").desc()]
        if direction == "desc"
        else [F("issued_at").asc(), F("id").asc()]
    )
    return [*columns, *tie]


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    rows = list(queryset[params.offset : params.offset + params.limit])
    return {
        "rows": [row(item) for item in rows],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "invoice.invoice.list",
    kind="query",
    permission="invoice.view_invoice",
    input=InvoiceListIn,
    output=InvoicePage,
    expose_api=True,
    ai={
        "description": "List the invoices, the last issued first: search by number, customer's name or tax ID; filter "
        "by status (issued, paid, cancelled), type (F1, F2 ticket, F3, R1–R5), series, source, issue dates and total "
        "(cents). Pages of up to 100."
    },
)
def list_invoices(ctx: OperationContext, params: InvoiceListIn) -> dict:
    invoices = Invoice.objects.all()
    if params.search:
        text = params.search.strip()
        invoices = invoices.filter(
            Q(number__icontains=text)
            | Q(customer_name__icontains=text)
            | Q(customer_tax_id__icontains=text)
        )
    exact = {
        "status": params.status,
        "invoice_type": params.invoice_type,
        "series_code": params.series_code.strip().upper()
        if params.series_code
        else None,
        "source_type": params.source_type,
        "customer_id": params.customer_id,
        "issue_date__gte": params.issue_date_from,
        "issue_date__lte": params.issue_date_to,
        "total_amount__gte": params.total_amount_from,
        "total_amount__lte": params.total_amount_to,
    }
    invoices = invoices.filter(
        **{lookup: value for lookup, value in exact.items() if value is not None}
    )
    invoices = with_links(invoices).order_by(*_ordering(params.sort, params.dir))
    return _page(invoices, params, invoice_row)


@operation(
    "invoice.invoice.get",
    kind="query",
    permission="invoice.view_invoice",
    input=InvoiceGetIn,
    output=InvoiceOut,
    expose_api=True,
    ai={
        "description": "Read one invoice by its number (or id): its issuer, recipient, lines, tax breakdown, totals, "
        "status, and the documents it rectifies, replaces or is rectified or replaced by."
    },
)
def get_invoice(ctx: OperationContext, params: InvoiceGetIn) -> dict:
    return invoice_detail(find_invoice(params.invoice_id, params.number))


@operation(
    "invoice.invoice.by_source",
    kind="query",
    permission="invoice.view_invoice",
    input=BySourceIn,
    output=BySourceOut,
    expose_api=True,
    ai={
        "description": "The invoice in force of a sale (by the sale's number of the day or id): its ticket or invoice, "
        "or the full invoice that replaced its ticket. Found false while it has none."
    },
)
def by_source(ctx: OperationContext, params: BySourceIn) -> dict:
    sale = find_sale(params.sale_id, params.sale)
    document = document_of_sale(sale.id)
    return {
        "found": document is not None,
        "invoice": invoice_detail(document) if document else None,
    }


# ── The printable document ──────────────────────────────────────────────────────────────────────


def _money(cents: int | Decimal, currency: str, language: str) -> str:
    """Minor units of ``currency`` (12100 is 121.00 €, and ¥12,100: the yen has no cents); a unit price keeps the two
    more decimals the price without VAT may have (0.8264 €)."""
    return money_text(cents, currency, language=language)


def _percent(rate, language: str) -> str:
    return format_percent(
        Decimal(str(rate)) / 100, locale=language, decimal_quantization=False
    )


def _tax_label(item: dict, language: str) -> list[tuple[str, int, int]]:
    """The printed rows of a breakdown entry: ``(label, base, amount)``; a surcharge is its own row."""
    qualification = item["qualification"]
    if qualification == "exempt":
        cause = item.get("exempt_reason", "")
        label = (
            gettext(TAX_EXEMPT_CAUSE) % {"cause": cause}
            if cause
            else str(TAX_EXEMPT)
        )
    elif qualification in ("not_subject", "not_subject_location"):
        label = str(TAX_NOT_SUBJECT)
    elif qualification == "subject_reverse":
        label = gettext(TAX_REVERSE_CHARGE)
    else:
        name = gettext(TAX_VAT) if item["tax"] == "vat" else item["tax"].upper()
        label = f"{name} {_percent(item['rate'], language)}"
    rows = [(label, item["base"], item["quota"])]
    if Decimal(str(item.get("surcharge_rate", "0"))):
        rows.append(
            (
                f"{gettext(TAX_SURCHARGE)} {_percent(item['surcharge_rate'], language)}",
                item["base"],
                item["surcharge_quota"],
            )
        )
    return rows


def document_note(invoice: Invoice) -> str:
    """The note of a document in the reader's language: a rectifying one names the invoice it rectifies
    and its reason (composed here: the database keeps no sentence); any other, its own notes."""
    if invoice.rectifies_id:
        reason = invoice.description.strip()
        number = invoice.rectifies.number
        if reason:
            return gettext(RECTIFIES_NOTE) % {"number": number, "reason": reason}
        return gettext(RECTIFIES_NOTE_NO_REASON) % {"number": number}
    return invoice.notes


def render_document(invoice: Invoice, *, duplicate: bool = False, qr: dict | None = None) -> str:
    """The A4 document of an invoice, in the active language (``templates/invoice/invoice.html``); with ``qr``
    (``{"url", "svg"}``), VeriFactu's QR on top, as the AEAT asks (Orden HAC/1177/2024, art. 21)."""
    invoice = _loaded(invoice)
    language = translation.get_language() or "en"
    if invoice.is_rectification:
        title = DOC_RECTIFYING
    elif invoice.invoice_type == "F2":
        title = DOC_SIMPLIFIED
    else:
        title = DOC_INVOICE
    money = lambda cents: _money(cents, invoice.currency, language)  # noqa: E731
    lines = list(invoice.lines.all())
    discounted = any(line.discount_amount for line in lines)
    context = {
        "invoice": invoice,
        "language": language,
        "title": title,
        "duplicate": duplicate,
        "copy_label": DOC_COPY,
        "issue_date": date_format(invoice.issue_date, "SHORT_DATE_FORMAT"),
        "operation_date": date_format(invoice.operation_date, "SHORT_DATE_FORMAT")
        if invoice.operation_date != invoice.issue_date
        else "",
        # RD 1619/2012 art. 6.1.f: the unit price without VAT and the discount apart, the amount its base.
        "discounted": discounted,
        "lines": [
            {
                "description": line.description,
                "quantity": format_decimal(line.quantity.normalize(), locale=language),
                "unit_price": _money(line.unit_price, invoice.currency, language),
                "discount": money(line.discount_amount) if line.discount_amount else "",
                "tax_rate": _percent(line.tax_rate, language),
                "amount": money(line.base_amount),
            }
            for line in lines
        ],
        "taxes": [
            {"label": label, "base": money(base), "amount": money(amount)}
            for item in invoice.tax_breakdown
            for label, base, amount in _tax_label(item, language)
        ],
        "base": money(invoice.base_amount),
        "total": money(invoice.total_amount),
        "note": document_note(invoice),
        "qr": qr,
    }
    return render_to_string("invoice/invoice.html", context)


@operation(
    "invoice.invoice.document",
    kind="query",
    permission="invoice.view_invoice",
    input=DocumentIn,
    output=DocumentOut,
    expose_api=True,
    ai={
        "description": "The printable A4 document of an invoice (by its number), a whole HTML page in the reader's "
        "language: issuer, recipient, lines, tax breakdown, totals and what it rectifies. duplicate marks a copy."
    },
)
def document(ctx: OperationContext, params: DocumentIn) -> dict:
    invoice = find_invoice(params.invoice_id, params.number)
    with translation.override(ctx.language):
        html = render_document(invoice, duplicate=params.duplicate)
    return {"invoice_id": invoice.id, "number": invoice.number, "html": html}


# The general rate of a territory is the one of its generic categories: goods first, then services.
GENERAL_CATEGORIES = ("product.generic", "service.generic")


@operation(
    "invoice.invoice.line_defaults",
    kind="query",
    permission="invoice.add_invoice",
    input=LineDefaultsIn,
    output=LineDefaultsOut,
    ai={
        "description": "The rate a line of a manual invoice starts with when its rate is typed: the territory's "
        "general rate from its own rule in Taxes, or none when the territory has no rule of its own tax. The tax "
        "it is declared with is the territory's, read with tax.settings.get (VAT, IGIC in the Canary Islands, "
        "IPSI in Ceuta and Melilla)."
    },
)
def line_defaults(ctx: OperationContext, params: LineDefaultsIn) -> dict:
    """A typed rate is declared subject, with the territory's tax (TAX-F11): a rule of another tax (a regional one
    kept with another tax; the national VAT never applies in a territory with its own) or an exempt one is never
    proposed."""
    tax = business_tax_kind()
    for key in GENERAL_CATEGORIES:
        resolution = resolve_tax(category_key=key)
        if resolution and resolution.tax_kind == tax and resolution.operation_class == "subject":
            return {"tax_rate": resolution.root.rate_pct}
    return {"tax_rate": None}


# ── Refunds of the Sales app, as an invoice names them ──────────────────────────────────────────


@operation(
    "invoice.refund.get",
    kind="query",
    permission="invoice.view_invoice",
    input=RefundGetIn,
    output=RefundOut,
    expose_api=True,
    ai={
        "description": "Name a refund of the Sales app by its id: the sale it gives back, what it gave back and the "
        "number of its rectifying invoice, if issued."
    },
)
def get_refund(ctx: OperationContext, params: RefundGetIn) -> dict:
    refund = Refund.objects.select_related("sale").filter(pk=params.refund_id).first()
    if refund is None:
        raise NotFound(str(REFUND_NOT_FOUND), code="invoice.refund_not_found")
    sale = refund.sale
    with translation.override(ctx.language):
        given_back = money_text(refund.total, sale.currency)
    return {
        "id": refund.id,
        "sale_id": sale.id,
        "sale_number": sale.number,
        "total": refund.total,
        "currency": sale.currency,
        "currency_decimals": get_currency_precision(sale.currency),
        "invoice_number": refund.invoice_number,
        "label": f"{sale.number} · {given_back}",
    }


# ── Series ──────────────────────────────────────────────────────────────────────────────────────


@operation(
    "invoice.series.list",
    kind="query",
    permission="invoice.view_invoice",
    input=SeriesListIn,
    output=SeriesPage,
    ai={
        "description": "List the numbering series (this year's first): code, name, type, year, prefix, format, the "
        "current number and the number the next document will carry. Search by code or name."
    },
)
def list_series(ctx: OperationContext, params: SeriesListIn) -> dict:
    series = InvoiceSeries.objects.annotate(
        started=Exists(Invoice.objects.filter(series=OuterRef("pk")))
    )
    if params.search:
        text = params.search.strip()
        series = series.filter(Q(code__icontains=text) | Q(name__icontains=text))
    exact = {
        "code": params.code.strip().upper() if params.code else None,
        "invoice_type": params.invoice_type,
        "year": params.year,
        "is_active": params.is_active,
        "is_default": params.is_default,
    }
    series = series.filter(
        **{field: value for field, value in exact.items() if value is not None}
    )
    column = F(params.sort).desc() if params.dir == "desc" else F(params.sort).asc()
    series = series.order_by(column, F("year").desc(), "code", "id")
    return _page(series, params, series_row)


def find_series(series_id, code: str | None, year: int | None) -> InvoiceSeries:
    if series_id is not None:
        series = InvoiceSeries.objects.filter(pk=series_id).first()
    else:
        series = InvoiceSeries.objects.filter(
            code=(code or "").strip().upper(), year=year or timezone.localdate().year
        ).first()
    if series is None:
        raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")
    return series


@operation(
    "invoice.series.peek_next",
    kind="query",
    permission="invoice.view_invoice",
    input=SeriesPeekIn,
    output=SeriesPeekOut,
    expose_api=True,
    ai={
        "description": "Preview the number the next document of a series (by its code, this year, or its id) will "
        "carry, written with its own format, WITHOUT using it; and whether its format can still change."
    },
)
def peek_next(ctx: OperationContext, params: SeriesPeekIn) -> dict:
    series = find_series(params.series_id, params.code, params.year)
    row = series_row(series)
    return {
        "series_id": series.id,
        "code": series.code,
        "year": series.year,
        "next_sequence": series.current_number + 1,
        "next_number": row["next_number"],
        "format_locked": row["format_locked"],
    }


@operation(
    "invoice.series.get",
    kind="query",
    permission="invoice.view_invoice",
    input=SeriesPeekIn,
    output=SeriesDetailOut,
    expose_api=True,
    ai={
        "description": "Get one numbering series, active or not, by its id or by its code (this year, or the year "
        "said): what the Series screen shows of it and how it is named (code, year and name)."
    },
)
def get_series(ctx: OperationContext, params: SeriesPeekIn) -> dict:
    """Named as the Series screen's card titles it, with its name in the reader's language: «FACT · 2026 · Invoices»."""
    series = find_series(params.series_id, params.code, params.year)
    with translation.override(ctx.language):
        row = series_row(series)
    return {**row, "label": " · ".join(part for part in (row["code"], str(row["year"]), row["display_name"]) if part)}


def born_series_values(code: str, year: int) -> dict:
    """What the series ``code`` of ``year`` is born with on its first use: name, type, prefix and format (and
    whether it is active), inherited from the latest earlier year's, or a factory one's (the code as prefix).
    ``NotFound`` for an unknown code."""
    previous = (
        InvoiceSeries.objects.filter(code=code, year__lt=year).order_by("-year").first()
    )
    if previous is not None:
        return {
            "name": previous.name,
            "invoice_type": previous.invoice_type,
            "prefix": previous.prefix,
            "format": previous.format,
            "is_active": previous.is_active,
        }
    if code in FACTORY_TYPES:
        return {
            "name": FACTORY_SERIES_NAMES[code][0],
            "invoice_type": FACTORY_TYPES[code],
            "prefix": code,
        }
    raise NotFound(str(SERIES_NOT_FOUND), code="invoice.series_not_found")


def next_number_of(code: str, year: int) -> str:
    """The number the next document of the series ``code`` of ``year`` will carry, WITHOUT taking it nor creating
    the series: one not born yet starts at 1, written as it will be born."""
    series = InvoiceSeries.objects.filter(code=code, year=year).first()
    if series is not None:
        return series_row(series)["next_number"]
    values = born_series_values(code, year)
    return fiscal.render_number(
        values.get("format", ""), prefix=values["prefix"], code=code, year=year, seq=1
    )


# ── Rectifying (INVOICE-F07–F10): what a rectification issues, before it does ────────────────────


def rectifying_type(original: Invoice, chosen: str | None = None) -> str:
    """R5 for a ticket; for a full invoice the type chosen, R1 by default (a refund is art. 80 Two)."""
    return "R5" if original.is_simplified else (chosen or "R1")


def rectifiable(
    original: Invoice, today: dt.date, issue_date: dt.date | None = None
) -> int:
    """What is left of ``original`` to rectify by hand, dated ``today`` (``issue_date``: the date asked, if any); a
    ``Conflict`` saying why when it cannot be: a rectifying invoice, a cancelled one, a ticket replaced by a full
    invoice, another day than today, nothing left."""
    if original.is_rectification:
        raise Conflict(
            str(CANNOT_RECTIFY_RECTIFICATION),
            code="invoice.cannot_rectify_rectification",
        )
    if original.status == Invoice.Status.CANCELLED:
        raise Conflict(str(ALREADY_CANCELLED), code="invoice.already_cancelled")
    if Invoice.objects.filter(substitutes=original).exists():
        raise Conflict(str(SUBSTITUTED), code="invoice.substituted")
    if (issue_date is not None and issue_date != today) or original.issue_date > today:
        raise Conflict(
            str(RECTIFY_DATE),
            code="invoice.rectify_date_not_allowed",
            fields={"issue_date": str(RECTIFY_DATE)},
        )
    left_over = remaining_of(original)
    if left_over <= 0:
        raise Conflict(str(NOTHING_LEFT), code="invoice.nothing_left")
    return left_over


def key_line(item: dict, description: str, returned: dict | None) -> dict:
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


def rectification_figures(
    original: Invoice,
    *,
    amount: int,
    line_description: str,
    returned: dict[fiscal.FiscalKey, tuple[int, str]] | None = None,
) -> tuple[list[dict], list[dict], bool]:
    """The breakdown and the lines of the rectification by differences of ``amount`` cents of what is left of
    ``original``, and whether it is the whole original: the whole original negated (breakdown and lines) when nothing
    rectified it yet and the amount is its total; else what is left prorated key by key — over the keys of the
    articles ``returned`` (their worth and their text, per key) when a refund brings them back — with one line per
    key at its own rate. What the preview says and what the rectification writes are these same figures."""
    previous = list(original.rectifications.all())
    if not previous and amount == original.total_amount:
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
        return entries, lines, True
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
    lines = [key_line(item, line_description, returned) for item in entries]
    return entries, lines, False


@operation(
    "invoice.invoice.rectification_preview",
    kind="query",
    permission="invoice.rectify_invoice",
    input=RectificationPreviewIn,
    output=RectificationPreviewOut,
    expose_api=True,
    ai={
        "description": "The rectifying invoice that rectifying an invoice (by its number) with that reason and type "
        "would issue now, before issuing it: the invoice it rectifies (number, date, customer, total and what is left "
        "of it), its type (R1 by default, R5 for a ticket), the reason, this year's RECT series and the next number "
        "(NOT reserved: say it as the next one), today's date, and its base, tax, total and lines in negative. Changes "
        "nothing and takes no number. Read it before rectifying and tell the person this preview; when the invoice "
        "cannot be rectified it says why, and there is nothing to rectify."
    },
)
def rectification_preview(
    ctx: OperationContext, params: RectificationPreviewIn
) -> dict:
    original = find_invoice(params.invoice_id, params.number)
    today = timezone.localdate()
    left_over = rectifiable(original, today)
    entries, lines, whole = rectification_figures(
        original, amount=left_over, line_description=params.reason
    )
    base = sum(item["base"] for item in entries)
    tax = sum(item["quota"] + item["surcharge_quota"] for item in entries)
    return {
        "original": {
            "invoice_id": original.id,
            "number": original.number,
            "invoice_type": original.invoice_type,
            "issue_date": original.issue_date,
            "customer_name": original.customer_name,
            "total_amount": original.total_amount,
            "remaining": left_over,
        },
        "invoice_type": rectifying_type(original, params.rectification_type),
        "reason": params.reason,
        "series_code": RECTIFYING,
        "next_number": next_number_of(RECTIFYING, today.year),
        "issue_date": today,
        "whole": whole,
        "base_amount": base,
        "tax_amount": tax,
        "total_amount": base + tax,
        "currency": original.currency,
        "currency_decimals": get_currency_precision(original.currency),
        "lines": [
            {
                "description": line["description"],
                "quantity": line["quantity"],
                "tax_rate": line["tax_rate"],
                "base_amount": line["base_amount"],
                "total_amount": line["total_amount"],
            }
            for line in lines
        ],
    }


# ── The numbering ───────────────────────────────────────────────────────────────────────────────


@operation(
    "invoice.numbering.status",
    kind="query",
    permission="invoice.view_invoice",
    input=NumberingStatusIn,
    output=NumberingStatusOut,
    ai={
        "description": "Whether this year's invoice numbering is set up: how many ordinary series (F1, F2, F3), "
        "rectifying series (R1–R5) and default series the business year has, and how many series in all."
    },
)
def numbering_status(ctx: OperationContext, params: NumberingStatusIn) -> dict:
    year = timezone.localdate().year
    this_year = InvoiceSeries.objects.filter(year=year)
    ordinary = this_year.filter(invoice_type__in=("F1", "F2", "F3")).count()
    rectifying = this_year.filter(invoice_type__startswith="R").count()
    return {
        "fiscal_year": year,
        "ordinary_series": ordinary,
        "rectifying_series": rectifying,
        "default_series": this_year.filter(is_default=True).count(),
        "total_series": InvoiceSeries.objects.count(),
        "configured": ordinary > 0 and rectifying > 0,
    }


@operation(
    "invoice.numbering.gaps",
    kind="query",
    permission="invoice.view_invoice",
    input=GapsIn,
    output=GapPage,
    expose_api=True,
    ai={
        "description": "The gaps of the invoice numbering: one row per missing stretch inside a series and year (after "
        "which number, from which, the next one recorded and how many are missing). None means it is correlative."
    },
)
def numbering_gaps(ctx: OperationContext, params: GapsIn) -> dict:
    documents = Invoice.objects.all()
    if params.code:
        documents = documents.filter(series_code=params.code.strip().upper())
    if params.year:
        documents = documents.filter(year=params.year)
    with_previous = documents.annotate(
        previous=Window(
            Lag("sequence"),
            partition_by=[F("series_code"), F("year")],
            order_by=F("sequence").asc(),
        )
    )
    gaps = (
        with_previous.filter(previous__isnull=False, sequence__gt=F("previous") + 1)
        .order_by("series_code", "year", "sequence")
        .values("series_code", "year", "sequence", "previous")
    )
    total = len(gaps)
    rows = [
        {
            "series_code": gap["series_code"],
            "year": gap["year"],
            "after_sequence": gap["previous"],
            "missing_from": gap["previous"] + 1,
            "next_recorded": gap["sequence"],
            "missing_count": gap["sequence"] - gap["previous"] - 1,
        }
        for gap in list(gaps)[params.offset : params.offset + params.limit]
    ]
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def _allocation(invoice: Invoice) -> dict:
    return {
        "series_code": invoice.series_code,
        "year": invoice.year,
        "sequence": invoice.sequence,
        "number": invoice.number,
        "invoice_id": invoice.id,
        "invoice_type": invoice.invoice_type,
        "issued_at": invoice.issued_at,
    }


@operation(
    "invoice.numbering.allocations",
    kind="query",
    permission="invoice.view_invoice",
    input=AllocationsIn,
    output=AllocationPage,
    expose_api=True,
    ai={
        "description": "The numbering book: one row per number handed out, by series, year and sequence, with the "
        "number written and the document behind it. Search by number or series code."
    },
)
def allocations(ctx: OperationContext, params: AllocationsIn) -> dict:
    documents = Invoice.objects.all()
    if params.search:
        text = params.search.strip()
        documents = documents.filter(
            Q(number__icontains=text) | Q(series_code__icontains=text)
        )
    if params.code:
        documents = documents.filter(series_code=params.code.strip().upper())
    if params.year:
        documents = documents.filter(year=params.year)
    return _page(
        documents.order_by("series_code", "year", "sequence", "id"), params, _allocation
    )


# ── The issuer ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "invoice.issuer.get",
    kind="query",
    permission="invoice.view_invoice",
    input=IssuerGetIn,
    output=IssuerOut,
    ai={
        "description": "The issuer of the invoices: the business's legal name, tax ID and address, whether it is set "
        "up (without it no document is issued) and whether it came from the ERPlora account."
    },
)
def get_issuer(ctx: OperationContext, params: IssuerGetIn) -> dict:
    return issuer_row(Issuer.objects.first())


# ── ERPlora's own invoices (its platform hub, PLAN-SAAS §4) ─────────────────────────────────────────────────────

PLATFORM_UNKNOWN = _("This ERPlora invoice was never issued here.")
PLATFORM_ISSUER_MISSING = _("The platform hub has no issuer: run create_platform_hub.")
PLATFORM_VERIFACTU_MISSING = _("VeriFactu does not answer in the platform hub.")
VERIFACTU_BY_INVOICE = "verifactu.record.by_invoice"
VERIFACTU_RECORD = "verifactu.record.get"
VERIFACTU_CONFIG = "verifactu.config.get"
#: The record's statuses the SaaS reads as «issued»: sealed, on its way to the AEAT.
ON_ITS_WAY = ("pending", "sent")
#: What the AEAT registered: only then does the document print the QR (the old SaaS, saas#1054).
IN_THE_AEAT = ("accepted", "accepted_with_errors")


def find_platform_invoice(platform_ref, *, lock: bool = False) -> Invoice | None:
    """ERPlora's invoice the SaaS keys by ``platform_ref``, or ``None``."""
    queryset = Invoice.objects.select_for_update() if lock else Invoice.objects
    return queryset.filter(platform_ref=platform_ref).first()


def _platform_invoice(platform_ref) -> Invoice:
    invoice = find_platform_invoice(platform_ref)
    if invoice is None:
        raise NotFound(str(PLATFORM_UNKNOWN), code="invoice.platform_unknown")
    return invoice


def _ask_verifactu(ctx: OperationContext, name: str, data: dict):
    """VeriFactu's answer to ``name`` (asked by name: Invoicing never imports it), or ``None`` without VeriFactu."""
    try:
        op = get_operation(name)
        return op(ctx, op.input.model_validate(data))
    except (UnknownOperation, AppInactive):
        return None


def _record_of(ctx: OperationContext, invoice: Invoice):
    answer = _ask_verifactu(ctx, VERIFACTU_BY_INVOICE, {"invoice_id": str(invoice.id)})
    return answer.record if answer is not None else None


def platform_answer(ctx: OperationContext, invoice: Invoice, *, already: bool = False) -> dict:
    """What the SaaS hears of one of its invoices: ``issuing`` without a record yet, ``issued`` while its record is
    on its way to the AEAT, else the AEAT's answer (with its code and message when it found a flaw); its QR link."""
    record = _record_of(ctx, invoice)
    if record is None:
        return {"status": "issuing", "qr": "", "error": None, "already": already}
    status = "issued" if record.status in ON_ITS_WAY else record.status
    error = None
    if status in ("rejected", "accepted_with_errors"):
        full = _ask_verifactu(ctx, VERIFACTU_RECORD, {"record_id": str(record.id)})
        error = {"code": full.aeat_code, "message": full.aeat_message}
    return {"status": status, "qr": record.qr_url, "error": error, "already": already}


@operation(
    "invoice.invoice.platform_status",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformRefIn,
    output=PlatformInvoiceOut,
    ai={
        "description": "System only: how an invoice of ERPlora stands in its platform hub (by the SaaS's id): issuing, "
        "issued, or what the AEAT answered, with its QR link."
    },
)
def platform_status(ctx: OperationContext, data: PlatformRefIn) -> dict:
    return platform_answer(ctx, _platform_invoice(data.id))


@operation(
    "invoice.invoice.platform_document",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformRefIn,
    output=PlatformDocumentOut,
    ai={
        "description": "System only: the A4 document of an invoice of ERPlora (by the SaaS's id), in its own language, "
        "with VeriFactu's QR once the AEAT registered it."
    },
)
def platform_document(ctx: OperationContext, data: PlatformRefIn) -> dict:
    invoice = _platform_invoice(data.id)
    record = _record_of(ctx, invoice)
    qr = (
        {"url": record.qr_url, "svg": record.qr_svg}
        if record is not None and record.status in IN_THE_AEAT
        else None
    )
    with translation.override(invoice.language or ctx.language):
        html = render_document(invoice, qr=qr)
    return {"invoice_id": invoice.id, "number": invoice.number, "html": html}


@operation(
    "invoice.invoice.platform_health",
    kind="query",
    permission="invoice.issue_platform",
    input=PlatformHealthIn,
    output=PlatformHealthOut,
    ai={
        "description": "System only: whether the platform hub can issue ERPlora's invoices now (its issuer is set and "
        "VeriFactu answers); what is missing otherwise."
    },
)
def platform_health(ctx: OperationContext, data: PlatformHealthIn) -> dict:
    issuer = Issuer.objects.first()
    if issuer is None or not issuer.configured:
        return {"ready": False, "detail": str(PLATFORM_ISSUER_MISSING)}
    if _ask_verifactu(ctx, VERIFACTU_CONFIG, {}) is None:
        return {"ready": False, "detail": str(PLATFORM_VERIFACTU_MISSING)}
    return {"ready": True, "detail": ""}
