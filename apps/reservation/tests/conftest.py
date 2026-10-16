"""Fixtures of the reservation tests: contexts per role and scope, users with a role on a host, a raw DSN,
a pinned business clock, and builders of the data a test starts from.

The book's own rows (slots, blocked dates, settings) are built straight on the models: the operations are
under test. The tables of Tables, the cards of Customers and the hours of Schedules are the real apps' —
their rows on their models, their writes through their own operations — never mocks: Reservations is
tested against what it requires. The builders import the models lazily, so the tests of apps.py still
collect while models.py does not exist.

The clock: every test runs at ``NOW`` (Wednesday 14 October 2026, 12:00 in Madrid), so «tomorrow at 21:00»
is always Thursday 15 October and nothing depends on when the suite runs.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")
MADRID = ZoneInfo("Europe/Madrid")

#: Wednesday 14 October 2026, 12:00 in Madrid (10:00 UTC, summer time).
NOW = dt.datetime(2026, 10, 14, 10, 0, tzinfo=dt.UTC)
TODAY = dt.date(2026, 10, 14)
TOMORROW = dt.date(2026, 10, 15)
#: Thursday = 3 (Monday = 0).
THURSDAY = 3


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    language: str = "en",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (owner and admin: every declared permission,
    as base.permissions; the others what each app's ``role_permissions`` gives them)."""
    configs = all_live_app_configs()
    if permissions is None:
        if role in ("hub_owner", "hub_admin"):
            permissions = {p for config in configs for p in config.permissions}
        else:
            permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def pin_clock(monkeypatch, instant: dt.datetime) -> None:
    """Pins Django's clock (``django.utils.timezone.now``, what the apps call «now») to ``instant``."""
    monkeypatch.setattr("django.utils.timezone.now", lambda: instant)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Every test runs at ``NOW``; a test moves it with ``pin_clock``."""
    pin_clock(monkeypatch, NOW)
    return NOW


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
    ):
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


# ── The book's own rows ──────────────────────────────────────────────────────────────────────────


def make_slot(
    day_of_week: int = THURSDAY,
    start: str = "20:00",
    end: str = "23:30",
    max_reservations: int = 10,
    **fields,
):
    from apps.reservation.models import TimeSlot

    return TimeSlot.objects.create(
        day_of_week=day_of_week,
        start_time=dt.time.fromisoformat(start),
        end_time=dt.time.fromisoformat(end),
        max_reservations=max_reservations,
        **fields,
    )


def open_week(max_reservations: int = 10, **fields) -> None:
    """Lunch (13:00–16:00) and dinner (20:00–23:30) every day of the week."""
    for day in range(7):
        make_slot(day, "13:00", "16:00", max_reservations, **fields)
        make_slot(day, "20:00", "23:30", max_reservations, **fields)


def make_blocked(date: dt.date = TOMORROW, **fields):
    from apps.reservation.models import BlockedDate

    return BlockedDate.objects.create(date=date, **fields)


def set_rules(**fields):
    """Saves the book's settings with ``fields`` changed (the rest as they come)."""
    from apps.reservation.models import Settings

    settings, _ = Settings.objects.get_or_create(singleton=True)
    for name, value in fields.items():
        setattr(settings, name, value)
    settings.save()
    return settings


def make_reservation(date: dt.date = TOMORROW, time: str = "21:00", **fields):
    """A reservation row straight on the model (no gate, no card): what a test starts from."""
    from apps.reservation.models import Reservation

    fields.setdefault("guest_name", "Ana García")
    fields.setdefault("party_size", 2)
    fields.setdefault("duration_minutes", 120)
    return Reservation.objects.create(
        date=date, time=dt.time.fromisoformat(time), **fields
    )


def make_entry(date: dt.date = TOMORROW, time: str = "21:00", **fields):
    from apps.reservation.models import WaitlistEntry

    fields.setdefault("guest_name", "Luis Pérez")
    fields.setdefault("guest_phone", "+34600222333")
    fields.setdefault("party_size", 2)
    return WaitlistEntry.objects.create(
        date=date, preferred_time=dt.time.fromisoformat(time), **fields
    )


def book(ctx: OperationContext | None = None, **data):
    """``reservation.reservation.create`` with a complete booking for tomorrow at 21:00 (override any field)."""
    payload = {
        "guest_name": "Ana García",
        "guest_phone": "600111222",
        "date": TOMORROW.isoformat(),
        "time": "21:00",
        "party_size": 4,
        **data,
    }
    return run("reservation.reservation.create", payload, ctx)


# ── Tables, Customers and Schedules: the real apps ───────────────────────────────────────────────


def make_zone(name: str = "Dining room", **fields):
    from apps.table.models import Zone

    return Zone.objects.create(name=name, **fields)


def make_table(number: str = "5", zone=None, capacity: int = 4, **fields):
    from apps.table.models import Table

    return Table.objects.create(number=number, zone=zone, capacity=capacity, **fields)


def holds(reservation_id) -> list:
    """The holds of Tables for a reservation, oldest first."""
    from apps.table.models import Hold

    return list(
        Hold.objects.filter(
            source="reservation", source_ref=str(reservation_id)
        ).order_by("created_at", "id")
    )


def make_customer(name: str = "Ana García", **more):
    """A customer card, made by Customers."""
    return run("customer.customer.create", {"name": name, **more}, system_context(A))


def set_week_hours(intervals: list[tuple[str, str]], days=range(7)) -> None:
    """The business's usual week in Schedules: every day in ``days`` open in ``intervals``."""
    for day in days:
        run(
            "schedule.week.set_day",
            {
                "weekday": day,
                "is_closed": not intervals,
                "intervals": [
                    {"open_time": start, "close_time": end} for start, end in intervals
                ],
            },
            system_context(A),
        )
