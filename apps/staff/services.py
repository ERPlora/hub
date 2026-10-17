"""Write operations of the staff app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). Every write on a
staff member locks the member's row first, so two requests on the same person never interleave
(two time-off requests at once cannot both slip past the overlap check). Events carry ids only.
"""

import datetime as dt
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.staff import events
from apps.staff.models import (
    Member,
    Role,
    Schedule,
    ScheduleDay,
    StaffSettings,
    TimeOff,
)
from apps.staff.queries import (
    LIVE_TIME_OFF,
    ROLE_NOT_FOUND,
    SCHEDULE_NOT_FOUND,
    TIME_OFF_NOT_FOUND,
    actor_user_id,
    business_today,
    load_member,
    load_role,
    load_schedule,
    load_time_off,
    overlapping_time_off,
    resolve_member,
    settings_out,
)
from apps.staff.schemas import (
    SCHEDULE_RANGE,
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
    TimeOffFieldsIn,
    TimeOffIn,
    TimeOffRequestIn,
)
from base.models import Membership

ROLE_UNAVAILABLE = _(
    "That role is not available: it does not exist in this business, or it has been deleted or retired."
)
ROLE_NAME_TAKEN = _("A role with that name already exists.")
USER_NOT_IN_BUSINESS = _("That Hub user has no access to this business.")
USER_ALREADY_LINKED = _(
    "That Hub user is already linked to %(name)s. A Hub user can belong to only one staff member: unlink it "
    "there first, or pick another user."
)
ALREADY_INACTIVE = _("That staff member is already inactive.")
ACTIVE_TIME_OFF = _(
    "That staff member has pending or approved time off that has not ended yet. Resolve it first."
)
OVERLAPPING_TIME_OFF = _(
    "That staff member already has pending or approved time off in those dates."
)
APPROVED_OVERLAP = _("That staff member already has approved time off in those dates.")
INVALID_TRANSITION = _(
    "That time-off request cannot change to that status from its current one."
)
NO_MEMBER_RECORD = _(
    "Your user is not linked to any staff member: ask a manager to link it."
)
OWN_PENDING_ONLY = _("You can only cancel your own pending requests.")
DEFAULT_SCHEDULE_NAME = _("Regular schedule")

VIEW_COMPENSATION = "staff.view_compensation"
MANAGE_TIME_OFF = "staff.manage_time_off"
#: The fields of a record that only the pay permission writes.
PAY_FIELDS = ("hourly_rate", "commission_rate", "notes")
#: Fields a ``null`` clears in staff.member.update; any other ``null`` leaves the field as it is.
CLEARABLE = ("role_id", "user_id", "hire_date")
USER_UNIQUE = "staff_member_user_unique"
ROLE_UNIQUE = "staff_role_name_unique"
#: The moves a time-off request may make (Factorial, Personio, BambooHR, Deputy).
TRANSITIONS = {
    "approve": (
        {TimeOff.Status.PENDING},
        TimeOff.Status.APPROVED,
        events.TIME_OFF_APPROVED,
    ),
    "reject": (
        {TimeOff.Status.PENDING},
        TimeOff.Status.REJECTED,
        events.TIME_OFF_REJECTED,
    ),
    "cancel": (
        {TimeOff.Status.PENDING, TimeOff.Status.APPROVED},
        TimeOff.Status.CANCELLED,
        events.TIME_OFF_CANCELLED,
    ),
}


# --- Members ---------------------------------------------------------------------------------------


@operation(
    "staff.member.create",
    kind="command",
    permission="staff.add_member",
    input=MemberIn,
    output=MemberDetailOut,
    expose_api=True,
    ai={
        "description": "Adds a staff member (a person who works in the business).",
        "risk": "normal",
    },
)
def create_member(ctx: OperationContext, data: MemberIn) -> Member | None:
    """STAFF-F01: born active unless told otherwise; the role and the user are checked first."""
    _require_pay_permission(ctx, data.model_fields_set)
    fields = data.model_dump(exclude={"role"})
    fields["role_id"] = _role_for(data.role_id, data.role)
    _check_user(ctx, data.user_id)
    member = Member(**fields)
    _save(member)
    record_event(ctx, events.MEMBER_CREATED, {"id": str(member.id)})
    return load_member(member.id)


