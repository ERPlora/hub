"""Fixtures of the schedule tests: contexts per role and scope, and model builders for the data a test
starts from (straight to the models: the operations are under test).

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it; a test
of B asks for ``hub_b`` and enters it."""

import datetime as dt

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from apps.invoice.tests.conftest import catalog_of, in_hubs
from apps.sale.tests.conftest import db_dsn, make_user
from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases (a person with a role in business A, the raw DSN of
#: control where the live notices go, the platform staff with business A chosen in the Hub admin, business A on a plan
#: with room for several sessions, the assistant's catalogue of a person of A) that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "db_dsn", "hub_staff", "in_business_a", "in_hubs",
    "make_user", "plan_with_room",
]


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
def empty_week(db):
    """No weekly day at all: the seeded default week (migration 0002) taken away."""
    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()


@pytest.fixture
def default_week_b(transactional_db, hub_b):
    """The week migration 0002 plants (Monday to Friday 09:00–18:00, the weekend closed), unconfirmed, in business B's
    database: a committed test that worked in B before this one emptied it, seeded rows included."""
    with use_hub(hub_b):
        if not WeekDay.objects.exists():
            for weekday in range(5):
                make_day(weekday, ("09:00", "18:00"))
            for weekday in (5, 6):
                make_day(weekday, closed=True)
        ScheduleSettings.objects.update(hours_confirmed=False)


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
