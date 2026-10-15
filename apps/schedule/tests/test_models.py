"""The schedule app's tables and the rules the database itself keeps: one row per weekday, one special day
per date, a range that ends after it starts, intervals that are never empty (00:00–00:00 is 24 hours),
one settings row, UUIDv7 keys, and intervals that go with their day."""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)
from apps.schedule.tests.conftest import d, make_day, make_override, make_special_day, t

pytestmark = pytest.mark.django_db


def refused(create) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        create()


def test_keys_are_uuid7():
    for row in (make_day(0, ("09:00", "18:00")), make_special_day(), make_override()):
        assert isinstance(row.pk, uuid.UUID) and row.pk.version == 7


def test_one_row_per_weekday_monday_to_sunday():
    make_day(0, ("09:00", "18:00"))
    refused(lambda: WeekDay.objects.create(weekday=0, is_closed=True))
    refused(lambda: WeekDay.objects.create(weekday=7, is_closed=True))


def test_an_interval_is_never_empty_but_00_00_00_00_is_24_hours():
    day = make_day(2, closed=False)
    WeekDayInterval.objects.create(
        day=day, position=0, open_time=t("00:00"), close_time=t("00:00")
    )
    refused(
        lambda: WeekDayInterval.objects.create(
            day=day, position=1, open_time=t("10:00"), close_time=t("10:00")
        )
    )
    # Closing before opening crosses midnight: allowed.
    WeekDayInterval.objects.create(
        day=day, position=2, open_time=t("22:00"), close_time=t("02:00")
    )


def test_one_interval_per_position_of_a_day():
    day = make_day(3, ("09:00", "14:00"))
    refused(
        lambda: WeekDayInterval.objects.create(
            day=day, position=0, open_time=t("16:00"), close_time=t("20:00")
        )
    )


def test_the_intervals_go_with_their_day_in_order():
    day = make_day(1, ("16:00", "20:00"), ("09:00", "14:00"))
    assert [(i.position, i.open_time) for i in day.intervals.all()] == [
        (0, t("16:00")),
        (1, t("09:00")),
    ]
    day_id = day.pk
    day.delete()
    assert not WeekDayInterval.objects.filter(day_id=day_id).exists()


def test_one_special_day_per_date():
    make_special_day("2026-12-25", "Christmas")
    refused(lambda: SpecialDay.objects.create(date=d("2026-12-25"), name="Again"))


def test_a_special_day_needs_a_name_and_takes_its_intervals_with_it():
    refused(lambda: SpecialDay.objects.create(date=d("2026-01-06"), name=""))
    eve = make_special_day("2026-12-24", "Eve", ("10:00", "13:00"), ("17:00", "19:00"))
    assert eve.is_closed is False
    assert [i.open_time for i in eve.intervals.all()] == [t("10:00"), t("17:00")]
    refused(
        lambda: SpecialDayInterval.objects.create(
            special_day=eve, position=2, open_time=t("09:00"), close_time=t("09:00")
        )
    )
    eve.delete()
    assert not SpecialDayInterval.objects.exists()


def test_a_special_day_is_closed_and_not_yearly_by_default():
    christmas = SpecialDay.objects.create(date=d("2026-12-25"), name="Christmas")
    assert (christmas.is_closed, christmas.recurring_yearly, christmas.notes) == (
        True,
        False,
        "",
    )


def test_a_temporary_change_ends_on_or_after_its_start_and_needs_a_reason():
    make_override("2026-08-01", "2026-08-01", "One day")
    refused(
        lambda: Override.objects.create(
            start_date=d("2026-08-15"), end_date=d("2026-08-01"), reason="Backwards"
        )
    )
    refused(
        lambda: Override.objects.create(
            start_date=d("2026-09-01"), end_date=d("2026-09-02"), reason=""
        )
    )


def test_a_temporary_change_takes_its_intervals_with_it():
    summer = make_override(
        "2026-07-01", "2026-08-31", "Summer", ("10:00", "13:30"), ("18:00", "21:00")
    )
    assert [i.position for i in summer.intervals.all()] == [0, 1]
    refused(
        lambda: OverrideInterval.objects.create(
            override=summer, position=0, open_time=t("08:00"), close_time=t("09:00")
        )
    )
    summer.delete()
    assert not OverrideInterval.objects.exists()


def test_settings_are_one_row_with_the_week_starting_on_monday():
    ScheduleSettings.objects.all().delete()
    row = ScheduleSettings.objects.create()
    assert (row.week_starts_on, row.hours_confirmed) == (1, False)
    refused(lambda: ScheduleSettings.objects.create())
    row.week_starts_on = 8
    refused(row.save)


def test_the_order_of_each_table():
    WeekDay.objects.all().delete()
    make_day(4, closed=True)
    make_day(0, ("09:00", "18:00"))
    assert list(WeekDay.objects.values_list("weekday", flat=True)) == [0, 4]
    make_special_day("2026-12-25", "Christmas")
    make_special_day("2026-01-06", "Epiphany")
    assert list(SpecialDay.objects.values_list("name", flat=True)) == [
        "Epiphany",
        "Christmas",
    ]
    make_override("2026-08-01", "2026-08-15", "August")
    make_override("2026-04-01", "2026-04-05", "Easter")
    assert list(Override.objects.values_list("reason", flat=True)) == [
        "Easter",
        "August",
    ]


def test_str_names_the_row():
    assert str(make_special_day("2026-12-25", "Christmas")) == "Christmas (2026-12-25)"
    assert (
        str(make_override("2026-08-01", "2026-08-15", "Summer"))
        == "Summer (2026-08-01 – 2026-08-15)"
    )
    assert str(make_day(0, ("09:00", "18:00")).intervals.get()) == "09:00–18:00"
    assert str(make_day(6, closed=True)) == "Sunday"
