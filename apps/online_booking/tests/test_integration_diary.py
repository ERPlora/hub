"""Online booking with the real diary and what it reads (no doubles): Citas' agenda and its rules, Horarios'
hours, Personal's shifts and time off, and Servicios' catalog changed through its own operations.

What the page offers is what the diary would give the customer, and what she books is what the agenda shows.
"""

import datetime as dt

import pytest
from live.errors import Conflict

from apps.appointment.models import Appointment

from .conftest import TUESDAY, at, booking_data, make_day, make_rules, public, run

pytestmark = pytest.mark.django_db


def times(salon, staff=None) -> list[str]:
    data = {"service_ids": [str(salon.cut.id)], "date": TUESDAY.isoformat()}
    if staff is not None:
        data["staff_id"] = str(staff.id)
    return [slot.start.strftime("%H:%M") for slot in public("slots", data).slots]


def make_shift(member, weekday: int, start: str, end: str):
    from apps.staff.models import Schedule, ScheduleDay

    schedule = Schedule.objects.create(member=member, name="Usual", is_default=True)
    ScheduleDay.objects.create(
        schedule=schedule,
        weekday=weekday,
        start_time=dt.time.fromisoformat(start),
        end_time=dt.time.fromisoformat(end),
    )


def make_time_off(member, day: dt.date):
    from apps.staff.models import TimeOff

    TimeOff.objects.create(
        member=member,
        start_date=day,
        end_date=day,
        is_full_day=True,
        status=TimeOff.Status.APPROVED,
    )


# ── Citas ──────────────────────────────────────────────────────────────────────────────────────


def test_the_booking_is_on_the_agenda_and_waits_to_be_confirmed_there(salon):
    make_rules(auto_confirm_online=False)
    booked = public("book", booking_data(salon, "10:00", staff_id=str(salon.ana.id)))
    agenda = run("appointment.appointment.list", {"date_from": TUESDAY.isoformat()})
    row = next(item for item in agenda.rows if item.number == booked.number)
    assert (row.source, row.status, row.booked_by_customer, row.staff_name) == (
        "online",
        "pending",
        True,
        "Ana López",
    )
    assert run("appointment.appointment.count_to_confirm").count == 1
    run("online_booking.booking.confirm", {"number": booked.number})
    assert run("appointment.appointment.count_to_confirm").count == 0
    assert (
        run("appointment.appointment.get", {"number": booked.number}).status
        == "confirmed"
    )


def test_a_time_once_booked_is_no_longer_offered_for_that_professional(salon):
    make_rules(slot_interval=60, min_booking_notice=0)
    make_day(1, ("09:00", "12:00"))
    assert times(salon, salon.ana) == ["09:00", "10:00", "11:00"]
    public("book", booking_data(salon, "10:00", staff_id=str(salon.ana.id)))
    assert times(salon, salon.ana) == ["09:00", "11:00"]
    # The diary's own check says the same.
    check = run(
        "appointment.availability.check",
        {
            "service_ids": [str(salon.cut.id)],
            "start": f"{TUESDAY}T10:00",
            "staff_id": str(salon.ana.id),
            "for_customer": True,
        },
    )
    assert (check.available, check.code) == (False, "overlap")


def test_the_customer_never_overlaps_even_when_the_front_desk_may(salon):
    make_rules(allow_overlapping=True)
    run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": f"{TUESDAY}T10:00",
        },
    )
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "10:00", staff_id=str(salon.ana.id)))
    assert error.value.code == "appointment.slot_taken"


