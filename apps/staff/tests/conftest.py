"""Fixtures of the staff tests: contexts per role and scope, users with a role on a host, model
builders for the data a test starts from and a raw DSN.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``). Business B (``hub_b``) has its own database beside it; a test of B asks for ``hub_b`` and enters it."""

import datetime as dt
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import atomic, get
from psycopg.conninfo import make_conninfo

from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import night_elsewhere
from apps.staff.models import Member, Role, Schedule, ScheduleDay, TimeOff
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, in_a_thread, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases (the platform staff with business A chosen in the Hub
#: admin, business A at night in another zone or on a plan with room for several sessions) and the assistant's catalogue
#: of a person of business A, that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "hub_staff", "in_business_a", "night_elsewhere",
    "plan_with_room",
]


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
    language: str = "en",
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``actor`` is a user for the operations that act on the caller's own record; ``permissions``
    replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language=language)


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
        host: str | None = A.key,
        role: str = Membership.Role.ADMIN,
        first_name: str = "",
    ):
        user = get_user_model().objects.create_user(
            username=username, password="pw", first_name=first_name
        )
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        # Who they are in the business's database, as their entry makes it: what a record hangs from.
        user.person = ensure_hub_user(user)
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


#: Every sale of these tests is charged by card: a cash charge would ask Cash register for an open drawer (SALE-F08).
CARD = [{"method": "card"}]


@pytest.fixture
def catalog():
    """Products made by Inventory, prices with tax included (what a line charges)."""
    for name, sku, price in (("Cut", "CUT", 1800), ("Fringe", "FRG", 506), ("Shampoo", "SHP", 121)):
        get("inventory.product.create")(
            system_context(A),
            get("inventory.product.create").input.model_validate(
                {"name": name, "sku": sku, "price": price, "tax_category_key": "product.generic"}
            ),
        )


def charge(key, *lines, staff=None):
    """A sale an administrator charges by card: ``lines`` as (sku, member or None); ``staff`` serves the whole sale."""
    op = get("sale.sale.complete")
    data = {
        "idempotency_key": key,
        "lines": [{"product": sku, **({"staff_id": str(member.id)} if member else {})} for sku, member in lines],
        **({"staff_id": str(staff.id)} if staff else {}),
        "payments": CARD,
    }
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


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


# What the tests of the reads and of the writes share.

TERMINATED = Member.Status.TERMINATED
# 2026-08-18 22:30 UTC is already 2026-08-19 00:30 in Madrid (the business's zone, settings.TIME_ZONE).
LATE_EVENING_UTC = dt.datetime(2026, 8, 18, 22, 30, tzinfo=dt.UTC)
QUIET = 0.3
WEEK = [
    {
        "weekday": 0,
        "start_time": "09:00",
        "end_time": "18:00",
        "break_start": "13:00",
        "break_end": "14:00",
    }
]


def run(name, data, role="hub_admin", **ctx):
    return get(name)(ctx_for(role, **ctx), data)


def t(value):
    return dt.time.fromisoformat(value)


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``timezone.now`` (and so the business's «today») at an instant."""

    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


def today():
    return timezone.localdate()


def outbox():
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


def names():
    return [name for name, _, _ in outbox()]


# Two people at the same instant: the second waits for the first's lock, then decides on what it wrote


def _in_thread(target):
    """``target`` in a session of its own of the business at work; ``outcome`` says its result or its error."""
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error

    thread = in_a_thread(body, [None])
    thread.start()
    return thread, outcome


def _race(first, second):
    """Run ``first`` in a transaction kept open until ``second`` (another thread) is blocked on it.

    Returns the outcomes of both. ``second`` must wait (a lock), never decide blind on what ``first``
    has not committed yet. Its tests run on a plan with room for both sessions (``plan_with_room``): on Free's,
    ``second`` would wait for its turn to open a transaction, never for the lock.
    """
    done, release = threading.Event(), threading.Event()

    def held():
        with atomic():
            result = first()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(second)
    waiter.join(QUIET)
    waited = waiter.is_alive()
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
    assert waited, "the second call did not wait for the first one's lock"
    return outcome
