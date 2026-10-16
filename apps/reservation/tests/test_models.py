"""The book's tables: their defaults, the rules the database itself keeps, and how they sort."""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)

from .conftest import (
    TOMORROW,
    make_blocked,
    make_customer,
    make_entry,
    make_reservation,
    make_slot,
    make_table,
)

pytestmark = pytest.mark.django_db


def refused(make) -> bool:
    try:
        with transaction.atomic():
            make()
    except IntegrityError:
        return True
    return False


def test_every_key_is_a_uuid7():
    reservation = make_reservation()
    assert isinstance(reservation.pk, uuid.UUID) and reservation.pk.version == 7


def test_the_settings_come_with_the_old_modules_rules_and_a_phone_always_required():
    settings = Settings.objects.create()
    assert (
        settings.min_party_size,
        settings.max_party_size,
        settings.min_advance_hours,
        settings.max_advance_days,
        settings.default_duration_minutes,
        settings.auto_confirm,
        settings.require_phone,
        settings.require_email,
        settings.no_show_window_minutes,
    ) == (1, 20, 1, 30, 120, False, True, False, 15)


def test_there_is_one_settings_row():
    Settings.objects.create()
    assert refused(lambda: Settings.objects.create())


def test_a_reservation_is_born_pending_from_the_phone_for_two_hours():
    reservation = make_reservation()
    assert (reservation.status, reservation.source, reservation.duration_minutes) == (
        "pending",
        "phone",
        120,
    )
    assert reservation.is_deleted is False
    assert str(reservation) == "Ana García · 2026-10-15 21:00"


def test_the_database_refuses_an_unknown_status_or_source_and_an_empty_party():
    assert refused(lambda: make_reservation(status="lost"))
    assert refused(lambda: make_reservation(source="pigeon"))
    assert refused(lambda: make_reservation(party_size=0))
    assert refused(lambda: make_reservation(duration_minutes=0))
    assert refused(lambda: make_reservation(duration_minutes=24 * 60 + 1))


def test_reservations_sort_by_day_then_time():
    late = make_reservation(time="22:00")
    early = make_reservation(time="20:00")
    before = make_reservation(date=TOMORROW - dt.timedelta(days=1), time="23:00")
    assert list(Reservation.objects.all()) == [before, early, late]


def test_a_reservation_keeps_its_table_and_its_customer_and_they_cannot_be_deleted_under_it():
    table = make_table("5")
    customer = make_customer()
    reservation = make_reservation(table=table, customer_id=customer.id)
    assert (reservation.table, reservation.customer_id) == (table, customer.id)
    assert refused(lambda: table.delete())


def test_a_slot_ends_after_it_starts_and_takes_at_least_one_reservation():
    assert refused(lambda: make_slot(start="21:00", end="20:00"))
    assert refused(lambda: make_slot(start="21:00", end="21:00"))
    assert refused(lambda: make_slot(max_reservations=0))
    assert refused(lambda: make_slot(max_covers=0))
    assert refused(lambda: make_slot(day_of_week=7))
    slot = make_slot(max_covers=40)
    assert (slot.max_covers, slot.is_deleted) == (40, False)


def test_slots_sort_by_day_then_start():
    dinner = make_slot(3, "20:00", "23:00")
    lunch = make_slot(3, "13:00", "16:00")
    monday = make_slot(0, "20:00", "23:00")
    assert list(TimeSlot.objects.all()) == [monday, lunch, dinner]


def test_a_blocked_date_is_the_whole_day_or_a_window_that_ends_after_it_starts():
    assert make_blocked(reason="Holiday").is_full_day is True
    assert refused(lambda: make_blocked(is_full_day=False))
    assert refused(
        lambda: make_blocked(
            is_full_day=False,
            blocked_from=dt.time(22, 0),
            blocked_until=dt.time(21, 0),
        )
    )
    window = make_blocked(
        TOMORROW + dt.timedelta(days=1),
        is_full_day=False,
        blocked_from=dt.time(20, 0),
        blocked_until=dt.time(22, 0),
    )
    assert window.pk


def test_a_date_is_blocked_once_at_the_same_hour_among_the_live_ones():
    first = make_blocked()
    assert refused(lambda: make_blocked())
    first.is_deleted = True
    first.save()
    assert make_blocked().pk
    assert BlockedDate.objects.filter(date=TOMORROW).count() == 2


def test_the_waitlist_keeps_the_order_people_were_written_down_in():
    second = make_entry(time="21:00")
    first_of_the_day_before = make_entry(date=TOMORROW - dt.timedelta(days=1))
    third = make_entry(time="21:00", guest_name="Marta")
    earlier_time = make_entry(time="20:30")
    assert list(WaitlistEntry.objects.all()) == [
        first_of_the_day_before,
        earlier_time,
        second,
        third,
    ]
    assert (second.is_contacted, second.reservation_id) == (False, None)
