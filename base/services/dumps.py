"""The copies of a hub's data (``base.tenancy.dumps``), kept in control.
"""

import datetime as dt
from uuid import UUID

from base.services.provisioning import _control_transaction
from control.models import HubDump


def expired_dumps_forgotten(*, before: dt.datetime) -> int:
    """Forget the copies made before ``before``: the bucket's lifecycle rule deleted them (90 days)."""
    with _control_transaction():
        forgotten, _ = HubDump.objects.filter(created_at__lt=before).delete()
    return forgotten


def dump_key_taken(key: str) -> bool:
    """Whether a copy is already kept at ``key`` (two copies of a hub in the same second get the next second)."""
    from base.tenancy.context import use_control

    with use_control():
        return HubDump.objects.filter(key=key).exists()


def dump_recorded(  # noqa: PLR0913
    hub_id: UUID, *, kind: str, key: str, size: int, created_at: dt.datetime, requested_by: str = ""
) -> HubDump:
    """Keep in control the copy of ``hub_id`` just uploaded to ``key``."""
    with _control_transaction():
        return HubDump.objects.create(
            hub_id=hub_id, kind=kind, key=key, bytes=size, created_at=created_at, requested_by=requested_by[:150]
        )
