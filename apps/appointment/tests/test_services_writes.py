"""The rules every write of the appointment app shares (APPOINTMENT-F01, APPOINTMENT-F04): an automation is judged
as the customer, the notice and the length count real hours the nights the clock changes, and who may book or
change an appointment for whom.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, PermissionDenied
from live.operations import get

from apps.appointment.models.appointments import Appointment
from base.api_keys import KeyCaller

from .conftest import HUB_DB, MADRID, MONDAY, TESTER, at, ctx_for, make_appointment, make_settings, pin_clock, run, wall
from .write_checks import actions, book, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


# The front desk's exceptions (a time already gone, inside the minimum notice, «book anyway» on an overlap,
# cancelling outside the policy) exist because a person is looking at the agenda. Only a person (a user account)
# gets them: an automation — a flow's step, the platform itself, an anonymous caller, any kind still to come — is
# judged as the customer, whatever source it sends, so a message cannot talk it into the front desk's door.
AUTOMATIONS = ["flow_run:0190a1b2", "system", None]


def as_caller(salon, actor, start, day=MONDAY, **extra):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "start": wall(day, start),
        **extra,
    }
    return run("appointment.appointment.create", data, actor=actor)


@pytest.mark.parametrize("actor", AUTOMATIONS)
def test_an_automation_books_by_the_customers_rules_whatever_source_it_sends(salon, actor):
    yesterday = timezone.localdate() - dt.timedelta(days=1)
    refused("appointment.in_past", lambda: as_caller(salon, actor, "10:00", day=yesterday))
    assert book(salon, "10:00", day=yesterday).status == "confirmed"
    as_caller(salon, actor, "10:00")
    refused(
        "appointment.slot_taken",
        lambda: as_caller(salon, actor, "10:15", confirm_overlap=True),
    )
    assert book(salon, "10:15", confirm_overlap=True).status == "confirmed"
    make_settings(min_booking_notice=60 * 24 * 30)
    refused("appointment.too_soon", lambda: as_caller(salon, actor, "12:00"))
    assert book(salon, "12:00").status == "confirmed"


@pytest.mark.parametrize("actor", AUTOMATIONS)
def test_an_automation_moves_and_books_a_batch_by_the_customers_rules(salon, actor):
    out = book(salon, "10:00")
    yesterday = wall(timezone.localdate() - dt.timedelta(days=1), "10:00")
    refused(
        "appointment.in_past",
        lambda: run(
            "appointment.appointment.reschedule",
            {"id": str(out.id), "start": yesterday},
            actor=actor,
        ),
    )
    refused(
        "appointment.in_past",
        lambda: run(
            "appointment.appointment.bulk_create",
            {
                "customer_id": str(salon.lucia.id),
                "services": [{"service_id": str(salon.cut.id)}],
                "staff_id": str(salon.ana.id),
                "starts": [yesterday],
            },
            actor=actor,
        ),
    )
    # The front desk writes down the hour she was really seen, even one already gone.
    moved = run("appointment.appointment.reschedule", {"id": str(out.id), "start": yesterday})
    assert moved.start == at(timezone.localdate() - dt.timedelta(days=1), "10:00")


@pytest.mark.parametrize("actor", AUTOMATIONS)
def test_an_automation_cancels_only_within_the_customers_policy(salon, actor):
    out = book(salon, "10:00")
    make_settings(allow_customer_cancellation=False)
    cancel = lambda who: run("appointment.appointment.cancel", {"id": str(out.id)}, actor=who)  # noqa: E731
    refused("appointment.customer_cancellation_disabled", lambda: cancel(actor))
    make_settings(allow_customer_cancellation=True, cancellation_notice_hours=24 * 30)
    refused("appointment.cancellation_notice_required", lambda: cancel(actor))
    assert cancel(TESTER).status == "cancelled"


@pytest.mark.parametrize(
    ("clock", "too_soon", "in_time"),
    [
        pytest.param(
            (dt.date(2026, 10, 25), "00:32"),
            (dt.date(2026, 10, 25), "23:00"),
            (dt.date(2026, 10, 26), "00:00"),
            id="25h-day",
        ),
        pytest.param(
            (dt.date(2026, 10, 24), "10:00"),
            (dt.date(2026, 10, 25), "08:00"),
            (dt.date(2026, 10, 25), "09:00"),
            id="eve-of-the-25h-day",
        ),
        pytest.param(
            (dt.date(2027, 3, 28), "00:32"),
            (dt.date(2027, 3, 29), "01:00"),
            (dt.date(2027, 3, 29), "02:00"),
            id="23h-day",
        ),
        pytest.param(
            (dt.date(2027, 3, 27), "10:00"),
            (dt.date(2027, 3, 28), "10:00"),
            (dt.date(2027, 3, 28), "11:00"),
            id="eve-of-the-23h-day",
        ),
    ],
)
def test_the_customers_booking_keeps_the_notice_in_real_hours(salon, monkeypatch, clock, too_soon, in_time):
    pin_clock(monkeypatch, at(*clock))
    make_settings(min_booking_notice=24 * 60)
    refused("appointment.too_soon", lambda: book(salon, too_soon[1], day=too_soon[0], source="online"))
    assert book(salon, in_time[1], day=in_time[0], source="online").start == at(*in_time)


@pytest.mark.parametrize(
    ("clock", "too_late", "in_time"),
    [
        pytest.param(
            (dt.date(2026, 10, 24), "10:00"),
            (dt.date(2026, 10, 25), "08:00"),
            (dt.date(2026, 10, 25), "09:00"),
            id="eve-of-the-25h-day",
        ),
        pytest.param(
            (dt.date(2027, 3, 27), "10:00"),
            (dt.date(2027, 3, 28), "10:00"),
            (dt.date(2027, 3, 28), "11:00"),
            id="eve-of-the-23h-day",
        ),
    ],
)
def test_the_customer_cancels_only_with_the_notice_in_real_hours(salon, monkeypatch, clock, too_late, in_time):
    pin_clock(monkeypatch, at(*clock))
    make_settings(allow_customer_cancellation=True, cancellation_notice_hours=24)
    close = book(salon, too_late[1], day=too_late[0])
    far = book(salon, in_time[1], day=in_time[0])
    cancel = lambda booked: run(  # noqa: E731
        "appointment.appointment.cancel", {"id": str(booked.id)}, actor="flow_run:0190a1b2"
    )
    refused("appointment.cancellation_notice_required", lambda: cancel(close))
    assert cancel(far).status == "cancelled"


AUTUMN = dt.date(2026, 10, 25)  # Madrid's day of 25 hours: 03:00 goes back to 02:00
SPRING = dt.date(2027, 3, 28)  # Madrid's day of 23 hours: 02:00 jumps to 03:00
ACROSS_THE_CHANGE = [
    pytest.param(AUTUMN, "01:37", 90, "2026-10-25T02:07:00+01:00", id="25h-day-90-min"),
    pytest.param(AUTUMN, "02:30", 60, "2026-10-25T02:30:00+01:00", id="25h-day-60-min"),
    pytest.param(SPRING, "01:37", 90, "2027-03-28T04:07:00+02:00", id="23h-day-90-min"),
    pytest.param(SPRING, "01:30", 60, "2027-03-28T03:30:00+02:00", id="23h-day-60-min"),
]


def assert_lasts_real_time(appointment_id, minutes: int, end: str) -> None:
    """Read back in UTC, the subtraction counts real time, not the wall clock's."""
    saved = Appointment.objects.get(pk=appointment_id)
    assert saved.end - saved.start == dt.timedelta(minutes=minutes)
    assert saved.end.astimezone(MADRID).isoformat() == end
    assert saved.duration_minutes == minutes


