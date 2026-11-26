"""Is it open? (SCHEDULE-F10): the business's own week and exceptions, read on its clock, now if no moment."""

import datetime as dt

import pytest
from django.utils import timezone

from .conftest import HUB_DB, make_day, make_override, make_special_day
from .test_queries import is_open

pytestmark = HUB_DB


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``timezone.now`` at an instant."""

    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


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
