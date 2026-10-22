"""Write operations of the staff app: one transaction each, with its events in the outbox.

The cases come from the old module's batteries (member_lifecycle, tenant_role, user_link,
user_link_race, time_off_guards, business_day, self_service, schedules_availability,
settings_defaults and the handler's tests). A refused command leaves no trace: no row, no event.
"""

import datetime as dt
import json
import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.db import connection, transaction
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.staff import events, services
from apps.staff.models import (
    Member,
    Role,
    Schedule,
    ScheduleDay,
    StaffSettings,
    TimeOff,
)
from apps.staff.schemas import (
    BulkCreatedOut,
    BulkCreateIn,
    ByIdIn,
    DeletedOut,
    MemberDetailOut,
    MemberIn,
    MemberPatchIn,
    MemberRefIn,
    RoleIn,
    RoleOut,
    RolePatchIn,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdateIn,
    SetActiveIn,
    SettingsIn,
    SettingsOut,
    TerminatedOut,
    TerminateIn,
    TimeOffDetailOut,
    TimeOffIn,
    TimeOffRequestIn,
)

from .conftest import (
    A,
    B,
    ctx_for,
    make_member,
    make_role,
    make_schedule,
    make_time_off,
)

WAIT = 1.0
QUIET = 0.3
# 2026-08-18 22:30 UTC is already 2026-08-19 00:30 in Madrid (the business's zone).
LATE_EVENING_UTC = dt.datetime(2026, 8, 18, 22, 30, tzinfo=dt.UTC)
WEEK = [
    {
        "weekday": 0,
        "start_time": "09:00",
        "end_time": "18:00",
        "break_start": "13:00",
        "break_end": "14:00",
    }
]


def run(name, data, role="hub_admin", **ctx):
    return get(name)(ctx_for(role, **ctx), data)


def outbox():
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


def names():
    return [name for name, _, _ in outbox()]


def t(value):
    return dt.time.fromisoformat(value)


def today():
    return timezone.localdate()


@pytest.fixture
def frozen_now(monkeypatch):
    def freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)

    return freeze


def create(first="Ana", last="López", as_role="hub_admin", **fields):
    return run("staff.member.create", MemberIn(first_name=first, last_name=last, **fields), as_role)


def update(as_role="hub_admin", **fields):
    return run("staff.member.update", MemberPatchIn(**fields), as_role)


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        ("staff.member.create", "staff.add_member", MemberIn, MemberDetailOut, True),
        (
            "staff.member.bulk_create",
            "staff.add_member",
            BulkCreateIn,
            BulkCreatedOut,
            False,
        ),
        (
            "staff.member.update",
            "staff.change_member",
            MemberPatchIn,
            MemberDetailOut,
            True,
        ),
        (
            "staff.member.deactivate",
            "staff.delete_member",
            MemberRefIn,
            MemberDetailOut,
            False,
        ),
        (
            "staff.member.terminate",
            "staff.delete_member",
            TerminateIn,
            TerminatedOut,
            False,
        ),
        ("staff.role.create", "staff.manage_settings", RoleIn, RoleOut, False),
        ("staff.role.update", "staff.manage_settings", RolePatchIn, RoleOut, False),
        (
            "staff.schedule.create",
            "staff.manage_settings",
            ScheduleIn,
            ScheduleOut,
            False,
        ),
        (
            "staff.schedule.update",
            "staff.manage_settings",
            ScheduleUpdateIn,
            ScheduleOut,
            False,
        ),
        (
            "staff.schedule.set_active",
            "staff.manage_settings",
            SetActiveIn,
            ScheduleOut,
            False,
        ),
        ("staff.schedule.delete", "staff.manage_settings", ByIdIn, DeletedOut, False),
        (
            "staff.time_off.create",
            "staff.manage_time_off",
            TimeOffIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.request",
            "staff.request_time_off",
            TimeOffRequestIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.approve",
            "staff.manage_time_off",
            ByIdIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.reject",
            "staff.manage_time_off",
            ByIdIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.time_off.cancel",
            "staff.request_time_off",
            ByIdIn,
            TimeOffDetailOut,
            False,
        ),
        (
            "staff.settings.update",
            "staff.manage_settings",
            SettingsIn,
            SettingsOut,
            False,
        ),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "command",
        permission,
        input,
        output,
        expose_api,
    )


# staff.member.create (STAFF-F01, STAFF-F03)

pytestmark = pytest.mark.django_db


def test_create_returns_the_record_and_records_created():
    stylist = make_role("Stylist")
    detail = create(
        email="ana@shop.es",
        role_id=stylist.id,
        hire_date=dt.date(2026, 1, 15),
        booking_buffer=10,
        hourly_rate=1500,
        commission_rate=Decimal("12.5"),
        notes="Reviews in March",
    )
    member = Member.objects.get()
    assert (
        detail.id,
        detail.full_name,
        detail.role_name,
        detail.status,
        detail.booking_buffer,
    ) == (
        member.id,
        "Ana López",
        "Stylist",
        "active",
        10,
    )
    assert (member.hourly_rate, member.commission_rate, member.notes) == (
        1500,
        Decimal("12.50"),
        "Reviews in March",
    )
    assert outbox() == [(events.MEMBER_CREATED, "a", {"id": str(member.id)})]
    assert OutboxEvent.objects.get().actor == "tester"