@pytest.mark.parametrize(("day", "start", "minutes", "end"), ACROSS_THE_CHANGE)
def test_an_appointment_lasts_its_real_minutes_the_nights_the_clock_changes(salon, monkeypatch, day, start, minutes, end):
    pin_clock(monkeypatch, at(day, "00:01"))
    out = book(salon, start, day=day, duration_minutes=minutes)
    assert out.end.isoformat() == end
    assert_lasts_real_time(out.id, minutes, end)


@pytest.mark.parametrize(("day", "start", "minutes", "end"), ACROSS_THE_CHANGE)
def test_an_appointment_moved_onto_the_change_lasts_its_real_minutes(salon, monkeypatch, day, start, minutes, end):
    pin_clock(monkeypatch, at(day, "00:01"))
    booked = book(salon, "10:00", day=day, duration_minutes=minutes)
    moved = run("appointment.appointment.reschedule", {"id": str(booked.id), "start": wall(day, start)})
    assert moved.end.isoformat() == end
    assert_lasts_real_time(booked.id, minutes, end)


@pytest.mark.parametrize(("day", "start", "minutes", "end"), ACROSS_THE_CHANGE)
def test_a_batch_books_each_time_for_its_real_minutes(salon, monkeypatch, day, start, minutes, end):
    pin_clock(monkeypatch, at(day, "00:01"))
    out = run(
        "appointment.appointment.bulk_create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "duration_minutes": minutes,
            "starts": [wall(day, start)],
        },
    )
    assert_lasts_real_time(out.rows[0].id, minutes, end)


