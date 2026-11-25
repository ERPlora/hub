"""Time off: register it, ask for one's own, approve it, reject it and cancel it (STAFF-F17 to F19 and F24)."""

from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.staff import events, time_off_card
from apps.staff.models import Member, TimeOff
from apps.staff.queries.reads import actor_user_id, resolve_member
from apps.staff.queries.time_off_reads import TIME_OFF_NOT_FOUND, load_time_off, overlapping_time_off
from apps.staff.schemas.time_off import TimeOffDetailOut, TimeOffFieldsIn, TimeOffIn, TimeOffRefIn, TimeOffRequestIn
from base.services.sessions import acting_hub_user

from .locks import _locked_live_member

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

MANAGE_TIME_OFF = "staff.manage_time_off"
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


@operation(
    "staff.time_off.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_time_off",
    input=TimeOffIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "register a vacation for Lucía from 1 to 7 August",
                "Pablo is off sick tomorrow",
                "add a training day off for Ana on Friday",
            ),
            "es": (
                "registra unas vacaciones de Lucía del 1 al 7 de agosto",
                "Pablo está de baja por enfermedad mañana",
                "apunta una ausencia por formación de Ana el viernes",
            ),
        },
        "description": "Registers a time-off request (vacation, sick leave, personal, training or other) "
        "for a staff member, by id or by name; it starts pending.",
        "risk": "normal",
        "summary": time_off_card.summary,
    },
)
def create_time_off(ctx: OperationContext, data: TimeOffIn) -> TimeOff | None:
    """STAFF-F17: for any record that is not terminated; never over another pending or approved one."""
    member = resolve_member(data.member_id, data.member, lock=True)
    return _register_time_off(ctx, member, data)


@operation(
    "staff.time_off.request",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.request_time_off",
    input=TimeOffRequestIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "I want to ask for a day off on Friday",
                "request vacation for me from 1 to 15 August",
                "I need the afternoon off tomorrow",
            ),
            "es": (
                "quiero pedirme un día libre el viernes",
                "solicito vacaciones del 1 al 15 de agosto",
                "necesito librar mañana por la tarde",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_time_off",
    input=TimeOffRefIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "approve Lucía's vacation",
                "accept Pablo's time-off request for Friday",
                "say yes to Ana's day off",
            ),
            "es": (
                "aprueba las vacaciones de Lucía",
                "acepta la solicitud de ausencia de Pablo del viernes",
                "dale el visto bueno al día libre de Ana",
            ),
        },
        "description": "Approves a pending time-off request: its hours leave the person's availability.",
        "risk": "normal",
    },
)
def approve_time_off(ctx: OperationContext, data: TimeOffRefIn) -> TimeOff | None:
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
    time_off.approved_by = acting_hub_user(ctx)
    time_off.approved_at = timezone.now()
    return _finish_move(ctx, time_off, "approve", ["approved_by", "approved_at"])


@operation(
    "staff.time_off.reject",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_time_off",
    input=TimeOffRefIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "reject Lucía's vacation request",
                "say no to Pablo's day off on Friday",
                "turn down Ana's pending time off",
            ),
            "es": (
                "rechaza la solicitud de vacaciones de Lucía",
                "dile que no al día libre de Pablo del viernes",
                "deniega la ausencia pendiente de Ana",
            ),
        },
        "description": "Rejects a pending time-off request.",
        "risk": "normal",
    },
)
def reject_time_off(ctx: OperationContext, data: TimeOffRefIn) -> TimeOff | None:
    """STAFF-F18."""
    return _finish_move(ctx, _move(data.id, "reject"), "reject")


@operation(
    "staff.time_off.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.request_time_off",
    input=TimeOffRefIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "cancel Lucía's vacation",
                "Pablo no longer needs Friday off, cancel it",
                "withdraw my pending day off",
            ),
            "es": (
                "cancela las vacaciones de Lucía",
                "Pablo ya no necesita el viernes libre, anúlalo",
                "retira mi solicitud de día libre pendiente",
            ),
        },
        "description": "Cancels a pending or approved time-off request (an employee may only withdraw their "
        "own pending one).",
        "risk": "normal",
    },
)
def cancel_time_off(ctx: OperationContext, data: TimeOffRefIn) -> TimeOff | None:
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
