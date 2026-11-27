"""What the reads and the writes share: the live records and how one is named, the business's day and a list's page."""

import datetime as dt
from typing import Any
from uuid import UUID

from django.db.models import F, QuerySet, Value
from django.db.models.functions import Concat
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound

from apps.staff.models import Member
from apps.staff.schemas.fields import PageIn
from base.business import business_zone
from base.queries.people import hub_user_of
from base.text_search import contains_text

MEMBER_NOT_FOUND = _("That staff member does not exist in this business.")
AMBIGUOUS_MEMBER = _(
    "There are several staff members called “%(name)s”: %(matches)s. Say which one."
)

TERMINATED = Member.Status.TERMINATED
#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5


def live_members() -> QuerySet[Member]:
    """Every record that is not terminated, with its role's name as ``role_name``."""
    return Member.objects.exclude(status=TERMINATED).annotate(role_name=F("role__name"))


def load_member(member_id: UUID) -> Member | None:
    """A live record (a ``MemberDetailOut``), or ``None``; services returns it after a write."""
    return live_members().filter(pk=member_id).first()


def resolve_member(
    member_id: UUID | None, name: str | None, *, lock: bool = False
) -> Member:
    """The live record named by id, or by name: an exact full name first, then a part of it.

    ``lock`` takes the record's row until the end of the command's transaction. ``NotFound`` when
    nothing matches; 409 ``staff.ambiguous_member`` naming the candidates when several do.
    """
    members = live_members().annotate(
        search_name=Concat("first_name", Value(" "), "last_name")
    )
    if lock:
        members = members.select_for_update(of=("self",))
    if member_id is not None:
        member = members.filter(pk=member_id).first()
    else:
        ordered = members.order_by("first_name", "last_name", "id")
        matches = list(
            ordered.filter(search_name__iexact=name)[: MAX_CANDIDATES + 1]
        ) or list(ordered.filter(contains_text(name, "search_name"))[: MAX_CANDIDATES + 1])
        if len(matches) > 1:
            names = ", ".join(match.full_name for match in matches[:MAX_CANDIDATES])
            raise Conflict(
                str(AMBIGUOUS_MEMBER) % {"name": name, "matches": names},
                code="staff.ambiguous_member",
            )
        member = matches[0] if matches else None
    if member is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return member


def actor_user_id(ctx: OperationContext) -> UUID | None:
    """The id of the caller's person in the business's database (``base.HubUser``); ``None`` for the platform itself,
    an API key, an anonymous caller or a person it does not know yet (who has no record hanging from them)."""
    person = hub_user_of(ctx)
    return None if person is None else person.pk


def own_member(ctx: OperationContext) -> Member | None:
    """The live record linked to the caller's user, if any."""
    user_id = actor_user_id(ctx)
    return None if user_id is None else live_members().filter(user_id=user_id).first()


def business_today() -> dt.date:
    """Today in the business's time zone (hub#771)."""
    return timezone.localdate(timezone=business_zone())


def _page(rows: QuerySet[Any], params: PageIn) -> dict:
    return {
        "rows": list(rows[params.offset : params.offset + params.limit]),
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