def test_the_night_the_clock_jumps_a_booking_is_judged_up_to_its_real_end(salon, monkeypatch):
    # 00:30 + 3 real hours ends at 04:30 on the wall: 04:00 is taken (the wall clock's sum ended at 03:30).
    pin_clock(monkeypatch, at(SPRING, "00:01"))
    make_settings(allow_overlapping=False)
    book(salon, "04:00", day=SPRING)
    refused("appointment.slot_taken", lambda: book(salon, "00:30", day=SPRING, duration_minutes=180))


def test_the_night_the_clock_goes_back_a_booking_is_judged_up_to_its_real_end(salon, monkeypatch):
    # 01:00 + 2.5 real hours ends at 02:30 the second time: 03:00 is free (the wall clock's sum ended at 03:30).
    pin_clock(monkeypatch, at(AUTUMN, "00:01"))
    make_settings(allow_overlapping=False)
    book(salon, "03:00", day=AUTUMN)
    out = book(salon, "01:00", day=AUTUMN, duration_minutes=150)
    assert_lasts_real_time(out.id, 150, "2026-10-25T02:30:00+01:00")


def batch_at(salon, day: dt.date, start: str, minutes: int):
    return run(
        "appointment.appointment.bulk_create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "duration_minutes": minutes,
            "starts": [wall(day, start)],
        },
    )


def test_the_night_the_clock_jumps_a_batch_is_judged_up_to_its_real_end(salon, monkeypatch):
    # 00:30 + 3 real hours ends at 04:30 on the wall: 04:00 is taken (the wall clock's sum ended at 03:30).
    pin_clock(monkeypatch, at(SPRING, "00:01"))
    make_settings(allow_overlapping=False)
    book(salon, "04:00", day=SPRING)
    refused("appointment.slot_taken", lambda: batch_at(salon, SPRING, "00:30", 180))


def test_the_night_the_clock_goes_back_a_batch_is_judged_up_to_its_real_end(salon, monkeypatch):
    # 01:00 + 2.5 real hours ends at 02:30 the second time: 03:00 is free (the wall clock's sum ended at 03:30).
    pin_clock(monkeypatch, at(AUTUMN, "00:01"))
    make_settings(allow_overlapping=False)
    book(salon, "03:00", day=AUTUMN)
    out = batch_at(salon, AUTUMN, "01:00", 150)
    assert_lasts_real_time(out.rows[0].id, 150, "2026-10-25T02:30:00+01:00")


def test_a_time_the_clock_change_skips_is_a_422_on_the_start(salon):
    spring = dt.date(2027, 3, 28)
    make_settings(max_advance_booking=0)
    error = refused(
        "appointment.invalid_local_time",
        lambda: book(salon, "02:30", day=spring),
        InvalidPayload,
    )
    assert "start" in error.fields


def test_an_employee_books_for_themselves_only(salon, make_user):
    user = make_user("bea", role="hub_employee")
    salon.bea.user = user.person
    salon.bea.save()
    ctx = ctx_for("hub_employee", actor=user)
    op = get("appointment.appointment.create")
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "start": wall(MONDAY, "10:00"),
    }
    own = op(ctx, op.input.model_validate({**data, "staff_id": str(salon.bea.id)}))
    assert own.staff_id == salon.bea.id
    with pytest.raises(PermissionDenied):
        op(ctx, op.input.model_validate({**data, "staff_id": str(salon.ana.id)}))


