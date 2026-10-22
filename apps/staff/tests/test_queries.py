"""Read operations of the staff app: directory, records, pay, positions, schedules, availability and time off."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.staff.models import Member, StaffSettings, TimeOff
from apps.staff.schemas import (
    AccountListIn,
    AccountPage,
    AvailabilityIn,
    AvailabilityOut,
    ByIdIn,
    CommissionPage,
    CommissionSummaryIn,
    CompensationListIn,
    CompensationPage,
    MemberDetailOut,
    MemberListIn,
    MemberPage,
    MemberRefIn,
    MemberStatsIn,
    MemberStatsOut,
    MineIn,
    MineOut,
    MyTimeOffIn,
    RoleListIn,
    RolePage,
    ScheduleListIn,
    ScheduleOut,
    SchedulePage,
    SettingsGetIn,
    SettingsOut,
    TimeOffDetailOut,
    TimeOffDetailPage,
    TimeOffListIn,
    TimeOffPage,
    TodayIn,
)

from .conftest import ctx_for, make_member, make_role, make_schedule, make_time_off

pytestmark = pytest.mark.django_db

TERMINATED = Member.Status.TERMINATED
# 2026-08-18 22:30 UTC is already 2026-08-19 00:30 in Madrid (the business's zone, settings.TIME_ZONE).
LATE_EVENING_UTC = dt.datetime(2026, 8, 18, 22, 30, tzinfo=dt.UTC)


def run(name, data, role="hub_admin", **ctx):
    return get(name)(ctx_for(role, **ctx), data)


def t(value):
    return dt.time.fromisoformat(value)


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze ``timezone.now`` (and so the business's «today») at an instant."""

    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


def today():
    return timezone.localdate()


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        ("staff.member.list", "staff.view", MemberListIn, MemberPage, True),
        ("staff.member.detail", "staff.view", MemberRefIn, MemberDetailOut, True),
        ("staff.member.mine", "staff.view", MineIn, MineOut, True),
        ("staff.member.compensation", "staff.view_compensation", CompensationListIn, CompensationPage, False),
        ("staff.member.stats", "staff.view", MemberStatsIn, MemberStatsOut, False),
        ("staff.commission.summary", "staff.view_compensation", CommissionSummaryIn, CommissionPage, True),
        ("staff.role.list", "staff.view", RoleListIn, RolePage, True),
        ("staff.schedule.list", "staff.view", ScheduleListIn, SchedulePage, True),
        ("staff.schedule.detail", "staff.view", ByIdIn, ScheduleOut, False),
        ("staff.availability.for_member", "staff.view", AvailabilityIn, AvailabilityOut, True),
        ("staff.time_off.list", "staff.view_time_off", TimeOffListIn, TimeOffPage, False),
        ("staff.time_off.detail", "staff.view_time_off_detail", ByIdIn, TimeOffDetailOut, False),
        ("staff.time_off.today", "staff.view_time_off", TodayIn, TimeOffPage, False),
        ("staff.time_off.mine", "staff.view_time_off", MyTimeOffIn, TimeOffDetailPage, True),
        ("staff.settings.get", "staff.view", SettingsGetIn, SettingsOut, False),
        # Two permissions may read it (add or change a record): the operation checks them itself.
        ("staff.account.list", None, AccountListIn, AccountPage, False),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        permission,
        input,
        output,
        expose_api,
    )


# staff.member.list (STAFF-F09)


def members(role="hub_admin", **params):
    return run("staff.member.list", MemberListIn(**params), role)


def test_empty_directory():
    assert members().model_dump() == {"rows": [], "total": 0, "limit": 50, "offset": 0}