@operation(
    "staff.member.bulk_create",
    kind="command",
    permission="staff.add_member",
    input=BulkCreateIn,
    output=BulkCreatedOut,
    ai={
        "description": "Adds several staff members at once (up to 100); a row with a problem is skipped "
        "with its reason and the rest go in.",
        "risk": "normal",
    },
)
def bulk_create_members(ctx: OperationContext, data: BulkCreateIn) -> dict:
    """STAFF-F07: tolerant per row, never silent; one «record created» per record that went in."""
    if any(row.hourly_rate > 0 for row in data.members):
        _require_pay_permission(ctx, {"hourly_rate"})
    created, skipped = [], []
    for index, row in enumerate(data.members):
        reason, fields = _bulk_row(row)
        if reason:
            skipped.append({"index": index, "reason": reason})
            continue
        member = Member.objects.create(**fields)
        record_event(ctx, events.MEMBER_CREATED, {"id": str(member.id)})
        created.append(member.id)
    return {"created": created, "skipped": skipped}


def _bulk_row(row: Any) -> tuple[str | None, dict]:
    """``(reason, None)`` for a row to skip, ``(None, fields)`` for one to create."""
    if not row.first_name or not row.last_name:
        return "name_required", {}
    if row.email:
        try:
            validate_email(row.email)
        except DjangoValidationError:
            return "invalid_email", {}
    hire_date = None
    if row.hire_date:
        try:
            hire_date = dt.date.fromisoformat(row.hire_date)
        except ValueError:
            return "invalid_hire_date", {}
    if row.hourly_rate < 0:
        return "negative_hourly_rate", {}
    role_id = None
    if row.role_id is not None or row.role:
        role_id = _active_role_id(row.role_id, row.role)
        if role_id is None:
            return "role_not_found", {}
    fields = row.model_dump(exclude={"role", "role_id", "hire_date"})
    return None, {**fields, "role_id": role_id, "hire_date": hire_date}


@operation(
    "staff.member.update",
    kind="command",
    permission="staff.change_member",
    input=MemberPatchIn,
    output=MemberDetailOut,
    expose_api=True,
    ai={
        "description": "Changes the details of a staff member, named by id or by name (only what is sent; "
        "it can change their pay, role and linked user).",
        "risk": "high",
    },
)
def update_member(ctx: OperationContext, data: MemberPatchIn) -> Member | None:
    """STAFF-F02: only what was sent; ``null`` clears the role, the user and the hire date."""
    member = resolve_member(data.id, data.member, lock=True)
    sent = data.model_dump(exclude_unset=True, exclude={"id", "member", "role"})
    sent = {
        field: value
        for field, value in sent.items()
        if value is not None or field in CLEARABLE
    }
    _require_pay_permission(ctx, sent)
    if data.role is not None:
        sent["role_id"] = _role_for(None, data.role)
    elif sent.get("role_id") is not None and sent["role_id"] != member.role_id:
        sent["role_id"] = _role_for(sent["role_id"], None)
    if sent.get("user_id") is not None and sent["user_id"] != member.user_id:
        _check_user(ctx, sent["user_id"], exclude=member.id)
    changes = {
        field: value for field, value in sent.items() if getattr(member, field) != value
    }
    if changes.get("status") == Member.Status.INACTIVE:
        _refuse_live_time_off(member)
    if changes:
        for field, value in changes.items():
            setattr(member, field, value)
        _save(member, update_fields=[*changes, "updated_at"])
        record_event(ctx, events.MEMBER_UPDATED, {"id": str(member.id)})
    return load_member(member.id)


