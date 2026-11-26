"""A staff member's record: add one or several, change it, take it out of the agenda and end it (STAFF-F01 to F03, F05 to F07)."""

import datetime as dt
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, PermissionDenied
from live.operations import atomic, operation
from live.outbox import record_event

from apps.staff import events
from apps.staff.models import Member
from apps.staff.queries.reads import business_today, load_member, resolve_member
from apps.staff.queries.roles import active_role, role_for
from apps.staff.queries.time_off_reads import LIVE_TIME_OFF
from apps.staff.schemas.fields import MemberRefIn
from apps.staff.schemas.members import (
    BulkCreatedOut,
    BulkCreateIn,
    MemberDetailOut,
    MemberIn,
    MemberPatchIn,
    TerminatedOut,
    TerminateIn,
)
from base.assistant import file_rows
from base.models import HubUser, Membership

USER_NOT_IN_BUSINESS = _("That Hub user has no access to this business.")
USER_ALREADY_LINKED = _(
    "That Hub user is already linked to %(name)s. A Hub user can belong to only one staff member: unlink it "
    "there first, or pick another user."
)
ALREADY_INACTIVE = _("That staff member is already inactive.")
ACTIVE_TIME_OFF = _(
    "That staff member has pending or approved time off that has not ended yet. Resolve it first."
)

VIEW_COMPENSATION = "staff.view_compensation"
#: The fields of a record that only the pay permission writes.
PAY_FIELDS = ("hourly_rate", "commission_rate", "notes")
#: Fields a ``null`` clears in staff.member.update; any other ``null`` leaves the field as it is.
CLEARABLE = ("role_id", "user_id", "hire_date")
USER_UNIQUE = "staff_member_hub_user_unique"


@operation(
    "staff.member.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.add_member",
    input=MemberIn,
    output=MemberDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add Lucía to the team as a stylist",
                "register a new waiter, Pablo, at 12 € an hour",
                "create a staff record for Ana with a 10 % commission",
            ),
            "es": (
                "añade a Lucía al equipo como estilista",
                "da de alta a un camarero nuevo, Pablo, a 12 € la hora",
                "crea la ficha de Ana con un 10 % de comisión",
            ),
        },
        "description": "Adds a staff member (a person who works in the business). Their role is one of the "
        "business's active roles: read them with staff.role.list first. A role it does not have is refused at once "
        "and nothing is created: say which roles it has instead.",
        "risk": "normal",
        # hub#538: a role the business does not have is told to the model before the card, not after the yes.
        "check": "staff.role.resolve",
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.add_member",
    input=BulkCreateIn,
    output=BulkCreatedOut,
    ai={
        "asks": {
            "en": (
                "add Lucía, Pablo and Ana to the team at once",
                "register these three new waiters together",
                "load the whole team in one go",
            ),
            "es": (
                "añade de golpe a Lucía, Pablo y Ana al equipo",
                "da de alta a estos tres camareros nuevos juntos",
                "carga a todo el personal de una vez",
            ),
        },
        "description": "Adds several staff members at once (up to 100); a row with a problem is skipped "
        "with its reason and the rest go in.",
        "risk": "normal",
        "summary": file_rows.rows_named_by("members", "first_name", "last_name"),
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.change_member",
    input=MemberPatchIn,
    output=MemberDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "raise Lucía to 14 € an hour",
                "change Pablo's role to manager",
                "update Ana's phone number",
            ),
            "es": (
                "sube a Lucía a 14 € la hora",
                "cambia el rol de Pablo a encargado",
                "actualiza el teléfono de Ana",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.delete_member",
    input=MemberRefIn,
    output=MemberDetailOut,
    ai={
        "asks": {
            "en": (
                "deactivate Pablo while he is away",
                "take Lucía off the agenda without deleting her record",
                "deactivate Ana for a while, keeping everything",
            ),
            "es": (
                "desactiva a Pablo mientras esté fuera",
                "desactiva a Lucía en la agenda sin borrar nada",
                "desactiva a Ana una temporada sin perder sus datos",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.delete_member",
    input=TerminateIn,
    output=TerminatedOut,
    ai={
        "asks": {
            "en": (
                "Pablo is leaving the business, terminate him today",
                "Lucía no longer comes: end her contract and free her user",
                "terminate Ana for good from Friday",
            ),
            "es": (
                "Pablo se va del negocio, dalo de baja hoy",
                "Lucía ya no viene: termina su contrato y libera su usuario",
                "da de baja definitiva a Ana desde el viernes",
            ),
        },
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
    role = active_role(role_id, name)
    return role.id if role else None


def _role_for(role_id: UUID | None, name: str | None) -> UUID | None:
    """The id of an active role given by id or by name (``queries.role_for``: staff.role.resolve checks it so before
    the assistant's card); 422 on that field when there is none."""
    role = role_for(role_id, name)
    return role.id if role else None


def _check_user(
    ctx: OperationContext, user_id: UUID | None, exclude: UUID | None = None
) -> None:
    """A person of the business's database (``base.HubUser``) may hang a record when they are still in the business,
    have access to it (a ``Membership`` on the scope's host, control's) and no other live record."""
    if user_id is None:
        return
    person = HubUser.objects.filter(pk=user_id, is_active=True).first()
    if person is None or not Membership.objects.filter(user__username=person.username, host=ctx.scope.key).exists():
        raise InvalidPayload(
            str(USER_NOT_IN_BUSINESS), fields={"user_id": str(USER_NOT_IN_BUSINESS)}
        )
    holder = _holder_of(user_id, exclude=exclude)
    if holder is not None:
        raise _already_linked(holder.full_name)


def _holder_of(user_id: UUID, exclude: UUID | None = None) -> Member | None:
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
        with atomic():
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