def test_the_owners_preview_is_judged_as_the_customer_never_as_the_front_desk(salon):
    """The public operations are the customer's door whoever opens it: a person of the team previewing the
    page (Citas' ``by_person``) gets none of the front desk's exceptions — an overlap, a time inside the
    notice or in the past, a cancellation outside the policy (ONLINE_BOOKING-F01, F11)."""

    def preview(name: str, data: dict):
        return run(f"online_booking.public.{name}", data, role="hub_admin")

    make_rules(allow_overlapping=True, min_booking_notice=24 * 60)
    run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": f"{(TUESDAY + dt.timedelta(days=1)).isoformat()}T10:00",
        },
    )
    refused = {}
    for label, data in {
        "overlap": booking_data(salon, "10:00", day=TUESDAY + dt.timedelta(days=1), staff_id=str(salon.ana.id)),
        "notice": booking_data(salon, "07:00"),
        "past": booking_data(salon, "07:00", day=TUESDAY - dt.timedelta(days=2)),
    }.items():
        with pytest.raises(Conflict) as error:
            preview("book", data)
        refused[label] = error.value.code
    assert refused == {
        "overlap": "appointment.slot_taken",
        "notice": "appointment.too_soon",
        "past": "appointment.in_past",
    }
    make_rules(min_booking_notice=0)
    booked = preview("book", booking_data(salon, "10:00"))
    make_rules(cancellation_notice_hours=48)
    with pytest.raises(Conflict) as error:
        preview("cancel", {"token": booked.token})
    assert error.value.code == "appointment.cancellation_notice_required"
    appointment = Appointment.objects.get(number=booked.number)
    assert (appointment.source, appointment.status) == ("online", "confirmed")


def test_the_maximum_advance_is_the_diarys(salon):
    make_rules(max_advance_booking=7)
    with pytest.raises(Conflict) as error:
        public(
            "book", booking_data(salon, "10:00", day=TUESDAY + dt.timedelta(days=10))
        )
    assert error.value.code == "appointment.too_far"
    assert times(salon) != []


# ── Horarios and Personal ──────────────────────────────────────────────────────────────────────


def test_a_day_the_business_is_closed_offers_nothing(salon):
    make_day(1, closed=True)
    assert times(salon) == []
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "10:00"))
    assert error.value.code == "appointment.outside_schedule"


def test_the_professionals_shift_and_time_off_decide_who_takes_it(salon):
    make_rules(slot_interval=60, min_booking_notice=0)
    make_day(1, ("09:00", "13:00"))
    make_shift(salon.ana, 1, "09:00", "11:00")
    make_time_off(salon.bea, TUESDAY)
    assert times(salon, salon.ana) == ["09:00", "10:00"]
    assert times(salon, salon.bea) == []
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "12:00", staff_id=str(salon.ana.id)))
    assert error.value.code == "appointment.outside_staff_hours"
    # «Anyone» at 10:00: Ana works, Bea is off.
    assert public("book", booking_data(salon, "10:00")).staff_name == "Ana López"


# ── Servicios ──────────────────────────────────────────────────────────────────────────────────


def test_a_service_taken_off_online_booking_in_services_leaves_the_page(salon):
    run(
        "service.service.update",
        {"id": str(salon.colour.id), "allow_online_booking": False},
    )
    assert [row.name for row in public("services").rows] == ["Haircut"]
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "10:00", service_ids=[str(salon.colour.id)]))
    assert error.value.code == "online_booking.service_not_online"


def test_the_professionals_own_length_and_price_are_what_is_booked(salon):
    from apps.service.models import Assignment

    Assignment.objects.filter(service=salon.cut, member=salon.bea).update(
        custom_duration=45, custom_price=2500
    )
    booked = public("book", booking_data(salon, "10:00", staff_id=str(salon.bea.id)))
    appointment = Appointment.objects.get(number=booked.number)
    assert appointment.duration_minutes == 45
    assert appointment.end == at(TUESDAY, "10:45")
    assert run("online_booking.booking.get", {"number": booked.number}).total == 2500


def test_services_settings_decide_what_the_page_shows(salon):
    run("service.settings.update", {"show_prices": False})
    cut = next(row for row in public("services").rows if row.name == "Haircut")
    assert (cut.price, cut.duration_minutes) == (None, 30)


def test_a_service_that_requires_confirmation_waits_in_the_inbox_even_with_auto_confirm(salon):
    make_rules(auto_confirm_online=True)
    run("service.service.update", {"id": str(salon.colour.id), "requires_confirmation": True})
    plain = public("book", booking_data(salon, "10:00"))
    waiting = public("book", booking_data(salon, "12:00", phone="699 000 111", service_ids=[str(salon.colour.id)]))
    assert (plain.status, waiting.status) == ("confirmed", "pending")
    assert waiting.message == "We have received your booking. The business will confirm it shortly."
    pending = run("online_booking.booking.list", {"status": "pending"})
    assert [row.number for row in pending.rows] == [waiting.number]