def test_a_record_can_be_born_inactive_or_on_leave():
    assert create(status="on_leave").status == "on_leave"


def test_the_role_by_name_for_the_assistant():
    stylist = make_role("Stylist")
    assert create(role=" stylist ").role_id == stylist.id


@pytest.mark.parametrize(
    "make", [lambda: make_role("Old", is_active=False).id, lambda: uuid.uuid7()]
)
def test_a_role_that_is_retired_or_unknown_is_refused(make):
    role_id = make()
    with pytest.raises(InvalidPayload) as excinfo:
        create(role_id=role_id)
    assert excinfo.value.fields == {
        "role_id": "That role is not available: it does not exist in this business, or it has been deleted or retired."
    }
    assert not Member.objects.exists() and outbox() == []


def test_an_unknown_role_name_is_refused_on_its_field():
    with pytest.raises(InvalidPayload) as excinfo:
        create(role="Astronaut")
    assert set(excinfo.value.fields) == {"role"}


def test_a_user_with_access_to_the_business_is_linked(make_user):
    account = make_user("ana", host="a", role="hub_employee")
    assert create(user_id=account.id).user_id == account.id


def test_a_user_without_access_to_this_business_is_refused(make_user):
    stranger = make_user("bea", host="b")
    for user_id in (stranger.id, 999_999):
        with pytest.raises(InvalidPayload) as excinfo:
            create(user_id=user_id)
        assert excinfo.value.fields == {
            "user_id": "That Hub user has no access to this business."
        }
    assert not Member.objects.exists()


def test_one_user_one_live_record_names_the_holder(make_user):
    account = make_user("ana")
    create("Ana", "López", user_id=account.id)
    OutboxEvent.objects.all().delete()

    with pytest.raises(Conflict) as excinfo:
        create("Bea", "Ruiz", user_id=account.id)

    assert (excinfo.value.status, excinfo.value.code) == (
        409,
        "staff.user_already_linked",
    )
    assert "Ana López" in excinfo.value.message
    assert Member.objects.count() == 1 and outbox() == []


def test_the_database_settles_two_links_at_once(make_user, monkeypatch):
    # user_link_race: both reads see nobody; the index stops the second write with the same answer.
    account = make_user("ana")
    create("Ana", user_id=account.id)
    monkeypatch.setattr(services, "_holder_of", lambda user_id, exclude=None: None)
    with pytest.raises(Conflict) as excinfo:
        create("Bea", user_id=account.id)
    assert excinfo.value.code == "staff.user_already_linked"
    assert Member.objects.count() == 1


def test_pay_needs_the_pay_permission():
    # A role that may add records but not see pay (no customer role is like that; an API key may be).
    clerk = {"staff.add_member", "staff.change_member", "staff.view"}
    for fields in (
        {"hourly_rate": 1},
        {"commission_rate": Decimal("5")},
        {"notes": "x"},
    ):
        with pytest.raises(PermissionDenied):
            get("staff.member.create")(
                ctx_for(permissions=clerk),
                MemberIn(first_name="A", last_name="B", **fields),
            )
    assert get("staff.member.create")(
        ctx_for(permissions=clerk), MemberIn(first_name="A", last_name="B")
    ).id
    assert not Member.objects.filter(hourly_rate__gt=0).exists()


def test_an_employee_cannot_add_records():
    with pytest.raises(PermissionDenied):
        create(as_role="hub_employee")


# staff.member.bulk_create (STAFF-F07)


def test_bulk_create_adds_the_good_rows_and_names_the_skipped_ones():
    stylist = make_role("Stylist")
    make_role("Retired", is_active=False)
    rows = [
        {
            "first_name": "Ana",
            "last_name": "López",
            "role_id": str(stylist.id),
            "hourly_rate": 1200,
        },
        {"first_name": "  ", "last_name": "Ruiz"},
        {"first_name": "Bea", "last_name": "Ruiz", "role": "retired"},
        {"first_name": "Carla", "last_name": "Gil", "hire_date": "2026-13-40"},
        {"first_name": "Dora", "last_name": "Paz", "hourly_rate": -5},
        {"first_name": "Eva", "last_name": "Sanz", "email": "nope"},
        {
            "first_name": "Fe",
            "last_name": "Mar",
            "hire_date": "2026-02-01",
            "role": "Stylist",
            "is_bookable": False,
        },
    ]

    result = run("staff.member.bulk_create", BulkCreateIn(members=rows))

    created = list(Member.objects.order_by("first_name"))
    assert [member.first_name for member in created] == ["Ana", "Fe"]
    assert {member.id for member in created} == set(result.created)
    assert [(row.index, row.reason) for row in result.skipped] == [
        (1, "name_required"),
        (2, "role_not_found"),
        (3, "invalid_hire_date"),
        (4, "negative_hourly_rate"),
        (5, "invalid_email"),
    ]
    fe = created[1]
    assert (fe.role_id, fe.hire_date, fe.is_bookable, fe.status) == (
        stylist.id,
        dt.date(2026, 2, 1),
        False,
        "active",
    )
    assert created[0].hourly_rate == 1200
    # One «record created» per record, never one for rows that did not go in.
    assert sorted(payload["id"] for name, _, payload in outbox()) == sorted(
        str(member.id) for member in created
    )


