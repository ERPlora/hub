"""ERPlora's support coming into a business that lets it in (BASE-F126): erplora.com's code with the role
``hub_support``.

The person of support enters on a copy of their own (``saas-support:<id>``, never staff), apart from their customer copy
(``saas:<id>``) and their staff copy (``saas-staff:<id>``), so being a member of a business or staff of the Hub admin
changes nothing here. Their ``Membership`` gives what an administrator may do but owning the business
(``base.permissions``), and their session says how it was opened (``SessionOwner.Credential.SUPPORT``), which keeps
them out of what is the business's own: its devices, its visits and activity, its team.
"""

from django.db import transaction
from django.http import HttpRequest
from live.context import OperationContext, Scope, system_context
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event

from base import events, queries
from base.auth import RedeemedUser
from base.models import Membership
from base.models.sessions import SessionOwner
from base.models.support_access import SupportVisit
from base.registry import internal_only
from base.schemas.support_access import SupportEnterIn, SupportEnterOut
from base.services.sessions import _end_sessions, _local_copy, _log_in, ensure_hub_user

SUPPORT_USERNAME_PREFIX = "saas-support:"


class SupportAccessOff(Exception):
    """The business does not let ERPlora's support in: no session is opened."""


def support_username_for(saas_user_id: str) -> str:
    """The support copy of a SaaS account."""
    return f"{SUPPORT_USERNAME_PREFIX}{saas_user_id}"


@transaction.atomic  # control's: the copy, its Membership and the session
@atomic  # the hub's: the entry and the person (base.HubUser)
def open_support_session(request: HttpRequest, redeemed: RedeemedUser, slug: str):
    """Log the person of support in on the business ``slug`` (a new session key) when it lets support in; else
    ``SupportAccessOff``, with nothing saved."""
    user = _local_copy(redeemed, username=support_username_for(redeemed.user_id), is_staff=False, is_superuser=False)
    entry = SupportEnterIn(username=user.get_username(), name=user.first_name, email=redeemed.email)
    if not support_access_enter(system_context(Scope("host", slug)), entry).entered:
        raise SupportAccessOff(slug)
    Membership.objects.update_or_create(user=user, host=slug, defaults={"role": Membership.SUPPORT})
    ensure_hub_user(user)
    _log_in(request, user, redeemed.user_id, credential=SessionOwner.Credential.SUPPORT)
    return user


# Not an assistant tool: the entry of a person of support, before there is an actor.
@operation(
    "base.support_access.enter",
    kind="command",
    permission=None,
    input=SupportEnterIn,
    output=SupportEnterOut,
    ai=INTERNAL,
)
def support_access_enter(ctx: OperationContext, data: SupportEnterIn) -> dict:
    """Note that a person of support came in, when the business lets support in: «Support access» lists it at once."""
    internal_only(ctx)
    if not queries.support_access.support_may_enter():
        return {"entered": False}
    SupportVisit.objects.create(username=data.username, name=data.name, email=data.email)
    record_event(ctx, events.SUPPORT_ACCESS_ENTERED, {})
    return {"entered": True}


def end_support_sessions(slug: str) -> int:
    """End every session of support open in the business of ``slug``; their tabs wake and leave. How many ended."""
    return _end_sessions(SessionOwner.objects.filter(host=slug, credential=SessionOwner.Credential.SUPPORT))
