"""The writes on time off: register it, ask for one's own, and decide it. A refused command leaves no trace."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.staff import events
from apps.staff.models import Member, TimeOff
from apps.staff.schemas.time_off import TimeOffIn, TimeOffRefIn, TimeOffRequestIn
from apps.staff.services.time_off import reject_time_off

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, _race, ctx_for, make_member, make_time_off, names, outbox, run

pytestmark = HUB_DB


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
        (events.TIME_OFF_CREATED, A.key, {"id": str(row.id), "member_id": str(member.id)})
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
    with pytest.raises(PermissionDenied):
        reject_time_off(ctx_for("hub_employee"), TimeOffRefIn(id=make_time_off(make_member(), "2026-10-12").id))


# staff.time_off.request (STAFF-F24)


def request(actor, role="hub_employee", **fields):
    data = {"start_date": "2026-10-12", "end_date": "2026-10-12", **fields}
    return run("staff.time_off.request", TimeOffRequestIn(**data), role, actor=actor)


def test_an_employee_asks_for_their_own_time_off(make_user):
    me = make_user("ana", role="hub_employee")
    member = make_member(user=me.person)
    leave = request(me, reason="Wedding")
    assert (leave.member_id, leave.status, leave.reason) == (
        member.id,
        "pending",
        "Wedding",
    )
    assert outbox() == [
        (
            events.TIME_OFF_CREATED,
            A.key,
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
    make_time_off(make_member(user=me.person), "2026-10-12", status=TimeOff.Status.APPROVED)
    with pytest.raises(Conflict):
        request(me)


# staff.time_off.approve, reject and cancel (STAFF-F18, STAFF-F19)


def decide(action, leave, role="hub_admin", **ctx):
    return run(f"staff.time_off.{action}", TimeOffRefIn(id=leave.id), role, **ctx)


def test_approve_stamps_who_and_when(make_user):
    boss = make_user("boss", first_name="Marta")
    member = make_member()
    leave = make_time_off(member, "2026-10-12")

    approved = decide("approve", leave, actor=boss)

    leave.refresh_from_db()
    assert (leave.status, leave.approved_by, approved.approved_by_name) == (
        "approved",
        boss.person,
        "Marta",
    )
    assert leave.approved_at is not None
    assert outbox() == [
        (
            events.TIME_OFF_APPROVED,
            A.key,
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


def test_whoever_approves_before_their_person_exists_signs_it_all_the_same(django_user_model):
    # A session opened before the business's database knew them: their first write makes their person.
    boss = django_user_model.objects.create_user(username="saas:9", first_name="Marta")
    leave = make_time_off(make_member(), "2026-10-12")

    decide("approve", leave, actor=boss)

    leave.refresh_from_db()
    assert (leave.approved_by.username, leave.approved_by.name) == ("saas:9", "Marta")


def test_cancel_keeps_who_approved_it(make_user):
    boss = make_user("boss")
    leave = make_time_off(
        make_member(),
        "2026-10-12",
        status=TimeOff.Status.APPROVED,
        approved_by=boss.person,
        approved_at=timezone.now(),
    )
    cancelled = decide("cancel", leave)
    leave.refresh_from_db()
    assert (cancelled.status, leave.approved_by) == ("cancelled", boss.person)
    assert names() == [events.TIME_OFF_CANCELLED]


def test_an_employee_withdraws_only_their_own_pending_request(make_user):
    me = make_user("ana", role="hub_employee")
    mine = make_member("Ana", user=me.person)
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


def _register_in(member, start, end=None):
    data = TimeOffIn(member_id=member.id, start_date=start, end_date=end or start)
    return lambda: get("staff.time_off.create")(ctx_for(), data)


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_overlapping_requests_at_once_keep_one():
    member = make_member()
    outcome = _race(_register_in(member, "2026-10-12", "2026-10-14"), _register_in(member, "2026-10-14"))
    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert TimeOff.objects.count() == 1


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_overlapping_requests_of_my_own_at_once_keep_one(make_user):
    me = make_user("ana", role="hub_employee")
    make_member(user=me.person)
    data = TimeOffRequestIn(start_date="2026-10-12", end_date="2026-10-12")

    def ask():
        return get("staff.time_off.request")(ctx_for("hub_employee", actor=me), data)

    outcome = _race(ask, ask)

    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert TimeOff.objects.count() == 1


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_two_overlapping_approvals_at_once_keep_one():
    member = make_member()
    # Possible with old data: two pending requests over the same days.
    first = TimeOff.objects.create(member=member, start_date=dt.date(2026, 10, 12), end_date=dt.date(2026, 10, 13))
    second = TimeOff.objects.create(member=member, start_date=dt.date(2026, 10, 13), end_date=dt.date(2026, 10, 14))

    outcome = _race(
        lambda: get("staff.time_off.approve")(ctx_for(), TimeOffRefIn(id=first.id)),
        lambda: get("staff.time_off.approve")(ctx_for(), TimeOffRefIn(id=second.id)),
    )

    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "staff.overlapping_time_off"
    assert list(TimeOff.objects.order_by("start_date").values_list("status", flat=True)) == ["approved", "pending"]


@HUB_DB_COMMITTED
@pytest.mark.usefixtures("plan_with_room")
def test_an_employee_cannot_cancel_a_request_approved_while_they_were_cancelling(make_user):
    # STAFF-F19: an employee withdraws only a PENDING request of their own, judged on the locked row.
    me = make_user("ana", role="hub_employee")
    leave = make_time_off(make_member(user=me.person), "2026-10-12")

    outcome = _race(
        lambda: get("staff.time_off.approve")(ctx_for(), TimeOffRefIn(id=leave.id)),
        lambda: get("staff.time_off.cancel")(ctx_for("hub_employee", actor=me), TimeOffRefIn(id=leave.id)),
    )

    assert isinstance(outcome.get("error"), PermissionDenied)
    leave.refresh_from_db()
    assert leave.status == "approved"
