"""The Excel of the issued invoices (INVOICE-F24): what the list shows for its search and filters, as the accountant reads
it. A document has a row per tax rate, and each row's total is its base, its tax and its surcharge: the column adds up
to the invoices' totals."""

import base64
import calendar
import datetime as dt
import io
from collections.abc import Iterable, Iterator
from decimal import Decimal

import xlsxwriter
from babel.numbers import get_currency_precision
from django.utils import translation
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.operations import operation

from apps.invoice import fiscal
from apps.invoice.models import Invoice
from apps.invoice.queries.invoices import filter_invoices
from apps.invoice.queries.ownership import ALL_INVOICES
from apps.invoice.schemas.export import InvoiceExportIn, InvoiceExportOut

CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILE_NAME = pgettext_lazy("invoice export", "invoices")
SHEET_NAME = pgettext_lazy("invoice export", "Invoices")
NUMBER = pgettext_lazy("invoice export", "Number")
DATE = pgettext_lazy("invoice export", "Date")
CUSTOMER = pgettext_lazy("invoice export", "Customer")
TAX_ID = pgettext_lazy("invoice export", "Tax ID")
BASE = pgettext_lazy("invoice export", "Taxable base")
RATE = pgettext_lazy("invoice export", "Rate %")
QUOTA = pgettext_lazy("invoice export", "Tax")
SURCHARGE_RATE = pgettext_lazy("invoice export", "Surcharge rate %")
SURCHARGE = pgettext_lazy("invoice export", "Surcharge")
TOTAL = pgettext_lazy("invoice export", "Total")

#: What a column holds, which says how its cells are written.
TEXT, DAY, AMOUNT, PERCENT = "text", "day", "amount", "percent"


@operation(
    "invoice.invoice.export",
    kind="query",
    permission=ALL_INVOICES,
    input=InvoiceExportIn,
    output=InvoiceExportOut,
    expose_api=True,
    ai={
        # Every customer's name and tax ID in a file for a person to download: no automation runs it alone.
        "risk": "high",
        "asks": {
            "en": (
                "download the invoices of October in Excel for my accountant",
                "give me an Excel file with this quarter's invoices",
                "export what we invoiced this month to a spreadsheet",
            ),
            "es": (
                "descárgame en Excel las facturas de octubre para la gestoría",
                "pásame un Excel con las facturas emitidas este trimestre",
                "exporta a una hoja de cálculo lo que hemos facturado este mes",
            ),
        },
        "description": "Writes an Excel file of the issued invoices for the accountant, as the invoice list shows them "
        "for the same search and filters (issue dates, status, type, series, source), cancelled and rectifying ones "
        "included: a row per invoice and tax rate with its number, date, customer, tax ID, taxable base, rate, tax and "
        "equivalence surcharge if any.",
    },
)
def export_invoices(ctx: OperationContext, params: InvoiceExportIn) -> dict:
    invoices = list(
        filter_invoices(ctx, params)
        .order_by("issue_date", "series_code", "year", "sequence", "id")
        .only("number", "issue_date", "customer_name", "customer_tax_id", "currency", "tax_breakdown")
    )
    with translation.override(ctx.language):
        rows = list(_rows(invoices))
        columns = _columns(any("surcharge" in row for row in rows))
        return {
            "filename": _filename(params.issue_date_from, params.issue_date_to),
            "content_type": CONTENT_TYPE,
            "invoices": len(invoices),
            "content_base64": base64.b64encode(_workbook(columns, rows)).decode("ascii"),
        }


def _columns(surcharged: bool) -> list[tuple[str, object, str]]:
    """``(key, header, kind)`` of every column; the surcharge's two only in a file that has one."""
    surcharge = [("surcharge_rate", SURCHARGE_RATE, PERCENT), ("surcharge", SURCHARGE, AMOUNT)]
    return [
        ("number", NUMBER, TEXT),
        ("date", DATE, DAY),
        ("customer", CUSTOMER, TEXT),
        ("tax_id", TAX_ID, TEXT),
        ("base", BASE, AMOUNT),
        ("rate", RATE, PERCENT),
        ("quota", QUOTA, AMOUNT),
        *(surcharge if surcharged else []),
        ("total", TOTAL, AMOUNT),
    ]