def test_a_batch_where_every_row_is_skipped_announces_nothing():
    result = run(
        "staff.member.bulk_create",
        BulkCreateIn(members=[{"first_name": " ", "last_name": "x"}]),
    )
    assert (result.created, len(result.skipped)) == ([], 1)
    assert outbox() == []


# staff.member.update (STAFF-F02, STAFF-F03)


def test_update_changes_only_what_was_sent_and_clears_with_null():
    stylist = make_role("Stylist")
    member = make_member(
        role=stylist, hire_date=dt.date(2026, 1, 15), phone="600", email="a@b.es"
    )

    detail = update(
        id=member.id,
        employee_number="E-7",
        color="#ff0000",
        booking_buffer=15,
        role_id=None,
        hire_date=None,
    )

    member.refresh_from_db()
    assert (member.employee_number, member.color, member.booking_buffer) == (
        "E-7",
        "#ff0000",
        15,
    )
    assert (member.role_id, member.hire_date, member.phone, member.email) == (
        None,
        None,
        "600",
        "a@b.es",
    )
    assert (detail.role_id, detail.hire_date) == (None, None)
    assert outbox() == [(events.MEMBER_UPDATED, "a", {"id": str(member.id)})]


def test_null_keeps_a_field_that_cannot_be_empty_and_an_unsent_role_stays():
    stylist = make_role("Stylist")
    member = make_member(role=stylist)
    update(id=member.id, first_name=None, phone="700")
    member.refresh_from_db()
    assert (member.first_name, member.role_id, member.phone) == (
        "Ana",
        stylist.id,
        "700",
    )


def test_update_by_name_and_the_role_by_name():
    barber = make_role("Barber")
    member = make_member("Ana", "López")
    update(member="Ana López", role="barber", is_bookable=False)
    member.refresh_from_db()
    assert (member.role_id, member.is_bookable) == (barber.id, False)


def test_update_without_changes_records_nothing():
    member = make_member()
    detail = update(id=member.id, first_name="Ana")
    assert detail.id == member.id and outbox() == []


def test_update_to_a_retired_role_keeps_the_previous_one():
    stylist = make_role("Stylist")
    member = make_member(role=stylist)
    with pytest.raises(InvalidPayload):
        update(id=member.id, role_id=make_role("Old", is_active=False).id)
    member.refresh_from_db()
    assert member.role_id == stylist.id and outbox() == []


def test_update_of_a_missing_or_terminated_record_is_not_found():
    gone = make_member(status=Member.Status.TERMINATED)
    for member_id in (gone.id, uuid.uuid7()):
        with pytest.raises(NotFound):
            update(id=member_id, phone="1")
    assert outbox() == []


def test_moving_another_record_onto_a_linked_user_is_refused(make_user):
    account = make_user("ana")
    holder = make_member("Ana", user=account)
    other = make_member("Bea")
    with pytest.raises(Conflict) as excinfo:
        update(id=other.id, user_id=account.id)
    assert excinfo.value.code == "staff.user_already_linked"
    # The holder may be edited and keep its own user.
    update(id=holder.id, user_id=account.id, phone="1")
    holder.refresh_from_db()
    assert holder.user_id == account.id


def test_unlinking_or_terminating_frees_the_user(make_user):
    account = make_user("ana")
    ana = make_member("Ana", user=account)
    update(id=ana.id, user_id=None)
    bea = make_member("Bea")
    update(id=bea.id, user_id=account.id)
    run("staff.member.terminate", TerminateIn(id=bea.id))
    assert create("Carla", user_id=account.id).user_id == account.id


def test_changing_pay_needs_the_pay_permission():
    member = make_member(hourly_rate=1000)
    clerk = {"staff.change_member", "staff.view"}
    with pytest.raises(PermissionDenied):
        get("staff.member.update")(
            ctx_for(permissions=clerk), MemberPatchIn(id=member.id, hourly_rate=2000)
        )
    member.refresh_from_db()
    assert member.hourly_rate == 1000


def test_setting_inactive_from_the_form_checks_live_time_off():
    member = make_member()
    make_time_off(member, today().isoformat(), status=TimeOff.Status.APPROVED)
    with pytest.raises(Conflict) as excinfo:
        update(id=member.id, status="inactive")
    assert excinfo.value.code == "staff.active_time_off"
    free = make_member("Bea")
    assert update(id=free.id, status="inactive").status == "inactive"
    # Back to work: active again; Bookable is the person's own switch.
    assert update(id=free.id, status="active").status == "active"


