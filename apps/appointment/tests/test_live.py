"""Live queries of the appointment app: which events re-run which query after the COMMIT.

The agenda is live: a booking, a move, a state change, a charge, a block, a change of the business's
hours or of a professional's shift re-runs what shows it. The time's verdict (``availability.check``) is
asked at the moment of acting: not followed.
"""

from pathlib import Path

from live.live_registry import live_registry
from live.operations import get

from apps.appointment import events

EVENTS_SOURCE = Path(events.__file__).read_text()
APPOINTMENT = events.APPOINTMENT_EVENTS
CUSTOMER_GONE = ["customer.customer.merged", "customer.customer.erased"]


def appointment_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("appointment.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    availability = [
        *APPOINTMENT,
        *events.BLOCKED_TIME_EVENTS,
        events.SETTINGS_UPDATED,
        *events.SCHEDULE_EVENTS,
        *events.STAFF_EVENTS,
        *events.SERVICE_EVENTS,
    ]
    assert appointment_queries() == {
        "appointment.appointment.list": APPOINTMENT,
        "appointment.appointment.get": APPOINTMENT,
        "appointment.appointment.history": APPOINTMENT,
        "appointment.appointment.list_for_customer": [*APPOINTMENT, *CUSTOMER_GONE],
        "appointment.appointment.count_active_for_service": [
            *APPOINTMENT,
            "service.service.archived",
        ],
        "appointment.appointment.count_to_confirm": APPOINTMENT,
        "appointment.agenda.lanes": [*APPOINTMENT, *events.STAFF_EVENTS],
        "appointment.availability.slots": availability,
        "appointment.blocked_time.list": [
            *events.BLOCKED_TIME_EVENTS,
            *events.STAFF_EVENTS,
        ],
        "appointment.recurring.list": [
            *events.RECURRING_EVENTS,
            *CUSTOMER_GONE,
            "service.service.updated",
        ],
        "appointment.recurring.get": [
            *events.RECURRING_EVENTS,
            *APPOINTMENT,
            *CUSTOMER_GONE,
        ],
        "appointment.settings.get": [events.SETTINGS_UPDATED],
    }


def test_every_live_query_is_a_read_with_a_permission():
    for name in appointment_queries():
        op = get(name)
        assert (op.kind, op.permission is not None) == ("query", True), name


def test_every_own_event_is_a_literal_of_events_py():
    for on in appointment_queries().values():
        for event in on:
            if event.startswith("appointment."):
                assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_booking_re_runs_the_agenda_and_the_free_times_but_not_the_settings():
    affected = live_registry.affected([events.APPOINTMENT_CREATED])
    assert {
        "appointment.appointment.list",
        "appointment.availability.slots",
        "appointment.agenda.lanes",
    } <= affected
    assert "appointment.settings.get" not in affected


def test_a_change_of_hours_or_of_a_shift_re_runs_the_free_times():
    assert "appointment.availability.slots" in live_registry.affected(
        ["schedule.special_day.created"]
    )
    assert "appointment.availability.slots" in live_registry.affected(
        ["staff.time_off.approved"]
    )
    assert "appointment.availability.check" not in live_registry.subscribable