def test_the_directory_by_name_without_terminated_records(make_user):
    stylist = make_role("Stylist")
    account = make_user("bea")
    bea = make_member(
        "Bea",
        "Ruiz",
        role=stylist,
        user=account,
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
        account.id,
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
    ana = make_member("Ana", user=account)
    make_member("Bea")
    assert [row.id for row in members(user_id=account.id).rows] == [ana.id]


def test_every_column_sorts_both_ways_with_id_as_the_tie_break():
    ana = make_member("Ana", "Zamora", hire_date=dt.date(2026, 1, 1), email="z@x.es")
    bea = make_member("Bea", "Alonso", hire_date=dt.date(2025, 1, 1), email="a@x.es")
    carla = make_member("Carla", "Alonso")

    def order(sort):
        return [row.id for row in members(sort=sort).rows]

    assert order("name") == [ana.id, bea.id, carla.id]
    assert order("-name") == [carla.id, bea.id, ana.id]
    assert order("last_name") == [bea.id, carla.id, ana.id]
    assert order("email")[:2] == [carla.id, bea.id]  # empty first
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


def test_detail_of_a_terminated_or_missing_record_is_not_found():
    terminated = make_member(status=TERMINATED)
    for member_id in (terminated.id, uuid.uuid7()):
        with pytest.raises(NotFound) as excinfo:
            run("staff.member.detail", MemberRefIn(id=member_id))
        assert (excinfo.value.status, excinfo.value.code) == (404, "not_found")


def test_a_member_by_name_for_the_assistant():
    ana = make_member("Ana", "López")
    make_member("Bea", "Ruiz")
    make_member("Ana", "Gone", status=TERMINATED)
    for spoken in ("ana lópez", "Ana", "lópez"):
        assert run("staff.member.detail", MemberRefIn(member=spoken)).id == ana.id


def test_an_exact_name_wins_over_partial_matches():
    ana = make_member("Ana", "López")
    make_member("Mariana", "López")
    assert run("staff.member.detail", MemberRefIn(member="Ana López")).id == ana.id


def test_an_ambiguous_name_names_the_candidates():
    make_member("Ana", "López")
    make_member("Ana", "Ruiz")
    with pytest.raises(Conflict) as excinfo:
        run("staff.member.detail", MemberRefIn(member="ana"))
    assert (excinfo.value.status, excinfo.value.code) == (409, "staff.ambiguous_member")
    assert "Ana López" in excinfo.value.message and "Ana Ruiz" in excinfo.value.message


def test_an_unknown_name_is_not_found():
    with pytest.raises(NotFound):
        run("staff.member.detail", MemberRefIn(member="Nobody"))


# staff.member.mine (STAFF-F08)


def test_mine_is_the_callers_own_record_with_their_own_pay(make_user):
    ana_user, bea_user = make_user("ana"), make_user("bea")
    ana = make_member(
        "Ana", user=ana_user, hourly_rate=1500, commission_rate=Decimal("12.5")
    )
    make_member("Bea", user=bea_user, hourly_rate=9900)
    make_member("Carla")

    mine = run("staff.member.mine", MineIn(), "hub_employee", actor=ana_user).member

    assert (mine.id, mine.hourly_rate, mine.commission_rate) == (
        ana.id,
        1500,
        Decimal("12.50"),
    )


def test_mine_is_empty_without_a_live_linked_record(make_user):
    linked, unlinked = make_user("ana"), make_user("bea")
    make_member("Ana", user=linked, status=TERMINATED)
    for actor in (linked, unlinked, "system"):
        assert (
            run("staff.member.mine", MineIn(), "hub_employee", actor=actor).member
            is None
        )


# staff.member.compensation (STAFF-F21)


def test_the_pay_sheet_names_both_ids_of_each_person(make_user):
    account = make_user("ana")
    ana = make_member(
        "Ana",
        user=account,
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
            "user_id": account.id,
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
        {"email": "shop", "status": "active", "sort": "email", "limit": 2},
        {"is_bookable": True, "sort": "-email", "limit": 100},
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


# staff.commission.summary (STAFF-F21)


def test_the_commission_sheet_lists_who_can_earn_one_with_both_ids(make_user):
    account = make_user("ana")
    ana = make_member("Ana", user=account, commission_rate=Decimal("15"), role=make_role("Stylist"))
    bea = make_member("Bea", status=Member.Status.ON_LEAVE)  # a zero rate is listed too
    make_member("Carla", status=Member.Status.INACTIVE, commission_rate=Decimal("10"))
    make_member("Dora", status=TERMINATED, commission_rate=Decimal("10"))

    page = run("staff.commission.summary", CommissionSummaryIn(), "hub_manager")

    assert [row.model_dump() for row in page.rows] == [
        {
            "id": ana.id,
            "user_id": account.id,
            "full_name": "Ana López",
            "role_id": ana.role_id,
            "role_name": "Stylist",
            "commission_rate": Decimal("15.00"),
        },
        {
            "id": bea.id,
            "user_id": None,
            "full_name": "Bea López",
            "role_id": None,
            "role_name": None,
            "commission_rate": Decimal("0.00"),
        },
    ]
    assert [row.id for row in run("staff.commission.summary", CommissionSummaryIn(search="bea")).rows] == [bea.id]


def test_an_employee_does_not_see_the_commission_sheet():
    with pytest.raises(PermissionDenied):
        run("staff.commission.summary", CommissionSummaryIn(), "hub_employee")


# staff.role.list (STAFF-F04, STAFF-F23)


def test_positions_with_their_active_members():
    stylist, barber = (
        make_role("Stylist", description="Cuts and colour", color="#ff0000"),
        make_role("Barber"),
    )
    make_member("Ana", role=stylist)
    make_member("Bea", role=stylist, status=Member.Status.ON_LEAVE)
    make_member("Carla", role=stylist, status=TERMINATED)
    retired = make_role("Washer", is_active=False)

    page = run("staff.role.list", RoleListIn(), "hub_employee")

    assert [(row.name, row.member_count, row.is_active) for row in page.rows] == [
        ("Barber", 0, True),
        ("Stylist", 1, True),
        ("Washer", 0, False),
    ]
    assert (page.rows[1].description, page.rows[1].color) == (
        "Cuts and colour",
        "#ff0000",
    )
    assert [
        row.id for row in run("staff.role.list", RoleListIn(is_active=False)).rows
    ] == [retired.id]
    assert [
        row.id for row in run("staff.role.list", RoleListIn(search="COLOUR")).rows
    ] == [stylist.id]
    assert [
        row.id for row in run("staff.role.list", RoleListIn(search="barb")).rows
    ] == [barber.id]


def test_roles_carry_their_order_and_sort_and_filter_like_the_old_table():
    stylist = make_role("Stylist", color="#ff0000", order=2)
    barber = make_role("Barber", order=1)
    make_member("Ana", role=stylist)
    make_member("Bea", role=stylist)
    make_member("Carla", role=barber)

    def names(**params):
        return [row.name for row in run("staff.role.list", RoleListIn(**params)).rows]

    assert [row.order for row in run("staff.role.list", RoleListIn()).rows] == [1, 2]
    assert names(sort="-member_count") == ["Stylist", "Barber"]
    assert names(sort="order") == ["Barber", "Stylist"]
    assert names(sort="-name") == ["Stylist", "Barber"]
    assert names(color="#FF0000") == ["Stylist"]
    assert names(member_count_min=2) == ["Stylist"]
    assert names(member_count_max=1) == ["Barber"]


# staff.schedule.list and staff.schedule.detail (STAFF-F13–F15)


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
    detail = run("staff.schedule.detail", ByIdIn(id=schedule.id), "hub_employee")
    assert (detail.id, [day.weekday for day in detail.days]) == (schedule.id, [2])
    with pytest.raises(NotFound):
        run("staff.schedule.detail", ByIdIn(id=uuid.uuid7()))


def test_the_schedules_of_a_member_named_by_name():
    ana = make_member("Ana", "López")
    usual = make_schedule(ana)
    assert [row.id for row in run("staff.schedule.list", ScheduleListIn(member="ana lópez")).rows] == [usual.id]
    with pytest.raises(NotFound):
        run("staff.schedule.list", ScheduleListIn(member="Nobody"))


# staff.availability.for_member (STAFF-F16)

MONDAY = dt.date(2026, 10, 12)  # a Monday


def availability(member, start=MONDAY, end=None):
    data = AvailabilityIn(member_id=member.id, date_from=start, date_to=end or start)
    return run("staff.availability.for_member", data, "hub_employee").days


def spans(intervals):
    return [
        (item.start.strftime("%H:%M"), item.end.strftime("%H:%M")) for item in intervals
    ]


def test_without_a_schedule_no_day_is_governed():
    [day] = availability(make_member())
    assert (day.date, day.schedule_id, day.shifts, day.time_off, day.available) == (
        MONDAY,
        None,
        [],
        [],
        [],
    )


def test_the_default_schedule_split_around_its_break():
    ana = make_member()
    usual = make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})

    monday, tuesday = availability(ana, MONDAY, MONDAY + dt.timedelta(days=1))

    assert (monday.schedule_id, spans(monday.shifts), spans(monday.available)) == (
        usual.id,
        [("09:00", "13:00"), ("14:00", "18:00")],
        [("09:00", "13:00"), ("14:00", "18:00")],
    )
    # The schedule governs Tuesday too, as a day off: not «no schedule».
    assert (tuesday.date, tuesday.schedule_id, tuesday.shifts) == (
        MONDAY + dt.timedelta(days=1),
        usual.id,
        [],
    )


