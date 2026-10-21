"""Events of the service app (``service.<entity>.<fact>``) and its reactions to Staff's and Customers' events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids (and a service's name), never a reason for voiding or
adjusting a voucher (free text that may name the customer).

The sessions of the till are no reactions: Sales reserves, releases, delivers and gives them back by
calling this app's operations inside its own transaction (WORKBOOK «Contrato con Ventas»).

Reactions: a professional who leaves (``staff.member.terminated``) stops performing every service, two
customer cards merged (``customer.customer.merged``) move the absorbed card's vouchers to the one that
stays, and a card erased (``customer.customer.erased``, GDPR) empties the free texts of its vouchers;
each through an operation of this app run as the system, in its own transaction. The
outbox relay (``base.relay``, on every tick of the worker) hands each event named in ``REACTIONS`` to ``react``,
in the scope of the hub that recorded it; the three operations are idempotent, so a repeated delivery changes
nothing (``tests/test_relay.py``).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

SERVICE_CREATED = "service.service.created"
SERVICE_UPDATED = "service.service.updated"
SERVICE_ARCHIVED = "service.service.archived"
SERVICE_RESTORED = "service.service.restored"
CATEGORY_CREATED = "service.category.created"
CATEGORY_UPDATED = "service.category.updated"
CATEGORY_DELETED = "service.category.deleted"
SETTINGS_UPDATED = "service.settings.updated"
ASSIGNMENT_ASSIGNED = "service.assignment.assigned"
ASSIGNMENT_UPDATED = "service.assignment.updated"
ASSIGNMENT_REMOVED = "service.assignment.removed"
PACKAGE_CREATED = "service.package.created"
PACKAGE_UPDATED = "service.package.updated"
PACKAGE_DELETED = "service.package.deleted"
GRANT_GRANTED = "service.grant.granted"
GRANT_VOIDED = "service.grant.voided"
GRANT_ADJUSTED = "service.grant.adjusted"
GRANT_REDEEMED = "service.grant.redeemed"
GRANT_REASSIGNED = "service.grant.reassigned"
GRANT_ERASED = "service.grant.erased"
SESSION_RESERVED = "service.session.reserved"
SESSION_RELEASED = "service.session.released"
SESSION_SETTLED = "service.session.settled"
SESSION_EXPIRED = "service.session.expired"
SESSION_RETURNED = "service.session.returned"

ALL = [
    SERVICE_CREATED,
    SERVICE_UPDATED,
    SERVICE_ARCHIVED,
    SERVICE_RESTORED,
    CATEGORY_CREATED,
    CATEGORY_UPDATED,
    CATEGORY_DELETED,
    SETTINGS_UPDATED,
    ASSIGNMENT_ASSIGNED,
    ASSIGNMENT_UPDATED,
    ASSIGNMENT_REMOVED,
    PACKAGE_CREATED,
    PACKAGE_UPDATED,
    PACKAGE_DELETED,
    GRANT_GRANTED,
    GRANT_VOIDED,
    GRANT_ADJUSTED,
    GRANT_REDEEMED,
    GRANT_REASSIGNED,
    GRANT_ERASED,
    SESSION_RESERVED,
    SESSION_RELEASED,
    SESSION_SETTLED,
    SESSION_EXPIRED,
    SESSION_RETURNED,
]

#: Everything that changes what a service row says.
SERVICE_EVENTS = [SERVICE_CREATED, SERVICE_UPDATED, SERVICE_ARCHIVED, SERVICE_RESTORED]
CATEGORY_EVENTS = [CATEGORY_CREATED, CATEGORY_UPDATED, CATEGORY_DELETED]
ASSIGNMENT_EVENTS = [ASSIGNMENT_ASSIGNED, ASSIGNMENT_UPDATED, ASSIGNMENT_REMOVED]
PACKAGE_EVENTS = [PACKAGE_CREATED, PACKAGE_UPDATED, PACKAGE_DELETED]
GRANT_EVENTS = [
    GRANT_GRANTED,
    GRANT_VOIDED,
    GRANT_ADJUSTED,
    GRANT_REDEEMED,
    GRANT_REASSIGNED,
    GRANT_ERASED,
]
#: The steps of a session of the till (SERVICE-F22–F27): each one moves a voucher's balance.
SESSION_EVENTS = [
    SESSION_RESERVED,
    SESSION_RELEASED,
    SESSION_SETTLED,
    SESSION_EXPIRED,
    SESSION_RETURNED,
]

# Other apps' events (their WORKBOOKs fix the payload: ``{"id": …}`` and ``{"id", "absorbed_id"}``).
STAFF_MEMBER_TERMINATED = "staff.member.terminated"
STAFF_MEMBER_EVENTS = [
    "staff.member.created",
    "staff.member.updated",
    "staff.member.deactivated",
    STAFF_MEMBER_TERMINATED,
]
CUSTOMER_MERGED = "customer.customer.merged"
CUSTOMER_ERASED = "customer.customer.erased"
CUSTOMER_GONE = [
    "customer.customer.deleted",
    CUSTOMER_ERASED,
    CUSTOMER_MERGED,
]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    STAFF_MEMBER_TERMINATED: "service.assignment.release_member",
    CUSTOMER_MERGED: "service.grant.reassign",
    CUSTOMER_ERASED: "service.grant.forget_customer",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
