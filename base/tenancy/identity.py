"""The identity of a hub's database (PLAN-DB §3 and §14.4; plan 2026-10-22-fase-2-tenencia, step 6).

Every hub's database holds one row in ``base_hub_identity`` (``base.models.HubIdentity``): its hub's id, written
when the database is made (:func:`write`). ``use_hub`` checks it the first time a process uses an alias
(:func:`verify`): a database that says it is another hub, or has no identity table, is refused
(``HubIdentityMismatch``) and nothing is served from it; one that is its hub is not read again in this process. A
database that cannot be reached now raises its own ``DatabaseError``: passing, never taken for a mismatch. Outside any
operation, on purpose: it runs before anything of the hub does.
"""

import threading
import uuid

from django.db import ProgrammingError, connections

IDENTITY_TABLE = "base_hub_identity"

#: The aliases this process already checked.
_verified: set[str] = set()
_lock = threading.Lock()


class HubIdentityMismatch(RuntimeError):
    """A hub's database that is not that hub's: nothing is served from it."""


def verify(alias: str, hub_id: uuid.UUID) -> None:
    """Refuse ``alias`` unless its database says it is the hub ``hub_id``; once per process and alias."""
    if alias in _verified:
        return
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute(f"SELECT hub_id FROM {IDENTITY_TABLE}")
            found = [row[0] for row in cursor.fetchall()]
    except ProgrammingError as error:
        # No identity table: the database is no hub's (a template, a database that was never provisioned).
        raise HubIdentityMismatch(f"The database of {alias} has no identity ({error}): refused.") from error
    # Any other DatabaseError (unreachable, a failover) goes up as it came: a passing failure, not a mismatch, and
    # the alias is read again next time.
    if found != [hub_id]:
        raise HubIdentityMismatch(
            f"The database of {alias} says it is {[str(value) for value in found]}, not the hub {hub_id}: refused."
        )
    with _lock:
        _verified.add(alias)


def write(alias: str, hub_id: uuid.UUID) -> None:
    """Write the identity of the database behind ``alias``, made for the hub ``hub_id`` (its provisioning; S2)."""
    with connections[alias].cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {IDENTITY_TABLE} (hub_id) VALUES (%s) ON CONFLICT DO NOTHING",
            [hub_id],
        )