def test_a_break_at_an_edge_leaves_no_empty_piece():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "09:00", "10:00")})
    assert spans(availability(ana)[0].shifts) == [("10:00", "18:00")]


def test_a_specific_schedule_beats_the_default_within_its_dates():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    special = make_schedule(
        ana,
        {0: ("10:00", "12:00")},
        name="One day",
        is_default=False,
        effective_from=MONDAY,
        effective_until=MONDAY,
    )

    on, after = availability(ana, MONDAY, MONDAY + dt.timedelta(days=7))[0::7]

    assert (on.schedule_id, spans(on.shifts)) == (special.id, [("10:00", "12:00")])
    assert (after.date, spans(after.shifts)) == (
        MONDAY + dt.timedelta(days=7),
        [("09:00", "18:00")],
    )


def test_a_non_default_schedule_without_dates_beats_the_default_always():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    open_ended = make_schedule(
        ana, {0: ("08:00", "15:00")}, name="New", is_default=False
    )
    assert availability(ana)[0].schedule_id == open_ended.id


def test_between_specific_schedules_the_latest_start_then_the_newest_wins():
    ana = make_member()
    make_schedule(
        ana,
        {0: ("09:00", "10:00")},
        name="Autumn",
        is_default=False,
        effective_from=MONDAY - dt.timedelta(days=30),
    )
    late = make_schedule(
        ana,
        {0: ("09:00", "11:00")},
        name="Week",
        is_default=False,
        effective_from=MONDAY,
    )
    assert availability(ana)[0].schedule_id == late.id
    newer = make_schedule(
        ana,
        {0: ("09:00", "12:00")},
        name="Week bis",
        is_default=False,
        effective_from=MONDAY,
    )
    assert availability(ana)[0].schedule_id == newer.id