def test_a_manager_edits_but_an_employee_does_not():
    member = make_member()
    assert update(as_role="hub_manager", id=member.id, phone="1").phone == "1"
    with pytest.raises(PermissionDenied):
        update(as_role="hub_employee", id=member.id, phone="2")


# staff.member.deactivate (STAFF-F05)


def deactivate(role="hub_admin", **ref):
    return run("staff.member.deactivate", MemberRefIn(**ref), role)


def test_deactivate_takes_the_record_out_of_the_agenda():
    member = make_member(status=Member.Status.ON_LEAVE)
    detail = deactivate(id=member.id)
    member.refresh_from_db()
    assert (detail.status, member.status, member.is_bookable) == (
        "inactive",
        "inactive",
        False,
    )
    assert outbox() == [(events.MEMBER_DEACTIVATED, "a", {"id": str(member.id)})]


def test_deactivate_twice_is_refused():
    member = make_member(status=Member.Status.INACTIVE)
    with pytest.raises(Conflict) as excinfo:
        deactivate(member="Ana")
    assert excinfo.value.code == "staff.already_inactive"
    assert member.is_bookable and outbox() == []


@pytest.mark.parametrize("status", [TimeOff.Status.PENDING, TimeOff.Status.APPROVED])
def test_deactivate_is_refused_with_live_time_off(status):
    member = make_member()
    make_time_off(
        member,
        (today() - dt.timedelta(days=3)).isoformat(),
        today().isoformat(),
        status=status,
    )
    with pytest.raises(Conflict) as excinfo:
        deactivate(id=member.id)
    assert excinfo.value.code == "staff.active_time_off"
    member.refresh_from_db()
    assert member.status == "active" and outbox() == []


def test_finished_rejected_or_cancelled_time_off_does_not_block(frozen_now):
    frozen_now(LATE_EVENING_UTC)  # the business is already on the 19th
    member = make_member()
    make_time_off(member, "2026-08-10", "2026-08-18", status=TimeOff.Status.APPROVED)
    make_time_off(member, "2026-08-20", status=TimeOff.Status.REJECTED)
    make_time_off(member, "2026-08-21", status=TimeOff.Status.CANCELLED)
    assert deactivate(id=member.id).status == "inactive"


def test_only_the_owner_or_the_admin_deactivates():
    member = make_member()
    with pytest.raises(PermissionDenied):
        deactivate(role="hub_manager", id=member.id)


# staff.member.terminate (STAFF-F06)


def test_terminate_with_date_and_reason():
    member = make_member(status=Member.Status.INACTIVE)
    make_time_off(
        member, today().isoformat(), status=TimeOff.Status.APPROVED
    )  # does not stop it

    result = run(
        "staff.member.terminate",
        TerminateIn(
            id=member.id, termination_date=dt.date(2026, 8, 31), reason="moved abroad"
        ),
    )

    member.refresh_from_db()
    assert result.model_dump() == {
        "id": member.id,
        "termination_date": dt.date(2026, 8, 31),
    }
    assert (
        member.status,
        member.termination_date,
        member.termination_reason,
        member.is_bookable,
    ) == (
        "terminated",
        dt.date(2026, 8, 31),
        "moved abroad",
        False,
    )
    # The event never carries the reason.
    assert outbox() == [(events.MEMBER_TERMINATED, "a", {"id": str(member.id)})]


def test_terminate_without_a_date_stamps_the_business_day(frozen_now):
    frozen_now(LATE_EVENING_UTC)
    member = make_member()
    assert run(
        "staff.member.terminate", TerminateIn(member="Ana")
    ).termination_date == dt.date(2026, 8, 19)


def test_terminate_again_is_not_found_and_the_record_is_gone():
    member = make_member()
    run("staff.member.terminate", TerminateIn(id=member.id))
    OutboxEvent.objects.all().delete()
    with pytest.raises(NotFound):
        run("staff.member.terminate", TerminateIn(id=member.id))
    with pytest.raises(NotFound):
        run("staff.member.detail", MemberRefIn(id=member.id))
    assert outbox() == []


# staff.role.create and staff.role.update (STAFF-F04)


def test_create_a_role():
    role = run(
        "staff.role.create",
        RoleIn(name="Stylist", description="Cuts", color="#123456", order=3),
    )
    assert (
        role.name,
        role.description,
        role.color,
        role.order,
        role.member_count,
        role.is_active,
    ) == (
        "Stylist",
        "Cuts",
        "#123456",
        3,
        0,
        True,
    )
    assert outbox() == [(events.ROLE_CREATED, "a", {"id": str(role.id)})]


def test_a_role_name_is_not_repeated():
    make_role("Stylist")
    with pytest.raises(Conflict) as excinfo:
        run("staff.role.create", RoleIn(name="STYLIST"))
    assert excinfo.value.code == "staff.role_name_taken"
    assert Role.objects.count() == 1 and outbox() == []


