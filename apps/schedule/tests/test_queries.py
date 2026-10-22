"""Read operations of the schedule app: the week, the special days, the temporary changes, the settings,
«is it open?» and the hours of a range of days (the appointment book's contract)."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone, translation
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.schedule.models import ScheduleSettings
from apps.schedule.queries import day_label, resolve_override, resolve_special_day
from apps.schedule.schemas import (
    HoursRangeIn,
    IsOpenIn,
    NoParamsIn,
    OverrideListIn,
    SpecialDayListIn,
)

from .conftest import ctx_for, make_day, make_override, make_special_day

pytestmark = pytest.mark.django_db

NINE_TO_SIX = [{"open_time": dt.time(9), "close_time": dt.time(18)}]


def run(name, data=None, role="hub_admin", **ctx):
    op = get(name)
    return get(name)(ctx_for(role, **ctx), data if data is not None else op.input())


def t(value):
    return dt.time.fromisoformat(value)


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``timezone.now`` at an instant."""

    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


# ── Permissions ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("schedule.week.get", NoParamsIn()),
        ("schedule.special_day.list", SpecialDayListIn()),
        ("schedule.override.list", OverrideListIn()),
        ("schedule.settings.get", NoParamsIn()),
        ("schedule.business.is_open", IsOpenIn()),
        ("schedule.hours.for_range", HoursRangeIn(date_from=dt.date(2026, 8, 17))),
    ],
)
def test_every_role_sees_the_hours_and_nobody_else(name, data):
    for role in ("hub_owner", "hub_admin", "hub_manager", "hub_employee"):
        run(name, data, role)
    with pytest.raises(PermissionDenied):
        run(name, data, permissions=set())


# ── The week (SCHEDULE-F01) ────────────────────────────────────────────────────────────────────


def test_the_week_is_born_as_the_default_one_unconfirmed():
    week = run("schedule.week.get")
    assert (week.week_starts_on, week.confirmed, week.timezone) == (
        1,
        False,
        "Europe/Madrid",
    )
    assert [(d.weekday, d.name, d.is_set, d.is_closed) for d in week.days] == [
        (0, "Monday", True, False),
        (1, "Tuesday", True, False),
        (2, "Wednesday", True, False),
        (3, "Thursday", True, False),
        (4, "Friday", True, False),
        (5, "Saturday", True, True),
        (6, "Sunday", True, True),
    ]
    assert [i.model_dump() for i in week.days[0].intervals] == NINE_TO_SIX
    assert week.days[5].intervals == []


