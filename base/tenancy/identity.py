"""The identity of a hub's database (PLAN-DB §3 and §14.4; plan 2026-10-22-fase-2-tenencia, step 6).

Every hub's database holds one row in ``base_hub_identity`` (``base.models.HubIdentity``): its hub's id, written
when the database is made (:func:`write`). ``use_hub`` checks it the first time a process uses an alias
(:func:`verify`): a database that says it is another hub, or says nothing, is refused (``HubIdentityMismatch``) and
nothing is served from it; one that is its hub is not read again in this process. Outside any operation, on purpose:
it runs before anything of the hub does.
"""

import threading
import uuid

from django.db import DatabaseError, connections

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
    except DatabaseError as error:
        raise HubIdentityMismatch(f"The database of {alias} has no readable identity ({error}): refused.") from error
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
