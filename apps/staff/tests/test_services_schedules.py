"""The writes on a person's weekly schedules. A refused command leaves no trace: no row, no event."""

import datetime as dt
import uuid

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

from apps.staff import events
from apps.staff.models import Member, Schedule, ScheduleDay, StaffSettings
from apps.staff.schemas.fields import DeletedOut
from apps.staff.schemas.schedules import ScheduleIn, ScheduleRefIn, ScheduleUpdateIn, SetActiveIn
from apps.staff.services.schedules import delete_schedule

from .conftest import HUB_DB, WEEK, A, ctx_for, make_member, make_schedule, names, outbox, run, t

pytestmark = HUB_DB


# staff.schedule.* (STAFF-F13–F15)


def create_schedule(who, **fields):
    data = {"member_id": who.id, "name": "Usual", "days": WEEK, **fields}
    return run("staff.schedule.create", ScheduleIn(**data))


def test_create_a_schedule_with_its_week():
    member = make_member()
    schedule = create_schedule(
        member,
        days=[
            *WEEK,
            {"weekday": 5, "start_time": "10:00", "end_time": "14:00"},
            {"weekday": 6, "is_working": False},
        ],
    )
    assert (schedule.member_id, schedule.name, schedule.is_default) == (
        member.id,
        "Usual",
        True,
    )
    assert [
        (day.weekday, day.start_time, day.break_start) for day in schedule.days
    ] == [(0, t("09:00"), t("13:00")), (5, t("10:00"), None)]
    assert outbox() == [
        (
            events.SCHEDULE_CREATED,
            A.key,
            {"id": str(schedule.id), "member_id": str(member.id)},
        )
    ]


def test_a_schedule_without_a_name_is_the_regular_schedule_in_the_callers_language():
    member = make_member()
    assert create_schedule(member, name="").name == "Regular schedule"


def test_a_new_default_schedule_demotes_the_others():
    member = make_member()
    old = make_schedule(member, name="Old")
    other = make_schedule(make_member("Bea"))
    new = create_schedule(member, member=None, name="New")
    old.refresh_from_db()
    other.refresh_from_db()
    assert (new.is_default, old.is_default, other.is_default) == (True, False, True)


def test_a_schedule_for_a_missing_or_terminated_member_is_refused():
    gone = make_member(status=Member.Status.TERMINATED)
    with pytest.raises(NotFound):
        create_schedule(gone)
    with pytest.raises(NotFound):
        run("staff.schedule.create", ScheduleIn(member="Nobody", days=WEEK))
    assert not Schedule.objects.exists() and outbox() == []


def test_update_replaces_the_week_and_keeps_what_was_not_sent():
    member = make_member()
    schedule = make_schedule(
        member,
        {0: ("09:00", "18:00"), 1: ("09:00", "18:00")},
        name="Usual",
        effective_from=dt.date(2026, 1, 1),
    )

    updated = run(
        "staff.schedule.update",
        ScheduleUpdateIn(
            id=schedule.id,
            days=[{"weekday": 2, "start_time": "10:00", "end_time": "12:00"}],
        ),
    )

    assert (updated.name, updated.is_default, updated.effective_from) == (
        "Usual",
        True,
        dt.date(2026, 1, 1),
    )
    assert [(day.weekday, day.start_time) for day in updated.days] == [(2, t("10:00"))]
    assert ScheduleDay.objects.count() == 1
    assert outbox() == [
        (
            events.SCHEDULE_UPDATED,
            A.key,
            {"id": str(schedule.id), "member_id": str(member.id)},
        )
    ]


def test_update_clears_a_date_with_null_and_checks_the_merged_range():
    member = make_member()
    schedule = make_schedule(
        member,
        effective_from=dt.date(2026, 6, 1),
        effective_until=dt.date(2026, 6, 30),
        is_default=False,
    )
    cleared = run(
        "staff.schedule.update",
        ScheduleUpdateIn(id=schedule.id, effective_until=None, days=WEEK),
    )
    assert (cleared.effective_from, cleared.effective_until) == (
        dt.date(2026, 6, 1),
        None,
    )
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "staff.schedule.update",
            ScheduleUpdateIn(
                id=schedule.id, effective_until=dt.date(2026, 5, 1), days=WEEK
            ),
        )
    assert excinfo.value.fields == {
        "effective_until": "The schedule's validity ends before it starts."
    }


