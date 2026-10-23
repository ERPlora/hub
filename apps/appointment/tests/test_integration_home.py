"""Citas on the Home's bell (PLAN-HUB round 2026-10-21; appointments#169, hub#1678): base's ``base.bell.counters``
shows «Appointments to confirm» while the customers' own upcoming bookings wait for confirmation in the agenda the
person sees, and leads to the agenda; at zero it is not shown. Every change of that number records an event the
counter is refreshed on, and a booking in hub B re-runs the bell on B's channel only.

base and appointment run for real: the counter comes from AppointmentConfig through base's own query, never a
stand-in module.
"""

import datetime as dt
import json
import uuid

import psycopg
import pytest
from django.apps import apps
from django.utils import timezone
from live.context import system_context
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from base.schemas import BellCountersIn

from .conftest import A, B, MONDAY, at, ctx_for, make_appointment, make_settings, run, wall
from .test_queries import employee_linked_to

pytestmark = pytest.mark.usefixtures("anytime")

COUNTER = {
    "key": "appointment.to_confirm",
    "app": "appointment",
    "route": "/appointment/agenda",
    "label": "Appointments to confirm",
    "icon": "ion:calendar-outline",
}
WAIT = 1.0
QUIET = 0.3


def bell(ctx) -> dict | None:
    """Citas's row of the bell for the person of ``ctx``, as the SPA receives it (``None``: not shown)."""
    counters = get("base.bell.counters")(ctx, BellCountersIn()).model_dump(mode="json")["counters"]
    rows = [row for row in counters if row["app"] == "appointment"]
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def counted(ctx) -> int:
    row = bell(ctx)
    return row["count"] if row else 0


def waiting(salon, member=None, start=None, **fields):
    """A booking the customer made herself that waits for the business («I review them first»)."""
    return make_appointment(
        salon.lucia,
        salon.ana if member is None else member,
        [salon.cut],
        start or at(MONDAY, "10:00"),
        status="pending",
        source="whatsapp",
        **fields,
    )


@pytest.mark.django_db
def test_a_customers_booking_waiting_is_counted_and_leads_to_the_agenda(salon):
    waiting(salon)
    assert bell(ctx_for("hub_admin")) == {**COUNTER, "count": 1}


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words(salon):
    waiting(salon)
    assert bell(ctx_for("hub_admin", language="es"))["label"] == "Citas por confirmar"


@pytest.mark.django_db
def test_a_past_confirmed_cancelled_or_deleted_booking_does_not_count_and_at_zero_nothing_shows(salon):
    waiting(salon, start=timezone.now() - dt.timedelta(hours=2))
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"), status="confirmed", source="online")
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), status="cancelled", source="online")
    waiting(salon, start=at(MONDAY, "13:00"), deleted_at=timezone.now())
    admin = ctx_for("hub_admin")
    assert bell(admin) is None

    waiting(salon, start=at(MONDAY, "16:00"))
    assert bell(admin) == {**COUNTER, "count": 1}


@pytest.mark.django_db
def test_an_employee_counts_only_her_own_and_the_manager_everybodys(salon, make_user):
    waiting(salon, salon.ana, at(MONDAY, "10:00"))
    waiting(salon, salon.bea, at(MONDAY, "12:00"))
    make_appointment(salon.lucia, None, [salon.cut], at(MONDAY, "14:00"), status="pending", source="online")
    assert counted(employee_linked_to(salon.ana, make_user)) == 1
    assert counted(ctx_for("hub_manager")) == 3


@pytest.mark.django_db
def test_an_employee_without_a_professional_of_her_own_is_not_shown_the_counter(salon):
    waiting(salon)
    assert bell(ctx_for("hub_employee")) is None


@pytest.mark.django_db
def test_without_a_permission_of_citas_there_is_no_counter(salon):
    waiting(salon)
    assert bell(ctx_for("hub_employee", permissions={"base.view_home"})) is None


# ── What refreshes it: every change of the number records one of its events ──────────────────────────────────────


def book_online(salon, appointment):
    make_settings(auto_confirm_online=False)
    run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": wall(MONDAY, "12:00"),
            "source": "online",
        },
    )


def charge_at_the_till(salon, appointment):
    op = get("appointment.appointment.mark_charged")
    op(system_context(A), op.input.model_validate({"sale_id": str(uuid.uuid7()), "appointment_id": str(appointment.id)}))


def professional_leaves(salon, appointment):
    op = get("appointment.staff.release")
    op(system_context(A), op.input.model_validate({"id": str(salon.ana.id)}))


def ref(name):
    return lambda salon, appointment: run(name, {"id": str(appointment.id)})


#: Each event of the counter's ``refresh_on`` → a change of the number that records it, made by the front desk or
#: the platform, seen by Ana's own employee.
CHANGES = {
    "appointment.appointment.created": book_online,
    "appointment.appointment.confirmed": ref("appointment.appointment.confirm"),
    "appointment.appointment.started": ref("appointment.appointment.start"),
    "appointment.appointment.completed": charge_at_the_till,
    "appointment.appointment.cancelled": ref("appointment.appointment.cancel"),
    "appointment.appointment.rescheduled": lambda salon, appointment: run(
        "appointment.appointment.reschedule",
        {"id": str(appointment.id), "start": wall(timezone.localdate() - dt.timedelta(days=1), "10:00")},
    ),
    "appointment.appointment.unassigned": professional_leaves,
    "appointment.appointment.deleted": ref("appointment.appointment.delete"),
}


def to_confirm():
    return apps.get_app_config("appointment").bell[0]


@pytest.mark.django_db
@pytest.mark.parametrize("event", list(CHANGES))
def test_each_change_of_the_number_records_an_event_that_refreshes_the_bell(salon, make_user, event):
    appointment = waiting(salon)
    ana = employee_linked_to(salon.ana, make_user)
    before = counted(ana)
    seen = set(OutboxEvent.objects.values_list("id", flat=True))

    CHANGES[event](salon, appointment)

    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert counted(ana) != before
    assert recorded & set(to_confirm().refresh_on) == {event}


def test_every_event_it_is_refreshed_on_changes_the_number():
    """Not one more: the counter is re-run on what changes it, and nothing else."""
    assert set(to_confirm().refresh_on) == set(CHANGES)


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_booking_in_hub_b_re_runs_the_bell_of_b_and_tells_a_nothing(salon, listen):
    make_settings(auto_confirm_online=False)
    on_a, on_b = listen(A), listen(B)
    run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": wall(MONDAY, "10:00"),
            "source": "online",
        },
        scope=B,
    )
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.bell.counters" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