@operation(
    "staff.member.deactivate",
    kind="command",
    permission="staff.delete_member",
    input=MemberRefIn,
    output=MemberDetailOut,
    ai={
        "description": "Deactivates a staff member (named by id or by name) without deleting anything: "
        "they stop being bookable.",
        "risk": "high",
    },
)
def deactivate_member(ctx: OperationContext, data: MemberRefIn) -> Member | None:
    """STAFF-F05: refused when already inactive or with time off that has not ended yet."""
    member = resolve_member(data.id, data.member, lock=True)
    if member.status == Member.Status.INACTIVE:
        raise Conflict(str(ALREADY_INACTIVE), code="staff.already_inactive")
    _refuse_live_time_off(member)
    member.status, member.is_bookable = Member.Status.INACTIVE, False
    member.save(update_fields=["status", "is_bookable", "updated_at"])
    record_event(ctx, events.MEMBER_DEACTIVATED, {"id": str(member.id)})
    return load_member(member.id)


@operation(
    "staff.member.terminate",
    kind="command",
    permission="staff.delete_member",
    input=TerminateIn,
    output=TerminatedOut,
    ai={
        "description": "Terminates a staff member (named by id or by name) for good: stamps the last day "
        "(today by default) and the reason, frees their user and removes them from the team.",
        "risk": "high",
    },
)
def terminate_member(ctx: OperationContext, data: TerminateIn) -> dict:
    """STAFF-F06: the only road to ``terminated``; irreversible, and it frees the linked user."""
    member = resolve_member(data.id, data.member, lock=True)
    member.status, member.is_bookable = Member.Status.TERMINATED, False
    member.termination_date = data.termination_date or business_today()
    member.termination_reason = data.reason
    member.save(
        update_fields=[
            "status",
            "is_bookable",
            "termination_date",
            "termination_reason",
            "updated_at",
        ]
    )
    record_event(ctx, events.MEMBER_TERMINATED, {"id": str(member.id)})
    return {"id": member.id, "termination_date": member.termination_date}


def _require_pay_permission(ctx: OperationContext, fields: Any) -> None:
    if not ctx.has(VIEW_COMPENSATION) and any(field in fields for field in PAY_FIELDS):
        raise PermissionDenied(
            gettext("Permission “%(permission)s” is required.")
            % {"permission": VIEW_COMPENSATION}
        )


def _active_role_id(role_id: UUID | None, name: str | None) -> UUID | None:
    roles = Role.objects.filter(is_active=True)
    role = (
        roles.filter(pk=role_id).first()
        if role_id is not None
        else roles.filter(name__iexact=name).first()
    )
    return role.id if role else None


def _role_for(role_id: UUID | None, name: str | None) -> UUID | None:
    """The id of an active role given by id or by name; 422 on that field when there is none."""
    if role_id is None and not name:
        return None
    found = _active_role_id(role_id, name)
    if found is None:
        field = "role_id" if role_id is not None else "role"
        raise InvalidPayload(
            str(ROLE_UNAVAILABLE), fields={field: str(ROLE_UNAVAILABLE)}
        )
    return found


def _check_user(
    ctx: OperationContext, user_id: int | None, exclude: UUID | None = None
) -> None:
    """A user may hang a record when it has access to this business and no other live record."""
    if user_id is None:
        return
    # Phase 1: «access» is a Membership on the scope's host; phase 2 checks the hub's own users.
    if not Membership.objects.filter(user_id=user_id, host=ctx.scope.key).exists():
        raise InvalidPayload(
            str(USER_NOT_IN_BUSINESS), fields={"user_id": str(USER_NOT_IN_BUSINESS)}
        )
    holder = _holder_of(user_id, exclude=exclude)
    if holder is not None:
        raise _already_linked(holder.full_name)


def _holder_of(user_id: int, exclude: UUID | None = None) -> Member | None:
    holders = Member.objects.exclude(status=Member.Status.TERMINATED).filter(
        user_id=user_id
    )
    if exclude is not None:
        holders = holders.exclude(pk=exclude)
    return holders.first()


