"""What every write on a person locks first: their record, still theirs once it is locked."""

import pytest
from live.errors import NotFound
from live.operations import atomic, get

from apps.staff.models import Schedule
from apps.staff.schemas.members import TerminateIn
from apps.staff.schemas.schedules import ScheduleRefIn, ScheduleUpdateIn, SetActiveIn
from apps.staff.schemas.time_off import TimeOffRefIn
from apps.staff.services.locks import _locked_live_member, lock_members

from .conftest import HUB_DB_COMMITTED, WEEK, _race, ctx_for, make_member, make_schedule, make_time_off


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_a_record_terminated_while_approving_is_not_found():
    member = make_member()
    leave = make_time_off(member, "2026-10-12")

    outcome = _race(
        lambda: get("staff.member.terminate")(ctx_for(), TerminateIn(id=member.id)),
        lambda: get("staff.time_off.approve")(ctx_for(), TimeOffRefIn(id=leave.id)),
    )

    assert isinstance(outcome.get("error"), NotFound), outcome
    leave.refresh_from_db()
    assert leave.status == "pending"
    with atomic():
        assert _locked_live_member(member.id) is None and lock_members([member.id]) == [member.id]


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
@pytest.mark.parametrize(
    "command",
    [
        lambda schedule: get("staff.schedule.update")(ctx_for(), ScheduleUpdateIn(id=schedule.id, days=WEEK)),
        lambda schedule: get("staff.schedule.set_active")(ctx_for(), SetActiveIn(id=schedule.id, is_active=False)),
        lambda schedule: get("staff.schedule.delete")(ctx_for(), ScheduleRefIn(id=schedule.id)),
    ],
)
def test_a_schedule_of_a_record_terminated_meanwhile_is_not_found(command):
    member = make_member()
    schedule = make_schedule(member)

    outcome = _race(
        lambda: get("staff.member.terminate")(ctx_for(), TerminateIn(id=member.id)),
        lambda: command(schedule),
    )

    assert isinstance(outcome.get("error"), NotFound), outcome
    assert Schedule.objects.get().is_active is True
