"""Fixtures of the staff tests: contexts per role and scope, users with a role on a host, model
builders for the data a test starts from, and a raw DSN."""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from apps.staff.models import Member, Role, Schedule, ScheduleDay, TimeOff
from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``actor`` is a user for the operations that act on the caller's own record; ``permissions``
    replaces the role's when a test needs a combination no role has.
    """
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
    def make(
        username: str = "ana",
        *,
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
        first_name: str = "",
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", first_name=first_name
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (LISTEN, or reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


# Builders of the data a test starts from (straight to the models: the operations are under test).


def make_role(name: str = "Stylist", **fields) -> Role:
    return Role.objects.create(name=name, **fields)


def make_member(first_name: str = "Ana", last_name: str = "López", **fields) -> Member:
    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def make_schedule(member: Member, days=None, name: str = "Usual", **fields) -> Schedule:
    """``days`` maps a weekday to ``(start, end)`` or ``(start, end, break_start, break_end)`` as "HH:MM"."""
    schedule = Schedule.objects.create(member=member, name=name, **fields)
    for weekday, hours in (days if days is not None else {0: ("09:00", "18:00")}).items():
        start, end, *pause = (dt.time.fromisoformat(value) for value in hours)
        ScheduleDay.objects.create(
            schedule=schedule,
            weekday=weekday,
            start_time=start,
            end_time=end,
            break_start=pause[0] if pause else None,
            break_end=pause[1] if pause else None,
        )
    return schedule


def make_time_off(member: Member, start: str, end: str | None = None, hours: tuple[str, str] | None = None, **fields) -> TimeOff:
    """Whole days unless ``hours`` = ("HH:MM", "HH:MM"); dates as "YYYY-MM-DD"."""
    times = {}
    if hours is not None:
        times = {"is_full_day": False, "start_time": dt.time.fromisoformat(hours[0]), "end_time": dt.time.fromisoformat(hours[1])}
    return TimeOff.objects.create(
        member=member, start_date=dt.date.fromisoformat(start), end_date=dt.date.fromisoformat(end or start), **times, **fields
    )
