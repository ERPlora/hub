"""People and permissions: a manager's approval (``base.approval.*``).
"""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError, PermissionDenied, Unauthorized
from live.operations import operation
from live.outbox import record_event

from base import access, events, queries
from base import approvals as approval_rules
from base.models import Approval
from base.permissions import VIEW_HOME
from base.schemas import ApprovalIn, ApprovalPassOut, ApprovalSpendIn, ApprovalSpentOut
from base.services.devices import badge_owner, too_many_message
from base.throttle import client_key


def _approval_refused() -> Unauthorized:
    return Unauthorized(
        gettext("Those details do not approve this. Check the name and the PIN, and try again."),
        code="base.approval_refused",
    )


def _approval_too_many(wait: int) -> OperationError:
    return OperationError(
        too_many_message(wait, gettext("Too many wrong attempts.")), code="base.too_many_attempts", status=429
    )


def _approver(ctx: OperationContext, data: ApprovalIn):
    """Who approves, by their PIN (counted against that person) or their badge (against the card), with the PIN
    pad's brakes: a wrong one also counts against the address; a right one starts the count again."""
    slug, address = ctx.scope.key, client_key(ctx.request)
    wait = access.PIN_ADDRESS_LIMIT.wait(slug, address)
    if wait:
        raise _approval_too_many(wait)
    if data.badge:
        user, card = badge_owner(slug, data.badge)
        brake = ("badge", card)
        way = Approval.Way.BADGE
    else:
        person = (data.person or "")[:64]
        brake = (person,)
        wait = access.PIN_PERSON_LIMIT.wait(slug, *brake)
        if wait:
            raise _approval_too_many(wait)
        user = queries.access.pin_owner(slug, person, (data.pin or "")[:16]) if data.pin else None
        way = Approval.Way.PIN
    if data.badge and (wait := access.PIN_PERSON_LIMIT.wait(slug, *brake)):
        raise _approval_too_many(wait)
    if user is None:
        access.PIN_PERSON_LIMIT.failed(slug, *brake)
        access.PIN_ADDRESS_LIMIT.failed(slug, address)
        raise _approval_refused()
    access.PIN_PERSON_LIMIT.clear(slug, *brake)
    return user, way


@operation(
    "base.approval.approve",
    kind="command",
    permission=VIEW_HOME,
    input=ApprovalIn,
    output=ApprovalPassOut,
    ai={
        "description": "Not an assistant tool (it takes a manager's PIN, never typed in a chat): a manager approves "
        "one action the person at the screen may not do, and the hub hands back a pass of one use.",
        "risk": "high",
    },
)
def approval_approve(ctx: OperationContext, data: ApprovalIn) -> dict:
    """«An approval is needed»: somebody of the business who may do the action approves it with their PIN
    or badge; a pass of one use for two minutes, bound to who asked, that action and that very request."""
    found = approval_rules.approvable(data.operation)
    if found is None:
        raise Conflict(gettext("This is not approved with a PIN."), code="base.approval_not_offered")
    op, _label = found
    if ctx.has(op.permission):
        raise Conflict(gettext("This no longer needs an approval: do it again."), code="base.approval_not_needed")
    if not data.badge and not (data.person and data.pin):
        raise InvalidPayload(
            gettext("Choose who approves it and type their PIN."), code="base.approval_incomplete", fields={"pin": "required"}
        )
    approver, way = _approver(ctx, data)
    if not queries.approvals.holds(approver, ctx.scope, op.permission):
        raise PermissionDenied(
            gettext("That person cannot approve this: ask somebody who may do it themselves."),
            code="base.approver_cannot",
        )
    token = approval_rules.new_token()
    approver_name = queries.people.face_name(approver)
    approval = Approval.objects.create(
        operation=op.name,
        permission=op.permission,
        fingerprint=data.fingerprint,
        token_digest=approval_rules.digest(token),
        requested_by=ctx.actor.get_username(),
        requested_by_name=queries.people.face_name(ctx.actor)[:150],
        approved_by=approver.get_username(),
        approved_by_name=approver_name[:150],
        way=way,
        expires_at=timezone.now() + dt.timedelta(seconds=approval_rules.PASS_SECONDS),
    )
    record_event(ctx, events.APPROVAL_GRANTED, {"id": str(approval.pk), "operation": op.name})
    return {"token": token, "approver": approver_name, "expires_in": approval_rules.PASS_SECONDS}


@operation(
    "base.approval.spend",
    kind="command",
    permission=VIEW_HOME,
    input=ApprovalSpendIn,
    output=ApprovalSpentOut,
    ai={
        "description": "Not an assistant tool, and no route: the approval's door spends a pass on the request it was "
        "given for (base.approvals).",
        "risk": "high",
    },
)
def approval_spend(ctx: OperationContext, data: ApprovalSpendIn) -> dict:
    """Spend a pass on the request it was given for: once, in time, by who asked, on that action and that request of
    this business. Anything else spends nothing."""
    if not hasattr(ctx.actor, "get_username"):
        return {"spent": False, "id": "", "approver": ""}
    now = timezone.now()
    approval = (
        Approval.objects.select_for_update()
        .filter(
            token_digest=approval_rules.digest(data.token),
            operation=data.operation,
            fingerprint=data.fingerprint,
            requested_by=ctx.actor.get_username(),
            used_at=None,
            expires_at__gt=now,
        )
        .first()
    )
    if approval is None:
        return {"spent": False, "id": "", "approver": ""}
    approval.used_at = now
    approval.figures = data.figures or None
    approval.save(update_fields=["used_at", "figures"])
    record_event(ctx, events.APPROVAL_USED, {"id": str(approval.pk), "operation": approval.operation})
    return {"spent": True, "id": str(approval.pk), "approver": approval.approved_by_name}
