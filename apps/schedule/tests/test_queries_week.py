"""The usual week (SCHEDULE-F01): seven days from the one the settings say, each closed, not set or with its
intervals, named in the reader's language."""

import datetime as dt

from django.utils import translation

from apps.schedule.models import ScheduleSettings

from .conftest import HUB_DB, make_day
from .test_queries import run, t

pytestmark = HUB_DB

NINE_TO_SIX = [{"open_time": dt.time(9), "close_time": dt.time(18)}]


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
