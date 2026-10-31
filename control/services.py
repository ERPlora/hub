"""Control's commands: the database clusters the hubs' databases are on (round 2026-10-30b of PLAN-DB, decision 1 of
Ioan; tranche S7, part 1).

The Hub admin (``control.admin``) registers, edits, closes and deletes a cluster only through these operations, for
the platform's admins (staff and superuser, ``platform_admin``) or the platform itself; support only reads. Each runs
on control (the registry's scope) and records its event in control's outbox in the same transaction.

- A cluster with a ``secret_name`` is saved only once its app's secret (``<secret_name>/app``) resolves through
  ``base.tenancy.credentials.credentials_for``: the web, where the admin runs, may read only that one (aws#23), so the
  migrator's is never asked from here (the worker and ``hub-migrate`` read it when they first reach the cluster).
- «Close to new hubs» (``control.cluster.close``) takes it out of the placement of new hubs
  (``base.services.place_hub``); the hubs on it stay there.
- Its writer (``host``, ``port``) never changes under the hubs on it: another writer is another server, and the way
  there is moving them (``base.hub.move``). Its PgBouncer, limit, secret and name may change.
- A cluster any hub's row still points at (a purged demo's included: the foreign key protects it), a hub is moving to,
  or that still keeps a hub's moved copy, is never deleted.
- ``control.hub.move`` asks the worker to move a ready hub's own database to another cluster (``base.tenancy.move``):
  only to an open one with room (as a new hub is placed, counting the hubs on their way there), and only a database
  small enough for a copy (:data:`MOVE_MAX_BYTES`, measured on its server: ``control.queries``); a larger one needs
  logical replication, which the Hub does not do yet. Its host answers 503 «maintenance» until the worker is done.

Each locks the cluster's row first, as the placement does, so a hub placed at the same time is either counted or
placed after.
"""

import datetime as dt
from contextlib import contextmanager
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event

from base.registry import internal_only
from base.tenancy.credentials import APP, CredentialsUnavailable, credentials_for
from control import events, queries
from control.models import Cluster, Hub, HubDue, LeftoverDatabase, MovedCopy
from control.schemas import (
    ClusterDeletedOut,
    ClusterIdIn,
    ClusterIn,
    ClusterOut,
    ClusterUpdateIn,
    HubIdIn,
    HubMoveIn,
    HubMoveOut,
)

#: What a cluster is registered with (``ClusterIn``), in the model's own names.
CLUSTER_FIELDS = tuple(ClusterIn.model_fields)
#: Which server it is: never changed under the hubs on it.
WRITER_FIELDS = ("host", "port")
#: The largest database a move copies (``pg_dump``/``pg_restore``, its hub closed meanwhile): a few minutes' work. A
#: larger one needs logical replication, which the Hub does not do yet.
MOVE_MAX_BYTES = 512 * 1024 * 1024


def platform_admin_only(ctx: OperationContext) -> None:
    """The platform, or one of its admins in the Hub admin (staff and superuser); support and customers are refused."""
    actor = ctx.actor
    if getattr(actor, "is_staff", False) and getattr(actor, "is_superuser", False):
        return
    internal_only(ctx)


def living_hubs(cluster: Cluster):
    """The hubs on ``cluster`` that still have, or will have, a database there: all but the purged demos."""
    return Hub.objects.filter(cluster=cluster).exclude(status=Hub.Status.PURGED)


def _holds_anything(cluster: Cluster) -> bool:
    """Whether a database of a hub is, or is about to be, on ``cluster``: a living hub, one on its way there, or a
    copy or a leftover of a move kept there."""
    return (
        living_hubs(cluster).exists()
        or Hub.objects.filter(moving_to=cluster).exists()
        or MovedCopy.objects.filter(cluster=cluster).exists()
        or LeftoverDatabase.objects.filter(cluster=cluster).exists()
    )


def cluster_answer(cluster: Cluster) -> dict:
    """``cluster`` as its operations answer it (``ClusterOut``), with the hubs on it."""
    return {field: getattr(cluster, field) for field in CLUSTER_FIELDS} | {
        "id": cluster.pk,
        "hubs": living_hubs(cluster).count(),
    }


def _locked(cluster_id: UUID) -> Cluster:
    cluster = Cluster.objects.select_for_update().filter(pk=cluster_id).first()
    if cluster is None:
        raise NotFound(gettext("No cluster has this id."))
    return cluster


def _name_taken(name: str) -> Conflict:
    message = gettext("Another cluster is already called %(name)s.") % {"name": name}
    return Conflict(message, code="control.cluster_name_taken", fields={"name": message})