def test_the_week_always_has_seven_days_a_missing_one_is_not_set(empty_week):
    make_day(2, ("10:00", "14:00"), ("17:00", "20:00"))
    week = run("schedule.week.get")
    assert len(week.days) == 7
    assert [d.is_set for d in week.days] == [
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert week.days[0].id is None and week.days[0].intervals == []
    assert [(i.open_time, i.close_time) for i in week.days[2].intervals] == [
        (t("10:00"), t("14:00")),
        (t("17:00"), t("20:00")),
    ]


def test_the_intervals_of_a_day_come_in_opening_order():
    make_day(1, ("17:00", "20:00"), ("10:00", "14:00"))
    assert [i.open_time for i in run("schedule.week.get").days[1].intervals] == [
        t("10:00"),
        t("17:00"),
    ]


def test_the_week_starts_on_the_day_of_the_settings():
    ScheduleSettings.objects.create(week_starts_on=7, hours_confirmed=True)
    week = run("schedule.week.get")
    assert [d.weekday for d in week.days] == [6, 0, 1, 2, 3, 4, 5]
    assert (week.week_starts_on, week.confirmed) == (7, True)
    ScheduleSettings.objects.update(week_starts_on=3)
    assert [d.weekday for d in run("schedule.week.get").days] == [2, 3, 4, 5, 6, 0, 1]


def test_the_day_names_speak_the_readers_language():
    with translation.override("es"):
        assert [d.name for d in run("schedule.week.get").days][:3] == [
            "Lunes",
            "Martes",
            "Miércoles",
        ]


# ── Special days ───────────────────────────────────────────────────────────────────────────────


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


# ── Temporary changes ──────────────────────────────────────────────────────────────────────────


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


# ── References by name, date or id (the assistant's) ───────────────────────────────────────────


def test_a_special_day_is_found_by_id_name_or_date():
    christmas = make_special_day("2026-12-25", "Christmas", recurring_yearly=True)
    make_special_day("2026-12-24", "Christmas Eve")
    assert resolve_special_day(christmas.id, None) == christmas
    assert (
        resolve_special_day(None, "christmas") == christmas
    )  # the exact name beats a part of another
    assert resolve_special_day(None, "2026-12-25") == christmas
    # A yearly one also answers for its day and month of another year.
    assert resolve_special_day(None, "2027-12-25") == christmas
    with pytest.raises(NotFound):
        resolve_special_day(None, "Easter")
    with pytest.raises(NotFound):
        resolve_special_day(uuid.uuid7(), None)


def test_a_name_that_fits_several_special_days_names_them():
    make_special_day("2026-05-01", "Local holiday A")
    make_special_day("2026-09-08", "Local holiday B")
    with pytest.raises(Conflict) as refused:
        resolve_special_day(None, "local")
    assert refused.value.code == "schedule.ambiguous_reference"
    assert (
        "Local holiday A" in refused.value.message
        and "Local holiday B" in refused.value.message
    )


def test_a_temporary_change_is_found_by_id_reason_or_a_date_it_covers():
    summer = make_override(
        "2026-07-01", "2026-08-31", "Summer hours", ("10:00", "14:00")
    )
    assert resolve_override(None, "summer") == summer
    assert resolve_override(None, "2026-08-15") == summer
    with pytest.raises(NotFound):
        resolve_override(None, "2026-09-01")


# ── A day ready to say (Appointments' and Reservations' «…_date_label») ──────────────────────────


def test_a_day_is_said_with_its_weekday_in_the_language_asked_whatever_the_thread_speaks():
    tuesday = dt.date(2030, 3, 5)
    with translation.override("en"):
        assert day_label(tuesday, "es") == "martes, 5 de marzo de 2030"
        assert translation.get_language() == "en"
    with translation.override("es"):
        assert day_label(tuesday, "en") == "Tuesday, March 5, 2030"


# ── Settings (SCHEDULE-F08, F09) ───────────────────────────────────────────────────────────────


def test_the_settings_are_the_defaults_until_saved_with_the_business_zone():
    settings = run("schedule.settings.get")
    assert (settings.week_starts_on, settings.hours_confirmed, settings.timezone) == (
        1,
        False,
        "Europe/Madrid",
    )
    ScheduleSettings.objects.create(week_starts_on=7)
    assert run("schedule.settings.get").week_starts_on == 7


# ── Is it open? (SCHEDULE-F10) ─────────────────────────────────────────────────────────────────


def is_open(when=None):
    return run("schedule.business.is_open", IsOpenIn(when=when))


def test_is_open_reads_the_hubs_own_week(empty_week):
    monday = make_day(0, ("09:00", "14:00"), ("16:00", "20:00"))
    make_day(1, closed=True)
    verdict = is_open("2026-08-17T10:00")
    assert (verdict.is_open, verdict.code, verdict.source, verdict.rule_id) == (
        True,
        "open_interval",
        "weekly",
        monday.id,
    )
    assert (verdict.today, verdict.current_time, verdict.timezone, verdict.reason) == (
        dt.date(2026, 8, 17),
        "10:00",
        "Europe/Madrid",
        None,
    )
    assert is_open("2026-08-17T15:00").code == "outside_hours"
    assert is_open("2026-08-18T10:00").code == "closed_today"
    assert is_open("2026-08-19T10:00").code == "no_hours"


def test_an_instant_is_read_on_the_business_clock(empty_week):
    make_day(1, ("09:00", "18:00"))
    # 08:00 UTC is 10:00 in Madrid (summer time).
    verdict = is_open("2026-08-18T08:00:00Z")
    assert (verdict.is_open, verdict.today, verdict.current_time) == (
        True,
        dt.date(2026, 8, 18),
        "10:00",
    )


def test_without_a_moment_it_answers_for_now(empty_week, frozen_now):
    make_day(1, ("09:00", "18:00"))
    # 23:30 UTC of Monday is already 01:30 of Tuesday in Madrid.
    frozen_now(dt.datetime(2026, 8, 17, 23, 30, tzinfo=dt.UTC))
    verdict = is_open()
    assert (verdict.today, verdict.current_time, verdict.code) == (
        dt.date(2026, 8, 18),
        "01:30",
        "outside_hours",
    )


def test_a_special_day_or_a_change_decides_with_its_name_as_the_reason():
    christmas = make_special_day("2026-12-25", "Navidad")
    summer = make_override(
        "2026-08-01", "2026-08-31", "Summer hours", ("10:00", "14:00")
    )
    verdict = is_open("2026-12-25T11:00")
    assert (
        verdict.is_open,
        verdict.code,
        verdict.source,
        verdict.rule_id,
        verdict.reason,
    ) == (
        False,
        "exception_closed",
        "special_day",
        christmas.id,
        "Navidad",
    )
    verdict = is_open("2026-08-17T12:00")
    assert (
        verdict.is_open,
        verdict.source,
        verdict.rule_id,
        verdict.reason,
        verdict.intervals,
    ) == (
        True,
        "override",
        summer.id,
        "Summer hours",
        ["10:00–14:00"],
    )


def test_the_tail_of_yesterdays_overnight_interval_is_open(empty_week):
    make_day(4, ("22:00", "02:00"))
    make_day(5, closed=True)
    verdict = is_open("2026-08-22T01:00")
    assert (verdict.is_open, verdict.code) == (True, "overnight_open")


# ── The hours of a range (SCHEDULE-F11: the appointment book's contract) ───────────────────────


def hours(date_from, date_to=None):
    return run(
        "schedule.hours.for_range",
        HoursRangeIn(
            date_from=dt.date.fromisoformat(date_from),
            date_to=date_to and dt.date.fromisoformat(date_to),
        ),
    )


def test_the_hours_of_each_day_of_a_range_with_its_rule_and_spans(empty_week):
    make_day(0, ("10:00", "14:00"), ("22:00", "02:00"))
    make_day(1, closed=True)
    christmas = make_special_day("2026-08-19", "Local holiday", ("10:00", "13:00"))
    summer = make_override("2026-08-20", "2026-08-21", "Inventory")
    answer = hours("2026-08-17", "2026-08-23")
    assert answer.timezone == "Europe/Madrid"
    assert [(day.date, day.source, day.is_closed, day.name) for day in answer.days] == [
        (dt.date(2026, 8, 17), "weekly", False, ""),
        (dt.date(2026, 8, 18), "weekly", True, ""),
        (dt.date(2026, 8, 19), "special_day", False, "Local holiday"),
        (dt.date(2026, 8, 20), "override", True, "Inventory"),
        (dt.date(2026, 8, 21), "override", True, "Inventory"),
        (dt.date(2026, 8, 22), "none", False, ""),
        (dt.date(2026, 8, 23), "none", False, ""),
    ]
    monday = answer.days[0]
    assert [(s.start, s.end) for s in monday.spans] == [
        (dt.datetime(2026, 8, 17, 10), dt.datetime(2026, 8, 17, 14)),
        (dt.datetime(2026, 8, 17, 22), dt.datetime(2026, 8, 18, 2)),
    ]
    assert answer.days[1].spans == []
    assert (
        answer.days[2].rule_id == christmas.id and answer.days[3].rule_id == summer.id
    )
    assert answer.days[5].rule_id is None and answer.days[5].spans == []


def test_one_day_alone_and_a_yearly_special_day_of_another_year():
    make_special_day("2020-12-25", "Christmas", recurring_yearly=True)
    answer = hours("2026-12-25")
    assert [(day.date, day.source, day.name) for day in answer.days] == [
        (dt.date(2026, 12, 25), "special_day", "Christmas")
    ]


def test_a_24_hours_day_spans_until_the_next_midnight(empty_week):
    make_day(5, ("00:00", "00:00"))
    assert [(s.start, s.end) for s in hours("2026-08-22").days[0].spans] == [
        (dt.datetime(2026, 8, 22, 0), dt.datetime(2026, 8, 23, 0))
    ]


def test_the_ends_of_the_allowed_calendar_answer(empty_week):
    # 1900-01-01 is a Monday; 2200-12-31 a Wednesday. An overnight interval at either end stays a date.
    make_day(0, ("22:00", "02:00"))
    make_day(2, ("22:00", "02:00"))
    first = hours("1900-01-01")
    assert [(s.start, s.end) for s in first.days[0].spans] == [(dt.datetime(1900, 1, 1, 22), dt.datetime(1900, 1, 2, 2))]
    last = hours("2200-12-31")
    assert [(s.start, s.end) for s in last.days[0].spans] == [(dt.datetime(2200, 12, 31, 22), dt.datetime(2201, 1, 1, 2))]
    assert is_open("1900-01-01T23:00").is_open
    assert is_open("2200-12-31T23:30+00:00").code == "overnight_open"