def _rows(invoices: Iterable[Invoice]) -> Iterator[dict]:
    """A row per entry of each invoice's breakdown; the money in the units of its currency."""
    for invoice in invoices:
        decimals = get_currency_precision(invoice.currency)
        for entry in invoice.tax_breakdown:
            key = fiscal.key_of(entry)
            surcharge = entry.get("surcharge_quota", 0)
            row = {
                "number": invoice.number,
                "date": invoice.issue_date,
                "customer": invoice.customer_name,
                "tax_id": invoice.customer_tax_id,
                "base": _amount(entry["base"], decimals),
                "rate": float(key.rate),
                "quota": _amount(entry["quota"], decimals),
                "total": _amount(fiscal.gross_of(entry), decimals),
                "decimals": decimals,
            }
            if surcharge or key.surcharge_rate:
                row["surcharge_rate"] = float(key.surcharge_rate)
                row["surcharge"] = _amount(surcharge, decimals)
            yield row


def _amount(cents: int, decimals: int) -> float:
    return float(Decimal(cents).scaleb(-decimals))


def _filename(date_from: dt.date | None, date_to: dt.date | None) -> str:
    """``invoices-2026-10.xlsx`` for a whole month, its two days for another period, else ``invoices.xlsx``."""
    name = str(FILE_NAME)
    if date_from is None or date_to is None:
        return f"{name}.xlsx"
    last_day = calendar.monthrange(date_from.year, date_from.month)[1]
    if date_from.day == 1 and date_to == date_from.replace(day=last_day):
        return f"{name}-{date_from:%Y-%m}.xlsx"
    return f"{name}-{date_from.isoformat()}_{date_to.isoformat()}.xlsx"


def _workbook(columns: list[tuple[str, object, str]], rows: Iterable[dict]) -> bytes:
    """The workbook with its one sheet: the headers, then a row per item. A customer's own words are always text, never
    a formula, whatever they start with."""
    buffer = io.BytesIO()
    with xlsxwriter.Workbook(buffer, {"in_memory": True}) as book:
        formats: dict[tuple[str, int], object] = {}

        def cell_format(kind: str, decimals: int):
            if (kind, decimals) not in formats:
                formats[kind, decimals] = book.add_format({"num_format": _number_format(kind, decimals)})
            return formats[kind, decimals]

        sheet = book.add_worksheet(str(SHEET_NAME))
        bold = book.add_format({"bold": True})
        for at, (_key, header, kind) in enumerate(columns):
            sheet.set_column(at, at, 20 if kind == TEXT else 14)
            sheet.write_string(0, at, str(header), bold)
        sheet.freeze_panes(1, 0)
        for line, row in enumerate(rows, start=1):
            for at, (key, _header, kind) in enumerate(columns):
                _write(sheet, (line, at), row.get(key), cell_format(kind, row["decimals"]))
    return buffer.getvalue()


def _number_format(kind: str, decimals: int) -> str:
    if kind == DAY:
        return "dd/mm/yyyy"
    if kind == AMOUNT:
        return "#,##0." + "0" * decimals if decimals else "#,##0"
    return "@" if kind == TEXT else "General"


def _write(sheet, at: tuple[int, int], value, cell_format) -> None:
    """A text, a day or a number as what it is; nothing in the cell of an empty text or a missing value."""
    if isinstance(value, str):
        if value:
            sheet.write_string(*at, value, cell_format)
    elif isinstance(value, dt.date):
        sheet.write_datetime(*at, dt.datetime.combine(value, dt.time()), cell_format)
    elif value is not None:
        sheet.write_number(*at, value, cell_format)