def _secret_resolves(secret_name: str) -> None:
    """Refuse ``secret_name`` unless its app's secret can be read and has its user and password."""
    if not secret_name:
        return
    try:
        credentials_for(Cluster(secret_name=secret_name), APP)
    except CredentialsUnavailable as failed:
        message = gettext("This secret does not resolve: %(reason)s") % {"reason": failed}
        raise InvalidPayload(message, code="control.cluster_secret_unavailable", fields={"secret_name": message}) from None


def _saved(cluster: Cluster, *, update_fields: list[str] | None = None) -> None:
    """Save ``cluster`` in a savepoint; its name is its only unique column a valid ``ClusterIn`` can break (the id is
    a fresh UUIDv7, the bounds are the schema's), so a refusal of the database is another cluster with that name,
    taken before or at the same time."""
    try:
        with atomic():
            cluster.save(update_fields=update_fields)
    except IntegrityError:
        raise _name_taken(cluster.name) from None


def _record(ctx: OperationContext, name: str, cluster: Cluster, cluster_id: UUID | None = None) -> None:
    record_event(ctx, name, {"id": str(cluster_id or cluster.pk), "name": cluster.name})


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation("control.cluster.create", kind="command", permission=None, input=ClusterIn, output=ClusterOut, ai=INTERNAL)
def cluster_create(ctx: OperationContext, data: ClusterIn) -> dict:
    """Register a cluster, open or closed, with its limit of hubs; its secret, if it names one, must resolve first."""
    platform_admin_only(ctx)
    _secret_resolves(data.secret_name)
    cluster = Cluster(**data.model_dump())
    _saved(cluster)
    _record(ctx, events.CLUSTER_CREATED, cluster)
    return cluster_answer(cluster)


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.cluster.update", kind="command", permission=None, input=ClusterUpdateIn, output=ClusterOut, ai=INTERNAL
)
def cluster_update(ctx: OperationContext, data: ClusterUpdateIn) -> dict:
    """Edit a cluster: its name, PgBouncer, whether it is open, its limit and its secret (a new one must resolve); its
    writer only while no hub is on it."""
    platform_admin_only(ctx)
    cluster = _locked(data.id)
    wanted = data.model_dump(include=set(CLUSTER_FIELDS))
    changed = [field for field in CLUSTER_FIELDS if getattr(cluster, field) != wanted[field]]
    if not changed:
        return cluster_answer(cluster)
    moved = [field for field in WRITER_FIELDS if field in changed]
    if moved and _holds_anything(cluster):
        message = gettext(
            "The databases of its hubs are on this writer: move them to another cluster before changing it."
        )
        raise Conflict(message, code="control.cluster_holds_hubs", fields=dict.fromkeys(moved, message))
    if "secret_name" in changed:
        _secret_resolves(wanted["secret_name"])
    for field in changed:
        setattr(cluster, field, wanted[field])
    _saved(cluster, update_fields=changed)
    _record(ctx, events.CLUSTER_UPDATED, cluster)
    return cluster_answer(cluster)


# Not an assistant tool: the platform's admins, in the Hub admin («Close to new hubs»).
@operation("control.cluster.close", kind="command", permission=None, input=ClusterIdIn, output=ClusterOut, ai=INTERNAL)
def cluster_close(ctx: OperationContext, data: ClusterIdIn) -> dict:
    """Close a cluster to new hubs: none is placed on it from now on; the ones on it stay. A closed one stays so."""
    platform_admin_only(ctx)
    cluster = _locked(data.id)
    if cluster.is_open:
        cluster.is_open = False
        cluster.save(update_fields=["is_open"])
        _record(ctx, events.CLUSTER_CLOSED, cluster)
    return cluster_answer(cluster)


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.cluster.delete", kind="command", permission=None, input=ClusterIdIn, output=ClusterDeletedOut, ai=INTERNAL
)
def cluster_delete(ctx: OperationContext, data: ClusterIdIn) -> dict:
    """Delete a cluster that no hub's row points at; one that holds any is refused with how many."""
    platform_admin_only(ctx)
    cluster = _locked(data.id)
    held = Hub.objects.filter(Q(cluster=cluster) | Q(moving_to=cluster)).count()
    if held:
        raise Conflict(
            ngettext(
                "%(count)d hub is on this cluster or moving to it: a cluster is only deleted once no hub is.",
                "%(count)d hubs are on this cluster or moving to it: a cluster is only deleted once no hub is.",
                held,
            )
            % {"count": held},
            code="control.cluster_holds_hubs",
        )
    kept = MovedCopy.objects.filter(cluster=cluster).count() + LeftoverDatabase.objects.filter(cluster=cluster).count()
    if kept:
        raise Conflict(
            ngettext(
                "%(count)d database left behind by a move is still kept on this cluster: it is deleted once it is "
                "dropped.",
                "%(count)d databases left behind by moves are still kept on this cluster: it is deleted once they are "
                "dropped.",
                kept,
            )
            % {"count": kept},
            code="control.cluster_holds_hubs",
        )
    cluster.delete()
    _record(ctx, events.CLUSTER_DELETED, cluster, data.id)
    return {"id": data.id}