def _already_linked(name: str) -> Conflict:
    return Conflict(
        str(USER_ALREADY_LINKED) % {"name": name}, code="staff.user_already_linked"
    )


def _save(member: Member, **options: Any) -> None:
    """Save, turning the race of two links of one user (the database's unique index) into the 409."""
    try:
        with transaction.atomic():
            member.save(**options)
    except IntegrityError as error:
        if USER_UNIQUE not in str(error):
            raise
        holder = _holder_of(member.user_id, exclude=member.id)
        raise _already_linked(holder.full_name if holder else "") from None


def _refuse_live_time_off(member: Member) -> None:
    """Deactivate's guard: pending or approved time off that has not ended by today (the business's)."""
    if member.time_off.filter(
        status__in=LIVE_TIME_OFF, end_date__gte=business_today()
    ).exists():
        raise Conflict(str(ACTIVE_TIME_OFF), code="staff.active_time_off")


def lock_members(ids) -> list[UUID]:
    """Locks the records ``ids`` (terminated ones too) in id order; the ids of those still there.

    Every write on a person locks their record before what hangs from it (their schedules, their time
    off, what other apps keep about them), and so does the Hub admin's «Delete» (admin.py) before Django
    deletes all that and then the record: the other way round, each waited for the other.
    """
    rows = Member.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


# --- Roles -----------------------------------------------------------------------------------------


@operation(
    "staff.role.create",
    kind="command",
    permission="staff.manage_settings",
    input=RoleIn,
    output=RoleOut,
    ai={
        "description": "Creates a role of the business (a catalogue label such as stylist; it grants no "
        "permission).",
        "risk": "normal",
    },
)
def create_role(ctx: OperationContext, data: RoleIn) -> Role | None:
    role = Role(**data.model_dump())
    _save_role(role)
    record_event(ctx, events.ROLE_CREATED, {"id": str(role.id)})
    return load_role(role.id)


