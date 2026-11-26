"""The lists of the special days and of the temporary changes: their intervals, search, filters, sort and pages."""

import datetime as dt

from apps.schedule.schemas.overrides import OverrideListIn
from apps.schedule.schemas.special_days import SpecialDayListIn

from .conftest import HUB_DB, make_override, make_special_day
from .test_queries import run, t

pytestmark = HUB_DB


def test_special_days_with_their_intervals_by_date():
    christmas = make_special_day(
        "2026-12-25", "Christmas", recurring_yearly=True, notes="Family"
    )
    eve = make_special_day(
        "2026-12-24", "Christmas Eve", ("17:00", "19:00"), ("10:00", "13:00")
    )
    page = run("schedule.special_day.list", SpecialDayListIn())
    assert page.total == 2
    assert [row.id for row in page.rows] == [eve.id, christmas.id]
    assert [(i.open_time, i.close_time) for i in page.rows[0].intervals] == [
        (t("10:00"), t("13:00")),
        (t("17:00"), t("19:00")),
    ]
    assert (
        page.rows[1].is_closed,
        page.rows[1].recurring_yearly,
        page.rows[1].notes,
        page.rows[1].intervals,
    ) == (
        True,
        True,
        "Family",
        [],
    )


def test_special_days_search_filter_sort_and_page():
    make_special_day("2026-01-06", "Epiphany")
    make_special_day("2026-08-15", "Assumption", notes="Town fair")
    make_special_day("2026-12-25", "Christmas", recurring_yearly=True)
    make_special_day("2026-12-24", "Christmas Eve", ("10:00", "13:00"))

    def names(**params):
        return [
            row.name
            for row in run("schedule.special_day.list", SpecialDayListIn(**params)).rows
        ]

    assert names(search="christmas") == ["Christmas Eve", "Christmas"]
    assert names(search="fair") == ["Assumption"]
    assert names(name="ep") == ["Epiphany"]
    assert names(date_from=dt.date(2026, 8, 1), date_to=dt.date(2026, 12, 24)) == [
        "Assumption",
        "Christmas Eve",
    ]
    assert names(is_closed=False) == ["Christmas Eve"]
    assert names(recurring_yearly=True) == ["Christmas"]
    assert names(sort="name") == [
        "Assumption",
        "Christmas",
        "Christmas Eve",
        "Epiphany",
    ]
    assert names(sort="date", dir="desc") == [
        "Christmas",
        "Christmas Eve",
        "Assumption",
        "Epiphany",
    ]
    page = run("schedule.special_day.list", SpecialDayListIn(limit=2, offset=2))
    assert ([row.name for row in page.rows], page.total, page.limit, page.offset) == (
        ["Christmas Eve", "Christmas"],
        4,
        2,
        2,
    )


def test_temporary_changes_with_their_intervals_by_start():
    summer = make_override(
        "2026-07-01",
        "2026-08-31",
        "Summer hours",
        ("18:00", "21:00"),
        ("10:00", "13:30"),
    )
    easter = make_override("2026-04-01", "2026-04-05", "Easter")
    page = run("schedule.override.list", OverrideListIn())
    assert [row.id for row in page.rows] == [easter.id, summer.id]
    assert [(i.open_time, i.close_time) for i in page.rows[1].intervals] == [
        (t("10:00"), t("13:30")),
        (t("18:00"), t("21:00")),
    ]
    assert (page.rows[0].is_closed, page.rows[0].intervals) == (True, [])


def test_temporary_changes_search_filter_and_sort():
    make_override("2026-04-01", "2026-04-05", "Easter")
    make_override("2026-07-01", "2026-08-31", "Summer hours", ("10:00", "14:00"))
    make_override("2026-11-02", "2026-11-03", "Works")

    def reasons(**params):
        return [
            row.reason
            for row in run("schedule.override.list", OverrideListIn(**params)).rows
        ]

    assert reasons(search="summer") == ["Summer hours"]
    assert reasons(reason="o") == ["Summer hours", "Works"]
    assert reasons(start_from=dt.date(2026, 5, 1)) == ["Summer hours", "Works"]
    assert reasons(start_to=dt.date(2026, 7, 1)) == ["Easter", "Summer hours"]
    assert reasons(end_from=dt.date(2026, 8, 31), end_to=dt.date(2026, 11, 2)) == [
        "Summer hours"
    ]
    assert reasons(is_closed=True) == ["Easter", "Works"]
    assert reasons(sort="reason", dir="desc") == ["Works", "Summer hours", "Easter"]
    assert reasons(sort="end_date", dir="desc") == ["Works", "Summer hours", "Easter"]


def test_a_descending_sort_breaks_its_ties_by_id_descending_too():
    # The tie-break follows the direction (``base/ordering.py``), so a touched row does not
    # jump and the pages neither repeat nor lose rows (WORKBOOK «Para quien lo mantiene», «Listas»).
    holidays = sorted(
        [make_special_day("2026-01-06", "Holiday").id, make_special_day("2026-05-01", "Holiday").id]
    )
    works = sorted(
        [
            make_override("2026-02-01", "2026-02-02", "Works").id,
            make_override("2026-03-01", "2026-03-02", "Works").id,
        ]
    )

    def ids(name, params):
        return [row.id for row in run(name, params).rows]

    assert ids("schedule.special_day.list", SpecialDayListIn(sort="name")) == holidays
    assert ids("schedule.special_day.list", SpecialDayListIn(sort="name", dir="desc")) == holidays[::-1]
    assert ids("schedule.override.list", OverrideListIn(sort="reason")) == works
    assert ids("schedule.override.list", OverrideListIn(sort="reason", dir="desc")) == works[::-1]
