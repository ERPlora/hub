"""The CSV of the working days (attendance.record.export): its header and lines, formulas defused, an employee's own
days only, and its file name after the dates."""

import csv
import datetime as dt
import io

import pytest
from live.errors import PermissionDenied

from apps.attendance import queries
from apps.attendance.schemas import ExportOut
from apps.staff.models import Member

from .conftest import HUB_DB, NOW, ctx_for, day, make_member, run

pytestmark = HUB_DB


# attendance.record.export: the CSV (ATTENDANCE-F10; the old csv.test.ts cases)


def rows_of(export: ExportOut) -> list[list[str]]:
    return list(csv.reader(io.StringIO(export.csv)))


def test_the_csv_header_and_its_lines(person, clock):
    clock(NOW)
    ana, _ = person()
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    day(
        ana,
        "2026-10-05T07:02:41",
        "2026-10-05T15:05:03",
        breaks=[("2026-10-05T11:00", "2026-10-05T11:30")],
        in_within_radius=True,
        out_within_radius=False,
    )
    day(gone, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    day(gone, "2026-10-04T08:00", status="needs_review")

    export = run(
        "attendance.record.export",
        {"date_from": "2026-10-01", "date_to": "2026-10-31", "sort": "clock_in_at"},
        ctx_for("hub_manager"),
    )

    assert isinstance(export, ExportOut)
    assert (export.filename, export.content_type, export.rows) == (
        "attendance-2026-10.csv",
        "text/csv",
        3,
    )
    assert export.csv.split("\r\n")[0] == (
        "date,user,clock_in,clock_out,break_minutes,worked_minutes,status,within_radius_in,within_radius_out"
    )
    assert export.csv.endswith("\r\n")
    assert rows_of(export)[1:] == [
        [
            "2026-10-04",
            "Carlos Gil",
            "2026-10-04 10:00",
            "",
            "0",
            "",
            "needs_review",
            "",
            "",
        ],
        [
            "2026-10-05",
            "Ana López",
            "2026-10-05 09:02",
            "2026-10-05 17:05",
            "30",
            "452",
            "closed",
            "1",
            "0",
        ],
        # Open: worked until the export instant, the running break taken off.
        [
            "2026-10-06",
            "Carlos Gil",
            "2026-10-06 10:00",
            "",
            "30",
            "120",
            "open",
            "",
            "",
        ],
    ]


def test_the_csv_defuses_formulas_and_quotes_commas(clock):
    clock(NOW)
    tricky = make_member('Pérez, Ana "La', 'jefa"')
    formula = make_member("=HYPERLINK(", '"x")')
    day(tricky, "2026-10-05T07:00", "2026-10-05T15:00")
    day(formula, "2026-10-06T07:00", "2026-10-06T08:00")
    text = run(
        "attendance.record.export", {"sort": "clock_in_at"}, ctx_for("hub_manager")
    ).csv
    assert '"Pérez, Ana ""La jefa"""' in text
    assert '"\'=HYPERLINK( ""x"")"' in text


def test_an_empty_filter_exports_only_the_header(person):
    _, ctx = person()
    export = run(
        "attendance.record.export",
        {"date_from": "2026-01-01", "date_to": "2026-01-31"},
        ctx,
    )
    assert (export.rows, export.csv.count("\r\n"), export.filename) == (
        0,
        1,
        "attendance-2026-01.csv",
    )


def test_an_employee_exports_only_their_own_days(person, clock):
    clock(NOW)
    ana, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    day(bea, "2026-10-05T07:00", "2026-10-05T15:00")
    assert [
        row[1] for row in rows_of(run("attendance.record.export", {}, ctx))[1:]
    ] == ["Ana López"]
    with pytest.raises(PermissionDenied):
        run("attendance.record.export", {"member_id": str(bea.id)}, ctx)


def test_the_file_name_follows_the_dates():
    assert (
        queries.exports.export_filename(dt.date(2026, 2, 1), dt.date(2026, 2, 28))
        == "attendance-2026-02.csv"
    )
    assert (
        queries.exports.export_filename(dt.date(2026, 2, 1), dt.date(2026, 2, 27))
        == "attendance-2026-02-01_2026-02-27.csv"
    )
    assert queries.exports.export_filename(None, None) == "attendance.csv"


def test_the_csv_writes_a_forgotten_day_as_needs_review_without_worked_time(person, clock):
    clock("2026-10-06T07:00")
    ana, _ = person()
    day(ana, "2026-10-05T07:00")
    line = rows_of(run("attendance.record.export", {}, ctx_for("hub_manager")))[1]
    assert line[4:7] == ["0", "", "needs_review"]