@operation(
    "staff.role.update",
    kind="command",
    permission="staff.manage_settings",
    input=RolePatchIn,
    output=RoleOut,
    ai={
        "description": "Changes a role (name, description, colour, order) or retires it (is_active false) "
        "so it is no longer offered.",
        "risk": "normal",
    },
)
def update_role(ctx: OperationContext, data: RolePatchIn) -> Role | None:
    role = Role.objects.select_for_update().filter(pk=data.id).first()
    if role is None:
        raise NotFound(str(ROLE_NOT_FOUND))
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
    changes = {
        field: value for field, value in sent.items() if getattr(role, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(role, field, value)
        _save_role(role, update_fields=[*changes, "updated_at"])
        record_event(ctx, events.ROLE_UPDATED, {"id": str(role.id)})
    return load_role(role.id)


def _save_role(role: Role, **options: Any) -> None:
    try:
        with transaction.atomic():
            role.save(**options)
    except IntegrityError as error:
        if ROLE_UNIQUE not in str(error):
            raise
        raise Conflict(str(ROLE_NAME_TAKEN), code="staff.role_name_taken") from None


# --- Schedules -------------------------------------------------------------------------------------


@operation(
    "staff.schedule.create",
    kind="command",
    permission="staff.manage_settings",
    input=ScheduleIn,
    output=ScheduleOut,
    ai={
        "description": "Creates a weekly work schedule for a staff member (by id or by name), with the "
        "hours and break of each working day.",
        "risk": "normal",
    },
)
def create_schedule(ctx: OperationContext, data: ScheduleIn) -> Schedule | None:
    """STAFF-F13: a new default schedule demotes the member's others in the same transaction."""
    member = resolve_member(data.member_id, data.member, lock=True)
    if data.is_default:
        member.schedules.filter(is_default=True).update(is_default=False)
    schedule = Schedule.objects.create(
        member=member,
        name=data.name or str(DEFAULT_SCHEDULE_NAME),
        is_default=data.is_default,
        effective_from=data.effective_from,
        effective_until=data.effective_until,
    )
    _write_week(schedule, data.days)
    record_event(
        ctx,
        events.SCHEDULE_CREATED,
        {"id": str(schedule.id), "member_id": str(member.id)},
    )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.update",
    kind="command",
    permission="staff.manage_settings",
    input=ScheduleUpdateIn,
    output=ScheduleOut,
    ai={
        "description": "Edits a work schedule (name, validity, default) and replaces its whole week of "
        "working hours.",
        "risk": "normal",
    },
)
def update_schedule(ctx: OperationContext, data: ScheduleUpdateIn) -> Schedule | None:
    """STAFF-F14: what is not sent is kept, ``null`` clears a date, and the week is replaced."""
    schedule = _locked_schedule(data.id)
    sent = data.model_dump(exclude_unset=True, exclude={"id", "days"})
    if "name" in sent:
        sent["name"] = sent["name"] or str(DEFAULT_SCHEDULE_NAME)
    if sent.get("is_default") is None:
        sent.pop("is_default", None)
    for field, value in sent.items():
        setattr(schedule, field, value)
    if (
        schedule.effective_from
        and schedule.effective_until
        and schedule.effective_until < schedule.effective_from
    ):
        raise InvalidPayload(
            str(SCHEDULE_RANGE), fields={"effective_until": str(SCHEDULE_RANGE)}
        )
    if schedule.is_default:
        Schedule.objects.filter(member_id=schedule.member_id, is_default=True).exclude(
            pk=schedule.pk
        ).update(is_default=False)
    schedule.save()
    schedule.days.all().delete()
    _write_week(schedule, data.days)
    record_event(
        ctx,
        events.SCHEDULE_UPDATED,
        {"id": str(schedule.id), "member_id": str(schedule.member_id)},
    )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.set_active",
    kind="command",
    permission="staff.manage_settings",
    input=SetActiveIn,
    output=ScheduleOut,
    ai={
        "description": "Activates or deactivates a work schedule; an inactive schedule never governs "
        "availability.",
        "risk": "normal",
    },
)
def set_schedule_active(ctx: OperationContext, data: SetActiveIn) -> Schedule | None:
    """STAFF-F15; no change, no event."""
    schedule = _locked_schedule(data.id)
    if schedule.is_active != data.is_active:
        schedule.is_active = data.is_active
        schedule.save(update_fields=["is_active", "updated_at"])
        record_event(
            ctx,
            events.SCHEDULE_UPDATED,
            {"id": str(schedule.id), "member_id": str(schedule.member_id)},
        )
    return load_schedule(schedule.id)


@operation(
    "staff.schedule.delete",
    kind="command",
    permission="staff.manage_settings",
    input=ByIdIn,
    output=DeletedOut,
    ai={
        "description": "Deletes a work schedule and its working hours; they stop counting for availability.",
        "risk": "high",
    },
)
def delete_schedule(ctx: OperationContext, data: ByIdIn) -> dict:
    """STAFF-F15: deleting the default one does not make another one the default."""
    schedule = _locked_schedule(data.id)
    member_id = schedule.member_id
    schedule.delete()
    record_event(
        ctx, events.SCHEDULE_DELETED, {"id": str(data.id), "member_id": str(member_id)}
    )
    return {"id": data.id}


def _locked_schedule(schedule_id: UUID) -> Schedule:
    """The schedule with its member's row and its own row locked (the default flag is per member).

    The member is locked first and must still be live once locked: one terminated meanwhile (its
    termination held the lock) is ``NotFound``, never a write on a record that is gone.
    """
    member_id = Schedule.objects.filter(pk=schedule_id).values_list("member_id", flat=True).first()
    if member_id is None or _locked_live_member(member_id) is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    schedule = Schedule.objects.select_for_update().filter(pk=schedule_id).first()
    if schedule is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    return schedule


def _locked_live_member(member_id: UUID) -> Member | None:
    """The member's row locked until the end of the command, if it is still not terminated once locked."""
    return Member.objects.select_for_update().exclude(status=Member.Status.TERMINATED).filter(pk=member_id).first()