def test_update_and_retire_a_role():
    role = make_role("Stylist")
    make_member(role=role)
    updated = run(
        "staff.role.update",
        RolePatchIn(id=role.id, name="Senior stylist", is_active=False),
    )
    assert (updated.name, updated.is_active, updated.member_count) == (
        "Senior stylist",
        False,
        1,
    )
    assert outbox() == [(events.ROLE_UPDATED, "a", {"id": str(role.id)})]


def test_role_update_rules():
    role, other = make_role("Stylist"), make_role("Barber")
    with pytest.raises(Conflict):
        run("staff.role.update", RolePatchIn(id=other.id, name="stylist"))
    run(
        "staff.role.update", RolePatchIn(id=role.id, name="Stylist")
    )  # no change, no event
    with pytest.raises(NotFound):
        run("staff.role.update", RolePatchIn(id=uuid.uuid7(), name="x"))
    assert outbox() == []


def test_an_employee_does_not_manage_roles():
    with pytest.raises(PermissionDenied):
        run("staff.role.create", RoleIn(name="x"), "hub_employee")


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
            "a",
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
            "a",
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
    assert run("staff.schedule.delete", ByIdIn(id=schedule.id)) == DeletedOut(
        id=schedule.id
    )
    assert not Schedule.objects.exists() and not ScheduleDay.objects.exists()
    assert names() == [events.SCHEDULE_UPDATED, events.SCHEDULE_DELETED]
    with pytest.raises(NotFound):
        run("staff.schedule.delete", ByIdIn(id=schedule.id))


def test_an_employee_does_not_manage_schedules():
    with pytest.raises(PermissionDenied):
        run(
            "staff.schedule.create",
            ScheduleIn(member_id=make_member().id, days=WEEK),
            "hub_employee",
        )


# staff.time_off.create (STAFF-F17)


def register(who=None, start="2026-10-12", end=None, as_role="hub_admin", **fields):
    """``who`` is the record; ``member="<name>"`` names it as the assistant would."""
    data = {"start_date": start, "end_date": end or start, **fields}
    if who is not None:
        data["member_id"] = who.id
    return run("staff.time_off.create", TimeOffIn(**data), as_role)


def test_register_a_pending_time_off():
    member = make_member()
    leave = register(
        member,
        "2026-10-12",
        "2026-10-14",
        leave_type="sick",
        reason="Flu",
        notes="Doctor's note",
    )
    row = TimeOff.objects.get()
    assert (leave.id, leave.status, leave.leave_type, leave.reason, leave.notes) == (
        row.id,
        "pending",
        "sick",
        "Flu",
        "Doctor's note",
    )
    # The event never carries the reason.
    assert outbox() == [
        (events.TIME_OFF_CREATED, "a", {"id": str(row.id), "member_id": str(member.id)})
    ]


def test_register_by_the_members_name_also_for_an_inactive_record():
    make_member("Ana", "López", status=Member.Status.INACTIVE)
    assert register(member="Ana López").member_name == "Ana López"


@pytest.mark.parametrize(
    ("existing", "status", "clashes"),
    [
        (
            ("2026-10-10", "2026-10-12", None),
            TimeOff.Status.PENDING,
            True,
        ),  # touching edge
        (("2026-10-14", "2026-10-20", None), TimeOff.Status.APPROVED, True),
        (("2026-10-01", "2026-10-11", None), TimeOff.Status.APPROVED, False),
        (("2026-10-12", "2026-10-12", None), TimeOff.Status.REJECTED, False),
        (("2026-10-12", "2026-10-12", None), TimeOff.Status.CANCELLED, False),
        (
            ("2026-10-12", "2026-10-12", ("09:00", "13:00")),
            TimeOff.Status.PENDING,
            True,
        ),  # part day vs whole
    ],
)
def test_a_new_whole_day_absence_must_not_overlap(existing, status, clashes):
    member = make_member()
    start, end, hours = existing
    make_time_off(member, start, end, hours=hours, status=status)
    if clashes:
        with pytest.raises(Conflict) as excinfo:
            register(member, "2026-10-12", "2026-10-14")
        assert excinfo.value.code == "staff.overlapping_time_off"
        assert TimeOff.objects.count() == 1 and outbox() == []
    else:
        assert register(member, "2026-10-12", "2026-10-14").status == "pending"


def test_a_morning_and_an_afternoon_off_the_same_day_do_not_clash():
    member = make_member()
    register(member, is_full_day=False, start_time="09:00", end_time="13:00")
    assert (
        register(member, is_full_day=False, start_time="15:00", end_time="18:00").status
        == "pending"
    )
    with pytest.raises(Conflict):
        register(member, is_full_day=False, start_time="12:00", end_time="16:00")


def test_another_members_time_off_does_not_clash():
    make_time_off(make_member("Bea"), "2026-10-12", status=TimeOff.Status.APPROVED)
    assert register(make_member("Ana")).status == "pending"


def test_time_off_for_a_missing_member_is_refused():
    with pytest.raises(NotFound):
        register(member="Nobody")
    with pytest.raises(NotFound):
        register(make_member(status=Member.Status.TERMINATED))
    assert outbox() == []


