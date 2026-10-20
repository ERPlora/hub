"""Write operations of the attendance app: one transaction each, with its events in the outbox.

The cases come from the old module's batteries (clock_cycle against the kernel; data.pg: two clock-ins
in a row, the geofence, clock-out closing the running break, the correction guards and the overlap of
attendance#12, the review of forgotten days, the settings singleton) and the WORKBOOK. A refused command
leaves no trace: no row, no event.
"""

import datetime as dt
import json

import psycopg
import pytest
from django.utils import timezone
from geopy.distance import geodesic
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.attendance import events
from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from apps.attendance.schemas import ClosedOut, RecordOut, ReviewOut, SettingsOut
from apps.staff.models import Member

from .conftest import A, B, ctx_for, make_member, run, utc

pytestmark = pytest.mark.django_db

WORKPLACE = (40.4168, -3.7038)  # Puerta del Sol
NEAR = (40.4173, -3.7038)  # 55 m north
FAR = (40.4245, -3.7038)  # 855 m north


def outbox(prefix: str = "attendance.") -> list[tuple[str, dict]]:
    return [
        (e.name, e.payload)
        for e in OutboxEvent.objects.filter(name__startswith=prefix).order_by(
            "created_at", "id"
        )
    ]


def names() -> list[str]:
    return [name for name, _ in outbox()]


def location_on(
    radius: int = 100, workplace=WORKPLACE, hours: int = 12
) -> AttendanceSettings:
    lat, lng = workplace if workplace else (None, None)
    return AttendanceSettings.objects.create(
        require_location=True,
        geofence_radius_m=radius,
        workplace_lat=lat,
        workplace_lng=lng,
        auto_close_after_hours=hours,
    )


def refused(code: str, name: str, data, ctx) -> Conflict:
    before = (
        Record.objects.count(),
        Break.objects.count(),
        Correction.objects.count(),
        len(outbox()),
    )
    with pytest.raises(Conflict) as caught:
        run(name, data, ctx)
    assert caught.value.code == code
    after = (
        Record.objects.count(),
        Break.objects.count(),
        Correction.objects.count(),
        len(outbox()),
    )
    assert after == before, "a refused command left a trace"
    return caught.value


# attendance.record.clock_in (ATTENDANCE-F01)


def test_clocking_in_opens_my_day_at_the_servers_time(person, clock):
    now = clock("2026-10-06T07:00")
    ana, ctx = person()
    result = run("attendance.record.clock_in", {}, ctx)
    assert isinstance(result, RecordOut)
    day = Record.objects.get()
    assert (result.id, day.member, day.status, day.source) == (
        day.id,
        ana,
        "open",
        "shared",
    )
    assert (day.clock_in_at, day.work_date, day.created_by) == (
        now,
        dt.date(2026, 10, 6),
        ctx.actor,
    )
    assert (day.in_lat, day.in_distance_m, day.in_within_radius) == (None, None, None)
    assert outbox() == [
        (events.CLOCKED_IN, {"id": str(day.id), "member_id": str(ana.id)})
    ]


