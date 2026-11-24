"""Who reads and who changes what: the permissions, whose agenda a caller may change or book in, and what a caller that
is not a person never reads."""

from uuid import UUID

from live.context import OperationContext

from apps.staff.queries import own_member

from .ownership import is_own

VIEW_OWN = "appointment.view_own_appointment"
ADD_ALL = "appointment.add_appointment"
ADD_OWN = "appointment.add_own_appointment"
CHANGE_ALL = "appointment.change_appointment"
CHANGE_OWN = "appointment.change_own_appointment"


def own_staff_id(ctx: OperationContext) -> UUID | None:
    member = own_member(ctx)
    return member.id if member else None


def may_change(ctx: OperationContext, staff_id: UUID | None) -> bool:
    return ctx.has(CHANGE_ALL) or (ctx.has(CHANGE_OWN) and is_own(ctx, staff_id))


def may_book_for(ctx: OperationContext, staff_id: UUID | None) -> bool:
    return ctx.has(ADD_ALL) or (ctx.has(ADD_OWN) and is_own(ctx, staff_id))


def by_person(ctx: OperationContext) -> bool:
    """Whether a person of the team acts (a user account). Only a person gets the front desk's exceptions
    and reads what is the salon's: an automation — a flow's step, the platform itself, an anonymous caller,
    any kind still to come — is judged and answered as the customer."""
    return hasattr(ctx.actor, "get_username")


#: What a caller that is not a person never reads: the customer's contact, the salon's notes and a
#: cancellation's reason (they may hold health data). The market's client-facing surfaces never show them.
PRIVATE = ("customer_phone", "customer_email", "notes", "internal_notes", "cancellation_reason")


def for_caller(ctx: OperationContext, answer: dict) -> dict:
    """``answer`` as ``ctx`` may read it: whole for a person, without ``PRIVATE`` for anyone else."""
    if by_person(ctx):
        return answer
    return {name: "" if name in PRIVATE else value for name, value in answer.items()}
