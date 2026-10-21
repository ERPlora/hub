"""Fixtures of the appointment tests: contexts per role and scope, users with a role on a host, a raw DSN,
a fixed business day in the future, and builders of the data a test starts from (straight to the models
of each app: the operations are under test).

The builders import the models lazily, so that the tests of apps.py and engine.py still collect while
models.py does not exist.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")
MADRID = ZoneInfo("Europe/Madrid")


class Teammate:
    """A person of the team as the platform passes one (a user account), without a database row: no linked
    staff record. A plain string actor is what an automation or the platform itself passes."""

    pk = None
    email = ""

    def get_username(self) -> str:
        return "tester"

    def get_full_name(self) -> str:
        return "tester"

    def __str__(self) -> str:
        return "tester"


TESTER = Teammate()


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = TESTER,
    permissions: set[str] | None = None,
    language: str = "en",
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``permissions`` replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language=language)


def run(name: str, data: dict | None = None, role: str = "hub_admin", **ctx):
    """Runs the operation ``name`` as ``role`` (or the context ``ctx`` builds) with ``data``."""
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data or {}))


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


# The business's clock


def next_weekday(weekday: int, weeks_ahead: int = 1) -> dt.date:
    """The business date of the ``weekday`` (Monday = 0) at least ``weeks_ahead`` weeks from today."""
    today = timezone.localdate()
    ahead = (weekday - today.weekday()) % 7 + 7 * weeks_ahead
    return today + dt.timedelta(days=ahead)


#: A Monday one to two weeks ahead: inside the default 90 days of advance, never in the past.
MONDAY = next_weekday(0)


def at(day: dt.date, hhmm: str) -> dt.datetime:
    """``day`` at ``hhmm`` on the business's wall clock, as an aware instant."""
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm), tzinfo=MADRID)


def wall(day: dt.date, hhmm: str) -> str:
    """``day`` at ``hhmm`` as the naive wall-clock text a person types («2026-10-19T10:00»)."""
    return f"{day.isoformat()}T{hhmm}"


# Builders: Schedules (the business's hours)


@pytest.fixture
def anytime(db):
    """No rule of hours at all (the seeded default week taken away): the business never refuses on hours."""
    from apps.schedule.models import ScheduleSettings, WeekDay

    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()


def make_day(weekday: int, *intervals: tuple[str, str], closed: bool = False):
    """Replaces the business's ``weekday`` with these ``("HH:MM", "HH:MM")`` intervals (or closed)."""
    from apps.schedule.models import WeekDay, WeekDayInterval

    WeekDay.objects.filter(weekday=weekday).delete()
    day = WeekDay.objects.create(weekday=weekday, is_closed=closed)
    for position, (start, end) in enumerate(intervals):
        WeekDayInterval.objects.create(
            day=day,
            position=position,
            open_time=dt.time.fromisoformat(start),
            close_time=dt.time.fromisoformat(end),
        )
    return day


def make_special_day(on: dt.date, name: str = "Holiday", *intervals: tuple[str, str]):
    """A special day of the business: closed unless it has intervals."""
    from apps.schedule.models import SpecialDay, SpecialDayInterval

    special = SpecialDay.objects.create(date=on, name=name, is_closed=not intervals)
    for position, (start, end) in enumerate(intervals):
        SpecialDayInterval.objects.create(
            special_day=special,
            position=position,
            open_time=dt.time.fromisoformat(start),
            close_time=dt.time.fromisoformat(end),
        )
    return special


# Builders: Taxes, Services, Staff, Customers


def make_tax(key: str = "test.appointment", name: str = "Services — test", **fields):
    from apps.tax.models import TaxCategory

    return TaxCategory.objects.create(key=key, name=name, **fields)


def make_service(
    name: str = "Haircut",
    *,
    price: int = 2000,
    duration: int = 30,
    tax=None,
    **fields,
):
    from apps.service.models import Service

    return Service.objects.create(
        name=name, price=price, duration_minutes=duration, tax_category=tax, **fields
    )


def make_member(first_name: str = "Ana", last_name: str = "López", **fields):
    from apps.staff.models import Member

    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def assign(
    service, member, *, duration: int | None = None, price: int | None = None, **fields
):
    """``member`` performs ``service`` (with their own minutes and price, if given)."""
    from apps.service.models import Assignment

    return Assignment.objects.create(
        service=service,
        member=member,
        custom_duration=duration,
        custom_price=price,
        **fields,
    )


