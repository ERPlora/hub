"""The worker's side of a recovery from a separate copy (``base.tenancy.recovery``): its own lease."""

import datetime as dt
from uuid import UUID

from django.utils import timezone

from control.models import CopyRecovery, RestoredCopy
from control.services.worker_copy import _claim, _release
from control.services.worker_move import MoveTaken, _control_transaction


def recoveries_due() -> list[UUID]:
    """The recoveries still to do, of copies that are made, the longest asked first."""
    return list(
        CopyRecovery.objects.filter(status=CopyRecovery.Status.ASKED, copy__status=RestoredCopy.Status.MADE)
        .order_by("asked_at", "pk")
        .values_list("pk", flat=True)
    )


def claim_recovery(recovery_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str) -> CopyRecovery | None:
    """Take for ``owner`` the lease of the recovery ``recovery_id`` still to do, with its copy, its hub and their
    clusters; ``None`` when someone else holds it (or it is done, failed or gone)."""
    if not _claim(CopyRecovery, recovery_id, now, lease, owner, CopyRecovery.Status.ASKED):
        return None
    return CopyRecovery.objects.select_related("copy", "copy__cluster", "copy__hub", "copy__hub__cluster").get(
        pk=recovery_id
    )


def still_recovering(recovery_id: UUID, lease: dt.timedelta, owner: str) -> None:
    """Before each record a recovery creates: its lease renewed from now while it is still ``owner``'s to do;
    ``MoveTaken`` otherwise (nothing renewed)."""
    renewed = CopyRecovery.objects.filter(
        pk=recovery_id, status=CopyRecovery.Status.ASKED, lease_owner=owner
    ).update(lease_until=timezone.now() + lease)
    if not renewed:
        raise MoveTaken(f"the recovery {recovery_id} is no longer {owner}'s to do.")


def _recovery_ended(recovery_id: UUID, owner: str, **ended) -> None:
    """The recovery ``recovery_id`` ended as ``ended`` says, its lease given back, on its locked row, only if it is
    still ``owner``'s to do (``MoveTaken`` otherwise: nothing written)."""
    with _control_transaction():
        row = CopyRecovery.objects.select_for_update().filter(pk=recovery_id).first()
        if row is None or row.status != CopyRecovery.Status.ASKED or row.lease_owner != owner:
            raise MoveTaken(f"the recovery {recovery_id} is no longer {owner}'s to do.")
        CopyRecovery.objects.filter(pk=recovery_id).update(lease_owner="", lease_until=None, **ended)


def recovery_done(recovery_id: UUID, results: list[dict], at: dt.datetime, owner: str) -> None:
    """The recovery ``recovery_id`` is done: what each app gave back (``results``), dated."""
    _recovery_ended(
        recovery_id, owner, status=CopyRecovery.Status.DONE, results=results, done_at=at, last_error=""
    )


def recovery_failed(recovery_id: UUID, error: str, results: list[dict], at: dt.datetime, owner: str) -> None:
    """The recovery ``recovery_id`` stopped at ``error``: what it gave back until then (``results``), dated."""
    _recovery_ended(
        recovery_id, owner, status=CopyRecovery.Status.FAILED, results=results, done_at=at, last_error=error
    )


def release_recovery(recovery_id: UUID, owner: str) -> None:
    """``owner``'s lease of the recovery ``recovery_id`` given back: a recovery left for later (its business was being
    moved or restored) or stopped goes on at the next pass."""
    _release(CopyRecovery, recovery_id, owner)
