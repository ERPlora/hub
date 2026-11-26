"""The worker's side of a move (``base.tenancy.move``): no operations, the platform's own steps on control."""

import datetime as dt
from contextlib import contextmanager
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from live.errors import Conflict
from live.operations import atomic

from base.business import zone_of
from control.models.copies import LeftoverDatabase, MovedCopy
from control.models.hubs import Hub, HubDue
from control.services.clusters import _locked
from control.services.move import _movable, night_start


class MoveTaken(RuntimeError):
    """The move is no longer this worker's: its lease went to another, the hub no longer moves to that cluster (another
    worker switched or undid it) or it was asked to be undone. Nothing more is written for it here."""


@contextmanager
def _control_transaction():
    """A transaction of control's own, whatever context the worker runs in."""
    from base.tenancy.context import use_control

    with use_control(), atomic():
        yield


def moves_scheduled_due(now: dt.datetime) -> list[UUID]:
    """The hubs whose move asked for the night is due by ``now``, the earliest first."""
    due = Hub.objects.filter(move_scheduled_to__isnull=False, move_scheduled_for__lte=now)
    return list(due.order_by("move_scheduled_for", "pk").values_list("pk", flat=True))


def start_scheduled_move(hub_id: UUID, now: dt.datetime, *, owner: str) -> bool:
    """Start the move of ``hub_id`` asked for its night, in one transaction on its locked row, while ``owner`` holds its
    lease (``MoveTaken`` otherwise, nothing written): due and in its night, it moves from now on (``moving_to``); due
    by its day, it waits for its next night; one a move now would be refused ends with why (``last_error``), nothing
    closed. Whether it started."""
    with _control_transaction():
        hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=hub_id).first()
        if hub is None or hub.move_scheduled_to_id is None or hub.move_scheduled_for > now:
            return False
        _held(hub, owner, forward=False, lock=True)
        starts = night_start(now, zone_of(hub.timezone))
        if starts != now:
            hub.move_scheduled_for = starts
            hub.save(update_fields=["move_scheduled_for", "updated_at"])
            return False
        target = _locked(hub.move_scheduled_to_id)
        hub.move_scheduled_to, hub.move_scheduled_for = None, None
        fields = ["move_scheduled_to", "move_scheduled_for", "last_error", "updated_at"]
        try:
            _movable(hub, target)
        except Conflict as refused:
            hub.last_error = f"move_not_started: {refused.code}: {refused.message}"[:2000]
            hub.save(update_fields=fields)
            return False
        hub.moving_to = target
        hub.last_error = ""
        hub.save(update_fields=[*fields, "moving_to"])
        return True


def hubs_moving() -> list[UUID]:
    """The hubs asked to move (or whose move is being undone), the longest asked first."""
    return list(Hub.objects.filter(moving_to__isnull=False).order_by("updated_at", "pk").values_list("pk", flat=True))


def hubs_restoring() -> list[UUID]:
    """The hubs asked to be restored (or whose restore is being undone), the longest asked first."""
    return list(
        Hub.objects.filter(restoring_from__isnull=False).order_by("updated_at", "pk").values_list("pk", flat=True)
    )


def moving_row(hub_id: UUID) -> Hub | None:
    """``hub_id``'s row with the cluster it is on and the one it is moving to or restored from, as it is now."""
    return Hub.objects.select_related("cluster", "moving_to", "restoring_from").filter(pk=hub_id).first()


def _ours(hub: Hub, target_id: UUID, owner: str, *, forward: bool, lock: bool = False) -> None:
    """Refuse (``MoveTaken``) unless ``owner`` holds ``hub``'s lease, it still moves to ``target_id`` and, going
    forward, nobody asked to undo it. ``lock``: the lease's row is locked too (the switch, in its transaction)."""
    if hub.moving_to_id != target_id:
        raise MoveTaken(f"{hub.slug} no longer moves to {target_id}: another worker finished or undid it.")
    _held(hub, owner, forward=forward, lock=lock)