def _write_week(schedule: Schedule, days: list) -> None:
    """Only the working days are stored: a weekday missing is a day off."""
    ScheduleDay.objects.bulk_create(
        ScheduleDay(
            schedule=schedule,
            weekday=day.weekday,
            start_time=day.start_time,
            end_time=day.end_time,
            break_start=day.break_start,
            break_end=day.break_end,
        )
        for day in days
        if day.is_working
    )


# --- Time off --------------------------------------------------------------------------------------


@operation(
    "staff.time_off.create",
    kind="command",
    permission="staff.manage_time_off",
    input=TimeOffIn,
    output=TimeOffDetailOut,
    ai={
        "description": "Registers a time-off request (vacation, sick leave, personal, training or other) "
        "for a staff member, by id or by name; it starts pending.",
        "risk": "normal",
    },
)
def create_time_off(ctx: OperationContext, data: TimeOffIn) -> TimeOff | None:
    """STAFF-F17: for any record that is not terminated; never over another pending or approved one."""
    member = resolve_member(data.member_id, data.member, lock=True)
    return _register_time_off(ctx, member, data)


@operation(
    "staff.time_off.request",
    kind="command",
    permission="staff.request_time_off",
    input=TimeOffRequestIn,
    output=TimeOffDetailOut,
    ai={
        "description": "Asks for time off for the current user (their own staff record); it starts pending.",
        "risk": "normal",
    },
)
def request_time_off(ctx: OperationContext, data: TimeOffRequestIn) -> TimeOff | None:
    """STAFF-F24: the caller's own record, by their linked user."""
    user_id = actor_user_id(ctx)
    member = None
    if user_id is not None:
        member = (
            Member.objects.select_for_update()
            .exclude(status=Member.Status.TERMINATED)
            .filter(user_id=user_id)
            .first()
        )
    if member is None:
        raise Conflict(str(NO_MEMBER_RECORD), code="staff.no_member_record")
    return _register_time_off(ctx, member, data)


def _register_time_off(
    ctx: OperationContext, member: Member, data: TimeOffFieldsIn
) -> TimeOff | None:
    hours = (None, None) if data.is_full_day else (data.start_time, data.end_time)
    if overlapping_time_off(member, data.start_date, data.end_date, *hours).exists():
        raise Conflict(str(OVERLAPPING_TIME_OFF), code="staff.overlapping_time_off")
    time_off = TimeOff.objects.create(
        member=member,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        is_full_day=data.is_full_day,
        start_time=hours[0],
        end_time=hours[1],
        reason=data.reason,
        notes=data.notes,
    )
    record_event(
        ctx,
        events.TIME_OFF_CREATED,
        {"id": str(time_off.id), "member_id": str(member.id)},
    )
    return load_time_off(time_off.id)


@operation(
    "staff.time_off.approve",
    kind="command",
    permission="staff.manage_time_off",
    input=ByIdIn,
    output=TimeOffDetailOut,
    ai={
        "description": "Approves a pending time-off request: its hours leave the person's availability.",
        "risk": "normal",
    },
)
def approve_time_off(ctx: OperationContext, data: ByIdIn) -> TimeOff | None:
    """STAFF-F18: refused over another approved absence of the same person; stamps who and when."""
    time_off = _move(data.id, "approve")
    hours = (
        (None, None)
        if time_off.is_full_day
        else (time_off.start_time, time_off.end_time)
    )
    clashes = overlapping_time_off(
        time_off.member,
        time_off.start_date,
        time_off.end_date,
        *hours,
        statuses=(TimeOff.Status.APPROVED,),
        exclude_id=time_off.id,
    )
    if clashes.exists():
        raise Conflict(str(APPROVED_OVERLAP), code="staff.overlapping_time_off")
    time_off.approved_by_id = actor_user_id(ctx)
    time_off.approved_at = timezone.now()
    return _finish_move(ctx, time_off, "approve", ["approved_by", "approved_at"])