def test_an_inactive_or_out_of_date_schedule_never_governs():
    ana = make_member()
    usual = make_schedule(ana, {0: ("09:00", "18:00")})
    make_schedule(
        ana, {0: ("10:00", "11:00")}, name="Off", is_default=False, is_active=False
    )
    make_schedule(
        ana,
        {0: ("10:00", "11:00")},
        name="Past",
        is_default=False,
        effective_until=MONDAY - dt.timedelta(days=1),
    )
    make_schedule(
        ana,
        {0: ("10:00", "11:00")},
        name="Future",
        is_default=False,
        effective_from=MONDAY + dt.timedelta(days=1),
    )
    assert availability(ana)[0].schedule_id == usual.id


def test_an_approved_full_day_absence_leaves_nothing_available():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    make_time_off(
        ana,
        "2026-10-10",
        "2026-10-13",
        status=TimeOff.Status.APPROVED,
        leave_type="sick",
        reason="flu",
    )

    [day] = availability(ana)

    assert (spans(day.shifts), day.available) == ([("09:00", "18:00")], [])
    # The absence, without its type or its reason.
    assert [absence.model_dump() for absence in day.time_off] == [
        {"is_full_day": True, "start_time": None, "end_time": None}
    ]


def test_approved_part_day_absences_cut_the_shifts():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})
    make_time_off(
        ana, "2026-10-12", hours=("10:00", "11:00"), status=TimeOff.Status.APPROVED
    )
    make_time_off(
        ana, "2026-10-12", hours=("12:30", "15:00"), status=TimeOff.Status.APPROVED
    )

    [day] = availability(ana)

    assert spans(day.available) == [
        ("09:00", "10:00"),
        ("11:00", "12:30"),
        ("15:00", "18:00"),
    ]
    assert [(a.start_time, a.end_time) for a in day.time_off] == [
        (t("10:00"), t("11:00")),
        (t("12:30"), t("15:00")),
    ]