def test_a_second_clock_in_while_a_day_is_open_is_refused(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T07:05")
    error = refused(
        "attendance.already_clocked_in", "attendance.record.clock_in", {}, ctx
    )
    assert "You already have an open working day" in error.message
    assert Record.objects.filter(status="open").count() == 1


def test_a_user_without_a_staff_record_cannot_clock(make_user):
    ctx = ctx_for("hub_employee", actor=make_user("zoe"))
    for name in (
        "attendance.record.clock_in",
        "attendance.record.clock_out",
        "attendance.break.start",
        "attendance.break.end",
    ):
        refused("attendance.no_member_record", name, {}, ctx)


@pytest.mark.parametrize("status", [Member.Status.INACTIVE, Member.Status.ON_LEAVE])
def test_a_record_that_is_not_active_cannot_clock_in(person, clock, status):
    clock("2026-10-06T07:00")
    _, ctx = person(status=status)
    refused("attendance.member_not_active", "attendance.record.clock_in", {}, ctx)


def test_a_forgotten_day_is_flagged_when_the_person_clocks_in_again(person, clock):
    # ATTENDANCE-F05 without waiting for the worker: 12 h by default; the new day opens at once.
    clock("2026-10-05T07:00")
    ana, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    forgotten = Record.objects.get()
    clock("2026-10-06T07:00")
    run("attendance.record.clock_in", {}, ctx)
    forgotten.refresh_from_db()
    assert (forgotten.status, forgotten.clock_out_at) == ("needs_review", None)
    assert (
        Record.objects.filter(member=ana, status="open")
        .exclude(pk=forgotten.pk)
        .count()
        == 1
    )
    assert names()[-2:] == [events.RECORD_FLAGGED, events.CLOCKED_IN]


def test_an_open_day_younger_than_the_threshold_still_blocks(person, clock):
    AttendanceSettings.objects.create(auto_close_after_hours=10)
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T16:59")
    refused("attendance.already_clocked_in", "attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T17:01")
    run("attendance.record.clock_in", {}, ctx)
    assert sorted(Record.objects.values_list("status", flat=True)) == [
        "needs_review",
        "open",
    ]


# The workplace radius (ATTENDANCE-F03): only personal devices, never the clock-out. Whether a device is
# personal is the server's to know, never the payload's (review of 2026-10-15, finding 6): phase 1 has
# no device modes, so `services.device_source` says «shared»; these tests stand in for phase 2.


@pytest.fixture
def personal_device(monkeypatch):
    from apps.attendance import services

    monkeypatch.setattr(services, "device_source", lambda ctx: "personal")


def test_phase_1_clocks_every_device_as_the_shared_one_whatever_the_payload_says(person, clock):
    from apps.attendance import services

    clock("2026-10-06T07:00")
    location_on()
    _, ctx = person()
    assert services.device_source(ctx) == "shared"
    run("attendance.record.clock_in", {"source": "personal"}, ctx)
    assert (Record.objects.get().source, Record.objects.get().in_within_radius) == ("shared", None)


def test_a_personal_device_must_send_its_position(person, clock, personal_device):
    clock("2026-10-06T07:00")
    location_on()
    _, ctx = person()
    refused("attendance.location_required", "attendance.record.clock_in", {}, ctx)


def test_without_the_workplace_set_a_personal_device_cannot_clock_in(person, clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(workplace=None)
    _, ctx = person()
    data = {"lat": NEAR[0], "lng": NEAR[1]}
    refused("attendance.workplace_not_set", "attendance.record.clock_in", data, ctx)


def test_outside_the_radius_it_says_how_far(person, clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = person()
    data = {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 9.5}
    error = refused("attendance.outside_radius", "attendance.record.clock_in", data, ctx)
    assert error.message == (
        "You are 855 m from the workplace, outside the allowed 100 m. Move closer to clock in, or clock in at the counter."
    )


def test_inside_the_radius_the_day_keeps_where_it_was_clocked(person, clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = person()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1], "accuracy_m": 9.5}, ctx)
    day = Record.objects.get()
    assert (day.source, day.in_lat, day.in_lng, day.in_accuracy_m, day.in_within_radius) == (
        "personal",
        NEAR[0],
        NEAR[1],
        9.5,
        True,
    )
    # The Hub measures the distance itself (WGS-84 geodesic), never the device.
    assert day.in_distance_m == pytest.approx(geodesic(WORKPLACE, NEAR).meters, abs=0.5)


def test_the_counter_pos_is_never_asked_for_a_location(person, clock):
    clock("2026-10-06T07:00")
    location_on()
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    assert Record.objects.get().in_within_radius is None


def test_a_position_nobody_asked_for_keeps_only_how_far_never_where(person, clock):
    # Review of 2026-10-15, finding 7: the exact coordinates are kept only when the business requires
    # the location and the device is personal; otherwise only the distance, inside/outside and accuracy.
    clock("2026-10-06T07:00")
    AttendanceSettings.objects.create(workplace_lat=WORKPLACE[0], workplace_lng=WORKPLACE[1])
    _, ctx = person()
    run("attendance.record.clock_in", {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 7}, ctx)
    day = Record.objects.get()
    assert (day.in_lat, day.in_lng) == (None, None)
    assert (round(day.in_distance_m), day.in_within_radius, day.in_accuracy_m) == (855, False, 7)


def test_not_required_a_personal_device_keeps_no_coordinates_either(person, clock, personal_device):
    clock("2026-10-06T07:00")
    AttendanceSettings.objects.create(workplace_lat=WORKPLACE[0], workplace_lng=WORKPLACE[1])
    _, ctx = person()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1]}, ctx)
    day = Record.objects.get()
    assert (day.in_lat, day.in_lng, day.in_within_radius) == (None, None, True)


