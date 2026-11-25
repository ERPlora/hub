"""What the tests of roles share: what each role of a business is granted of an app's permissions, and a role the
business made with who holds it."""

from live.meta import LiveAppConfig, permissions_for_role

from base.models import HubUser, Membership
from base.models.roles import BusinessRole

#: The roles that work in the business, the ones a test of what whoever sells, clocks or cooks is offered runs for:
#: every one but the accountancy firm, which only reads (``base/tests/test_accountant.py`` fixes what it reaches).
WORKING_ROLES = tuple(role for role in Membership.Role if role != Membership.Role.ACCOUNTANT)


def grants_by_role(config: LiveAppConfig) -> dict[str, frozenset[str]]:
    """The permissions of app ``config`` that each basic role of a business is granted, by role."""
    return {role: permissions_for_role([config], role) for role in Membership.Role.values}


def a_role(name="Cashier", origin=Membership.Role.EMPLOYEE, **states) -> BusinessRole:
    """A role of the business saved with ``states`` (permission names with ``__`` for ``.``)."""
    saved = {permission.replace("__", "."): state for permission, state in states.items()}
    return BusinessRole.objects.create(name=name, origin=origin, states=saved)


def held_by(user, role: BusinessRole) -> None:
    HubUser.objects.update_or_create(username=user.get_username(), defaults={"business_role": role})
