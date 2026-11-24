"""The directory, a record, a person's own, the pay sheet and the statistics of the staff (STAFF-F08, F09, F21, F23)."""

import datetime as dt
from decimal import Decimal

import pytest
from live.errors import PermissionDenied

from apps.staff.models import Member, TimeOff
from apps.staff.queries.members import list_members
from apps.staff.schemas.fields import MemberRefIn
from apps.staff.schemas.members import CompensationListIn, CurrentMemberIn, MemberListIn, MemberStatsIn, MineIn

from .conftest import HUB_DB, LATE_EVENING_UTC, TERMINATED, ctx_for, make_member, make_role, make_time_off, run, t, today

pytestmark = HUB_DB


# staff.member.list (STAFF-F09)


def members(role="hub_admin", **params):
    return list_members(ctx_for(role), MemberListIn(**params))


def test_empty_directory():
    assert members().model_dump() == {"rows": [], "total": 0, "limit": 50, "offset": 0}


def test_the_directory_by_name_without_terminated_records(make_user):
    stylist = make_role("Stylist")
    account = make_user("bea")
    bea = make_member(
        "Bea",
        "Ruiz",
        role=stylist,
        user=account.person,
        email="bea@example.com",
        hire_date=dt.date(2026, 1, 15),
    )
    ana = make_member("Ana", "López", status=Member.Status.ON_LEAVE, is_bookable=False)
    make_member("Carla", "Gil", status=TERMINATED)

    page = members()

    assert [row.id for row in page.rows] == [ana.id, bea.id]
    assert page.total == 2
    row = page.rows[1]
    assert (
        row.full_name,
        row.role_id,
        row.role_name,
        row.user_id,
        row.email,
        row.hire_date,
    ) == (
        "Bea Ruiz",
        stylist.id,
        "Stylist",
        account.person.id,
        "bea@example.com",
        dt.date(2026, 1, 15),
    )
    assert (page.rows[0].status, page.rows[0].is_bookable, page.rows[0].role_name) == (
        "on_leave",
        False,
        None,
    )


def test_search_ignores_case_across_name_contact_number_and_position():
    make_member(
        "Ana", "López", email="ana@shop.es", phone="600111222", employee_number="E-7"
    )
    make_member("Bea", "Ruiz", role=make_role("Barber"))
    make_member("Carla", "Gil")

    def found(search):
        return [row.first_name for row in members(search=search).rows]

    assert found("ANA LÓ") == ["Ana"]
    assert found("lópez") == ["Ana"]
    assert found("shop.es") == ["Ana"]
    assert found("1112") == ["Ana"]
    assert found("e-7") == ["Ana"]
    assert found("barb") == ["Bea"]
    assert found("nobody") == []


def test_filters_by_status_position_and_bookable():
    barber = make_role("Barber")
    make_member("Ana", status=Member.Status.INACTIVE, is_bookable=False)
    make_member("Bea", role=barber)
    make_member("Carla", role=barber, is_bookable=False)

    assert [row.first_name for row in members(status="inactive").rows] == ["Ana"]
    assert [row.first_name for row in members(role_id=barber.id).rows] == [
        "Bea",
        "Carla",
    ]
    page = members(role_id=barber.id, is_bookable=True)
    assert ([row.first_name for row in page.rows], page.total) == (["Bea"], 1)