def test_clocking_out_is_never_blocked_by_the_location(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    location_on(radius=50)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {"lat": FAR[0], "lng": FAR[1], "accuracy_m": 12}, ctx)
    day = Record.objects.get()
    assert (day.status, round(day.out_distance_m), day.out_within_radius, day.out_accuracy_m) == ("closed", 855, False, 12)
    # The shared device: no coordinates kept.
    assert (day.out_lat, day.out_lng) == (None, None)
    # And without a position at all.
    clock("2026-10-07T07:00")
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-07T15:00")
    run("attendance.record.clock_out", {}, ctx)
    assert Record.objects.filter(status="closed").count() == 2


def test_a_personal_device_out_of_the_radius_still_clocks_out_and_keeps_where(person, clock, personal_device):
    clock("2026-10-06T07:00")
    location_on(radius=100)
    _, ctx = person()
    run("attendance.record.clock_in", {"lat": NEAR[0], "lng": NEAR[1]}, ctx)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {"lat": FAR[0], "lng": FAR[1]}, ctx)
    day = Record.objects.get()
    assert (day.status, day.out_lat, day.out_lng, day.out_within_radius) == ("closed", FAR[0], FAR[1], False)


# attendance.record.clock_out and the breaks (ATTENDANCE-F01, F02)


