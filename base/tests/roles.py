"""What an app's test of its roles compares: what each role of a business is granted of the app's permissions."""

from live.meta import LiveAppConfig, permissions_for_role

from base.models import Membership


def grants_by_role(config: LiveAppConfig) -> dict[str, frozenset[str]]:
    """The permissions of app ``config`` that each of the four roles of a business is granted, by role."""
    return {role: permissions_for_role([config], role) for role in Membership.Role.values}