# APPOINTMENT-F01, APPOINTMENT-F04: a caller that is not a person
# has no staff record, so «their own» appointments would be nobody's and what it was granted would never work. It
# takes the whole team's instead — as the customer, who books with any professional — and is judged by her rules. A
# person keeps «their own» (above), and nothing that was not granted is lent.
ADD_OWN = "appointment.add_own_appointment"
CHANGE_OWN = "appointment.change_own_appointment"
VIEW_ALL = "appointment.view_appointment"
NOT_A_PERSON = [
    "flow_run:0190a1b2",
    "system",
    None,
    KeyCaller(key_id="0190a1b2", name="Website", prefix="erpk_live_ab12", permissions=frozenset({ADD_OWN})),
]


def booking_with(salon, member, start="10:00", day=MONDAY) -> dict:
    return {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(member.id),
        "start": wall(day, start),
    }


@pytest.mark.parametrize("actor", NOT_A_PERSON)
def test_what_is_not_a_person_books_with_any_professional_with_its_own_permission(salon, actor):
    granted = {"actor": actor, "permissions": {ADD_OWN}}
    with_ana = run("appointment.appointment.create", booking_with(salon, salon.ana), **granted)
    with_bea = run("appointment.appointment.create", booking_with(salon, salon.bea, "11:00"), **granted)
    assert (with_ana.staff_id, with_bea.staff_id) == (salon.ana.id, salon.bea.id)
    week = [wall(MONDAY + dt.timedelta(weeks=n), "12:00") for n in (1, 2)]
    batch_of_bea = {key: value for key, value in booking_with(salon, salon.bea).items() if key != "start"}
    batch = run("appointment.appointment.bulk_create", {**batch_of_bea, "starts": week}, **granted)
    assert {row.staff_id for row in batch.rows} == {salon.bea.id}
    assert Appointment.objects.count() == 4


@pytest.mark.parametrize("actor", NOT_A_PERSON)
def test_with_its_own_permission_what_is_not_a_person_is_still_judged_as_the_customer(salon, actor):
    make_settings(min_booking_notice=60 * 24 * 30)
    refused(
        "appointment.too_soon",
        lambda: run("appointment.appointment.create", booking_with(salon, salon.bea), actor=actor, permissions={ADD_OWN}),
    )


def test_what_is_not_a_person_books_nothing_it_was_not_granted(salon):
    refused(
        "permission_denied",
        lambda: run("appointment.appointment.create", booking_with(salon, salon.bea), actor="flow_run:0190a1b2", permissions={VIEW_ALL}),
        PermissionDenied,
    )


def test_a_person_with_their_own_permission_and_no_staff_record_books_for_nobody(salon):
    refused(
        "permission_denied",
        lambda: run("appointment.appointment.create", booking_with(salon, salon.bea), permissions={ADD_OWN, VIEW_ALL}),
        PermissionDenied,
    )


@pytest.mark.parametrize("actor", ["flow_run:0190a1b2", "system", None])
def test_what_is_not_a_person_moves_confirms_and_edits_any_professionals_appointment_with_its_own_permission(
    salon, actor
):
    granted = {"actor": actor, "permissions": {CHANGE_OWN, VIEW_ALL}}
    beas = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"), status="pending")
    confirmed = run("appointment.appointment.confirm", {"id": str(beas.id)}, **granted)
    moved = run("appointment.appointment.reschedule", {"id": str(beas.id), "start": wall(MONDAY, "12:00")}, **granted)
    handed = run("appointment.appointment.reschedule", {"id": str(beas.id), "staff_id": str(salon.ana.id)}, **granted)
    run("appointment.appointment.update", {"id": str(beas.id), "notes": "Bring the photo"}, **granted)
    assert (confirmed.status, moved.start, handed.staff_id) == ("confirmed", at(MONDAY, "12:00"), salon.ana.id)
    assert Appointment.objects.get(pk=beas.id).notes == "Bring the photo"
    assert actions(beas.id) == ["confirmed", "rescheduled", "staff_changed"]


def test_a_person_with_their_own_permission_and_no_staff_record_changes_nobodys_appointment(salon):
    beas = make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"), status="pending")
    refused(
        "permission_denied",
        lambda: run("appointment.appointment.confirm", {"id": str(beas.id)}, permissions={CHANGE_OWN, VIEW_ALL}),
        PermissionDenied,
    )
