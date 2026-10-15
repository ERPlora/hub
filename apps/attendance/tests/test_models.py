"""The attendance tables and the rules the database itself keeps, whatever door writes (the admin, an
operation, a raw save): one open day per person, one running break per day, a coherent status, times in
order, one settings row with its ranges, and no staff record deleted under its working days."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.attendance.models import AttendanceSettings, Break, Correction, Record

from .conftest import make_member, utc

pytestmark = pytest.mark.django_db


def open_day(member, at="2026-10-06T08:00", **fields) -> Record:
    instant = utc(at)
    return Record.objects.create(
        member=member, clock_in_at=instant, work_date=instant.date(), **fields
    )


def refused(**create) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        create.pop("model").objects.create(**create)


def test_a_new_day_is_open_from_the_shared_device_with_no_location():
    day = open_day(make_member())
    assert day.status == Record.Status.OPEN
    assert day.source == Record.Source.SHARED
    assert day.clock_out_at is None
    assert (day.in_lat, day.in_within_radius, day.out_distance_m) == (None, None, None)
    assert day.note == ""
    # UUIDv7 keys: they sort by creation.
    assert day.pk.version == 7


def test_one_open_day_per_person():
    ana = make_member()
    open_day(ana)
    with pytest.raises(IntegrityError), transaction.atomic():
        open_day(ana, "2026-10-06T09:00")
    # Another person, or the same person with a closed day, is fine.
    open_day(make_member("Bea", "Ruiz"))
    Record.objects.filter(member=ana).update(
        status=Record.Status.CLOSED, clock_out_at=utc("2026-10-06T16:00")
    )
    open_day(ana, "2026-10-07T08:00")


def test_a_day_waiting_for_review_does_not_hold_the_open_slot():
    ana = make_member()
    open_day(ana, status=Record.Status.NEEDS_REVIEW)
    open_day(ana, "2026-10-07T08:00")
    assert Record.objects.filter(member=ana).count() == 2


@pytest.mark.parametrize(
    ("status", "clock_out"),
    [
        (Record.Status.OPEN, "2026-10-06T16:00"),
        (Record.Status.NEEDS_REVIEW, "2026-10-06T16:00"),
        (Record.Status.CLOSED, None),
        ("lost", None),
    ],
)
def test_the_status_matches_the_clock_out(status, clock_out):
    refused(
        model=Record,
        member=make_member(),
        clock_in_at=utc("2026-10-06T08:00"),
        work_date=utc("2026-10-06T08:00").date(),
        clock_out_at=utc(clock_out) if clock_out else None,
        status=status,
    )


def test_the_clock_out_is_after_the_clock_in():
    for out in ("2026-10-06T08:00", "2026-10-06T07:59"):
        refused(
            model=Record,
            member=make_member(),
            clock_in_at=utc("2026-10-06T08:00"),
            work_date=utc("2026-10-06T08:00").date(),
            clock_out_at=utc(out),
            status=Record.Status.CLOSED,
        )


def test_the_source_is_shared_or_personal():
    refused(
        model=Record,
        member=make_member(),
        clock_in_at=utc("2026-10-06T08:00"),
        work_date=utc("2026-10-06T08:00").date(),
        source="kiosk",
    )


def test_one_running_break_per_day_and_it_ends_after_it_starts():
    day = open_day(make_member())
    Break.objects.create(record=day, started_at=utc("2026-10-06T10:00"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Break.objects.create(record=day, started_at=utc("2026-10-06T10:05"))
    refused(
        model=Break,
        record=day,
        started_at=utc("2026-10-06T11:00"),
        ended_at=utc("2026-10-06T10:59"),
    )
    # A break of no length is a break that ended at once (a correction closes it at its own start).
    Break.objects.filter(record=day).update(ended_at=utc("2026-10-06T10:00"))
    Break.objects.create(record=day, started_at=utc("2026-10-06T12:00"))


def test_working_days_keep_their_staff_record():
    # The law asks for four years of records: a staff record with days cannot be deleted (staff
    # terminates, never deletes; the admin is refused here).
    ana = make_member()
    open_day(ana)
    with pytest.raises(ProtectedError):
        ana.delete()


def test_breaks_and_corrections_keep_their_day():
    day = open_day(make_member())
    Break.objects.create(record=day, started_at=utc("2026-10-06T10:00"))
    Correction.objects.create(
        record=day,
        old_clock_in_at=day.clock_in_at,
        old_status="open",
        new_clock_in_at=day.clock_in_at,
        new_status="open",
        reason="Same time",
    )
    with pytest.raises(ProtectedError):
        day.delete()


def test_ordering_newest_first():
    ana = make_member()
    first = open_day(
        ana,
        "2026-10-05T08:00",
        status=Record.Status.CLOSED,
        clock_out_at=utc("2026-10-05T16:00"),
    )
    second = open_day(ana, "2026-10-06T08:00")
    assert list(Record.objects.all()) == [second, first]
    assert str(second) == "Ana López · 2026-10-06"


def test_one_settings_row_with_the_old_defaults():
    settings_row = AttendanceSettings.objects.create()
    assert (
        settings_row.require_location,
        settings_row.geofence_radius_m,
        settings_row.workplace_lat,
        settings_row.workplace_lng,
        settings_row.auto_close_after_hours,
    ) == (False, 100, None, None, 12)
    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceSettings.objects.create()


@pytest.mark.parametrize(
    "fields",
    [
        {"geofence_radius_m": 75},
        {"auto_close_after_hours": 0},
        {"auto_close_after_hours": 25},
        {"workplace_lat": 91, "workplace_lng": 0},
        {"workplace_lat": 0, "workplace_lng": -181},
        {"workplace_lat": 40.4},
        {"workplace_lng": -3.7},
    ],
)
def test_the_settings_ranges(fields):
    refused(model=AttendanceSettings, **fields)


def test_a_correction_says_whether_the_system_made_it_and_keeps_the_name():
    day = open_day(make_member())
    trail = Correction.objects.create(
        record=day,
        old_clock_in_at=day.clock_in_at,
        old_status="open",
        new_clock_in_at=day.clock_in_at,
        new_status="open",
        reason="Same time",
    )
    assert (trail.is_system, trail.created_by_name) == (False, "")
