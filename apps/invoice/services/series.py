"""Numbering series (INVOICE-F12, F13): created, and changed only as far as the VeriFactu chain allows.
"""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.invoice import events, fiscal
from apps.invoice.models import InvoiceSeries
from apps.invoice.queries import series_row, series_started
from apps.invoice.schemas import SeriesCreateIn, SeriesOut, SeriesUpdateIn
from apps.invoice.services.numbering import SERIES_NOT_FOUND
from apps.invoice.services.writes import actor

SERIES_EXISTS = _("There is already a series with that code that year.")


SERIES_LOCKED = _(
    "This series has already issued invoices, so its prefix, its format and its next number can no longer "
    "change: the number is part of the VeriFactu chain. Create a new series if you need others."
)


NUMBER_TOO_LONG = _(
    "The numbers of this series would not fit in 60 characters (VeriFactu's limit): shorten the prefix or "
    "the format."
)


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="invoice.manage_series",
    input=SeriesCreateIn,
    output=SeriesOut,
    ai={
        "asks": {
            "en": (
                "create a new invoice series for the online shop",
                "add a numbering series called Eventos for 2027",
                "add a series for the airport shop",
            ),
            "es": (
                "crea una serie nueva para las facturas de la tienda online",
                "añade una serie de numeración Eventos para 2027",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="invoice.manage_series",
    input=SeriesUpdateIn,
    output=SeriesOut,
    ai={
        "asks": {
            "en": (
                "rename the Obras series to Works",
                "deactivate the Obras invoice series",
            ),
            "es": (
                "cambia el nombre de la serie Obras a Trabajos",
                "desactiva la serie de facturas Obras",
            ),
        },
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
