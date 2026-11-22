"""What an app's test of its roles compares: what each role of a business is granted of the app's permissions."""

from live.meta import LiveAppConfig, permissions_for_role

from base.models import Membership

#: The roles that work in the business, the ones a test of what whoever sells, clocks or cooks is offered runs for:
#: every one but the accountancy firm, which only reads (``base/tests/test_accountant.py`` fixes what it reaches).
WORKING_ROLES = tuple(role for role in Membership.Role if role != Membership.Role.ACCOUNTANT)


def grants_by_role(config: LiveAppConfig) -> dict[str, frozenset[str]]:
    """The permissions of app ``config`` that each basic role of a business is granted, by role."""
    return {role: permissions_for_role([config], role) for role in Membership.Role.values}