def _restoring_ours(hub: Hub, source_id: UUID, owner: str, *, forward: bool, lock: bool = False) -> None:
    """:func:`_ours` for a restore: it is still restored from ``source_id``."""
    if hub.restoring_from_id != source_id:
        raise MoveTaken(f"{hub.slug} is no longer restored from {source_id}: another worker finished or undid it.")
    _held(hub, owner, forward=forward, lock=lock)


def _held(hub: Hub, owner: str, *, forward: bool, lock: bool) -> None:
    # Whoever holds it: one that ran out and nobody took is still ``owner``'s (``base.services.reset.renew_lease`` too).
    leases = HubDue.objects.select_for_update() if lock else HubDue.objects
    if not leases.filter(pk=hub.pk, lease_owner=owner).exists():
        raise MoveTaken(f"the lease of {hub.slug} is no longer {owner}'s.")
    if forward and hub.move_undo_asked_at is not None:
        raise MoveTaken(f"the copy of {hub.slug} is to be undone.")


def still_ours(hub_id: UUID, target_id: UUID, owner: str, *, forward: bool = True) -> None:
    """Before a drop, a rename or the switch: ``MoveTaken`` unless the move is still ``owner``'s (see :func:`_ours`)."""
    hub = Hub.objects.filter(pk=hub_id).first()
    if hub is None:
        raise MoveTaken(f"the hub {hub_id} is gone.")
    _ours(hub, target_id, owner, forward=forward)


def still_restoring(hub_id: UUID, source_id: UUID, owner: str, *, forward: bool = True) -> None:
    """Before a drop, a rename or the end of a restore: ``MoveTaken`` unless it is still ``owner``'s
    (:func:`_restoring_ours`)."""
    hub = Hub.objects.filter(pk=hub_id).first()
    if hub is None:
        raise MoveTaken(f"the hub {hub_id} is gone.")
    _restoring_ours(hub, source_id, owner, forward=forward)


def attributed(cluster_id: UUID | None, db_name: str, *, besides: UUID | None = None) -> bool:
    """Whether control says ``db_name`` on ``cluster_id`` is a hub's database: one on that cluster (whichever), or one
    moving to it other than ``besides`` (the hub whose move asks)."""
    moving_there = Q(moving_to_id=cluster_id) & ~Q(pk=besides) if besides is not None else Q(moving_to_id=cluster_id)
    return Hub.objects.filter(Q(cluster_id=cluster_id) | moving_there, db_name=db_name).exists()


def move_finished(  # noqa: PLR0913
    hub_id: UUID, target_id: UUID, origin: UUID | None, copy_name: str, at: dt.datetime, *, owner: str
) -> None:
    """Switch ``hub_id`` to ``target_id`` and date its copy on ``origin`` (none: the settings' own server), in one
    transaction on its locked row; ``MoveTaken`` when the move is no longer ``owner``'s (nothing written then). The
    schema record is the destination's, which its migration wrote."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _ours(hub, target_id, owner, forward=True, lock=True)
        hub.cluster_id = target_id
        hub.moving_to = None
        hub.last_error = ""
        hub.save(update_fields=["cluster", "moving_to", "last_error", "updated_at"])
        _dated(hub_id, origin, copy_name, at)


def _dated(hub_id: UUID, cluster_id: UUID | None, copy_name: str, at: dt.datetime) -> None:
    """The copy ``copy_name`` on ``cluster_id`` left behind at ``at``: its note dated (its days count from then)."""
    MovedCopy.objects.update_or_create(
        cluster_id=cluster_id,
        db_name=copy_name,
        defaults={"hub_id": hub_id, "moved_at": at, "schema_state": "", "schema_apps": None},
    )


def restore_finished(  # noqa: PLR0913
    hub_id: UUID, source_id: UUID, cluster_id: UUID | None, kept_name: str, at: dt.datetime, *, owner: str
) -> None:
    """End the restore of ``hub_id`` and date the database it replaced, kept on its cluster (none: the settings' own
    server), in one transaction on its locked row; ``MoveTaken`` when the restore is no longer ``owner``'s (nothing
    written then). The schema record is the new database's, which its migration wrote."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _restoring_ours(hub, source_id, owner, forward=True, lock=True)
        hub.restoring_from = None
        hub.restore_point = None
        hub.last_error = ""
        hub.save(update_fields=["restoring_from", "restore_point", "last_error", "updated_at"])
        _dated(hub_id, cluster_id, kept_name, at)


