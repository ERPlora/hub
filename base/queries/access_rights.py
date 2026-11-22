"""Who can give a person a screen it may not open (``base.access.grantors``): the names «No access» shows."""

from typing import Any

from live.context import OperationContext
from live.operations import operation

from base import people as people_rules
from base.models import Membership
from base.permissions import VIEW_HOME
from base.schemas.sessions import GrantorsIn, GrantorsOut

from .people import people_of, signed_in_role

#: The roles that change someone's role on erplora.com (HUBS-F26); a manager or an employee changes none.
CHANGE_ROLES = frozenset({Membership.Role.OWNER, Membership.Role.ADMIN})


@operation(
    "base.access.grantors",
    kind="query",
    permission=VIEW_HOME,
    input=GrantorsIn,
    output=GrantorsOut,
    ai={
        "description": "Not an assistant tool: names who of the business can give the person a screen it may not "
        "open (by changing its role on erplora.com), for the «No access» screen."
    },
)
def access_grantors(ctx: OperationContext, data: GrantorsIn) -> dict[str, Any]:
    """The people who can give this person more access, by name only, from the top role. On erplora.com a role is
    changed by someone who outranks the person and gives a role above theirs, so an employee asks the owner or an
    administrator and a manager only the owner; those invited who have not entered yet count too."""
    rank = people_rules.role_rank(signed_in_role(ctx))
    return {
        "grantors": [
            {"name": person["name"]}
            for person in people_of(ctx.scope.key)
            if person["role"] in CHANGE_ROLES and people_rules.role_rank(person["role"]) + 1 < rank
        ]
    }
