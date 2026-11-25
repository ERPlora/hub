"""The numbering (INVOICE-F14, F15): whether this year's series are set up, its gaps and the book of numbers handed
out.
"""

from django.db.models import F, Q, Window
from django.db.models.functions import Lag
from live.context import OperationContext
from live.operations import operation

from apps.invoice.models import Invoice
from apps.invoice.queries.rows import _page
from apps.invoice.queries.series import business_series
from apps.invoice.schemas.numbering import (
    AllocationPage,
    AllocationsIn,
    GapPage,
    GapsIn,
    NumberingStatusIn,
    NumberingStatusOut,
)
from apps.tax.queries.jurisdiction import business_today


@operation(
    "invoice.numbering.status",
    kind="query",
    permission="invoice.view_invoice",
    input=NumberingStatusIn,
    output=NumberingStatusOut,
    ai={
        "asks": {
            "en": (
                "is this year's invoice numbering ready?", "is the numbering set up for this year's invoices?",
                "are the numbers ready for the new year?", "is the numbering ready for January?",
            ),
            "es": (
                "¿tenemos lista la numeración de este año?", "¿hay series de este año para empezar a facturar?",
                "¿falta preparar algo en la numeración del año nuevo?",
            ),
        },
        "description": "Whether this year's invoice numbering is set up: how many ordinary series (F1, F2, F3), "
        "rectifying series (R1–R5) and default series the business year has, and how many series in all. Nothing has "
        "to be done for the numbering to work: the series are created on their own with the first sale, so configured "
        "false does not mean something is left to do. A series is created by hand only to change the prefix or the "
        "format, or to continue another system's numbering, on /invoice/series before the first sale."
    },
)
def numbering_status(ctx: OperationContext, params: NumberingStatusIn) -> dict:
    year = business_today().year
    own = business_series(ctx)
    this_year = own.filter(year=year)
    ordinary = this_year.filter(invoice_type__in=("F1", "F2", "F3")).count()
    rectifying = this_year.filter(invoice_type__startswith="R").count()
    return {
        "fiscal_year": year,
        "ordinary_series": ordinary,
        "rectifying_series": rectifying,
        "default_series": this_year.filter(is_default=True).count(),
        "total_series": own.count(),
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
        "asks": {
            "en": (
                "are there gaps in the invoice numbers?",
                "is our invoice numbering correlative?",
                "is there a skipped number in our invoice numbering?",
            ),
            "es": (
                "¿falta algún número entre las facturas?",
                "¿la numeración de las facturas es correlativa?",
            ),
        },
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
        "asks": {
            "en": (
                "which document got number FACT-2025-000317?",
                "which number went to which document this year?",
                "show me this year's ledger of numbers handed out",
            ),
            "es": (
                "¿qué documento lleva el número FACT-2025-000317?",
                "enséñame el libro de números de este año",
            ),
        },
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
