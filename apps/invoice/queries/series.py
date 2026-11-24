"""Series (INVOICE-F11–F13): the list, one series, the number its next document will carry and what a series is born
with on its first use.
"""

from django.db.models import Exists, F, OuterRef, Q
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.invoice import fiscal
from apps.invoice.models import FACTORY_SERIES_NAMES, Invoice, InvoiceSeries
from apps.invoice.queries.rows import _page
from apps.invoice.schemas.series import SeriesDetailOut, SeriesListIn, SeriesPage, SeriesPeekIn, SeriesPeekOut
from apps.tax.queries import business_today

SERIES_NOT_FOUND = _("This numbering series does not exist.")


#: The code each kind of document is numbered in, and the type a series born for it takes.
TICKET, FULL, RECTIFYING = "TICKET", "FACT", "RECT"
FACTORY_TYPES = {TICKET: "F2", FULL: "F1", RECTIFYING: "R1"}


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


@operation(
    "invoice.series.list",
    kind="query",
    permission="invoice.view_invoice",
    input=SeriesListIn,
    output=SeriesPage,
    ai={
        "asks": {
            "en": (
                "which numbering series do we have?",
                "list this year's invoice series",
            ),
            "es": (
                "¿qué series de numeración tenemos?",
                "enséñame las series de facturas de este año",
                "¿qué prefijos usan nuestras series?",
            ),
        },
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
            code=(code or "").strip().upper(), year=year or business_today().year
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
        "asks": {
            "en": (
                "what number will the next invoice get?",
                "which number comes next in the FACT series?",
            ),
            "es": (
                "¿qué número llevará la próxima factura?",
                "¿cuál es el siguiente número de la serie FACT?",
            ),
        },
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
        "asks": {
            "en": (
                "show me this year's FACT series",
                "give me the details of the RECT series",
            ),
            "es": (
                "enséñame la serie FACT de este año",
                "¿cómo es la serie RECT?",
                "dame el detalle de la serie RECT",
            ),
        },
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
