"""The time off of the staff: the list, who is away today, a person's own and who reads the reason (STAFF-F08, F17–F20)."""

import datetime as dt

import pytest
from django.utils import translation
from live.errors import PermissionDenied

from apps.staff.models import TimeOff
from apps.staff.queries.time_off import list_time_off
from apps.staff.schemas.fields import ByIdIn
from apps.staff.schemas.members import MemberStatsIn
from apps.staff.schemas.time_off import MyTimeOffIn, TimeOffListIn, TodayIn

from .conftest import HUB_DB, LATE_EVENING_UTC, TERMINATED, ctx_for, make_member, make_time_off, run, t, today

pytestmark = HUB_DB


# staff.time_off.list (STAFF-F17–F19)


def time_off(role="hub_admin", **params):
    return list_time_off(ctx_for(role), TimeOffListIn(**params))


def test_time_off_most_recent_first_without_the_reason():
    ana = make_member("Ana", "López")
    old = make_time_off(ana, "2026-01-05", "2026-01-09", reason="trip")
    new = make_time_off(
        ana,
        "2026-10-12",
        hours=("09:00", "13:00"),
        leave_type="sick",
        status=TimeOff.Status.APPROVED,
    )
    make_time_off(make_member("Carla", status=TERMINATED), "2026-10-20")

    page = time_off(role="hub_employee")

    assert [row.id for row in page.rows] == [new.id, old.id]
    assert page.rows[0].model_dump() == {
        "id": new.id,
        "member_id": ana.id,
        "member_name": "Ana López",
        "leave_type": "sick",
        "leave_type_label": "Sick leave",
        "start_date": dt.date(2026, 10, 12),
        "end_date": dt.date(2026, 10, 12),
        "is_full_day": False,
        "start_time": t("09:00"),
        "end_time": t("13:00"),
        "status": "approved",
        "approved_by_id": None,
        "approved_at": None,
    }


def test_time_off_filters():
    ana, bea = make_member("Ana"), make_member("Bea", "Ruiz")
    october = make_time_off(ana, "2026-10-01", "2026-10-10", leave_type="training")
    make_time_off(ana, "2026-12-01", status=TimeOff.Status.APPROVED)
    ruiz = make_time_off(bea, "2026-10-05", status=TimeOff.Status.REJECTED)

    def ids(**params):
        return {row.id for row in time_off(**params).rows}

    assert ids(member_id=bea.id) == {ruiz.id}
    assert ids(status="rejected") == {ruiz.id}
    assert ids(leave_type="training") == {october.id}
    assert ids(date_from=dt.date(2026, 10, 10), date_to=dt.date(2026, 10, 31)) == {
        october.id
    }
    assert ids(date_to=dt.date(2026, 10, 4)) == {october.id}
    assert ids(search="RUIZ") == {ruiz.id}


def test_time_off_filters_of_the_old_table(make_user):
    boss = make_user("boss")
    ana = make_member("Ana")
    approved = make_time_off(ana, "2026-10-01", "2026-10-03", status=TimeOff.Status.APPROVED, approved_by=boss.person)
    hours = make_time_off(ana, "2026-10-20", hours=("09:00", "10:00"))
    make_time_off(ana, "2026-11-10", "2026-11-12")

    def ids(**params):
        return [row.id for row in time_off(**params).rows]

    assert ids(approved_by_id=boss.person.id) == [approved.id]
    assert time_off(approved_by_id=boss.person.id).rows[0].approved_by_id == boss.person.id
    assert ids(is_full_day=False) == [hours.id]
    assert ids(start_date_from=dt.date(2026, 10, 2), start_date_to=dt.date(2026, 10, 31)) == [hours.id]
    assert ids(end_date_from=dt.date(2026, 10, 3), end_date_to=dt.date(2026, 10, 20)) == [hours.id, approved.id]


def test_time_off_sorts_both_ways():
    ana, bea = make_member("Ana"), make_member("Bea")
    first = make_time_off(bea, "2026-10-01")
    second = make_time_off(ana, "2026-10-05", status=TimeOff.Status.APPROVED)

    def order(sort):
        return [row.id for row in time_off(sort=sort).rows]

    assert order("start_date") == [first.id, second.id]
    assert order("-start_date") == [second.id, first.id]
    assert order("member_name") == [second.id, first.id]
    assert order("status") == [second.id, first.id]