def test_an_employee_does_not_register_anybodys_time_off():
    with pytest.raises(PermissionDenied):
        register(make_member(), as_role="hub_employee")


# staff.time_off.request (STAFF-F24)


def request(actor, role="hub_employee", **fields):
    data = {"start_date": "2026-10-12", "end_date": "2026-10-12", **fields}
    return run("staff.time_off.request", TimeOffRequestIn(**data), role, actor=actor)


def test_an_employee_asks_for_their_own_time_off(make_user):
    me = make_user("ana", role="hub_employee")
    member = make_member(user=me)
    leave = request(me, reason="Wedding")
    assert (leave.member_id, leave.status, leave.reason) == (
        member.id,
        "pending",
        "Wedding",
    )
    assert outbox() == [
        (
            events.TIME_OFF_CREATED,
            "a",
            {"id": str(leave.id), "member_id": str(member.id)},
        )
    ]


def test_asking_without_a_linked_record_is_refused(make_user):
    for actor in (make_user("ana", role="hub_employee"), "system"):
        with pytest.raises(Conflict) as excinfo:
            request(actor)
        assert excinfo.value.code == "staff.no_member_record"
    assert not TimeOff.objects.exists()


def test_my_own_request_must_not_overlap_either(make_user):
    me = make_user("ana", role="hub_employee")
    make_time_off(make_member(user=me), "2026-10-12", status=TimeOff.Status.APPROVED)
    with pytest.raises(Conflict):
        request(me)


# staff.time_off.approve, reject and cancel (STAFF-F18, STAFF-F19)


def decide(action, leave, role="hub_admin", **ctx):
    return run(f"staff.time_off.{action}", ByIdIn(id=leave.id), role, **ctx)


def test_approve_stamps_who_and_when(make_user):
    boss = make_user("boss", first_name="Marta")
    member = make_member()
    leave = make_time_off(member, "2026-10-12")

    approved = decide("approve", leave, actor=boss)

    leave.refresh_from_db()
    assert (leave.status, leave.approved_by, approved.approved_by_name) == (
        "approved",
        boss,
        "Marta",
    )
    assert leave.approved_at is not None
    assert outbox() == [
        (
            events.TIME_OFF_APPROVED,
            "a",
            {"id": str(leave.id), "member_id": str(member.id)},
        )
    ]


def test_reject_a_pending_request():
    leave = make_time_off(make_member(), "2026-10-12")
    assert decide("reject", leave).status == "rejected"
    assert names() == [events.TIME_OFF_REJECTED]


@pytest.mark.parametrize(
    ("status", "action", "allowed"),
    [
        ("pending", "approve", True),
        ("pending", "reject", True),
        ("pending", "cancel", True),
        ("approved", "cancel", True),
        ("approved", "approve", False),
        ("approved", "reject", False),
        ("rejected", "approve", False),
        ("rejected", "cancel", False),
        ("cancelled", "approve", False),
        ("cancelled", "cancel", False),
    ],
)
def test_the_time_off_state_machine(status, action, allowed):
    leave = make_time_off(make_member(), "2026-10-12", status=status)
    if allowed:
        decide(action, leave)
    else:
        with pytest.raises(Conflict) as excinfo:
            decide(action, leave)
        assert excinfo.value.code == "staff.invalid_transition"
        assert outbox() == []


def test_approving_over_another_approved_absence_is_refused():
    member = make_member()
    make_time_off(member, "2026-10-12", status=TimeOff.Status.APPROVED)
    # Possible with old data or two requests at once: the request itself never counts.
    leave = TimeOff.objects.create(
        member=member, start_date=dt.date(2026, 10, 12), end_date=dt.date(2026, 10, 13)
    )
    with pytest.raises(Conflict) as excinfo:
        decide("approve", leave)
    assert (excinfo.value.code, excinfo.value.message) == (
        "staff.overlapping_time_off",
        "That staff member already has approved time off in those dates.",
    )
    other = make_time_off(make_member("Bea"), "2026-10-12")
    assert decide("approve", other).status == "approved"


def test_cancel_keeps_who_approved_it(make_user):
    boss = make_user("boss")
    leave = make_time_off(
        make_member(),
        "2026-10-12",
        status=TimeOff.Status.APPROVED,
        approved_by=boss,
        approved_at=timezone.now(),
    )
    cancelled = decide("cancel", leave)
    leave.refresh_from_db()
    assert (cancelled.status, leave.approved_by) == ("cancelled", boss)
    assert names() == [events.TIME_OFF_CANCELLED]


def test_an_employee_withdraws_only_their_own_pending_request(make_user):
    me = make_user("ana", role="hub_employee")
    mine = make_member("Ana", user=me)
    pending = make_time_off(mine, "2026-10-12")
    approved = make_time_off(mine, "2026-10-20", status=TimeOff.Status.APPROVED)
    others = make_time_off(make_member("Bea"), "2026-10-12")

    assert (
        decide("cancel", pending, role="hub_employee", actor=me).status == "cancelled"
    )
    for leave in (approved, others):
        with pytest.raises(PermissionDenied) as excinfo:
            decide("cancel", leave, role="hub_employee", actor=me)
        assert excinfo.value.message == "You can only cancel your own pending requests."
    with pytest.raises(PermissionDenied):
        decide("approve", others, role="hub_employee", actor=me)