def test_pages_are_stable_with_id_as_tie_break():
    created = [make_member("Ana", "López") for _ in range(5)]
    pages = [members(limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [row.id for page in pages for row in page.rows] == sorted(
        member.id for member in created
    )


def test_an_employee_reads_the_directory_and_a_stranger_does_not():
    make_member()
    assert members(role="hub_employee").total == 1
    with pytest.raises(PermissionDenied):
        members(role="nobody")


def test_the_old_tables_filters():
    stylist = make_role("Stylist")
    ana = make_member("Ana", "López", email="ana@shop.es", phone="600", role=stylist, hire_date=dt.date(2025, 1, 10), color="#ff0000")
    bea = make_member("Bea", "Ruiz", email="bea@mail.com", phone="700", hire_date=dt.date(2026, 3, 1))

    def ids(**params):
        return [row.id for row in members(**params).rows]

    assert ids(first_name="an") == [ana.id]
    assert ids(last_name="RUI") == [bea.id]
    assert ids(email="mail.com") == [bea.id]
    assert ids(phone="70") == [bea.id]
    assert ids(role_name="stylist") == [ana.id]
    assert ids(hire_date_from=dt.date(2026, 1, 1)) == [bea.id]
    assert ids(hire_date_to=dt.date(2025, 12, 31)) == [ana.id]
    assert ids(color="#FF0000") == [ana.id]


def test_the_directory_by_its_linked_user(make_user):
    account = make_user("ana")
    ana = make_member("Ana", user=account.person)
    make_member("Bea")
    assert [row.id for row in members(user_id=account.person.id).rows] == [ana.id]


def test_every_column_sorts_both_ways_with_id_as_the_tie_break():
    ana = make_member("Ana", "Zamora", hire_date=dt.date(2026, 1, 1))
    bea = make_member("Bea", "Alonso", hire_date=dt.date(2025, 1, 1))
    carla = make_member("Carla", "Alonso")

    def order(sort):
        return [row.id for row in members(sort=sort).rows]

    assert order("name") == [ana.id, bea.id, carla.id]
    assert order("-name") == [carla.id, bea.id, ana.id]
    assert order("last_name") == [bea.id, carla.id, ana.id]
    # A missing date goes last whichever the direction, so the dated rows lead.
    assert order("hire_date") == [bea.id, ana.id, carla.id]
    assert order("-hire_date") == [ana.id, bea.id, carla.id]
    assert order("id") == sorted([ana.id, bea.id, carla.id])


# staff.member.detail


def test_detail():
    member = make_member(
        role=make_role("Stylist"),
        booking_buffer=10,
        specialties="color",
        bio="Ten years",
    )
    detail = run("staff.member.detail", MemberRefIn(id=member.id), "hub_employee")
    assert (
        detail.id,
        detail.role_name,
        detail.booking_buffer,
        detail.specialties,
        detail.bio,
    ) == (
        member.id,
        "Stylist",
        10,
        "color",
        "Ten years",
    )


# staff.member.mine (STAFF-F08)


def test_mine_is_the_callers_own_record_with_their_own_pay(make_user):
    ana_user, bea_user = make_user("ana"), make_user("bea")
    ana = make_member(
        "Ana", user=ana_user.person, hourly_rate=1500, commission_rate=Decimal("12.5")
    )
    make_member("Bea", user=bea_user.person, hourly_rate=9900)
    make_member("Carla")

    mine = run("staff.member.mine", MineIn(), "hub_employee", actor=ana_user).member

    assert (mine.id, mine.hourly_rate, mine.commission_rate) == (
        ana.id,
        1500,
        Decimal("12.50"),
    )


def test_mine_is_empty_without_a_live_linked_record(make_user):
    linked, unlinked = make_user("ana"), make_user("bea")
    make_member("Ana", user=linked.person, status=TERMINATED)
    for actor in (linked, unlinked, "system"):
        assert (
            run("staff.member.mine", MineIn(), "hub_employee", actor=actor).member
            is None
        )


# staff.member.current (SALE-F16: who «Me» is at the till)


def test_current_is_the_id_and_name_of_the_callers_own_record_without_any_staff_permission(make_user):
    ana_user, bea_user = make_user("ana"), make_user("bea")
    ana = make_member("Ana", user=ana_user.person, hourly_rate=1500, commission_rate=Decimal("12.5"))
    make_member("Bea", user=bea_user.person)
    make_member("Carla")

    # A cashier may sell without seeing the team: her own record is no secret to her.
    current = run("staff.member.current", CurrentMemberIn(), actor=ana_user, permissions={"sale.take_payment"})

    assert current.model_dump() == {"member": {"id": ana.id, "full_name": "Ana López"}}


def test_current_is_empty_without_a_live_linked_record_or_a_user_behind_the_session(make_user):
    linked, unlinked = make_user("ana"), make_user("bea")
    make_member("Ana", user=linked.person, status=TERMINATED)
    for actor in (linked, unlinked, "system", "tester"):
        assert run("staff.member.current", CurrentMemberIn(), actor=actor, permissions=set()).member is None


def test_current_names_a_record_that_is_inactive_or_on_leave_and_still_sells(make_user):
    away, idle = make_user("ana"), make_user("bea")
    ana = make_member("Ana", user=away.person, status=Member.Status.ON_LEAVE)
    bea = make_member("Bea", user=idle.person, status=Member.Status.INACTIVE)
    assert run("staff.member.current", CurrentMemberIn(), actor=away).member.id == ana.id
    assert run("staff.member.current", CurrentMemberIn(), actor=idle).member.id == bea.id


# staff.member.compensation (STAFF-F21)


def test_the_pay_sheet_names_both_ids_of_each_person(make_user):
    account = make_user("ana")
    ana = make_member(
        "Ana",
        user=account.person,
        hourly_rate=1500,
        commission_rate=Decimal("15"),
        role=make_role("Stylist"),
        notes="Reviews in March",
    )
    bea = make_member("Bea", status=Member.Status.INACTIVE)
    make_member("Carla", status=TERMINATED, hourly_rate=1)

    page = run("staff.member.compensation", CompensationListIn(), "hub_manager")

    assert [row.model_dump() for row in page.rows] == [
        {
            "id": ana.id,
            "user_id": account.person.id,
            "full_name": "Ana López",
            "role_id": ana.role_id,
            "role_name": "Stylist",
            "status": "active",
            "hourly_rate": 1500,
            "commission_rate": Decimal("15.00"),
            "notes": "Reviews in March",
        },
        {
            "id": bea.id,
            "user_id": None,
            "full_name": "Bea López",
            "role_id": None,
            "role_name": None,
            "status": "inactive",
            "hourly_rate": 0,
            "commission_rate": Decimal("0.00"),
            "notes": "",
        },
    ]


def test_the_pay_sheet_filters_by_record_status_and_name():
    ana = make_member("Ana")
    make_member("Bea", status=Member.Status.INACTIVE)

    assert [
        row.id
        for row in run("staff.member.compensation", CompensationListIn(id=ana.id)).rows
    ] == [ana.id]
    assert [
        row.full_name
        for row in run(
            "staff.member.compensation", CompensationListIn(status="inactive")
        ).rows
    ] == ["Bea López"]
    assert [
        row.full_name
        for row in run(
            "staff.member.compensation", CompensationListIn(search="ana")
        ).rows
    ] == ["Ana López"]


def test_the_pay_sheet_pages_and_sorts_as_the_directory():
    """The Rate/h column reads the pay of exactly the rows on screen: same filters, sort and window."""
    for name, email in (("Ana", "ana@shop.es"), ("Bea", "bea@shop.es"), ("Carla", "carla@else.es"), ("Dora", "dora@shop.es")):
        make_member(name, email=email)
    make_member("Eva", email="eva@shop.es", status=Member.Status.INACTIVE)
    for params in (
        {"search": "shop", "sort": "-name", "limit": 2, "offset": 1},
        {"email": "shop", "status": "active", "sort": "first_name", "limit": 2},
        {"is_bookable": True, "sort": "-first_name", "limit": 100},
    ):
        directory = run("staff.member.list", MemberListIn(**params))
        pay = run("staff.member.compensation", CompensationListIn(**params))
        assert [row.id for row in pay.rows] == [row.id for row in directory.rows], params
        assert pay.total == directory.total, params


def test_an_employee_does_not_see_the_pay_sheet():
    with pytest.raises(PermissionDenied):
        run("staff.member.compensation", CompensationListIn(), "hub_employee")


# staff.member.stats (STAFF-F23)


def test_stats():
    ana = make_member("Ana")
    bea = make_member("Bea", status=Member.Status.ON_LEAVE)
    make_member("Carla", status=Member.Status.INACTIVE)
    gone = make_member("Dora", status=TERMINATED)
    day = today().isoformat()
    # Two approved absences of Ana today count her once.
    make_time_off(
        ana,
        day,
        status=TimeOff.Status.APPROVED,
        is_full_day=False,
        start_time=t("09:00"),
        end_time=t("10:00"),
    )
    make_time_off(
        ana,
        day,
        status=TimeOff.Status.APPROVED,
        is_full_day=False,
        start_time=t("12:00"),
        end_time=t("13:00"),
    )
    make_time_off(bea, day)  # pending: not away, but waiting
    make_time_off(bea, (today() + dt.timedelta(days=3)).isoformat())  # pending
    make_time_off(gone, day, status=TimeOff.Status.APPROVED)
    make_time_off(
        gone, day
    )  # a terminated record's request no longer waits for anybody

    assert run("staff.member.stats", MemberStatsIn(), "hub_employee").model_dump() == {
        "total": 3,
        "active": 1,
        "on_leave": 1,
        "inactive": 1,
        "absent_today": 1,
        "pending_time_off": 2,
    }


def test_empty_stats():
    assert set(run("staff.member.stats", MemberStatsIn()).model_dump().values()) == {0}


def test_absent_today_is_the_business_day(frozen_now):
    frozen_now(LATE_EVENING_UTC)
    starts, ended, also_ended = make_member("Ana"), make_member("Bea"), make_member("Carla")
    make_time_off(starts, "2026-08-19", "2026-08-25", status=TimeOff.Status.APPROVED)
    # Two people ended yesterday: the server's UTC date would count them (2), the business's day counts Ana.
    make_time_off(ended, "2026-08-10", "2026-08-18", status=TimeOff.Status.APPROVED)
    make_time_off(also_ended, "2026-08-18", status=TimeOff.Status.APPROVED)
    assert run("staff.member.stats", MemberStatsIn()).absent_today == 1
