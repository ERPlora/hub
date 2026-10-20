"""The rules of the business's hours, without a database (engine.py): what an interval is, how a set of
intervals is checked, which rule governs a day, the spans of a day and «is it open?».

Cases from the old module's handler tests (``handler/src/lib.rs``, schedules#1, #2, #8, #10, #23, #28)
and its WORKFLOW (SCHEDULES-F02, F04, F05, F10, F11). 2026-08-17 is a Monday.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest

from apps.schedule.engine import (
    Calendar,
    ExceptionRule,
    Interval,
    IntervalError,
    WeeklyDay,
    is_open,
    normalize,
    parse_when,
    rule_for,
    span_text,
    spans_of,
)

MADRID = ZoneInfo("Europe/Madrid")


def t(text: str) -> dt.time:
    return dt.time.fromisoformat(text)


def iv(open_time: str, close_time: str) -> Interval:
    return Interval(t(open_time), t(close_time))


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


def weekly(*days: tuple[int, bool, list[Interval]]) -> dict[int, WeeklyDay]:
    return {
        weekday: WeeklyDay(uuid.uuid7(), closed, tuple(intervals))
        for weekday, closed, intervals in days
    }


def special(
    on: str, name: str, closed: bool = True, intervals=(), yearly: bool = False
) -> ExceptionRule:
    return ExceptionRule(
        uuid.uuid7(), d(on), d(on), name, closed, tuple(intervals), yearly
    )


def override(
    start: str, end: str, reason: str, closed: bool = True, intervals=()
) -> ExceptionRule:
    return ExceptionRule(
        uuid.uuid7(), d(start), d(end), reason, closed, tuple(intervals)
    )


# ── An interval ────────────────────────────────────────────────────────────────────────────────


def test_an_interval_closing_before_it_opens_crosses_midnight_and_00_00_twice_is_24_hours():
    assert iv("22:00", "02:00").overnight
    assert not iv("09:00", "18:00").overnight
    assert iv("00:00", "00:00").all_day
    assert not iv("00:00", "00:00").overnight
    assert iv("22:00", "02:00").minutes == (1320, 1560)
    assert iv("00:00", "00:00").minutes == (0, 1440)


def test_span_text_is_hh_mm_en_dash_hh_mm():
    assert span_text(iv("09:00", "14:00")) == "09:00–14:00"


# ── normalize: the rules of a set of intervals (schedules#8, #23) ──────────────────────────────


def test_intervals_are_sorted_by_their_opening():
    assert normalize([iv("17:00", "20:00"), iv("10:00", "14:00")]) == [
        iv("10:00", "14:00"),
        iv("17:00", "20:00"),
    ]


def test_seconds_never_matter():
    assert normalize([Interval(dt.time(9, 0, 30), dt.time(18, 0, 59))]) == [
        iv("09:00", "18:00")
    ]


def test_an_empty_interval_is_refused_but_00_00_00_00_is_24_hours():
    assert normalize([iv("00:00", "00:00")]) == [iv("00:00", "00:00")]
    with pytest.raises(IntervalError) as refused:
        normalize([iv("09:00", "13:00"), iv("10:00", "10:00")])
    assert refused.value.code == "empty"


@pytest.mark.parametrize(
    "intervals",
    [
        [iv("09:00", "14:00"), iv("13:00", "18:00")],
        [iv("10:00", "14:00"), iv("13:00", "20:00")],
        # An overnight interval followed by a later one the same evening.
        [iv("22:00", "02:00"), iv("23:00", "23:30")],
        # Through midnight: a 22:00–02:00 tail clashes with a 01:00 start.
        [iv("22:00", "02:00"), iv("01:00", "01:30")],
        # 24 hours leaves room for nothing else.
        [iv("00:00", "00:00"), iv("10:00", "11:00")],
    ],
)
def test_overlapping_intervals_are_refused(intervals):
    with pytest.raises(IntervalError) as refused:
        normalize(intervals)
    assert refused.value.code == "overlapping"


def test_touching_intervals_do_not_overlap():
    assert normalize([iv("09:00", "14:00"), iv("14:00", "18:00")]) == [
        iv("09:00", "14:00"),
        iv("14:00", "18:00"),
    ]
    assert normalize([iv("22:00", "02:00"), iv("02:00", "06:00")]) == [
        iv("02:00", "06:00"),
        iv("22:00", "02:00"),
    ]


def test_at_most_twelve_intervals_a_day():
    twelve = [iv(f"{hour:02d}:00", f"{hour:02d}:30") for hour in range(12)]
    assert len(normalize(twelve)) == 12
    with pytest.raises(IntervalError) as refused:
        normalize([*twelve, iv("20:00", "21:00")])
    assert refused.value.code == "too_many"


# ── rule_for: which rule governs a day (SCHEDULES-F10 precedence) ──────────────────────────────


def test_nothing_configured_is_no_rule():
    rule = rule_for(Calendar(), d("2026-08-17"))
    assert (rule.source, rule.rule_id, rule.is_closed, rule.intervals) == (
        "none",
        None,
        False,
        (),
    )


def test_the_weekly_day_governs_a_plain_date():
    week = weekly((0, False, [iv("09:00", "18:00")]))
    rule = rule_for(Calendar(weekly=week), d("2026-08-17"))
    assert (rule.source, rule.rule_id, rule.intervals) == (
        "weekly",
        week[0].id,
        (iv("09:00", "18:00"),),
    )
    # Tuesday has no row: nothing configured that day, even with Monday set.
    assert rule_for(Calendar(weekly=week), d("2026-08-18")).source == "none"


def test_special_day_beats_override_beats_weekly():
    christmas = special("2026-12-25", "Christmas")
    winter = override(
        "2026-12-20",
        "2026-12-31",
        "Winter",
        closed=False,
        intervals=[iv("10:00", "14:00")],
    )
    calendar = Calendar(
        weekly=weekly(
            (4, False, [iv("09:00", "18:00")]), (5, False, [iv("09:00", "18:00")])
        ),
        special_days=[christmas],
        overrides=[winter],
    )
    rule = rule_for(calendar, d("2026-12-25"))
    assert (rule.source, rule.rule_id, rule.name, rule.is_closed) == (
        "special_day",
        christmas.id,
        "Christmas",
        True,
    )
    rule = rule_for(calendar, d("2026-12-26"))
    assert (rule.source, rule.rule_id, rule.name) == ("override", winter.id, "Winter")
    assert rule_for(calendar, d("2027-01-01")).source == "weekly"


def test_the_exact_date_beats_a_yearly_one_and_a_yearly_one_holds_every_year_even_before_its_date():
    yearly = special("2026-12-25", "Christmas", yearly=True)
    exact = special(
        "2030-12-25", "Christmas 2030", closed=False, intervals=[iv("10:00", "13:00")]
    )
    calendar = Calendar(special_days=[yearly, exact])
    assert rule_for(calendar, d("2027-12-25")).rule_id == yearly.id
    assert rule_for(calendar, d("2020-12-25")).rule_id == yearly.id
    assert rule_for(calendar, d("2030-12-25")).rule_id == exact.id
    # Not yearly: only its own date.
    once = special("2026-08-15", "Assumption")
    assert rule_for(Calendar(special_days=[once]), d("2027-08-15")).source == "none"


def test_a_yearly_special_day_beats_a_temporary_change_covering_it():
    christmas = special("2020-12-25", "Christmas", yearly=True)
    winter = override(
        "2026-12-20",
        "2026-12-31",
        "Winter",
        closed=False,
        intervals=[iv("10:00", "14:00")],
    )
    calendar = Calendar(special_days=[christmas], overrides=[winter])
    rule = rule_for(calendar, d("2026-12-25"))
    assert (rule.source, rule.rule_id, rule.name, rule.is_closed) == (
        "special_day",
        christmas.id,
        "Christmas",
        True,
    )
    assert rule_for(calendar, d("2026-12-24")).rule_id == winter.id


def test_a_yearly_29_february_only_exists_in_leap_years():
    leap = special("2024-02-29", "Leap day", yearly=True)
    calendar = Calendar(special_days=[leap])
    assert rule_for(calendar, d("2028-02-29")).rule_id == leap.id
    assert rule_for(calendar, d("2027-02-28")).source == "none"
    assert rule_for(calendar, d("2027-03-01")).source == "none"


def test_two_yearly_days_on_the_same_day_and_month_the_newest_date_wins():
    old = special("2020-12-25", "Old")
    old_yearly = ExceptionRule(old.id, old.start, old.end, old.name, True, (), True)
    new = special("2025-12-25", "New", yearly=True)
    assert (
        rule_for(Calendar(special_days=[old_yearly, new]), d("2026-12-25")).rule_id
        == new.id
    )


def test_an_override_covers_both_ends_of_its_range():
    summer = override("2026-08-01", "2026-08-15", "Summer")
    calendar = Calendar(overrides=[summer])
    assert rule_for(calendar, d("2026-08-01")).rule_id == summer.id
    assert rule_for(calendar, d("2026-08-15")).rule_id == summer.id
    assert rule_for(calendar, d("2026-08-16")).source == "none"
    assert rule_for(calendar, d("2026-07-31")).source == "none"


# ── spans_of: the opening spans of a day, as wall-clock datetimes ──────────────────────────────


def test_spans_of_a_day_with_a_split_shift_an_overnight_and_24_hours():
    calendar = Calendar(
        weekly=weekly(
            (0, False, [iv("10:00", "14:00"), iv("22:00", "02:00")]),
            (1, False, [iv("00:00", "00:00")]),
        )
    )
    assert spans_of(rule_for(calendar, d("2026-08-17")), d("2026-08-17")) == [
        (at("2026-08-17T10:00"), at("2026-08-17T14:00")),
        (at("2026-08-17T22:00"), at("2026-08-18T02:00")),
    ]
    assert spans_of(rule_for(calendar, d("2026-08-18")), d("2026-08-18")) == [
        (at("2026-08-18T00:00"), at("2026-08-19T00:00"))
    ]


def test_a_closed_day_and_a_day_without_rule_have_no_span():
    calendar = Calendar(weekly=weekly((5, True, [])))
    assert spans_of(rule_for(calendar, d("2026-08-22")), d("2026-08-22")) == []
    assert spans_of(rule_for(calendar, d("2026-08-23")), d("2026-08-23")) == []


# ── is_open (SCHEDULES-F10) ────────────────────────────────────────────────────────────────────

SPLIT_MONDAY = weekly(
    (0, False, [iv("09:00", "14:00"), iv("16:00", "20:00")]),
    (1, True, []),
)


@pytest.mark.parametrize(
    ("moment", "code", "opened"),
    [
        ("2026-08-17T10:00", "open_interval", True),  # inside a span
        ("2026-08-17T15:00", "outside_hours", False),  # in the gap between spans
        ("2026-08-17T05:00", "outside_hours", False),
        ("2026-08-18T10:00", "closed_today", False),  # the weekday is closed
        ("2026-08-16T10:00", "no_hours", False),  # nothing configured for a Sunday
    ],
)
def test_is_open_answers_with_a_stable_code(moment, code, opened):
    verdict = is_open(Calendar(weekly=SPLIT_MONDAY), at(moment))
    assert (verdict.code, verdict.is_open) == (code, opened)
    assert verdict.reason == ""


def test_the_verdict_names_the_rule_and_the_spans_that_explain_it():
    calendar = Calendar(weekly=SPLIT_MONDAY)
    evening = is_open(calendar, at("2026-08-17T17:00"))
    assert (evening.source, evening.rule_id, evening.intervals) == (
        "weekly",
        SPLIT_MONDAY[0].id,
        ["16:00–20:00"],
    )
    gap = is_open(calendar, at("2026-08-17T15:00"))
    assert gap.intervals == ["09:00–14:00", "16:00–20:00"]
    nothing = is_open(calendar, at("2026-08-16T10:00"))
    assert (nothing.source, nothing.rule_id, nothing.intervals) == ("none", None, [])


def test_open_from_the_opening_and_closed_exactly_at_the_closing():
    calendar = Calendar(weekly=weekly((6, False, [iv("10:00", "20:00")])))
    assert not is_open(calendar, at("2026-08-23T09:59")).is_open
    assert is_open(calendar, at("2026-08-23T10:00")).is_open
    assert is_open(calendar, at("2026-08-23T19:59")).is_open
    assert not is_open(calendar, at("2026-08-23T20:00")).is_open


def test_an_overnight_interval_reaches_into_the_next_morning_and_24_hours_is_always_open():
    # Thursday 2026-08-20 22:00–02:00; Friday has no row of its own.
    calendar = Calendar(weekly=weekly((3, False, [iv("22:00", "02:00")])))
    assert is_open(calendar, at("2026-08-20T23:00")).is_open
    after_midnight = is_open(calendar, at("2026-08-21T01:00"))
    assert (after_midnight.is_open, after_midnight.code, after_midnight.intervals) == (
        True,
        "overnight_open",
        ["22:00–02:00"],
    )
    assert not is_open(calendar, at("2026-08-21T03:00")).is_open
    assert not is_open(calendar, at("2026-08-20T21:00")).is_open
    all_day = Calendar(weekly=weekly((3, False, [iv("00:00", "00:00")])))
    assert is_open(all_day, at("2026-08-20T00:00")).is_open
    assert is_open(all_day, at("2026-08-20T23:59")).is_open
    assert not is_open(all_day, at("2026-08-21T00:00")).is_open


def test_yesterdays_tail_opens_a_closed_day_too():
    calendar = Calendar(
        weekly=weekly((3, False, [iv("22:00", "02:00")]), (4, True, []))
    )
    tail = is_open(calendar, at("2026-08-21T01:00"))
    assert (tail.is_open, tail.code) == (True, "overnight_open")
    assert is_open(calendar, at("2026-08-21T10:00")).code == "closed_today"


def test_an_interval_belongs_to_the_day_it_opens_whatever_the_rule():
    # New Year's Eve open 22:00–02:00 by a special day: still open at 01:00 of a closed 1 January.
    eve = special(
        "2026-12-31", "New Year's Eve", closed=False, intervals=[iv("22:00", "02:00")]
    )
    new_year = special("2027-01-01", "New Year", closed=True)
    calendar = Calendar(special_days=[eve, new_year])
    assert is_open(calendar, at("2026-12-31T23:30")).is_open
    assert not is_open(calendar, at("2026-12-31T21:00")).is_open
    tail = is_open(calendar, at("2027-01-01T01:00"))
    assert (tail.is_open, tail.code, tail.source, tail.rule_id, tail.reason) == (
        True,
        "overnight_open",
        "special_day",
        eve.id,
        "New Year's Eve",
    )
    assert is_open(calendar, at("2027-01-01T03:00")).code == "exception_closed"
    # And a closed special day the evening before stops the weekly tail of that evening.
    week = weekly((1, False, [iv("22:00", "02:00")]))
    eve_closed = special("2026-12-22", "Closed", closed=True)
    assert not is_open(
        Calendar(weekly=week, special_days=[eve_closed]), at("2026-12-23T01:00")
    ).is_open


def test_a_winning_special_day_keeps_its_name_as_the_reason():
    calendar = Calendar(special_days=[special("2026-12-25", "Navidad")])
    verdict = is_open(calendar, at("2026-12-25T11:00"))
    assert (verdict.code, verdict.is_open, verdict.source, verdict.reason) == (
        "exception_closed",
        False,
        "special_day",
        "Navidad",
    )


def test_is_open_walks_every_interval_of_the_winning_special_day_and_override():
    eve = special(
        "2026-12-24",
        "Eve",
        closed=False,
        intervals=[iv("10:00", "13:00"), iv("17:00", "19:00")],
    )
    calendar = Calendar(special_days=[eve])
    assert is_open(calendar, at("2026-12-24T11:00")).is_open
    midday = is_open(calendar, at("2026-12-24T15:00"))
    assert (midday.is_open, midday.code, midday.source, midday.rule_id) == (
        False,
        "exception_hours",
        "special_day",
        eve.id,
    )
    assert midday.intervals == ["10:00–13:00", "17:00–19:00"]
    assert is_open(calendar, at("2026-12-24T18:00")).code == "exception_hours"
    assert not is_open(calendar, at("2026-12-24T20:00")).is_open

    summer = override(
        "2026-08-01",
        "2026-08-31",
        "Summer",
        closed=False,
        intervals=[iv("10:00", "13:30"), iv("18:00", "21:00")],
    )
    calendar = Calendar(overrides=[summer])
    assert is_open(calendar, at("2026-08-05T12:00")).is_open
    assert not is_open(calendar, at("2026-08-05T16:00")).is_open
    evening = is_open(calendar, at("2026-08-05T19:00"))
    assert (evening.is_open, evening.source, evening.rule_id, evening.reason) == (
        True,
        "override",
        summer.id,
        "Summer",
    )


def test_a_24_hours_exception_is_open_all_day():
    calendar = Calendar(
        special_days=[
            special("2026-12-24", "Eve", closed=False, intervals=[iv("00:00", "00:00")])
        ]
    )
    assert is_open(calendar, at("2026-12-24T03:00")).is_open
    assert is_open(calendar, at("2026-12-24T23:59")).is_open


def test_daylight_saving_does_not_move_the_opening_hours():
    # Hours are wall-clock: the last Sundays of March and October change nothing.
    calendar = Calendar(weekly=weekly((6, False, [iv("10:00", "20:00")])))
    for day in ("2026-03-29", "2026-10-25"):
        assert not is_open(calendar, at(f"{day}T09:59")).is_open
        assert is_open(calendar, at(f"{day}T10:00")).is_open
        assert not is_open(calendar, at(f"{day}T20:00")).is_open


# ── parse_when: the moment asked about, on the business clock (schedules#1) ────────────────────

NOW = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.UTC)


def test_an_instant_is_converted_to_the_business_zone():
    assert parse_when("2026-08-18T08:00:00Z", MADRID, NOW) == at("2026-08-18T10:00")
    assert parse_when("2026-08-18T08:00:00+00:00", MADRID, NOW) == at(
        "2026-08-18T10:00"
    )


def test_a_bare_wall_clock_is_taken_as_the_shops_own():
    assert parse_when("2026-08-18T10:00", MADRID, NOW) == at("2026-08-18T10:00")
    assert parse_when("2026-08-18 10:00:45", MADRID, NOW) == at("2026-08-18T10:00")


def test_no_moment_is_now_on_the_business_clock():
    # 20:00 UTC is 22:00 of Monday in Madrid and 10:00 of Tuesday in Kiritimati (+14).
    assert parse_when(None, MADRID, NOW) == at("2026-08-17T22:00")
    assert parse_when("", ZoneInfo("Pacific/Kiritimati"), NOW) == at("2026-08-18T10:00")


def test_the_business_day_rolls_over_on_the_business_clock():
    assert parse_when(
        None, MADRID, dt.datetime(2026, 8, 17, 23, 30, tzinfo=dt.UTC)
    ) == at("2026-08-18T01:30")


def test_the_daylight_saving_changes_are_the_zones_not_a_fixed_offset():
    # Spring forward: 00:30 UTC is 01:30 CET, 01:30 UTC is 03:30 CEST.
    assert parse_when("2026-03-29T00:30:00Z", MADRID, NOW) == at("2026-03-29T01:30")
    assert parse_when("2026-03-29T01:30:00Z", MADRID, NOW) == at("2026-03-29T03:30")
    # Autumn: 02:30 local happens twice.
    assert parse_when("2026-10-25T00:30:00Z", MADRID, NOW) == at("2026-10-25T02:30")
    assert parse_when("2026-10-25T01:30:00Z", MADRID, NOW) == at("2026-10-25T02:30")


@pytest.mark.parametrize(
    "text", ["tomorrow", "2026-02-31T10:00", "2026-08-18", "2026-08-18T25:00", "10:00"]
)
def test_a_moment_that_is_not_a_real_date_and_time_is_refused(text):
    with pytest.raises(ValueError):
        parse_when(text, MADRID, NOW)


def test_an_instant_out_of_the_calendar_is_a_value_error_not_an_overflow():
    for text in ("0001-01-01T00:30+01:00", "9999-12-31T23:30-01:00"):
        with pytest.raises(ValueError):
            parse_when(text, MADRID, NOW)