def _move_refused(message: str, code: str) -> Conflict:
    return Conflict(message, code=code)


def _room_for_one_more(cluster: Cluster) -> bool:
    """Whether ``cluster`` takes one more hub: its living hubs and the ones on their way there, under its limit."""
    if cluster.max_hubs == 0:
        return True
    taken = living_hubs(cluster).count() + Hub.objects.filter(moving_to=cluster).count()
    return taken < cluster.max_hubs


# Not an assistant tool: the platform's admins, in the Hub admin («Move to cluster…»).
@operation("control.hub.move", kind="command", permission=None, input=HubMoveIn, output=HubMoveOut, ai=INTERNAL)
def hub_move(ctx: OperationContext, data: HubMoveIn) -> dict:
    """Ask the worker to move the ready hub ``data.hub``'s own database to the cluster ``data.cluster``."""
    platform_admin_only(ctx)
    hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=data.hub).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    target = _locked(data.cluster)
    if hub.status != Hub.Status.READY or not hub.db_name:
        raise _move_refused(
            gettext("Only a ready hub with a database of its own moves."), "control.hub_not_movable"
        )
    if hub.is_demo:
        raise _move_refused(gettext("A demo does not move: it ends on its own."), "control.hub_is_demo")
    if hub.moving_to_id is not None:
        raise _move_refused(gettext("This hub is already moving."), "control.hub_moving")
    if hub.cluster_id == target.pk:
        raise _move_refused(gettext("This hub is on that cluster already."), "control.hub_already_there")
    if not target.is_open:
        raise _move_refused(gettext("That cluster is closed to new hubs."), "control.cluster_closed")
    if not _room_for_one_more(target):
        raise _move_refused(gettext("That cluster has no room for another hub."), "control.cluster_full")
    size = queries._measure(hub.cluster, [hub.db_name]).get(hub.db_name)
    if size is None:
        raise _move_refused(
            gettext("The database of this hub is not on its server: there is nothing to move."),
            "control.hub_database_missing",
        )
    if size > MOVE_MAX_BYTES:
        raise _move_refused(
            gettext("This hub's database is too large to move with a copy: it needs logical replication."),
            "control.hub_too_large",
        )
    origin = hub.cluster_id
    hub.moving_to = target
    hub.last_error = ""
    hub.save(update_fields=["moving_to", "last_error", "updated_at"])
    record_event(
        ctx,
        events.HUB_MOVE_REQUESTED,
        {"id": str(hub.pk), "slug": hub.slug, "from": str(origin) if origin else "", "to": str(target.pk)},
    )
    return {"id": hub.pk, "slug": hub.slug, "cluster": origin, "moving_to": target.pk}


# Not an assistant tool: the platform's admins, in the Hub admin («Cancel the move»).
@operation(
    "control.hub.move_cancel", kind="command", permission=None, input=HubIdIn, output=HubMoveOut, ai=INTERNAL
)
def hub_move_cancel(ctx: OperationContext, data: HubIdIn) -> dict:
    """Ask the worker to undo the move of ``data.id``, started or not: its note is marked to be undone (made, with the
    origin's schema record, if the worker had not started); the worker puts the hub back on its origin."""
    from base.tenancy import names
    from base.tenancy.connections import control_name

    platform_admin_only(ctx)
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    if hub.moving_to_id is None:
        raise _move_refused(gettext("This hub is not moving."), "control.hub_not_moving")
    note = MovedCopy.objects.filter(hub=hub, moved_at__isnull=True).first()
    if note is None:
        MovedCopy.objects.update_or_create(
            cluster_id=hub.cluster_id,
            db_name=names.moved_db_name(control_name(), hub.id),
            defaults={
                "hub": hub,
                "moved_at": None,
                "undoing": True,
                "schema_state": hub.schema_state,
                "schema_apps": hub.schema_apps,
            },
        )
    else:
        note.undoing = True
        note.save(update_fields=["undoing"])
    hub.last_error = "move_cancelled: the move was cancelled in the Hub admin."
    hub.save(update_fields=["last_error", "updated_at"])
    record_event(ctx, events.HUB_MOVE_CANCEL_REQUESTED, {"id": str(hub.pk), "slug": hub.slug})
    return {"id": hub.pk, "slug": hub.slug, "cluster": hub.cluster_id, "moving_to": hub.moving_to_id}


# ── The worker's side of a move (``base.tenancy.move``): no operations, the platform's own steps on control ─────────


class MoveTaken(RuntimeError):
    """The move is no longer this worker's: its lease went to another, the hub no longer moves to that cluster (another
    worker switched or undid it) or it was asked to be undone. Nothing more is written for it here."""


