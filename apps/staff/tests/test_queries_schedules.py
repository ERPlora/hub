"""The schedules of a staff member, each with its week (STAFF-F13–F15)."""

import datetime as dt
import uuid

import pytest
from live.errors import NotFound

from apps.staff.queries.schedules import schedule_detail
from apps.staff.schemas.fields import ByIdIn
from apps.staff.schemas.schedules import ScheduleListIn

from .conftest import HUB_DB, TERMINATED, ctx_for, make_member, make_schedule, run, t

pytestmark = HUB_DB


def test_the_schedules_of_a_member_default_first_with_their_week():
    ana = make_member("Ana")
    summer = make_schedule(
        ana,
        {4: ("10:00", "14:00"), 0: ("09:00", "18:00", "13:00", "14:00")},
        name="Summer",
        is_default=False,
        effective_from=dt.date(2026, 7, 1),
        effective_until=dt.date(2026, 8, 31),
    )
    usual = make_schedule(ana, name="Usual")
    make_schedule(make_member("Bea"))

    page = run("staff.schedule.list", ScheduleListIn(member_id=ana.id), "hub_employee")

    assert [row.id for row in page.rows] == [usual.id, summer.id]
    assert page.total == 2
    assert page.rows[1].model_dump() == {
        "id": summer.id,
        "member_id": ana.id,
        "name": "Summer",
        "is_default": False,
        "effective_from": dt.date(2026, 7, 1),
        "effective_until": dt.date(2026, 8, 31),
        "is_active": True,
        "days": [
            {
                "weekday": 0,
                "start_time": t("09:00"),
                "end_time": t("18:00"),
                "break_start": t("13:00"),
                "break_end": t("14:00"),
            },
            {
                "weekday": 4,
                "start_time": t("10:00"),
                "end_time": t("14:00"),
                "break_start": None,
                "break_end": None,
            },
        ],
    }


def test_a_terminated_members_schedules_are_gone():
    gone = make_member(status=TERMINATED)
    schedule = make_schedule(gone)
    with pytest.raises(NotFound):
        run("staff.schedule.list", ScheduleListIn(member_id=gone.id))
    with pytest.raises(NotFound):
        run("staff.schedule.detail", ByIdIn(id=schedule.id))


def test_schedule_detail():
    schedule = make_schedule(make_member(), {2: ("08:00", "12:00")})
    detail = schedule_detail(ctx_for("hub_employee"), ByIdIn(id=schedule.id))
    assert (detail.id, [day.weekday for day in detail.days]) == (schedule.id, [2])
    with pytest.raises(NotFound):
        run("staff.schedule.detail", ByIdIn(id=uuid.uuid7()))


def test_the_schedules_of_a_member_named_by_name():
    ana = make_member("Ana", "López")
    usual = make_schedule(ana)
    assert [row.id for row in run("staff.schedule.list", ScheduleListIn(member="ana lópez")).rows] == [usual.id]
    with pytest.raises(NotFound):
        run("staff.schedule.list", ScheduleListIn(member="Nobody"))