def make_shift(
    member, *days: tuple[int, str, str], break_at: tuple[str, str] | None = None
):
    """A default weekly schedule for ``member``: ``(weekday, "HH:MM", "HH:MM")`` per working day."""
    from apps.staff.models import Schedule, ScheduleDay

    schedule = Schedule.objects.create(member=member, name="Usual", is_default=True)
    for weekday, start, end in days:
        ScheduleDay.objects.create(
            schedule=schedule,
            weekday=weekday,
            start_time=dt.time.fromisoformat(start),
            end_time=dt.time.fromisoformat(end),
            break_start=dt.time.fromisoformat(break_at[0]) if break_at else None,
            break_end=dt.time.fromisoformat(break_at[1]) if break_at else None,
        )
    return schedule


def make_time_off(
    member,
    start: dt.date,
    end: dt.date | None = None,
    *,
    hours: tuple[str, str] | None = None,
):
    """An APPROVED absence of ``member``: whole days, or the same hours each day."""
    from apps.staff.models import TimeOff

    return TimeOff.objects.create(
        member=member,
        start_date=start,
        end_date=end or start,
        is_full_day=hours is None,
        start_time=dt.time.fromisoformat(hours[0]) if hours else None,
        end_time=dt.time.fromisoformat(hours[1]) if hours else None,
        status=TimeOff.Status.APPROVED,
    )


def make_customer(name: str = "Lucía Pérez", **fields):
    from apps.customer.models import Customer

    fields.setdefault("phone", "+34600111222")
    return Customer.objects.create(name=name, **fields)


# Builders: this app


def make_settings(**fields):
    from apps.appointment.models import Settings

    Settings.objects.all().delete()
    return Settings.objects.create(**fields)


def make_appointment(
    customer,
    member,
    services,
    start: dt.datetime,
    *,
    status: str = "confirmed",
    number: str | None = None,
    duration: int | None = None,
    **fields,
):
    """An appointment straight in the table (no rules applied), its service lines frozen from the catalog."""
    from apps.appointment.models import Appointment, AppointmentService

    services = list(services)
    minutes = duration or sum(service.duration_minutes for service in services)
    appointment = Appointment.objects.create(
        number=number or f"APT-TEST-{Appointment.objects.count() + 1:04d}",
        customer=customer,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_email=customer.email,
        staff=member,
        staff_name=member.full_name if member else "",
        start=start,
        end=start + dt.timedelta(minutes=minutes),
        duration_minutes=minutes,
        status=status,
        **fields,
    )
    for position, service in enumerate(services):
        AppointmentService.objects.create(
            appointment=appointment,
            service=service,
            name=service.name,
            price=service.price,
            duration_minutes=service.duration_minutes,
            position=position,
        )
    return appointment


def make_series(salon, **fields):
    """A weekly series of a cut with Ana (or ``staff``) for Lucía, straight in the table (nothing booked yet)."""
    from apps.appointment.models import Recurring, RecurringService

    staff = fields.pop("staff", salon.ana)
    series = Recurring.objects.create(
        customer=salon.lucia,
        customer_name=salon.lucia.name,
        staff=staff,
        staff_name=staff.full_name,
        frequency=fields.pop("frequency", "weekly"),
        day_of_week=fields.pop("day_of_week", 0),
        time=dt.time(10),
        duration_minutes=30,
        start_date=fields.pop("start_date", MONDAY),
        **fields,
    )
    RecurringService.objects.create(recurring=series, service=salon.cut, position=0)
    return series


def make_block(
    start: dt.datetime,
    end: dt.datetime,
    *,
    member=None,
    title: str = "Closed",
    **fields,
):
    from apps.appointment.models import BlockedTime

    return BlockedTime.objects.create(
        title=title, start=start, end=end, staff=member, **fields
    )


@pytest.fixture
def salon(db):
    """The usual cast: a customer, a cut and a colour (taxed), and Ana, who performs both."""
    tax = make_tax()
    cut = make_service("Haircut", price=2000, duration=30, tax=tax)
    colour = make_service("Colour", price=4500, duration=60, tax=tax)
    ana = make_member("Ana", "López")
    bea = make_member("Bea", "Ruiz")
    lucia = make_customer("Lucía Pérez")
    return type(
        "Salon",
        (),
        {
            "tax": tax,
            "cut": cut,
            "colour": colour,
            "ana": ana,
            "bea": bea,
            "lucia": lucia,
        },
    )
