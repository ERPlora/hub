"""The usual week (SCHEDULE-F02, F03): saving a day replaces its intervals and confirms the week, and the default
week is confirmed as it is, without changing an hour."""

import pytest
from live.errors import Conflict

from apps.schedule.models import WeekDay
from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.week import SetDayIn

from .conftest import HUB_DB, A
from .test_services import confirmed, hours, names, outbox, run, t

pytestmark = HUB_DB


def stored(day: int):
    row = WeekDay.objects.get(weekday=day)
    return row.is_closed, [
        (i.position, i.open_time, i.close_time)
        for i in row.intervals.order_by("position")
    ]


def test_saving_a_day_replaces_its_intervals_sorted_and_confirms_the_week():
    week = run(
        "schedule.week.set_day",
        SetDayIn(weekday=0, intervals=hours(("17:00", "20:00"), ("10:00", "14:00"))),
    )
    assert stored(0) == (
        False,
        [(0, t("10:00"), t("14:00")), (1, t("17:00"), t("20:00"))],
    )
    assert confirmed()
    assert [i.open_time for i in week.days[0].intervals] == [t("10:00"), t("17:00")]
    assert outbox() == [("schedule.week.updated", A.key, {"weekday": 0})]
    # Saving again replaces, never adds.
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=0, intervals=hours(("09:00", "13:00"))),
    )
    assert stored(0) == (False, [(0, t("09:00"), t("13:00"))])


def test_a_closed_day_keeps_no_interval_and_an_unset_day_is_created():
    WeekDay.objects.filter(weekday=6).delete()
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=6, is_closed=True, intervals=hours(("10:00", "14:00"))),
    )
    assert stored(6) == (True, [])
    run(
        "schedule.week.set_day",
        SetDayIn(weekday="sábado", intervals=hours(("00:00", "00:00"))),
    )
    assert stored(5) == (False, [(0, t("00:00"), t("00:00"))])
    run(
        "schedule.week.set_day",
        SetDayIn(weekday=4, intervals=hours(("22:00", "02:00"))),
    )
    assert stored(4) == (False, [(0, t("22:00"), t("02:00"))])


def test_confirming_the_default_week_changes_no_hour():
    before = [stored(day) for day in range(7)]
    week = run("schedule.week.confirm", NoParamsIn())
    assert week.confirmed and confirmed()
    assert [stored(day) for day in range(7)] == before
    assert names() == ["schedule.week.updated"]
    # Confirming twice changes nothing and says nothing.
    run("schedule.week.confirm", NoParamsIn())
    assert names() == ["schedule.week.updated"]


def test_a_week_that_is_not_there_cannot_be_confirmed():
    WeekDay.objects.all().delete()
    with pytest.raises(Conflict) as refused:
        run("schedule.week.confirm", NoParamsIn())
    assert refused.value.code == "schedule.no_week"
    assert refused.value.message == "There are no weekly opening hours to confirm."
    assert not confirmed() and outbox() == []
