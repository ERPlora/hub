"""The working days of a filter as a CSV for the accountant or a labour inspection: attendance.record.export."""

import calendar
import csv
import datetime as dt
import io
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.operations import operation

from apps.attendance.models import Record
from apps.attendance.schemas import ExportOut, RecordExportIn
from base.business import business_zone

from .days import durations, effective_status, scoped_records
from .reads import review_hours

CSV_HEADER = (
    pgettext_lazy("attendance export", "Date"),
    pgettext_lazy("attendance export", "Person"),
    pgettext_lazy("attendance export", "Clock-in"),
    pgettext_lazy("attendance export", "Clock-out"),
    pgettext_lazy("attendance export", "Break minutes"),
    pgettext_lazy("attendance export", "Worked minutes"),
    pgettext_lazy("attendance export", "Status"),
    pgettext_lazy("attendance export", "Clock-in within radius"),
    pgettext_lazy("attendance export", "Clock-out within radius"),
)
YES, NO = pgettext_lazy("attendance export", "Yes"), pgettext_lazy("attendance export", "No")
#: What a spreadsheet runs as a formula when a cell starts with it (OWASP «CSV injection»).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def export_filename(date_from: dt.date | None, date_to: dt.date | None) -> str:
    """``attendance-2026-10.csv`` for a whole month, the dates for another range, else ``attendance.csv``."""
    if date_from is None or date_to is None:
        return "attendance.csv"
    last_day = calendar.monthrange(date_from.year, date_from.month)[1]
    if date_from.day == 1 and date_to == date_from.replace(day=last_day):
        return f"attendance-{date_from:%Y-%m}.csv"
    return f"attendance-{date_from.isoformat()}_{date_to.isoformat()}.csv"


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def _local(instant: dt.datetime | None) -> str:
    return (
        ""
        if instant is None
        else timezone.localtime(instant, business_zone()).strftime("%Y-%m-%d %H:%M")
    )


def _flag(value: bool | None) -> str:
    return "" if value is None else str(YES if value else NO)


@operation(
    "attendance.record.export",
    kind="query",
    permission="attendance.clock",
    input=RecordExportIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "export this month's clock-ins to CSV",
                "download October's working days for the labour inspection",
                "give me last week's working days as a CSV",
            ),
            "es": (
                "exporta los fichajes del mes en CSV",
                "descarga las jornadas de octubre para la inspección de trabajo",
                "saca en CSV las jornadas de la semana pasada",
            ),
        },
        "description": "Exports the working days of the filter (every page) as a CSV for the accountant or a "
        "labour inspection: date, person, clock-in, clock-out, break and worked minutes, status and "
        "whether it was clocked within the workplace radius. An employee exports only their own."
    },
)
def export_records(ctx: OperationContext, params: RecordExportIn) -> dict:
    as_of = timezone.now()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    count = 0
    hours = review_hours()
    with translation.override(ctx.language):
        writer.writerow([str(title) for title in CSV_HEADER])
        for record in scoped_records(ctx, params, as_of, hours):
            breaks, worked = durations(record, as_of, hours)
            writer.writerow(
                [
                    record.work_date.isoformat(),
                    _cell(record.member_name),
                    _local(record.clock_in_at),
                    _local(record.clock_out_at),
                    breaks // 60,
                    "" if worked is None else worked // 60,
                    str(Record.Status(effective_status(record, hours, as_of)).label),
                    _flag(record.in_within_radius),
                    _flag(record.out_within_radius),
                ]
            )
            count += 1
    return {
        "filename": export_filename(params.date_from, params.date_to),
        "content_type": "text/csv",
        "rows": count,
        "csv": buffer.getvalue(),
    }
