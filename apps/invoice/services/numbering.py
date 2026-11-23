"""Series and numbers (INVOICE-F11): a series of a year is born on first use, and its next number is taken with
``UPDATE … RETURNING`` inside the document's transaction.
"""

from django.db.models import F
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict

from apps.invoice import fiscal
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.queries.series import born_series_values
from apps.invoice.services.writes import actor

SERIES_NOT_FOUND = _("This numbering series does not exist.")


NUMBER_TAKEN = _(
    "The number %(number)s already exists in series %(code)s: give the series a format with the year."
)


def series_of_year(
    code: str, year: int, ctx: OperationContext | None = None
) -> InvoiceSeries:
    """The series ``code`` of ``year``, born on first use: it inherits name, type, prefix and format from
    the latest earlier year's (or is a factory one: the code as prefix). ``NotFound`` for an unknown code."""
    existing = InvoiceSeries.objects.filter(code=code, year=year).first()
    if existing is not None:
        return existing
    values = born_series_values(code, year)
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