def move_undone(hub_id: UUID, origin: UUID | None, copy_name: str, error: str) -> None:
    """The move (or the restore) of ``hub_id`` was undone: ready where it was on its own database, with why, no longer
    asked to be undone, its note forgotten and the schema record of before given back (the migration of the database
    it was copied to wrote its own meanwhile)."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        note = MovedCopy.objects.filter(hub=hub, cluster_id=origin, db_name=copy_name, moved_at__isnull=True).first()
        fields = ["moving_to", "restoring_from", "restore_point", "move_undo_asked_at", "last_error", "updated_at"]
        if note is not None and note.schema_state:
            hub.schema_state, hub.schema_apps = note.schema_state, note.schema_apps or {}
            fields += ["schema_state", "schema_apps"]
        hub.moving_to = None
        hub.restoring_from = None
        hub.restore_point = None
        hub.move_undo_asked_at = None
        hub.last_error = error[:2000]
        hub.save(update_fields=fields)
        if note is not None:
            note.delete()


def move_stuck(hub_id: UUID, error: str) -> None:
    """The move (or the restore) of ``hub_id`` failed and could not be undone yet: still copying (its host closed),
    asked to be undone on the next pass, never taken forward."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(
            last_error=error[:2000], move_undo_asked_at=timezone.now(), updated_at=timezone.now()
        )


def pending_copy(hub_id: UUID) -> MovedCopy | None:
    """The note of ``hub_id``'s move or restore in course (no ``moved_at`` yet), if any."""
    return MovedCopy.objects.select_related("cluster").filter(hub_id=hub_id, moved_at__isnull=True).first()


def copy_pending(hub_id: UUID, cluster_id: UUID | None, db_name: str, *, schema_state: str, schema_apps) -> None:
    """Note, before the rename, that ``hub_id``'s data is about to be in the copy ``db_name`` on ``cluster_id``, and the
    origin's schema record; a note already there (a move cut short) keeps its record."""
    with _control_transaction():
        note, made = MovedCopy.objects.get_or_create(
            cluster_id=cluster_id,
            db_name=db_name,
            defaults={"hub_id": hub_id, "moved_at": None, "schema_state": schema_state, "schema_apps": schema_apps},
        )
        if not made and note.moved_at is not None:
            # A dated row whose copy is gone (the worker dropped the older copy right before): the note takes its place.
            note.hub_id, note.moved_at = hub_id, None
            note.schema_state, note.schema_apps = schema_state, schema_apps
            note.save()


def copies_due(before: dt.datetime) -> list[MovedCopy]:
    """The moved copies left behind by ``before`` (never one whose move still goes on), the oldest first, with their
    cluster."""
    return list(MovedCopy.objects.select_related("cluster").filter(moved_at__lte=before).order_by("moved_at", "pk"))


def forget_copy(cluster_id: UUID | None, db_name: str) -> None:
    """The moved copy ``db_name`` on ``cluster_id`` (none: the settings' own server) is gone: its row goes too."""
    with _control_transaction():
        MovedCopy.objects.filter(cluster_id=cluster_id, db_name=db_name).delete()


def leftover_noted(hub_id: UUID, cluster_id: UUID, db_name: str, at: dt.datetime) -> None:
    """Note that an undone move of ``hub_id`` may have left ``db_name`` on ``cluster_id``: dropped on a later pass."""
    with _control_transaction():
        LeftoverDatabase.objects.update_or_create(
            cluster_id=cluster_id, db_name=db_name, defaults={"hub_id": hub_id, "noted_at": at}
        )


def leftovers() -> list[LeftoverDatabase]:
    """What undone moves may have left on their destinations, the oldest first, with their cluster and hub."""
    return list(LeftoverDatabase.objects.select_related("cluster", "hub", "hub__cluster").order_by("noted_at", "pk"))


def forget_leftover(cluster_id: UUID, db_name: str) -> None:
    with _control_transaction():
        LeftoverDatabase.objects.filter(cluster_id=cluster_id, db_name=db_name).delete()