def test_deciding_a_missing_request_is_not_found():
    gone = make_time_off(make_member(status=Member.Status.TERMINATED), "2026-10-12")
    for leave in (gone, TimeOff(id=uuid.uuid7())):
        with pytest.raises(NotFound):
            decide("approve", leave)


# staff.settings.update (STAFF-F22)


def test_the_first_save_creates_the_settings_with_the_defaults_for_the_rest():
    settings = run("staff.settings.update", SettingsIn(default_break_duration=30))
    assert settings.model_dump() == {
        "default_work_start": "09:00",
        "default_work_end": "18:00",
        "default_break_duration": 30,
    }
    assert StaffSettings.objects.count() == 1
    assert outbox() == [(events.SETTINGS_UPDATED, "a", {})]


def test_hours_are_stored_without_seconds_and_a_second_save_updates_the_same_row():
    run("staff.settings.update", SettingsIn(default_work_start="07:30:45"))
    settings = run("staff.settings.update", SettingsIn(default_break_duration=45))
    row = StaffSettings.objects.get()
    assert (
        row.default_work_start,
        row.default_break_duration,
        settings.default_work_start,
    ) == (dt.time(7, 30), 45, "07:30")


def test_saving_the_same_settings_announces_nothing():
    run("staff.settings.update", SettingsIn(default_break_duration=30))
    OutboxEvent.objects.all().delete()
    run("staff.settings.update", SettingsIn(default_break_duration=30))
    assert outbox() == []


def test_an_employee_does_not_change_the_settings():
    with pytest.raises(PermissionDenied):
        run("staff.settings.update", SettingsIn(default_break_duration=30), "hub_employee")


# The default working day proposes the week of a new schedule (STAFF-F13), and a schedule's day never
# crosses midnight: the working day ends after it starts and its break is shorter than the day.


def refused_settings(data, saved=None):
    if saved is not None:
        StaffSettings.objects.create(**saved)
    with pytest.raises(InvalidPayload) as excinfo:
        run("staff.settings.update", data)
    return excinfo.value.fields


def test_a_working_day_that_ends_before_it_starts_is_refused_under_its_end():
    assert refused_settings(SettingsIn(default_work_start="22:00", default_work_end="06:00")) == {
        "default_work_end": "The start time must be before the end time."
    }
    assert refused_settings(SettingsIn(default_work_end="09:00")) == {
        "default_work_end": "The start time must be before the end time."
    }
    assert not StaffSettings.objects.exists() and outbox() == []


def test_a_start_after_the_saved_end_is_refused_under_the_start():
    fields = refused_settings(
        SettingsIn(default_work_start="19:00"),
        saved={"default_work_start": dt.time(9), "default_work_end": dt.time(18)},
    )
    assert fields == {"default_work_start": "The start time must be before the end time."}
    assert StaffSettings.objects.get().default_work_start == dt.time(9)
    assert outbox() == []


def test_the_break_must_be_shorter_than_the_working_day():
    message = {"default_break_duration": "The break must fall inside the working hours."}
    assert refused_settings(SettingsIn(default_work_start="09:00", default_work_end="10:00", default_break_duration=60)) == message
    # A day shortened under the saved break: the break is what no longer fits.
    StaffSettings.objects.all().delete()
    assert refused_settings(SettingsIn(default_work_end="09:30"), saved={"default_break_duration": 30}) == message
    StaffSettings.objects.all().delete()
    settings = run(
        "staff.settings.update",
        SettingsIn(default_work_start="09:00", default_work_end="10:00", default_break_duration=59),
    )
    assert (settings.default_work_end, settings.default_break_duration) == ("10:00", 59)


