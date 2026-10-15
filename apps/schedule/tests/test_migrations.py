"""Migration 0002 of the schedule app: the default week (SCHEDULE-F12), planted once on an empty week,
never over a week the business already has, and reversible while nobody confirmed it.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry and
a schema editor whose connection is the test database.
"""

import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.schedule.models import ScheduleSettings, WeekDay
from apps.schedule.tests.conftest import make_day

pytestmark = pytest.mark.django_db

NINE_TO_SIX = [(dt.time(9), dt.time(18))]


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _seed():
    return import_module("apps.schedule.migrations.0002_default_week")


def plant():
    _seed().plant(global_apps, _SchemaEditor())


def unplant():
    _seed().unplant(global_apps, _SchemaEditor())


def week() -> dict[int, tuple[bool, list[tuple[dt.time, dt.time]]]]:
    return {
        day.weekday: (
            day.is_closed,
            [(i.open_time, i.close_time) for i in day.intervals.all()],
        )
        for day in WeekDay.objects.prefetch_related("intervals")
    }


def test_the_tables_are_born_with_the_default_week_monday_to_friday_nine_to_six():
    # The test database ran every migration: the seed is already there, unconfirmed.
    assert week() == {
        0: (False, NINE_TO_SIX),
        1: (False, NINE_TO_SIX),
        2: (False, NINE_TO_SIX),
        3: (False, NINE_TO_SIX),
        4: (False, NINE_TO_SIX),
        5: (True, []),
        6: (True, []),
    }
    assert not ScheduleSettings.objects.filter(hours_confirmed=True).exists()


def test_planting_again_changes_nothing():
    plant()
    assert len(week()) == 7
    assert week()[0] == (False, NINE_TO_SIX)


def test_never_plants_over_a_week_the_business_has_touched():
    WeekDay.objects.all().delete()
    make_day(0, ("10:00", "14:00"))
    plant()
    assert week() == {0: (False, [(dt.time(10), dt.time(14))])}


def test_the_reverse_takes_the_default_week_away_while_it_is_unconfirmed():
    unplant()
    assert week() == {}
    plant()
    assert len(week()) == 7


def test_the_reverse_keeps_a_week_somebody_confirmed():
    ScheduleSettings.objects.update_or_create(
        slot=1, defaults={"hours_confirmed": True}
    )
    unplant()
    assert len(week()) == 7
