"""The time clock on the clock of the business, not the deployment's (hub#779): in a business in the Canaries whoever
clocks in at 9:00 there reads 9:00 in the CSV, a correction typed at 9:00 is 9:00 there, and a working day is the day
it is there."""

import csv
import datetime as dt
import io

import pytest

from apps.attendance.models import Record
from apps.attendance.queries import business_date
from apps.attendance.schemas import CorrectIn
from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import make_member, run, utc

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"
#: The Canaries are on UTC in November, Madrid an hour ahead: 23:30 there is already tomorrow in Madrid.
NIGHT = "2026-11-02T23:30"


def in_canary():
    return use_hub(Hub(slug="a", timezone=CANARY))


def test_the_csv_says_each_hour_on_the_businesss_clock():
    Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-11-02T09:00"),
        clock_out_at=utc("2026-11-02T17:00"),
        status="closed",
        work_date=dt.date(2026, 11, 2),
    )
    with in_canary():
        export = run("attendance.record.export", {"date_from": "2026-11-02", "date_to": "2026-11-02"})
    row = list(csv.reader(io.StringIO(export.csv)))[1]
    assert row[2:4] == ["2026-11-02 09:00", "2026-11-02 17:00"]


def test_an_hour_typed_without_offset_is_the_businesss_wall_clock():
    with in_canary():
        data = CorrectIn(
            record_id="01a16000-0000-7000-8000-000000000001", clock_in_at="2026-11-02T09:00", reason="At nine"
        )
    assert data.clock_in_at == utc("2026-11-02T09:00")


def test_the_day_of_an_instant_is_the_businesss_day():
    with in_canary():
        assert business_date(utc(NIGHT)) == dt.date(2026, 11, 2)


def test_clocking_in_before_the_businesss_midnight_opens_that_day(person, clock):
    _, ctx = person()
    clock(NIGHT)
    with in_canary():
        opened = run("attendance.record.clock_in", {}, ctx)
    assert opened.work_date == dt.date(2026, 11, 2)


def test_a_corrected_day_is_the_businesss_day(clock):
    record = Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-11-01T09:00"),
        clock_out_at=utc("2026-11-01T17:00"),
        status="closed",
        work_date=dt.date(2026, 11, 1),
    )
    clock("2026-11-03T12:00")
    with in_canary():
        corrected = run(
            "attendance.record.correct",
            {
                "record_id": str(record.id),
                "clock_in_at": "2026-11-02T23:30",
                "clock_out_at": None,
                "reason": "Forgot to clock in",
            },
        )
    assert (corrected.clock_in_at, corrected.work_date) == (utc(NIGHT), dt.date(2026, 11, 2))


def test_my_day_is_the_businesss_today(person, clock):
    member, ctx = person()
    Record.objects.create(member=member, clock_in_at=utc("2026-11-02T22:00"), status="open", work_date=dt.date(2026, 11, 2))
    clock(NIGHT)
    with in_canary():
        mine = run("attendance.record.current", {}, ctx)
    assert mine.today.worked_seconds == 5400