# Notifications: after the COMMIT, on the channel of the command's scope only


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


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen):
    on_a, on_b = listen(A), listen(B)

    member_id = get("staff.member.create")(
        ctx_for(scope=B), MemberIn(first_name="Ana", last_name="López")
    ).id

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.MEMBER_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []

    # Positive control: the same listener of A does hear a command run in A.
    get("staff.member.update")(ctx_for(scope=A), MemberPatchIn(id=member_id, phone="1"))
    assert received(on_a, stop_after=1) == [
        (channel_for(A), {"events": [events.MEMBER_UPDATED]})
    ]
    assert received(on_b, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_command_notifies_nobody(listen):
    member = Member.objects.create(
        first_name="Ana", last_name="López", status=Member.Status.INACTIVE
    )
    on_b = listen(B)
    with pytest.raises(Conflict):
        get("staff.member.deactivate")(ctx_for(scope=B), MemberRefIn(id=member.id))
    assert received(on_b, timeout=QUIET) == []


# staff.member.bulk_create: the row's own problems, and the pay permission (review of 2026-10-14)


def test_a_badly_written_date_skips_only_its_row():
    rows = [
        {"first_name": "Ana", "last_name": "López", "hire_date": "2026-01-15T00:00"},
        {"first_name": "Bea", "last_name": "Ruiz", "hire_date": "2026-01-15"},
    ]
    result = run("staff.member.bulk_create", BulkCreateIn(members=rows))
    assert [(row.index, row.reason) for row in result.skipped] == [(0, "invalid_hire_date")]
    assert list(Member.objects.values_list("first_name", "hire_date")) == [("Bea", dt.date(2026, 1, 15))]


def test_pay_in_a_batch_needs_the_pay_permission():
    clerk = {"staff.add_member", "staff.view"}
    rows = [{"first_name": "Ana", "last_name": "López"}, {"first_name": "Bea", "last_name": "Ruiz", "hourly_rate": 1200}]
    with pytest.raises(PermissionDenied):
        get("staff.member.bulk_create")(ctx_for(permissions=clerk), BulkCreateIn(members=rows))
    assert not Member.objects.exists() and outbox() == []


# Two people at the same instant: the second waits for the first's lock, then decides on what it wrote


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


def _race(first, second):
    """Run ``first`` in a transaction kept open until ``second`` (another thread) is blocked on it.

    Returns the outcomes of both. ``second`` must wait (a lock), never decide blind on what ``first``
    has not committed yet.
    """
    done, release = threading.Event(), threading.Event()

    def held():
        with transaction.atomic():
            result = first()
            done.set()
            release.wait(5)
        return result

    holder, held_outcome = _in_thread(held)
    assert done.wait(5)
    waiter, outcome = _in_thread(second)
    waiter.join(QUIET)
    waited = waiter.is_alive()
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held_outcome, held_outcome
    assert waited, "the second call did not wait for the first one's lock"
    return outcome


def _register_in(member, start, end=None):
    data = TimeOffIn(member_id=member.id, start_date=start, end_date=end or start)
    return lambda: get("staff.time_off.create")(ctx_for(), data)


@pytest.mark.django_db(transaction=True)
def test_two_overlapping_requests_at_once_keep_one():
    member = make_member()
    outcome = _race(_register_in(member, "2026-10-12", "2026-10-14"), _register_in(member, "2026-10-14"))
    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert TimeOff.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_overlapping_requests_of_my_own_at_once_keep_one(make_user):
    me = make_user("ana", role="hub_employee")
    make_member(user=me)
    data = TimeOffRequestIn(start_date="2026-10-12", end_date="2026-10-12")

    def ask():
        return get("staff.time_off.request")(ctx_for("hub_employee", actor=me), data)

    outcome = _race(ask, ask)

    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert TimeOff.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_overlapping_approvals_at_once_keep_one():
    member = make_member()
    # Possible with old data: two pending requests over the same days.
    first = TimeOff.objects.create(member=member, start_date=dt.date(2026, 10, 12), end_date=dt.date(2026, 10, 13))
    second = TimeOff.objects.create(member=member, start_date=dt.date(2026, 10, 13), end_date=dt.date(2026, 10, 14))

    outcome = _race(
        lambda: get("staff.time_off.approve")(ctx_for(), ByIdIn(id=first.id)),
        lambda: get("staff.time_off.approve")(ctx_for(), ByIdIn(id=second.id)),
    )

    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert list(TimeOff.objects.order_by("start_date").values_list("status", flat=True)) == ["approved", "pending"]


@pytest.mark.django_db(transaction=True)
def test_an_employee_cannot_cancel_a_request_approved_while_they_were_cancelling(make_user):
    # STAFF-F19: an employee withdraws only a PENDING request of their own, judged on the locked row.
    me = make_user("ana", role="hub_employee")
    leave = make_time_off(make_member(user=me), "2026-10-12")

    outcome = _race(
        lambda: get("staff.time_off.approve")(ctx_for(), ByIdIn(id=leave.id)),
        lambda: get("staff.time_off.cancel")(ctx_for("hub_employee", actor=me), ByIdIn(id=leave.id)),
    )

    assert isinstance(outcome.get("error"), PermissionDenied)
    leave.refresh_from_db()
    assert leave.status == "approved"


@pytest.mark.django_db(transaction=True)
def test_a_record_terminated_while_approving_is_not_found():
    member = make_member()
    leave = make_time_off(member, "2026-10-12")

    outcome = _race(
        lambda: get("staff.member.terminate")(ctx_for(), TerminateIn(id=member.id)),
        lambda: get("staff.time_off.approve")(ctx_for(), ByIdIn(id=leave.id)),
    )

    assert isinstance(outcome.get("error"), NotFound), outcome
    leave.refresh_from_db()
    assert leave.status == "pending"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "command",
    [
        lambda schedule: get("staff.schedule.update")(ctx_for(), ScheduleUpdateIn(id=schedule.id, days=WEEK)),
        lambda schedule: get("staff.schedule.set_active")(ctx_for(), SetActiveIn(id=schedule.id, is_active=False)),
        lambda schedule: get("staff.schedule.delete")(ctx_for(), ByIdIn(id=schedule.id)),
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