# staff.time_off.detail


def test_an_employee_does_not_read_the_reason():
    leave = make_time_off(make_member(), "2026-10-12", reason="Surgery")
    with pytest.raises(PermissionDenied):
        run("staff.time_off.detail", ByIdIn(id=leave.id), "hub_employee")


# staff.time_off.today (STAFF-F20)


def test_who_is_away_today_full_days_first_then_by_name():
    day = today().isoformat()
    ana, bea, carla = make_member("Ana"), make_member("Bea"), make_member("Carla")
    morning = make_time_off(
        ana, day, hours=("09:00", "11:00"), status=TimeOff.Status.APPROVED
    )
    week = make_time_off(
        carla,
        (today() - dt.timedelta(days=2)).isoformat(),
        (today() + dt.timedelta(days=2)).isoformat(),
        status=TimeOff.Status.APPROVED,
    )
    whole = make_time_off(bea, day, status=TimeOff.Status.APPROVED)
    make_time_off(
        ana,
        (today() + dt.timedelta(days=1)).isoformat(),
        status=TimeOff.Status.APPROVED,
    )
    make_time_off(bea, day, hours=("18:00", "19:00"))  # pending
    make_time_off(
        make_member("Dora", status=TERMINATED), day, status=TimeOff.Status.APPROVED
    )

    page = run("staff.time_off.today", TodayIn(), "hub_employee")

    assert [row.id for row in page.rows] == [whole.id, week.id, morning.id]


def test_who_is_away_today_says_each_type_in_the_callers_language():
    """The Home's «Today’s time off» paints the type under each name as the query gives it (STAFF-F20)."""
    day = today().isoformat()
    for first_name, leave_type in (("Ana", "vacation"), ("Bea", "sick"), ("Carla", "personal"), ("Dora", "training"), ("Eva", "other")):
        make_time_off(make_member(first_name), day, leave_type=leave_type, status=TimeOff.Status.APPROVED)
    with translation.override("en"):
        english = [row.leave_type_label for row in run("staff.time_off.today", TodayIn()).rows]
    with translation.override("es"):
        spanish = [row.leave_type_label for row in run("staff.time_off.today", TodayIn()).rows]
    assert english == ["Vacation", "Sick leave", "Personal", "Training", "Other"]
    assert spanish == ["Vacaciones", "Baja por enfermedad", "Asuntos propios", "Formación", "Otros"]


def test_today_is_the_business_day(frozen_now):
    frozen_now(LATE_EVENING_UTC)
    starts = make_time_off(
        make_member("Ana"), "2026-08-19", status=TimeOff.Status.APPROVED
    )
    make_time_off(make_member("Bea"), "2026-08-18", status=TimeOff.Status.APPROVED)
    assert [row.id for row in run("staff.time_off.today", TodayIn()).rows] == [
        starts.id
    ]


def test_who_is_away_today_goes_by_the_businesss_midnight(night_elsewhere):
    away = make_time_off(make_member("Ana"), "2026-11-02", status=TimeOff.Status.APPROVED)
    make_time_off(make_member("Bea"), "2026-11-03", status=TimeOff.Status.APPROVED)
    assert [row.id for row in run("staff.time_off.today", TodayIn()).rows] == [away.id]
    assert run("staff.member.stats", MemberStatsIn()).absent_today == 1


# staff.time_off.mine (STAFF-F08)


def test_my_time_off_with_its_reason(make_user):
    me = make_user("ana")
    ana = make_member("Ana", user=me.person)
    mine = [
        make_time_off(ana, "2026-10-12", reason="Wedding"),
        make_time_off(ana, "2026-11-02", status=TimeOff.Status.REJECTED),
    ]
    make_time_off(make_member("Bea"), "2026-10-12", reason="Not yours")

    page = run("staff.time_off.mine", MyTimeOffIn(), "hub_employee", actor=me)

    assert [row.id for row in page.rows] == [mine[1].id, mine[0].id]
    assert page.rows[1].reason == "Wedding"


def test_my_time_off_is_empty_without_a_record(make_user):
    make_time_off(make_member("Bea"), "2026-10-12")
    for actor in (make_user("nobody"), "system"):
        assert (
            run("staff.time_off.mine", MyTimeOffIn(), "hub_employee", actor=actor).total
            == 0
        )