def test_update_to_default_demotes_the_others():
    member = make_member()
    usual = make_schedule(member, name="Usual")
    summer = make_schedule(member, name="Summer", is_default=False)
    run(
        "staff.schedule.update",
        ScheduleUpdateIn(id=summer.id, is_default=True, days=WEEK),
    )
    usual.refresh_from_db()
    assert usual.is_default is False


def test_update_of_a_missing_schedule_is_not_found():
    with pytest.raises(NotFound):
        run("staff.schedule.update", ScheduleUpdateIn(id=uuid.uuid7(), days=WEEK))


def test_set_active_and_delete():
    member = make_member()
    schedule = make_schedule(member)
    assert (
        run(
            "staff.schedule.set_active", SetActiveIn(id=schedule.id, is_active=False)
        ).is_active
        is False
    )
    run(
        "staff.schedule.set_active", SetActiveIn(id=schedule.id, is_active=False)
    )  # no change, no event
    assert run("staff.schedule.delete", ScheduleRefIn(id=schedule.id)) == DeletedOut(
        id=schedule.id
    )
    assert not Schedule.objects.exists() and not ScheduleDay.objects.exists()
    assert names() == [events.SCHEDULE_UPDATED, events.SCHEDULE_DELETED]
    with pytest.raises(NotFound):
        run("staff.schedule.delete", ScheduleRefIn(id=schedule.id))


def test_an_employee_does_not_manage_schedules():
    with pytest.raises(PermissionDenied):
        run(
            "staff.schedule.create",
            ScheduleIn(member_id=make_member().id, days=WEEK),
            "hub_employee",
        )
    with pytest.raises(PermissionDenied):
        delete_schedule(ctx_for("hub_employee"), ScheduleRefIn(id=make_schedule(make_member()).id))


# A working day sent without its hours (the assistant, when the person does not say them) takes the business's default
# working day of Staff › Settings, as the window proposes a new schedule: never hours of its own (hub#2716).


def salon_working_day():
    StaffSettings.objects.create(default_work_start=t("10:00"), default_work_end=t("19:00"), default_break_duration=60)


def its_days(schedule) -> list[tuple]:
    return [(day.weekday, day.start_time, day.end_time, day.break_start, day.break_end) for day in schedule.days]


def test_a_week_without_its_hours_is_the_business_default_working_day():
    salon_working_day()
    schedule = create_schedule(make_member("Bea"), days=[{"weekday": day} for day in range(1, 6)])
    assert its_days(schedule) == [(day, t("10:00"), t("19:00"), t("14:00"), t("15:00")) for day in range(1, 6)]


def test_without_saved_settings_it_is_the_settings_own_working_day():
    schedule = create_schedule(make_member("Bea"), days=[{"weekday": 1}])
    assert its_days(schedule) == [(1, t("09:00"), t("18:00"), t("13:00"), t("14:00"))]


def test_an_hour_the_working_day_makes_wrong_is_refused_under_its_day_and_nothing_is_written():
    salon_working_day()
    with pytest.raises(InvalidPayload) as refused:
        create_schedule(make_member("Bea"), days=[{"weekday": 1}, {"weekday": 2, "start_time": "20:00"}])
    assert refused.value.fields == {"days.1.end_time": "The start time must be before the end time."}
    assert not Schedule.objects.exists() and outbox() == []


def test_an_edited_week_without_its_hours_is_the_business_default_working_day():
    salon_working_day()
    schedule = make_schedule(make_member("Bea"))
    updated = run("staff.schedule.update", ScheduleUpdateIn(id=schedule.id, days=[{"weekday": 5}]))
    assert its_days(updated) == [(5, t("10:00"), t("19:00"), t("14:00"), t("15:00"))]