def test_an_absence_covering_a_whole_shift_removes_it():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})
    make_time_off(
        ana, "2026-10-12", hours=("08:00", "13:30"), status=TimeOff.Status.APPROVED
    )
    assert spans(availability(ana)[0].available) == [("14:00", "18:00")]


def test_part_day_absences_repeat_on_every_day_of_their_range():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "12:00"), 1: ("09:00", "12:00")})
    make_time_off(
        ana,
        "2026-10-12",
        "2026-10-13",
        hours=("09:00", "10:00"),
        status=TimeOff.Status.APPROVED,
    )
    assert [
        spans(day.available)
        for day in availability(ana, MONDAY, MONDAY + dt.timedelta(days=1))
    ] == [
        [("10:00", "12:00")],
        [("10:00", "12:00")],
    ]


def test_only_approved_absences_count():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    for status in (
        TimeOff.Status.PENDING,
        TimeOff.Status.REJECTED,
        TimeOff.Status.CANCELLED,
    ):
        make_time_off(ana, "2026-10-12", status=status)
    [day] = availability(ana)
    assert (spans(day.available), day.time_off) == ([("09:00", "18:00")], [])


def test_one_row_per_day_of_the_range():
    days = availability(make_member(), MONDAY, MONDAY + dt.timedelta(days=730))
    assert (len(days), days[0].date, days[-1].date) == (
        731,
        MONDAY,
        MONDAY + dt.timedelta(days=730),
    )


def test_availability_of_a_terminated_or_missing_record_is_not_found():
    gone = make_member(status=TERMINATED)
    make_schedule(gone)
    with pytest.raises(NotFound):
        availability(gone)
    with pytest.raises(NotFound):
        run(
            "staff.availability.for_member",
            AvailabilityIn(member_id=uuid.uuid7(), date_from=MONDAY, date_to=MONDAY),
        )


def test_availability_of_a_member_named_by_name():
    ana = make_member("Ana", "López")
    make_schedule(ana, {0: ("09:00", "13:00")})
    data = AvailabilityIn(member="Ana", date_from=MONDAY, date_to=MONDAY)
    result = run("staff.availability.for_member", data)
    assert (result.member_id, spans(result.days[0].available)) == (ana.id, [("09:00", "13:00")])


# staff.time_off.list (STAFF-F17–F19)


def time_off(role="hub_admin", **params):
    return run("staff.time_off.list", TimeOffListIn(**params), role)


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
    approved = make_time_off(ana, "2026-10-01", "2026-10-03", status=TimeOff.Status.APPROVED, approved_by=boss)
    hours = make_time_off(ana, "2026-10-20", hours=("09:00", "10:00"))
    make_time_off(ana, "2026-11-10", "2026-11-12")

    def ids(**params):
        return [row.id for row in time_off(**params).rows]

    assert ids(approved_by_id=boss.id) == [approved.id]
    assert time_off(approved_by_id=boss.id).rows[0].approved_by_id == boss.id
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


def test_time_off_detail_with_its_reason_and_approver(make_user):
    boss = make_user("boss", first_name="Marta")
    leave = make_time_off(
        make_member(),
        "2026-10-12",
        reason="Surgery",
        notes="Back on Monday",
        status=TimeOff.Status.APPROVED,
        approved_by=boss,
        approved_at=timezone.now(),
    )
    detail = run("staff.time_off.detail", ByIdIn(id=leave.id), "hub_manager")
    assert (detail.reason, detail.notes, detail.approved_by_name, detail.approved_at) == (
        "Surgery",
        "Back on Monday",
        "Marta",
        leave.approved_at,
    )


def test_time_off_detail_names_an_approver_without_a_name_by_username(make_user):
    leave = make_time_off(make_member(), "2026-10-12", approved_by=make_user("saas:42"))
    assert (
        run("staff.time_off.detail", ByIdIn(id=leave.id)).approved_by_name == "saas:42"
    )


