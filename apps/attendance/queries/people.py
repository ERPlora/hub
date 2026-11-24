"""Who a clock-in, a clock-out or a break is for: the caller's own staff record, or the person named by their id or in
words. The write and the assistant's card before it find them with the same function (``clocked``), so the card names
the person the write will clock, and words that fit several people, or nobody, draw no card."""

from uuid import UUID

from django.db.models import CharField, Value
from django.db.models.functions import Concat
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import INTERNAL, operation

from apps.attendance.schemas import MemberRefIn, PersonOut
from apps.staff.models import Member
from base.models import HubUser
from base.queries.people import hub_user_of

MEMBER_NOT_FOUND = _("That person does not exist in Staff.")
AMBIGUOUS_MEMBER = _("Several people match “%(name)s”: %(matches)s. Say which one.")
NO_MEMBER_RECORD = _(
    "Your user is not linked to any staff record: ask a manager to link it in Staff."
)
OTHERS_DENIED = _("You can only clock yourself in and out.")

CLOCK_OTHERS = "attendance.clock_others"


def member_name_expression() -> Concat:
    return Concat("first_name", Value(" "), "last_name", output_field=CharField())


def actor_user(ctx: OperationContext) -> HubUser | None:
    """The caller's person in the business's database (``base.HubUser``), read only; ``None`` for the platform itself,
    an API key, an anonymous caller or a person it does not know yet (whom no record names)."""
    return hub_user_of(ctx)


def own_member(ctx: OperationContext) -> Member | None:
    """The live (not terminated) staff record linked to the caller's user, if any, with its ``name``."""
    user = actor_user(ctx)
    if user is None:
        return None
    return (
        Member.objects.annotate(name=member_name_expression())
        .exclude(status=Member.Status.TERMINATED)
        .filter(user_id=user.pk)
        .first()
    )


def find_member(
    member_id: UUID | None, name: str | None, *, include_terminated: bool = False
) -> Member:
    """The staff record named by id, or by name: an exact full name first, then a part of it.

    ``NotFound`` when nothing matches; 409 ``attendance.ambiguous_member`` naming the candidates.
    """
    members = Member.objects.annotate(name=member_name_expression())
    if not include_terminated:
        members = members.exclude(status=Member.Status.TERMINATED)
    member = None
    if member_id is not None:
        member = members.filter(pk=member_id).first()
    elif name:
        text = name.strip()
        matches = list(members.filter(name__iexact=text)[:2]) or list(
            members.filter(name__icontains=text).order_by(
                "first_name", "last_name", "id"
            )[:6]
        )
        if len(matches) > 1:
            names = ", ".join(m.full_name for m in matches[:5])
            raise Conflict(
                str(AMBIGUOUS_MEMBER) % {"name": text, "matches": names},
                code="attendance.ambiguous_member",
            )
        member = matches[0] if matches else None
    if member is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return member


def clocked(ctx: OperationContext, data: MemberRefIn) -> tuple[Member, bool]:
    """The staff record a clock-in, a clock-out or a break acts on, and whether it is the caller's own.

    None named: the caller's own (409 ``attendance.no_member_record`` without one). Someone else needs
    ``attendance.clock_others``.
    """
    own = own_member(ctx)
    if data.member_id is None and not data.member:
        if own is None:
            raise Conflict(str(NO_MEMBER_RECORD), code="attendance.no_member_record")
        return own, True
    member = find_member(data.member_id, data.member)
    mine = own is not None and member.pk == own.pk
    if not mine and not ctx.has(CLOCK_OTHERS):
        raise PermissionDenied(str(OTHERS_DENIED))
    return member, mine


def person_out(member: Member) -> dict:
    """A person as the «Person» filter names them; ``member`` comes with its ``name`` (``member_name_expression``)."""
    return {"id": member.id, "name": member.name, "status": member.status}


@operation(
    "attendance.person.check",
    kind="query",
    permission="attendance.clock",
    input=MemberRefIn,
    output=PersonOut,
    ai=INTERNAL,
)
def check_clocked(ctx: OperationContext, data: MemberRefIn) -> dict:
    """The person a clock-in, a clock-out or a break is for, as the write finds them: checked before the assistant's
    card, which names by it a person said in words."""
    member, _mine = clocked(ctx, data)
    return person_out(member)
