"""Models of the appointment app: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    Counter,
    History,
    Recurring,
    RecurringService,
    Settings,
)

from .conftest import (
    MONDAY,
    at,
    make_appointment,
    make_block,
    make_customer,
    make_member,
    make_service,
)

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def test_every_key_is_a_uuid7():
    customer, ana, cut = make_customer(), make_member(), make_service()
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    assert isinstance(appointment.id, uuid.UUID) and appointment.id.version == 7
    assert appointment.lines.get().id.version == 7


def test_the_factory_settings_are_one_set():
    settings = Settings()
    assert (
        settings.default_duration,
        settings.min_booking_notice,
        settings.max_advance_booking,
        settings.allow_overlapping,
        settings.allow_customer_cancellation,
        settings.cancellation_notice_hours,
        settings.calendar_start_hour,
        settings.calendar_end_hour,
        settings.slot_interval,
        settings.auto_confirm_online,
    ) == (60, 60, 90, True, True, 24, 8, 20, 15, True)


def test_the_settings_are_a_single_row():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())


def test_the_calendar_window_never_ends_before_it_starts():
    refused(
        lambda: Settings.objects.create(calendar_start_hour=20, calendar_end_hour=8)
    )


def test_one_counter_per_day():
    Counter.objects.create(day=MONDAY, last_number=3)
    refused(lambda: Counter.objects.create(day=MONDAY))


def test_an_appointment_ends_after_it_starts_and_its_number_is_unique():
    customer, ana, cut = make_customer(), make_member(), make_service()
    first = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"), number="APT-1")
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "11:00"), number="APT-1"
        )
    )
    first.end = first.start
    refused(lambda: first.save())


def test_an_unknown_status_or_source_is_refused():
    customer, ana, cut = make_customer(), make_member(), make_service()
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "10:00"), status="lost"
        )
    )
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "10:00"), source="fax"
        )
    )


def test_one_live_appointment_per_occurrence_of_a_series():
    customer, ana, cut = make_customer(), make_member(), make_service()
    series = Recurring.objects.create(
        customer=customer,
        customer_name=customer.name,
        staff=ana,
        staff_name=ana.full_name,
        frequency="weekly",
        day_of_week=0,
        time=dt.time(10),
        duration_minutes=30,
        start_date=MONDAY,
    )
    fields = {"recurring": series, "occurrence_date": MONDAY}
    first = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"), **fields)
    refused(
        lambda: make_appointment(customer, ana, [cut], at(MONDAY, "12:00"), **fields)
    )
    # A deleted occurrence frees its date (it is archived, not destroyed).
    first.deleted_at = first.start
    first.save()
    make_appointment(customer, ana, [cut], at(MONDAY, "12:00"), **fields)


def test_a_line_keeps_the_service_it_was_booked_with():
    customer, ana, cut = make_customer(), make_member(), make_service("Cut", price=1800)
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    line = appointment.lines.get()
    assert (line.name, line.price, line.duration_minutes, line.position) == (
        "Cut",
        1800,
        30,
        0,
    )
    refused(
        lambda: AppointmentService.objects.create(
            appointment=appointment,
            service=cut,
            name="Cut",
            price=1,
            duration_minutes=30,
            position=0,
        )
    )


def test_a_series_refuses_a_rule_that_cannot_repeat():
    customer, ana = make_customer(), make_member()
    base = {
        "customer": customer,
        "customer_name": customer.name,
        "staff": ana,
        "staff_name": ana.full_name,
        "time": dt.time(10),
        "duration_minutes": 30,
        "start_date": MONDAY,
    }
    refused(lambda: Recurring.objects.create(frequency="yearly", **base))
    refused(lambda: Recurring.objects.create(frequency="weekly", day_of_week=7, **base))
    refused(
        lambda: Recurring.objects.create(
            frequency="weekly", end_date=MONDAY - dt.timedelta(days=1), **base
        )
    )
    refused(
        lambda: Recurring.objects.create(frequency="weekly", max_occurrences=0, **base)
    )
    series = Recurring.objects.create(frequency="weekly", **base)
    RecurringService.objects.create(
        recurring=series, service=make_service(), position=0
    )
    assert series.lines.count() == 1


def test_a_block_ends_after_it_starts():
    make_block(at(MONDAY, "10:00"), at(MONDAY, "11:00"))
    refused(lambda: make_block(at(MONDAY, "11:00"), at(MONDAY, "11:00")))
    refused(
        lambda: make_block(at(MONDAY, "11:00"), at(MONDAY, "12:00"), block_type="party")
    )
    assert BlockedTime.objects.count() == 1


def test_history_belongs_to_its_appointment():
    customer, ana, cut = make_customer(), make_member(), make_service()
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    History.objects.create(appointment=appointment, action="created", actor="Ana")
    refused(lambda: History.objects.create(appointment=appointment, action="sneezed"))
    assert appointment.history.count() == 1


def test_a_row_reads_as_a_person_names_it():
    customer, ana, cut = (
        make_customer("Lucía"),
        make_member("Ana", "López"),
        make_service(),
    )
    appointment = make_appointment(
        customer, ana, [cut], at(MONDAY, "10:00"), number="APT-20261019-0001"
    )
    assert str(appointment) == "APT-20261019-0001"
    assert Appointment.Status.NO_SHOW == "no_show"
