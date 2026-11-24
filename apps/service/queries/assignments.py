"""Who performs each service: the assignments, their rows and their reads."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.service.models import Assignment
from apps.service.queries.catalog import find_service
from apps.service.queries.reads import _page
from apps.service.schemas.assignments import (
    AssignmentListIn,
    AssignmentPage,
    AssignmentDetailOut,
    EligibleIn,
    EligiblePage,
)
from apps.service.schemas.fields import ByIdIn
from apps.staff.models import Member
from apps.staff.queries.reads import resolve_member

ASSIGNMENT_NOT_FOUND = _("That assignment does not exist in this business.")

TERMINATED = Member.Status.TERMINATED


def _assignments():
    return Assignment.objects.select_related("service", "member").exclude(
        member__status=TERMINATED
    )


def assignment_row(assignment: Assignment) -> dict:
    service = assignment.service
    return {
        "id": assignment.id,
        "service_id": service.id,
        "service_name": service.name,
        "member_id": assignment.member_id,
        "member_name": assignment.member.full_name,
        "custom_duration": assignment.custom_duration,
        "custom_price": assignment.custom_price,
        "is_primary": assignment.is_primary,
        "is_active": assignment.is_active,
        "duration": assignment.custom_duration or service.duration_minutes,
        "price": service.price
        if assignment.custom_price is None
        else assignment.custom_price,
    }


def load_assignment(assignment_id: UUID) -> dict:
    return assignment_row(_assignments().get(pk=assignment_id))


@operation(
    "service.assignment.list",
    kind="query",
    permission="service.view_service",
    input=AssignmentListIn,
    output=AssignmentPage,
    expose_api=True,
    ai={
        "description": "List who performs each service: the professionals of a service, or the services of a "
        "professional, with their own duration and price and their main service first.",
        "asks": {
            "en": ("who does what in the salon?", "what is Sonia assigned to?"),
            "es": (
                "¿qué tiene asignado Raquel?",
                "¿a quién tenemos asignadas las mechas?",
                "¿quién se encarga de los tintes?",
            ),
        },
    },
)
def list_assignments(ctx: OperationContext, params: AssignmentListIn) -> dict:
    assignments = _assignments()
    if params.service_id or params.service:
        assignments = assignments.filter(
            service=find_service(params.service_id, params.service)
        )
    if params.member_id or params.member:
        assignments = assignments.filter(
            member=resolve_member(params.member_id, params.member)
        )
    ordered = assignments.order_by(
        "-is_primary", "member__first_name", "member__last_name", "service__name", "id"
    )
    return _page(ordered, params, assignment_row)


@operation(
    "service.assignment.get",
    kind="query",
    permission="service.view_service",
    input=ByIdIn,
    output=AssignmentDetailOut,
    expose_api=True,
    ai={
        "description": "Get one professional's assignment to a service by its id: the service, the professional and "
        "their own duration and price, if any. The assignment's id comes from service.assignment.list (by the "
        "service's or the professional's name).",
        "asks": {
            "en": (
                "show me Raquel's assignment to the beard trim",
                "what are Sonia's own price and time for highlights?",
            ),
            "es": ("dame la asignación de Sonia al tinte, con su precio", "¿cuánto tarda Raquel en hacer unas mechas?"),
        },
    },
)
def get_assignment(ctx: OperationContext, data: ByIdIn) -> dict:
    assignment = _assignments().filter(pk=data.id).first()
    if assignment is None:
        raise NotFound(str(ASSIGNMENT_NOT_FOUND), code="service.assignment_not_found")
    row = assignment_row(assignment)
    return {**row, "label": f"{row['service_name']} · {row['member_name']}"}


@operation(
    "service.assignment.eligible",
    kind="query",
    permission="service.view_service",
    input=EligibleIn,
    output=EligiblePage,
    expose_api=True,
    ai={
        "description": "Who may perform a service: the active, bookable professionals with an active assignment, "
        "with their own duration and price, main service first. Empty = nobody declared (the diary then lets the "
        "whole bookable team do it).",
        "asks": {
            "en": ("who can do a keratin treatment?", "who is able to do a manicure, and at what price?"),
            "es": ("¿quién puede hacer un alisado de keratina?", "¿quién del salón puede hacer la pedicura?"),
        },
    },
)
def eligible(ctx: OperationContext, params: EligibleIn) -> dict:
    service = find_service(params.service_id, params.service)
    assignments = (
        Assignment.objects.select_related("service", "member")
        .filter(
            service=service,
            is_active=True,
            member__status=Member.Status.ACTIVE,
            member__is_bookable=True,
        )
        .order_by("-is_primary", "member__first_name", "member__last_name", "id")
    )

    def row(assignment: Assignment) -> dict:
        out = assignment_row(assignment)
        member = assignment.member
        return {
            **{
                field: out[field]
                for field in (
                    "member_id",
                    "custom_duration",
                    "custom_price",
                    "is_primary",
                    "duration",
                    "price",
                )
            },
            "full_name": member.full_name,
            "color": member.color,
            "booking_buffer": member.booking_buffer,
        }

    return _page(assignments, params, row)
