"""The writes on a staff member's record: add one, add several, change it, take it out of the agenda and end it.

A refused command leaves no trace: no row, no event.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.staff import events
from apps.staff.models import Member, TimeOff
from apps.staff.schemas.fields import MemberRefIn
from apps.staff.schemas.members import BulkCreateIn, MemberIn, MemberPatchIn, TerminateIn
from apps.staff.services import members

from .conftest import HUB_DB, LATE_EVENING_UTC, A, B, ctx_for, make_member, make_role, make_time_off, outbox, run, today

pytestmark = HUB_DB


def create(first="Ana", last="López", as_role="hub_admin", **fields):
    return run("staff.member.create", MemberIn(first_name=first, last_name=last, **fields), as_role)


def update(as_role="hub_admin", **fields):
    return run("staff.member.update", MemberPatchIn(**fields), as_role)


# staff.member.create (STAFF-F01, STAFF-F03)


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
    assert outbox() == [(events.MEMBER_CREATED, A.key, {"id": str(member.id)})]
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
    account = make_user("ana", host=A.key, role="hub_employee")
    assert create(user_id=account.person.id).user_id == account.person.id


def test_a_user_without_access_to_this_business_is_refused(make_user):
    stranger = make_user("bea", host=B.key)
    for user_id in (stranger.person.id, uuid.uuid4()):
        with pytest.raises(InvalidPayload) as excinfo:
            create(user_id=user_id)
        assert excinfo.value.fields == {
            "user_id": "That Hub user has no access to this business."
        }
    assert not Member.objects.exists()


def test_a_person_who_left_the_business_is_refused_though_their_membership_lingers(make_user):
    # The photo marks whoever is no longer in the business (base.hub_user.sync): their record no longer hangs from them.
    account = make_user("ana", host=A.key, role="hub_employee")
    account.person.is_active = False
    account.person.save()

    with pytest.raises(InvalidPayload) as excinfo:
        create(user_id=account.person.id)

    assert excinfo.value.fields == {"user_id": "That Hub user has no access to this business."}


def test_one_user_one_live_record_names_the_holder(make_user):
    account = make_user("ana")
    create("Ana", "López", user_id=account.person.id)
    OutboxEvent.objects.all().delete()

    with pytest.raises(Conflict) as excinfo:
        create("Bea", "Ruiz", user_id=account.person.id)

    assert (excinfo.value.status, excinfo.value.code) == (
        409,
        "staff.user_already_linked",
    )
    assert "Ana López" in excinfo.value.message
    assert Member.objects.count() == 1 and outbox() == []


def test_the_database_settles_two_links_at_once(make_user, monkeypatch):
    # user_link_race: both reads see nobody; the index stops the second write with the same answer.
    account = make_user("ana")
    create("Ana", user_id=account.person.id)
    monkeypatch.setattr(members, "_holder_of", lambda user_id, exclude=None: None)
    with pytest.raises(Conflict) as excinfo:
        create("Bea", user_id=account.person.id)
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
    assert outbox() == [(events.MEMBER_UPDATED, A.key, {"id": str(member.id)})]


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
    holder = make_member("Ana", user=account.person)
    other = make_member("Bea")
    with pytest.raises(Conflict) as excinfo:
        update(id=other.id, user_id=account.person.id)
    assert excinfo.value.code == "staff.user_already_linked"
    # The holder may be edited and keep its own user.
    update(id=holder.id, user_id=account.person.id, phone="1")
    holder.refresh_from_db()
    assert holder.user_id == account.person.id


def test_unlinking_or_terminating_frees_the_user(make_user):
    account = make_user("ana")
    ana = make_member("Ana", user=account.person)
    update(id=ana.id, user_id=None)
    bea = make_member("Bea")
    update(id=bea.id, user_id=account.person.id)
    run("staff.member.terminate", TerminateIn(id=bea.id))
    assert create("Carla", user_id=account.person.id).user_id == account.person.id


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
    assert outbox() == [(events.MEMBER_DEACTIVATED, A.key, {"id": str(member.id)})]


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
    assert outbox() == [(events.MEMBER_TERMINATED, A.key, {"id": str(member.id)})]


def test_terminate_without_a_date_stamps_the_business_day(frozen_now):
    frozen_now(LATE_EVENING_UTC)
    make_member()
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


# staff.member.bulk_create: the row's own problems, and the pay permission


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
