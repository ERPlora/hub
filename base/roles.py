"""What a role of the business (``base.models.roles.BusinessRole``) allows of the apps of today, without the ORM.

A role keeps the state of every permission of the apps it was saved with. An app none of whose permissions it names
(one turned on after it was saved) gives what it gives the basic role the role was duplicated from; a permission an app
added after it was saved is off. Both are left to review, so a role never changes without its owner seeing it.
"""

from collections.abc import Collection, Mapping

ON = "on"
#: Done only if a manager approves it there and then with their PIN or badge (``base.approvals``).
APPROVAL = "approval"
OFF = "off"


def basic_state(permission: str, given: Collection[str], approvable: Collection[str]) -> str:
    """What a basic role that holds ``given`` does with ``permission``: it does it, it does it with a manager's approval
    when an app names one of its commands as approvable (``approvable``), or it does not."""
    if permission in given:
        return ON
    return APPROVAL if permission in approvable else OFF


def effective(
    states: Mapping[str, str],
    apps: Mapping[str, Collection[str]],
    given: Collection[str],
    approvable: Collection[str] = frozenset(),
) -> dict[str, str]:
    """Each permission of ``apps`` (``{app: its permissions}``) with what a role saved with ``states`` does with it.

    ``given`` and ``approvable`` are its origin's, for the apps it was not saved with."""
    allowed: dict[str, str] = {}
    for permissions in apps.values():
        if any(permission in states for permission in permissions):
            allowed.update({permission: states.get(permission, OFF) for permission in permissions})
        else:
            allowed.update({permission: basic_state(permission, given, approvable) for permission in permissions})
    return allowed


def to_review(states: Mapping[str, str], apps: Mapping[str, Collection[str]]) -> frozenset[str]:
    """The permissions of ``apps`` a role saved with ``states`` has not seen: every one of an app turned on after it
    was saved, and each one an app added since."""
    return frozenset(
        permission for permissions in apps.values() for permission in permissions if permission not in states
    )