@operation(
    "staff.time_off.reject",
    kind="command",
    permission="staff.manage_time_off",
    input=ByIdIn,
    output=TimeOffDetailOut,
    ai={"description": "Rejects a pending time-off request.", "risk": "normal"},
)
def reject_time_off(ctx: OperationContext, data: ByIdIn) -> TimeOff | None:
    """STAFF-F18."""
    return _finish_move(ctx, _move(data.id, "reject"), "reject")


@operation(
    "staff.time_off.cancel",
    kind="command",
    permission="staff.request_time_off",
    input=ByIdIn,
    output=TimeOffDetailOut,
    ai={
        "description": "Cancels a pending or approved time-off request (an employee may only withdraw their "
        "own pending one).",
        "risk": "normal",
    },
)
def cancel_time_off(ctx: OperationContext, data: ByIdIn) -> TimeOff | None:
    """STAFF-F19: final; keeps who approved it. Without manage rights, only one's own pending request.

    Judged on the locked row: a request approved while the employee was cancelling it is refused.
    """
    time_off = _locked_time_off(data.id)
    if not ctx.has(MANAGE_TIME_OFF):
        user_id = actor_user_id(ctx)
        # One answer for someone else's request and for one's own that is no longer pending.
        if user_id is None or time_off.member.user_id != user_id or time_off.status != TimeOff.Status.PENDING:
            raise PermissionDenied(str(OWN_PENDING_ONLY))
    return _finish_move(ctx, _check_move(time_off, "cancel"), "cancel")


def _move(time_off_id: UUID, action: str) -> TimeOff:
    """The request locked (``_locked_time_off``); 409 if ``action`` is not allowed from its status."""
    return _check_move(_locked_time_off(time_off_id), action)


def _locked_time_off(time_off_id: UUID) -> TimeOff:
    """The request with its member's row and its own row locked, the member first.

    Locking the member serialises every write on that person (two approvals of overlapping
    requests, a cancellation against an approval). A member terminated meanwhile is ``NotFound``.
    """
    member_id = TimeOff.objects.filter(pk=time_off_id).values_list("member_id", flat=True).first()
    member = None if member_id is None else _locked_live_member(member_id)
    time_off = None if member is None else TimeOff.objects.select_for_update().filter(pk=time_off_id).first()
    if time_off is None:
        raise NotFound(str(TIME_OFF_NOT_FOUND))
    time_off.member = member
    return time_off


def _check_move(time_off: TimeOff, action: str) -> TimeOff:
    allowed_from, _, _ = TRANSITIONS[action]
    if time_off.status not in allowed_from:
        raise Conflict(str(INVALID_TRANSITION), code="staff.invalid_transition")
    return time_off


def _finish_move(
    ctx: OperationContext,
    time_off: TimeOff,
    action: str,
    extra: list[str] | None = None,
) -> TimeOff | None:
    _, status, event = TRANSITIONS[action]
    time_off.status = status
    time_off.save(update_fields=["status", *(extra or []), "updated_at"])
    record_event(
        ctx, event, {"id": str(time_off.id), "member_id": str(time_off.member_id)}
    )
    return load_time_off(time_off.id)


# --- Settings --------------------------------------------------------------------------------------


@operation(
    "staff.settings.update",
    kind="command",
    permission="staff.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    ai={
        "description": "Changes the settings of the staff app (working day, booking notice, limits and "
        "notices); only what is sent.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    """STAFF-F22: the first save creates the row; hours are stored without seconds."""
    row = StaffSettings.objects.select_for_update().first()
    created = False
    if row is None:
        row, created = StaffSettings.objects.get_or_create(slot=1)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    for field in ("default_work_start", "default_work_end"):
        if field in sent:
            sent[field] = sent[field].replace(second=0, microsecond=0)
    changes = {field: value for field, value in sent.items() if getattr(row, field) != value}
    if changes:
        for field, value in changes.items():
            setattr(row, field, value)
        row.save()
    if changes or created:
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(row)