@contextmanager
def _control_transaction():
    """A transaction of control's own, whatever context the worker runs in."""
    from base.tenancy.context import use_control

    with use_control(), atomic():
        yield


def hubs_moving() -> list[UUID]:
    """The hubs asked to move (or whose move is being undone), the longest asked first."""
    return list(Hub.objects.filter(moving_to__isnull=False).order_by("updated_at", "pk").values_list("pk", flat=True))


def moving_row(hub_id: UUID) -> Hub | None:
    """``hub_id``'s row with the cluster it is on and the one it is moving to, as it is now."""
    return Hub.objects.select_related("cluster", "moving_to").filter(pk=hub_id).first()


def _ours(hub: Hub, target_id: UUID, owner: str, *, forward: bool) -> None:
    """Refuse (``MoveTaken``) unless ``owner`` holds ``hub``'s lease, it still moves to ``target_id`` and, going
    forward, nobody asked to undo it."""
    if hub.moving_to_id != target_id:
        raise MoveTaken(f"{hub.slug} no longer moves to {target_id}: another worker finished or undid it.")
    # Whoever holds it: one that ran out and nobody took is still ``owner``'s (``base.services.renew_lease`` too).
    if not HubDue.objects.filter(pk=hub.pk, lease_owner=owner).exists():
        raise MoveTaken(f"the lease of {hub.slug} is no longer {owner}'s.")
    if forward and MovedCopy.objects.filter(hub=hub, moved_at__isnull=True, undoing=True).exists():
        raise MoveTaken(f"the move of {hub.slug} is to be undone.")


def still_ours(hub_id: UUID, target_id: UUID, owner: str, *, forward: bool = True) -> None:
    """Before a drop, a rename or the switch: ``MoveTaken`` unless the move is still ``owner``'s (see :func:`_ours`)."""
    hub = Hub.objects.filter(pk=hub_id).first()
    if hub is None:
        raise MoveTaken(f"the hub {hub_id} is gone.")
    _ours(hub, target_id, owner, forward=forward)


def attributed(cluster_id: UUID | None, db_name: str, *, besides: UUID | None = None) -> bool:
    """Whether control says ``db_name`` on ``cluster_id`` is a hub's database: one on that cluster (whichever), or one
    moving to it other than ``besides`` (the hub whose move asks)."""
    moving_there = Q(moving_to_id=cluster_id) & ~Q(pk=besides) if besides is not None else Q(moving_to_id=cluster_id)
    return Hub.objects.filter(Q(cluster_id=cluster_id) | moving_there, db_name=db_name).exists()


def move_finished(
    hub_id: UUID, target_id: UUID, origin: UUID | None, copy_name: str, at: dt.datetime, *, owner: str
) -> None:
    """Switch ``hub_id`` to ``target_id`` and date its copy on ``origin`` (none: the settings' own server), in one
    transaction on its locked row; ``MoveTaken`` when the move is no longer ``owner``'s (nothing written then). The
    schema record is the destination's, which its migration wrote."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _ours(hub, target_id, owner, forward=True)
        hub.cluster_id = target_id
        hub.moving_to = None
        hub.last_error = ""
        hub.save(update_fields=["cluster", "moving_to", "last_error", "updated_at"])
        MovedCopy.objects.update_or_create(
            cluster_id=origin,
            db_name=copy_name,
            defaults={"hub_id": hub_id, "moved_at": at, "undoing": False, "schema_state": "", "schema_apps": None},
        )


def move_undone(hub_id: UUID, origin: UUID | None, copy_name: str, error: str) -> None:
    """The move of ``hub_id`` was undone: ready where it was, with why, its note forgotten and the schema record of its
    origin given back (the destination's migration wrote its own meanwhile)."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        note = MovedCopy.objects.filter(hub=hub, cluster_id=origin, db_name=copy_name, moved_at__isnull=True).first()
        fields = ["moving_to", "last_error", "updated_at"]
        if note is not None and note.schema_state:
            hub.schema_state, hub.schema_apps = note.schema_state, note.schema_apps or {}
            fields += ["schema_state", "schema_apps"]
        hub.moving_to = None
        hub.last_error = error[:2000]
        hub.save(update_fields=fields)
        if note is not None:
            note.delete()


def move_stuck(hub_id: UUID, error: str) -> None:
    """The move of ``hub_id`` failed and could not be undone yet: still moving (its host closed), its note marked to be
    undone on the next pass, never taken forward."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(last_error=error[:2000], updated_at=timezone.now())
        MovedCopy.objects.filter(hub_id=hub_id, moved_at__isnull=True).update(undoing=True)


def pending_copy(hub_id: UUID) -> MovedCopy | None:
    """The note of ``hub_id``'s move in course (no ``moved_at`` yet), if any."""
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
            note.hub_id, note.moved_at, note.undoing = hub_id, None, False
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