def test_a_full_working_day_with_two_breaks(person, clock):
    clock("2026-10-06T07:00")
    ana, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T10:00")
    started = run("attendance.break.start", {}, ctx)
    assert started.break_started_at == utc("2026-10-06T10:00")
    clock("2026-10-06T10:15")
    ended = run("attendance.break.end", {}, ctx)
    assert ended.break_started_at is None and ended.break_seconds == 900
    clock("2026-10-06T13:00")
    run("attendance.break.start", {}, ctx)
    clock("2026-10-06T15:00")
    # Clocking out in the middle of a break ends it at that very moment.
    closed = run("attendance.record.clock_out", {}, ctx)
    assert (closed.status, closed.clock_out_at, closed.break_count) == (
        "closed",
        utc("2026-10-06T15:00"),
        2,
    )
    assert closed.break_seconds == 900 + 2 * 3600
    assert closed.worked_seconds == 8 * 3600 - closed.break_seconds
    assert list(
        Break.objects.order_by("started_at").values_list("ended_at", flat=True)
    ) == [
        utc("2026-10-06T10:15"),
        utc("2026-10-06T15:00"),
    ]
    day_id = str(closed.id)
    assert outbox() == [
        (events.CLOCKED_IN, {"id": day_id, "member_id": str(ana.id)}),
        (
            events.BREAK_STARTED,
            {
                "id": str(Break.objects.order_by("started_at")[0].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_ENDED,
            {
                "id": str(Break.objects.order_by("started_at")[0].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_STARTED,
            {
                "id": str(Break.objects.order_by("started_at")[1].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_ENDED,
            {
                "id": str(Break.objects.order_by("started_at")[1].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (events.CLOCKED_OUT, {"id": day_id, "member_id": str(ana.id)}),
    ]


def test_the_guards_answer_their_codes(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    refused("attendance.no_break_running", "attendance.break.end", {}, ctx)
    refused("attendance.not_clocked_in", "attendance.break.start", {}, ctx)
    refused("attendance.not_clocked_in", "attendance.record.clock_out", {}, ctx)
    run("attendance.record.clock_in", {}, ctx)
    refused("attendance.no_break_running", "attendance.break.end", {}, ctx)
    clock("2026-10-06T08:00")
    run("attendance.break.start", {}, ctx)
    refused("attendance.break_running", "attendance.break.start", {}, ctx)


def test_a_day_waiting_for_review_cannot_be_clocked_out(person, clock):
    clock("2026-10-06T07:00")
    ana, ctx = person()
    Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-04T07:00"),
        work_date=dt.date(2026, 10, 4),
        status="needs_review",
    )
    refused("attendance.not_clocked_in", "attendance.record.clock_out", {}, ctx)


# Clocking someone else (ATTENDANCE-F12)


def test_a_manager_clocks_ana_in_and_out_by_name(person, clock, make_user):
    clock("2026-10-06T07:00")
    ana, _ = person()
    boss = make_user("boss", role="hub_manager")
    manager = ctx_for("hub_manager", actor=boss)
    run("attendance.record.clock_in", {"member": "ana"}, manager)
    day = Record.objects.get()
    assert (day.member, day.created_by) == (ana, boss)
    clock("2026-10-06T15:00")
    run("attendance.break.start", {"member_id": str(ana.id)}, manager)
    run("attendance.record.clock_out", {"member": "Ana López"}, manager)
    day.refresh_from_db()
    assert (day.status, day.updated_by) == ("closed", boss)


def test_an_employee_cannot_clock_someone_else(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    person("Bea", "Ruiz")
    with pytest.raises(PermissionDenied):
        run("attendance.record.clock_in", {"member": "Bea"}, ctx)
    # Naming themselves is fine.
    run("attendance.record.clock_in", {"member": "Ana"}, ctx)
    assert Record.objects.get().member.first_name == "Ana"


def test_naming_someone_who_is_not_there(person, clock):
    clock("2026-10-06T07:00")
    person()
    person("Ana", "Ruiz")
    make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    with pytest.raises(Conflict) as caught:
        run("attendance.record.clock_in", {"member": "Ana"}, ctx_for())
    assert (
        caught.value.code == "attendance.ambiguous_member"
        and "Ana López" in caught.value.message
    )
    for name in ("Nadie", "Carlos"):
        with pytest.raises(NotFound):
            run("attendance.record.clock_in", {"member": name}, ctx_for())


# attendance.record.correct (ATTENDANCE-F08, F09)


def closed_day(member, start, end) -> Record:
    return Record.objects.create(
        member=member,
        clock_in_at=utc(start),
        clock_out_at=utc(end),
        status="closed",
        work_date=timezone.localdate(utc(start)),
    )


def correct(record, start, end, reason="Forgot to clock out", ctx=None):
    data = {
        "record_id": str(record.id),
        "clock_in_at": f"{start}:00Z",
        "clock_out_at": f"{end}:00Z" if end else None,
        "reason": reason,
    }
    return run("attendance.record.correct", data, ctx)


def test_a_correction_rewrites_the_day_and_leaves_its_trail(person, clock, make_user):
    clock("2026-10-07T09:00")
    ana, _ = person()
    boss = make_user("boss", role="hub_manager")
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T07:05")
    result = correct(
        day,
        "2026-10-05T06:00",
        "2026-10-05T14:30",
        ctx=ctx_for("hub_manager", actor=boss),
    )
    day.refresh_from_db()
    assert (day.clock_in_at, day.clock_out_at, day.status, day.updated_by) == (
        utc("2026-10-05T06:00"),
        utc("2026-10-05T14:30"),
        "closed",
        boss,
    )
    # The business day follows the new clock-in.
    assert day.work_date == dt.date(2026, 10, 5) and result.work_date == day.work_date
    trail = Correction.objects.get()
    assert (trail.old_clock_in_at, trail.old_clock_out_at, trail.old_status) == (
        utc("2026-10-06T07:00"),
        utc("2026-10-06T07:05"),
        "closed",
    )
    assert (trail.new_clock_in_at, trail.new_clock_out_at, trail.new_status) == (
        utc("2026-10-05T06:00"),
        utc("2026-10-05T14:30"),
        "closed",
    )
    assert (trail.reason, trail.created_by) == ("Forgot to clock out", boss)
    # Who corrected is copied: a deleted user never turns into «System».
    assert (trail.is_system, trail.created_by_name) == (False, "boss")
    assert outbox() == [
        (
            events.RECORD_CORRECTED,
            {
                "id": str(day.id),
                "member_id": str(ana.id),
                "correction_id": str(trail.id),
            },
        )
    ]


def test_correcting_a_day_that_does_not_exist(clock):
    clock("2026-10-07T09:00")
    ghost = Record(id=None)
    with pytest.raises(NotFound):
        run(
            "attendance.record.correct",
            {
                "record_id": "0199c8a0-0000-7000-8000-000000000000",
                "clock_in_at": "2026-10-06T07:00:00Z",
                "reason": "Ghost",
            },
        )
    assert ghost.pk is None and Correction.objects.count() == 0


def test_an_employee_cannot_correct(person, clock):
    clock("2026-10-07T09:00")
    ana, ctx = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    with pytest.raises(PermissionDenied):
        correct(day, "2026-10-06T06:00", "2026-10-06T15:00", ctx=ctx)


def test_a_correction_cannot_be_in_the_future(person, clock):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    for start, end, field in (
        ("2026-10-07T09:30", None, "clock_in_at"),
        ("2026-10-07T07:00", "2026-10-07T10:00", "clock_out_at"),
    ):
        with pytest.raises(InvalidPayload) as caught:
            correct(day, start, end)
        assert list(caught.value.fields) == [field]
    assert Correction.objects.count() == 0


def test_without_a_clock_out_the_day_is_open_again(person, clock):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = closed_day(ana, "2026-10-07T07:00", "2026-10-07T07:01")
    correct(day, "2026-10-07T07:00", None)
    day.refresh_from_db()
    assert (day.status, day.clock_out_at) == ("open", None)


def test_reopening_a_day_while_another_is_open_is_refused(person, clock):
    clock("2026-10-07T09:00")
    ana, ctx = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    run("attendance.record.clock_in", {}, ctx)
    OutboxEvent.objects.all().delete()
    with pytest.raises(Conflict) as caught:
        correct(day, "2026-10-06T07:00", None)
    assert caught.value.code == "attendance.second_open_day"
    assert Correction.objects.count() == 0 and outbox() == []


def test_a_day_waiting_for_review_is_closed_with_a_correction_and_its_break_too(
    person, clock
):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=dt.date(2026, 10, 6),
        status="needs_review",
    )
    running = Break.objects.create(record=day, started_at=utc("2026-10-06T13:00"))
    correct(day, "2026-10-06T07:00", "2026-10-06T15:00")
    day.refresh_from_db()
    running.refresh_from_db()
    assert (day.status, running.ended_at) == ("closed", utc("2026-10-06T15:00"))
    # A break left running that began after the new clock-out ends at its own start.
    late = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-05T07:00"),
        work_date=dt.date(2026, 10, 5),
        status="needs_review",
    )
    after = Break.objects.create(record=late, started_at=utc("2026-10-05T16:00"))
    correct(late, "2026-10-05T07:00", "2026-10-05T15:00")
    after.refresh_from_db()
    assert after.ended_at == utc("2026-10-05T16:00")


class TestOverlap:
    """attendance#12: a correction never puts two days of the same person over each other."""

    @pytest.fixture
    def days(self, person, clock):
        clock("2026-10-06T13:00")
        ines, _ = person("Ines", "Mar")
        joan, _ = person("Joan", "Sol")
        first = closed_day(ines, "2026-10-06T08:00", "2026-10-06T09:00")
        second = closed_day(ines, "2026-10-06T10:00", "2026-10-06T11:00")
        closed_day(joan, "2026-10-06T08:30", "2026-10-06T09:30")
        return ines, first, second

    def refused_overlap(self, record, start, end):
        record.refresh_from_db()
        before = (record.clock_in_at, record.clock_out_at)
        trail = Correction.objects.filter(record=record).count()
        with pytest.raises(Conflict) as caught:
            correct(record, start, end)
        assert caught.value.code == "attendance.overlap"
        record.refresh_from_db()
        assert (record.clock_in_at, record.clock_out_at) == before
        assert Correction.objects.filter(record=record).count() == trail

    def test_moving_a_day_over_another_of_the_same_person(self, days):
        _, _, second = days
        self.refused_overlap(second, "2026-10-06T08:30", "2026-10-06T10:30")
        self.refused_overlap(second, "2026-10-06T07:00", "2026-10-06T12:00")

    def test_touching_is_not_overlapping_and_another_persons_day_never_blocks(
        self, days
    ):
        _, _, second = days
        correct(second, "2026-10-06T09:00", "2026-10-06T11:00")
        assert Correction.objects.filter(record=second).count() == 1

    def test_an_open_day_runs_until_now(self, days, clock):
        ines, _, second = days
        Record.objects.create(
            member=ines,
            clock_in_at=utc("2026-10-06T12:00"),
            work_date=dt.date(2026, 10, 6),
        )
        self.refused_overlap(second, "2026-10-06T11:30", "2026-10-06T12:30")
        correct(second, "2026-10-06T11:00", "2026-10-06T11:59")

    def test_reopening_runs_until_now_over_a_later_day(self, days):
        _, first, _ = days
        Record.objects.filter(member=first.member, status="open").delete()
        self.refused_overlap(first, "2026-10-06T08:00", None)

    def test_a_forgotten_day_is_only_its_clock_in(self, days, person):
        kai, _ = person("Kai", "Lin")
        Record.objects.create(
            member=kai,
            clock_in_at=utc("2026-10-06T08:00"),
            work_date=dt.date(2026, 10, 6),
            status="needs_review",
        )
        later = closed_day(kai, "2026-10-06T10:00", "2026-10-06T11:00")
        correct(later, "2026-10-06T09:00", "2026-10-06T11:00")
        self.refused_overlap(later, "2026-10-06T07:00", "2026-10-06T11:00")


# attendance.settings.update (ATTENDANCE-F04)


def test_the_first_save_creates_the_settings_and_only_what_is_sent_changes(clock):
    clock("2026-10-06T07:00")
    saved = run("attendance.settings.update", {"auto_close_after_hours": 10})
    assert isinstance(saved, SettingsOut)
    assert (
        saved.auto_close_after_hours,
        saved.geofence_radius_m,
        saved.require_location,
        saved.saved,
    ) == (10, 100, False, True)
    run(
        "attendance.settings.update",
        {
            "require_location": True,
            "workplace_lat": WORKPLACE[0],
            "workplace_lng": WORKPLACE[1],
            "geofence_radius_m": 250,
        },
    )
    row = AttendanceSettings.objects.get()
    assert (
        row.auto_close_after_hours,
        row.require_location,
        row.geofence_radius_m,
        row.workplace_lat,
    ) == (10, True, 250, WORKPLACE[0])
    assert names() == [events.SETTINGS_UPDATED, events.SETTINGS_UPDATED]


def test_saving_nothing_new_says_nothing(clock):
    clock("2026-10-06T07:00")
    run("attendance.settings.update", {"auto_close_after_hours": 10})
    run("attendance.settings.update", {"auto_close_after_hours": 10})
    assert names() == [events.SETTINGS_UPDATED]


def test_the_workplace_is_both_coordinates_or_neither(clock):
    clock("2026-10-06T07:00")
    run(
        "attendance.settings.update",
        {"workplace_lat": WORKPLACE[0], "workplace_lng": WORKPLACE[1]},
    )
    with pytest.raises(InvalidPayload) as caught:
        run("attendance.settings.update", {"workplace_lng": None})
    assert list(caught.value.fields) == ["workplace_lng"]
    cleared = run(
        "attendance.settings.update", {"workplace_lat": None, "workplace_lng": None}
    )
    assert (cleared.workplace_lat, cleared.workplace_set) == (None, False)


def test_an_employee_cannot_save_the_settings(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.settings.update", {"auto_close_after_hours": 3}, ctx)
    assert not AttendanceSettings.objects.exists()


# attendance.record.review_stale (ATTENDANCE-F05), as the scheduled task: the system


def test_the_review_flags_only_the_open_days_past_the_threshold(person, clock):
    from live.context import system_context

    clock("2026-10-06T20:00")
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carl, _ = person("Carl", "Paz")
    old = Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    Record.objects.create(
        member=bea, clock_in_at=utc("2026-10-06T09:00"), work_date=dt.date(2026, 10, 6)
    )
    closed_day(carl, "2026-10-05T07:00", "2026-10-05T15:00")

    result = run("attendance.record.review_stale", {}, system_context(A))

    assert isinstance(result, ReviewOut)
    assert (result.flagged, result.record_ids) == (1, [old.id])
    assert sorted(Record.objects.values_list("status", flat=True)) == [
        "closed",
        "needs_review",
        "open",
    ]
    assert outbox() == [
        (events.RECORD_FLAGGED, {"id": str(old.id), "member_id": str(ana.id)})
    ]
    # Nothing new to flag: nothing said.
    assert run("attendance.record.review_stale", {}, system_context(A)).flagged == 0
    assert len(outbox()) == 1


def test_the_review_uses_the_businesss_hours(person, clock):
    from live.context import system_context

    AttendanceSettings.objects.create(auto_close_after_hours=1)
    clock("2026-10-06T08:30")
    ana, _ = person()
    Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    assert run("attendance.record.review_stale", {}, system_context(A)).flagged == 1


# attendance.record.close_for_terminated (ATTENDANCE-F13)


def test_a_termination_closes_the_day_and_its_break(person, clock):
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    day = Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    pause = Break.objects.create(record=day, started_at=utc("2026-10-06T11:00"))
    Member.objects.filter(pk=ana.pk).update(status=Member.Status.TERMINATED)

    result = run(
        "attendance.record.close_for_terminated", {"id": str(ana.id)}, system_context(A)
    )

    assert isinstance(result, ClosedOut) and result.record.status == "closed"
    pause.refresh_from_db()
    assert pause.ended_at == utc("2026-10-06T12:00")
    trail = Correction.objects.get()
    assert (trail.is_system, trail.created_by_name) == (True, "")
    assert (trail.created_by, trail.reason, trail.old_status, trail.new_status) == (
        None,
        "Day closed when the person was terminated in Staff.",
        "open",
        "closed",
    )
    assert names() == [events.BREAK_ENDED, events.RECORD_CORRECTED]


def test_a_termination_without_an_open_day_changes_nothing(person, clock):
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    closed_day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    assert (
        run(
            "attendance.record.close_for_terminated",
            {"id": str(ana.id)},
            system_context(A),
        ).record
        is None
    )
    assert outbox() == [] and Correction.objects.count() == 0


# Live notifications: a write in one scope reaches that scope's channel only


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


def received(session, timeout=1.0, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_clocking_in_in_b_notifies_b_only(listen, person):
    on_a, on_b = listen(A), listen(B)
    _, ctx_b = person(scope=B)
    run("attendance.record.clock_in", {}, ctx_b)
    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.CLOCKED_IN]})
    ]
    assert received(on_a, timeout=0.3) == []
    # Positive control: the same listener of A hears a command run in A.
    _, ctx_a = person("Bea", "Ruiz", scope=A)
    run("attendance.record.clock_in", {}, ctx_a)
    assert received(on_a, stop_after=1) == [
        (channel_for(A), {"events": [events.CLOCKED_IN]})
    ]


@pytest.mark.django_db(transaction=True)
def test_a_refused_command_notifies_nobody(listen, person):
    on_a = listen(A)
    _, ctx = person()
    with pytest.raises(Conflict):
        run("attendance.record.clock_out", {}, ctx)
    assert received(on_a, timeout=0.3) == []


# A forgotten day is not closed as a 24-hour day: it waits for a manager's correction (review of
# 2026-10-15, finding 1). The commands judge it themselves, without waiting for the worker's review.


@pytest.mark.parametrize("name", ["attendance.record.clock_out", "attendance.break.start", "attendance.break.end"])
def test_a_forgotten_day_is_not_clocked_out_nor_paused_the_next_morning(person, clock, name):
    clock("2026-10-05T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T07:00")
    error = refused("attendance.day_needs_review", name, {}, ctx)
    assert "waiting for review" in error.message
    assert Record.objects.get().clock_out_at is None


def test_within_the_hours_a_long_day_still_clocks_out(person, clock):
    clock("2026-10-05T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-05T18:59")
    assert run("attendance.record.clock_out", {}, ctx).status == "closed"


def test_the_open_day_of_a_terminated_record_is_closed_by_a_correction(person, clock):
    # The person no longer clocks (their record is terminated): a manager closes the day.
    clock("2026-10-06T18:00")
    ana, _ = person()
    open_day = Record.objects.create(member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6))
    Member.objects.filter(pk=ana.pk).update(status=Member.Status.TERMINATED)
    corrected = correct(open_day, "2026-10-06T07:00", "2026-10-06T15:00", reason="Closed after leaving")
    assert corrected.status == "closed"


def test_the_reaction_closes_nothing_for_a_record_that_is_not_terminated(person, clock):
    # Review of 2026-10-15, finding 5: only a termination closes a day; a stray call changes nothing.
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    Record.objects.create(member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6))
    assert run("attendance.record.close_for_terminated", {"id": str(ana.id)}, system_context(A)).record is None
    assert Record.objects.get().status == "open"
    assert outbox() == [] and Correction.objects.count() == 0