def test_an_employee_does_not_read_the_reason():
    leave = make_time_off(make_member(), "2026-10-12", reason="Surgery")
    with pytest.raises(PermissionDenied):
        run("staff.time_off.detail", ByIdIn(id=leave.id), "hub_employee")


def test_time_off_detail_of_a_missing_or_terminated_record_is_not_found():
    gone = make_time_off(make_member(status=TERMINATED), "2026-10-12")
    for time_off_id in (gone.id, uuid.uuid7()):
        with pytest.raises(NotFound):
            run("staff.time_off.detail", ByIdIn(id=time_off_id))


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


def test_today_is_the_business_day(frozen_now):
    frozen_now(LATE_EVENING_UTC)
    starts = make_time_off(
        make_member("Ana"), "2026-08-19", status=TimeOff.Status.APPROVED
    )
    make_time_off(make_member("Bea"), "2026-08-18", status=TimeOff.Status.APPROVED)
    assert [row.id for row in run("staff.time_off.today", TodayIn()).rows] == [
        starts.id
    ]


# staff.time_off.mine (STAFF-F08)


def test_my_time_off_with_its_reason(make_user):
    me = make_user("ana")
    ana = make_member("Ana", user=me)
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


# staff.settings.get (STAFF-F22)


def test_settings_are_the_defaults_until_the_first_save():
    assert run("staff.settings.get", SettingsGetIn(), "hub_employee").model_dump() == {
        "default_work_start": "09:00",
        "default_work_end": "18:00",
        "default_break_duration": 60,
        "min_advance_booking": 1,
        "max_daily_hours": 12,
        "overtime_threshold": 40,
        "show_staff_photos": True,
        "show_staff_bio": True,
        "allow_staff_selection": True,
        "notify_new_appointment": True,
        "notify_cancellation": True,
    }
    assert not StaffSettings.objects.exists()  # a read never creates the row


def test_saved_settings_show_their_hours_as_hh_mm():
    StaffSettings.objects.create(default_work_start=dt.time(9, 30, 15), max_daily_hours=8, show_staff_bio=False)
    settings = run("staff.settings.get", SettingsGetIn())
    assert (settings.default_work_start, settings.max_daily_hours, settings.show_staff_bio) == ("09:30", 8, False)


# staff.account.list (STAFF-F03): the «Hub user» selector


def accounts(role="hub_admin", **params):
    return run("staff.account.list", AccountListIn(**params), role)


def test_the_accounts_with_access_to_this_business(make_user):
    marta = make_user("saas:1", host="a", role="hub_manager", first_name="Marta")
    eva = make_user("saas:2", host="a", role="hub_employee")
    eva.email = "eva@shop.es"
    eva.save()
    make_user("saas:3", host="b", first_name="Other business")
    gone = make_user("saas:4", host="a", first_name="Deactivated")
    gone.is_active = False
    gone.save()

    page = accounts()

    assert [row.model_dump() for row in page.rows] == [
        {"user_id": eva.id, "name": "eva@shop.es"},
        {"user_id": marta.id, "name": "Marta"},
    ]
    assert page.total == 2
    assert [row.user_id for row in accounts(search="MAR").rows] == [marta.id]


def test_one_account_by_its_user_to_name_the_one_a_record_hangs_from(make_user):
    marta = make_user("saas:1", host="a", role="hub_manager", first_name="Marta")
    make_user("saas:2", host="a", role="hub_employee", first_name="Eva")
    elsewhere = make_user("saas:3", host="b", first_name="Other business")
    gone = make_user("saas:4", host="a", first_name="Deactivated")
    gone.is_active = False
    gone.save()

    assert [row.name for row in accounts(user_id=marta.id).rows] == ["Marta"]
    # Without access to this business (another one's, or deactivated): nothing to name.
    assert accounts(user_id=elsewhere.id).rows == []
    assert accounts(user_id=gone.id).rows == []


def test_accounts_for_whoever_adds_or_edits_records():
    assert accounts(role="hub_manager").total == 0
    for permissions in ({"staff.add_member"}, {"staff.change_member"}):
        assert get("staff.account.list")(ctx_for(permissions=permissions), AccountListIn()).total == 0
    with pytest.raises(PermissionDenied):
        accounts(role="hub_employee")
