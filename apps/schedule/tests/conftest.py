"""Fixtures of the schedule tests: contexts per role and scope, and model builders for the data a test
starts from (straight to the models: the operations are under test)."""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership

from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig)."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.ADMIN):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


@pytest.fixture
def empty_week(db):
    """No weekly day at all: the seeded default week (migration 0002) taken away."""
    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()


def t(text: str) -> dt.time:
    return dt.time.fromisoformat(text)


def d(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def make_day(
    weekday: int, *intervals: tuple[str, str], closed: bool = False
) -> WeekDay:
    """Replaces ``weekday`` with these ``("HH:MM", "HH:MM")`` intervals (or closed)."""
    WeekDay.objects.filter(weekday=weekday).delete()
    day = WeekDay.objects.create(weekday=weekday, is_closed=closed)
    for position, (start, end) in enumerate(intervals):
        WeekDayInterval.objects.create(
            day=day, position=position, open_time=t(start), close_time=t(end)
        )
    return day


def make_special_day(
    on: str = "2026-12-25",
    name: str = "Christmas",
    *intervals: tuple[str, str],
    closed: bool | None = None,
    **fields,
) -> SpecialDay:
    """Closed unless it has intervals; ``on`` as "YYYY-MM-DD"."""
    is_closed = not intervals if closed is None else closed
    special = SpecialDay.objects.create(
        date=d(on), name=name, is_closed=is_closed, **fields
    )
    for position, (start, end) in enumerate(intervals):
        SpecialDayInterval.objects.create(
            special_day=special,
            position=position,
            open_time=t(start),
            close_time=t(end),
        )
    return special


def make_override(
    start: str = "2026-08-01",
    end: str = "2026-08-15",
    reason: str = "Holidays",
    *intervals: tuple[str, str],
    closed: bool | None = None,
) -> Override:
    """Closed unless it has intervals; dates as "YYYY-MM-DD"."""
    is_closed = not intervals if closed is None else closed
    change = Override.objects.create(
        start_date=d(start), end_date=d(end), reason=reason, is_closed=is_closed
    )
    for position, (open_time, close_time) in enumerate(intervals):
        OverrideInterval.objects.create(
            override=change,
            position=position,
            open_time=t(open_time),
            close_time=t(close_time),
        )
    return change
