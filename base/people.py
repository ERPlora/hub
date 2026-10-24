"""The people of a business and their roles, as Employees shows them (APP-BASE-5): rules without the ORM.

Who is in the business and with which role is erplora.com's (HUBS-F24…F29 of the SaaS: invite, change the role,
remove, the plan's places); the Hub keeps of each person how they get in at its tills (a PIN, a badge), and lets whoever
runs the business take a PIN away or give and take a badge. The owner's own way in is only the owner's to change, and
nobody gives themselves a badge (a badge says who is at the till: another person registers it), save the owner, whom
nobody outranks.
"""

from django.utils.translation import gettext_lazy as _

from base.models import Membership
from base.throttle import AttemptLimit

#: The roles of erplora.com, from the top: the order of Employees › Roles and of the list of people.
ROLE_ORDER = (
    Membership.Role.OWNER,
    Membership.Role.ADMIN,
    Membership.Role.MANAGER,
    Membership.Role.EMPLOYEE,
)

#: The local copy of an erplora.com account is named ``saas:<id>`` (``base.services.username_for``): a person the
#: SaaS's photo names is known by it before entering.
SAAS_PREFIX = "saas:"

#: Tries to give someone a badge: 30 an hour per editor, the accepted ones too («already taken» tells that a number
#: is somebody's card: gh:hub#2560, the old Hub's brake on PINs tried through a person's page, gh:hub#2518).
BADGE_CHANGE_LIMIT = AttemptLimit("badge-change", attempts=30, window=3600)

#: Why a person's way in cannot be changed by who asks; the codes the operations answer with.
OWNER_ONLY = "base.person_owner_only"
OWN_BADGE = "base.badge_own"

OWNER_ONLY_MESSAGE = _("Only the owner changes the owner's way in.")
OWN_BADGE_MESSAGE = _("Nobody registers their own badge: ask another administrator.")


def role_rank(role: str) -> int:
    """0 for the owner, 3 for an employee; a role erplora.com did not send (none) goes last."""
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return len(ROLE_ORDER)


def refusal(*, actor: str, actor_role: str, target: str, target_role: str, badge: bool = False) -> str | None:
    """Why ``actor`` (a username, with its role) may not change the way in of ``target``; ``None`` when it may.

    The owner's is the owner's alone; a badge is never one's own, save the owner's (nobody is above them)."""
    is_owner = actor_role == Membership.Role.OWNER
    if target_role == Membership.Role.OWNER and not (is_owner and actor == target):
        return OWNER_ONLY
    if badge and actor == target and not is_owner:
        return OWN_BADGE
    return None


def ways(*, pin: bool, badge: bool) -> dict[str, bool]:
    """How a person gets in: with their erplora.com account always (every person of the business has one), and at the
    shared tills with a PIN and a badge when the hub keeps them."""
    return {"account": True, "pin": pin, "badge": badge}
