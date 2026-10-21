"""Fixtures of the online booking tests: contexts per role (and the public door's), a fixed clock, and builders
of the data a test starts from, straight to the models of each app (the operations are under test).

The clock never depends on the real one: ``clock`` fixes ``django.utils.timezone.now`` (which Citas reads
for its rules and the models for their timestamps) on Monday 4 March 2030, 08:00 in Madrid. The builders
import the models lazily, so that the tests of apps.py still collect while models.py does not exist.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.test import RequestFactory
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

A = Scope("host", "a")
B = Scope("host", "b")
MADRID = ZoneInfo("Europe/Madrid")
#: «Now» in every test: Monday 4 March 2030, 08:00 on the business's clock.
NOW = dt.datetime(2030, 3, 4, 8, 0, tzinfo=MADRID)
MONDAY = NOW.date()
TUESDAY = MONDAY + dt.timedelta(days=1)
PUBLIC = {"online_booking.public"}


class Teammate:
    """A person of the team as the platform passes one (a user account), without a database row. Citas
    judges any other actor (a plain string: an automation, the platform) by the customer's rules."""

    pk = None
    email = ""

    def get_username(self) -> str:
        return "tester"

    def get_full_name(self) -> str:
        return "tester"

    def __str__(self) -> str:
        return "tester"


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = Teammate(),
    permissions: set[str] | None = None,
    ip: str | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (or exactly ``permissions``), with a request
    from ``ip`` when given."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    request = RequestFactory().post("/", REMOTE_ADDR=ip) if ip else None
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, request=request
    )


def public_ctx(ip: str = "203.0.113.7", scope: Scope = A) -> OperationContext:
    """The context the public door builds: nobody signed in, only the public permission, the visitor's request."""
    return ctx_for(scope=scope, actor=None, permissions=set(PUBLIC), ip=ip)


def run(
    name: str, data: dict | None = None, ctx: OperationContext | None = None, **options
):
    """Runs the operation ``name`` with ``data`` as ``ctx`` (or the context ``ctx_for(**options)`` builds)."""
    op = get(name)
    return op(ctx or ctx_for(**options), op.input.model_validate(data or {}))


def public(name: str, data: dict | None = None, ip: str = "203.0.113.7"):
    """Runs the public operation ``online_booking.public.<name>`` as a visitor from ``ip``."""
    return run(f"online_booking.public.{name}", data, ctx=public_ctx(ip))


def at(day: dt.date, hhmm: str) -> dt.datetime:
    """``day`` at ``hhmm`` on the business's wall clock, as an aware instant."""
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm), tzinfo=MADRID)


def wall(day: dt.date, hhmm: str) -> str:
    """``day`` at ``hhmm`` as the naive wall-clock text a person types («2030-03-05T10:00»)."""
    return f"{day.isoformat()}T{hhmm}"


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """The clock stands still at ``NOW`` (moved with ``clock.set``)."""

    class Clock:
        moment = NOW

        def set(self, moment: dt.datetime) -> None:
            self.moment = moment

    fixed = Clock()
    monkeypatch.setattr(timezone, "now", lambda: fixed.moment.astimezone(dt.UTC))
    return fixed


# Builders: Schedules, Services, Staff, Customers, Citas


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


def make_service(
    name: str = "Haircut", *, price: int = 2000, duration: int = 30, **fields
):
    from apps.service.models import Service

    return Service.objects.create(
        name=name, price=price, duration_minutes=duration, **fields
    )


def make_member(first_name: str = "Ana", last_name: str = "López", **fields):
    from apps.staff.models import Member

    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def assign(service, member, **fields):
    from apps.service.models import Assignment

    return Assignment.objects.create(service=service, member=member, **fields)


def make_customer(name: str = "Lucía Pérez", **fields):
    from apps.customer.models import Customer

    fields.setdefault("phone", "+34600111222")
    return Customer.objects.create(name=name, **fields)


def make_rules(**fields):
    """The booking rules of Citas (its settings row)."""
    from apps.appointment.models import Settings

    Settings.objects.all().delete()
    return Settings.objects.create(**fields)


def make_page(**fields):
    """This app's settings: the public page, switched on unless said otherwise."""
    from apps.online_booking.models import Settings

    Settings.objects.all().delete()
    fields.setdefault("is_enabled", True)
    return Settings.objects.create(**fields)


def make_appointment(
    customer,
    member,
    services,
    start: dt.datetime,
    *,
    status: str = "confirmed",
    **fields,
):
    """An appointment straight in the table (no rules applied), its service lines frozen from the catalog."""
    from apps.appointment.models import Appointment, AppointmentService

    services = list(services)
    minutes = sum(service.duration_minutes for service in services)
    fields.setdefault("source", "online")
    appointment = Appointment.objects.create(
        number=fields.pop("number", f"APT-TEST-{Appointment.objects.count() + 1:04d}"),
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


@pytest.fixture
def salon(db, anytime):
    """The usual cast: a cut and a colour that Ana and Bea perform, a customer, and the page switched on."""
    cut = make_service("Haircut", price=2000, duration=30)
    colour = make_service("Colour", price=4500, duration=60)
    ana = make_member("Ana", "López")
    bea = make_member("Bea", "Ruiz")
    for service in (cut, colour):
        assign(service, ana)
        assign(service, bea)
    lucia = make_customer("Lucía Pérez")
    make_page()
    return type(
        "Salon",
        (),
        {"cut": cut, "colour": colour, "ana": ana, "bea": bea, "lucia": lucia},
    )


def booking_data(
    salon, hhmm: str = "10:00", *, day: dt.date = TUESDAY, **fields
) -> dict:
    """What the public page sends to book the cut at ``hhmm``."""
    data = {
        "service_ids": [str(salon.cut.id)],
        "start": wall(day, hhmm),
        "name": "Marta Gil",
        "phone": "612 345 678",
        "email": "marta@example.com",
    }
    data.update(fields)
    return data


@pytest.fixture
def make_user(db):
    """A user with ``role`` on ``host`` (a Membership), for the routes' tests."""
    from django.contrib.auth import get_user_model

    from base.models import Membership

    def make(username: str = "ana", *, host: str | None = "a", role: str = Membership.Role.ADMIN):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    from django.db import connections
    from psycopg.conninfo import make_conninfo

    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
