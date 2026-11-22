"""Who performs each service (SERVICE-F31, F32): a professional assigned, changed and removed, and every service of a
professional released at once; the professional's record is locked first, so two writes never fight over the «main
service».
"""

from django.utils import timezone
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models import Assignment
from apps.service.queries.assignments import ASSIGNMENT_NOT_FOUND, load_assignment
from apps.service.queries.catalog import find_service
from apps.service.queries.reads import SYSTEM
from apps.service.schemas import (
    AssignIn,
    AssignmentOut,
    AssignmentPatchIn,
    AssignmentRefIn,
    DeletedOut,
    MemberReleaseIn,
    ReleasedOut,
)
from apps.service.services.writes import _changes
from apps.staff.models import Member
from apps.staff.queries import resolve_member


def _demote_other_primaries(member: Member, keep) -> None:
    Assignment.objects.filter(member=member, is_primary=True).exclude(pk=keep).update(
        is_primary=False, updated_at=timezone.now()
    )


def _assignment_payload(assignment: Assignment) -> dict:
    return {
        "id": str(assignment.id),
        "service_id": str(assignment.service_id),
        "member_id": str(assignment.member_id),
    }


@operation(
    "service.assignment.assign",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=AssignIn,
    output=AssignmentOut,
    expose_api=True,
    ai={
        "description": "Assign a professional of Staff (by name) to a service (by name), with their own duration and "
        "price if they have them; assigning them again changes those.",
        "risk": "normal",
        "asks": {
            "en": ("Sonia does manicures too now, at her own price", "give Raquel the colour, 40 minutes at 50 euros"),
            "es": (
                "asigna el tinte a Raquel con un precio propio de 50 €",
                "asígnale las manicuras también a Sonia, con 40 minutos",
            ),
        },
    },
)
def assign(ctx: OperationContext, data: AssignIn) -> dict:
    service_id = find_service(data.service_id, data.service).pk
    member = resolve_member(data.member_id, data.member, lock=True)
    # The assignment is locked before the service is held, in the order the Hub admin's deletion of the
    # service takes them (its assignments, then itself): the other way round, each waited for the other.
    assignment = (
        Assignment.objects.select_for_update()
        .filter(service_id=service_id, member=member)
        .first()
    )
    service = find_service(service_id, None, hold=True)
    created = assignment is None
    if created:
        assignment = Assignment(service=service, member=member)
    assignment.custom_duration = data.custom_duration
    assignment.custom_price = data.custom_price
    # Assigning someone again changes their main service only when it is said.
    if created or "is_primary" in data.model_fields_set:
        assignment.is_primary = data.is_primary
    assignment.is_active = True
    if assignment.is_primary:
        _demote_other_primaries(member, keep=assignment.pk)
    assignment.save()
    name = events.ASSIGNMENT_ASSIGNED if created else events.ASSIGNMENT_UPDATED
    record_event(ctx, name, _assignment_payload(assignment))
    return load_assignment(assignment.id)


def _locked_assignment(assignment_id) -> Assignment:
    """An assignment of a live professional, the professional's record locked first and then its row."""
    found = (
        Assignment.objects.exclude(member__status=Member.Status.TERMINATED)
        .filter(pk=assignment_id)
        .first()
    )
    if found is None:
        raise NotFound(str(ASSIGNMENT_NOT_FOUND), code="service.assignment_not_found")
    resolve_member(found.member_id, None, lock=True)
    assignment = Assignment.objects.select_for_update().filter(pk=assignment_id).first()
    if assignment is None:
        raise NotFound(str(ASSIGNMENT_NOT_FOUND), code="service.assignment_not_found")
    return assignment


@operation(
    "service.assignment.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=AssignmentPatchIn,
    output=AssignmentOut,
    expose_api=True,
    ai={
        "description": "Change who performs a service: their own duration or price (null = the service's), their main "
        "service, or switch the assignment on or off. The assignment's id comes from service.assignment.list (by the "
        "service's or the professional's name).",
        "risk": "normal",
        "asks": {
            "en": ("Raquel takes 40 minutes for highlights now", "make the manicure Sonia's main service"),
            "es": (
                "súbele a Raquel su precio propio del tinte a 55 €",
                "Sonia tiene la manicura como su servicio principal, márcalo",
            ),
        },
    },
)
def update_assignment(ctx: OperationContext, data: AssignmentPatchIn) -> dict:
    assignment = _locked_assignment(data.id)
    sent = data.model_fields_set
    values = {
        field: getattr(data, field)
        for field in ("custom_duration", "custom_price")
        if field in sent
    }
    values |= {
        field: getattr(data, field)
        for field in ("is_primary", "is_active")
        if getattr(data, field) is not None
    }
    changes = _changes(assignment, values)
    if changes:
        if changes.get("is_primary"):
            _demote_other_primaries(assignment.member, keep=assignment.pk)
        for field, value in changes.items():
            setattr(assignment, field, value)
        assignment.save()
        record_event(ctx, events.ASSIGNMENT_UPDATED, _assignment_payload(assignment))
    return load_assignment(assignment.id)


@operation(
    "service.assignment.remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=AssignmentRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a professional from a service: they no longer perform it. The assignment's id comes "
        "from service.assignment.list (by the service's or the professional's name).",
        "risk": "normal",
        "asks": {
            "en": ("Sonia no longer does pedicures", "take Raquel off the colour service"),
            "es": (
                "Sonia ya no hace pedicuras, quítala de esa asignación",
                "quita a la estilista Raquel de los cortes, ya no los hace",
            ),
        },
    },
)
def remove_assignment(ctx: OperationContext, data: AssignmentRefIn) -> dict:
    assignment = _locked_assignment(data.id)
    payload = _assignment_payload(assignment)
    assignment.delete()
    record_event(ctx, events.ASSIGNMENT_REMOVED, payload)
    return {"id": data.id}


@operation(
    "service.assignment.release_member",
    kind="command",
    permission=SYSTEM,
    input=MemberReleaseIn,
    output=ReleasedOut,
    ai={
        "description": "Platform reaction to staff.member.terminated: the professional who left stops performing "
        "every service.",
        "risk": "normal",
    },
)
def release_member(ctx: OperationContext, data: MemberReleaseIn) -> dict:
    assignments = list(
        Assignment.objects.select_for_update().filter(member_id=data.id).order_by("id")
    )
    for assignment in assignments:
        payload = _assignment_payload(assignment)
        assignment.delete()
        record_event(ctx, events.ASSIGNMENT_REMOVED, payload)
    return {"removed": len(assignments)}
