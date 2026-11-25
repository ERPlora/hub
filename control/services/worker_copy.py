"""The worker's side of a separate copy (``base.tenancy.restore``): under the row's own lease."""

import datetime as dt
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

from control.models.copies import RestoredCopy
from control.services.worker_move import MoveTaken, _control_transaction


def copies_to_make() -> list[UUID]:
    """The separate copies still to make, the longest asked first."""
    return list(
        RestoredCopy.objects.filter(status=RestoredCopy.Status.COPYING)
        .order_by("asked_at", "pk")
        .values_list("pk", flat=True)
    )


def _claim(model, row_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str, status: str) -> bool:  # noqa: PLR0913, PLR0917
    """Take for ``owner`` the lease of the row ``row_id`` of ``model`` (a separate copy or a recovery from one) while it
    is ``status``; whether it was taken (not when someone else holds it, or it is no longer ``status``, or gone)."""
    with _control_transaction():
        row = (
            model.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now), pk=row_id, status=status)
            .first()
        )
        if row is None:
            return False
        model.objects.filter(pk=row_id).update(lease_owner=owner, lease_until=now + lease)
    return True


def _release(model, row_id: UUID, owner: str) -> None:
    """``owner``'s lease of the row ``row_id`` of ``model`` given back (a stopped worker's: the next one goes on at
    once)."""
    model.objects.filter(pk=row_id, lease_owner=owner).update(lease_owner="", lease_until=None)


def claim_copy(copy_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str) -> RestoredCopy | None:
    """Take for ``owner`` the lease of the separate copy ``copy_id`` still to make, with its hub and clusters; ``None``
    when someone else holds it (or it is made, failed or gone)."""
    if not _claim(RestoredCopy, copy_id, now, lease, owner, RestoredCopy.Status.COPYING):
        return None
    return RestoredCopy.objects.select_related("hub", "cluster", "source").get(pk=copy_id)


def renew_copy(copy_id: UUID, lease: dt.timedelta, owner: str) -> None:
    """``owner``'s lease of the copy ``copy_id`` renewed from now, while it is still ``owner``'s."""
    RestoredCopy.objects.filter(pk=copy_id, lease_owner=owner).update(lease_until=timezone.now() + lease)


def _making(copy_id: UUID, owner: str, *, lock: bool = False) -> RestoredCopy:
    rows = RestoredCopy.objects.select_for_update() if lock else RestoredCopy.objects
    row = rows.filter(pk=copy_id).first()
    if row is None or row.status != RestoredCopy.Status.COPYING or row.lease_owner != owner:
        raise MoveTaken(f"the separate copy {copy_id} is no longer {owner}'s to make.")
    return row


def still_making(copy_id: UUID, owner: str) -> None:
    """Before a drop or the end of a separate copy: ``MoveTaken`` unless it is still ``owner``'s to make."""
    _making(copy_id, owner)


def copy_made(copy_id: UUID, at: dt.datetime, owner: str) -> None:
    """The separate copy ``copy_id`` is made: dated, its temporary cluster let go and its lease given back, on its
    locked row, only if it is still ``owner``'s (``MoveTaken`` otherwise: nothing written)."""
    with _control_transaction():
        _making(copy_id, owner, lock=True)
        RestoredCopy.objects.filter(pk=copy_id).update(
            status=RestoredCopy.Status.MADE, made_at=at, source=None, last_error="", lease_owner="", lease_until=None
        )


def copy_failed(copy_id: UUID, error: str, owner: str) -> None:
    """The separate copy ``copy_id`` could not be made (nothing of it is left): why, its temporary cluster let go and
    its lease given back, only if it is still ``owner``'s (``MoveTaken`` otherwise: nothing written)."""
    with _control_transaction():
        _making(copy_id, owner, lock=True)
        RestoredCopy.objects.filter(pk=copy_id).update(
            status=RestoredCopy.Status.FAILED, source=None, last_error=error, lease_owner="", lease_until=None
        )


def release_copy(copy_id: UUID, owner: str) -> None:
    """``owner``'s lease of the copy ``copy_id`` given back (a stopped worker's: the next one goes on at once)."""
    _release(RestoredCopy, copy_id, owner)


def aside_copies_due(before: dt.datetime) -> list[RestoredCopy]:
    """The separate copies past their days by ``before``: made by then, or failed and asked by then (nothing of those
    is left but the row); never one still to make. The oldest first, with their cluster."""
    return list(
        RestoredCopy.objects.select_related("cluster")
        .filter(
            Q(status=RestoredCopy.Status.MADE, made_at__lte=before)
            | Q(status=RestoredCopy.Status.FAILED, asked_at__lte=before)
        )
        .order_by("asked_at", "pk")
    )


def forget_aside_copy(copy_id: UUID) -> None:
    """The separate copy ``copy_id`` is gone: its row goes too."""
    with _control_transaction():
        RestoredCopy.objects.filter(pk=copy_id).delete()
