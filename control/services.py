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
from control.models import Cluster, Hub, MovedCopy
from control.schemas import ClusterDeletedOut, ClusterIdIn, ClusterIn, ClusterOut, ClusterUpdateIn, HubMoveIn, HubMoveOut

#: What a cluster is registered with (``ClusterIn``), in the model's own names.
CLUSTER_FIELDS = tuple(ClusterIn.model_fields)
#: Which server it is: never changed under the hubs on it.
WRITER_FIELDS = ("host", "port")
#: The largest database a move copies (``pg_dump``/``pg_restore``, its hub closed meanwhile): a few seconds' work. A
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
    if moved and living_hubs(cluster).exists():
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
    kept = MovedCopy.objects.filter(cluster=cluster).count()
    if kept:
        raise Conflict(
            ngettext(
                "%(count)d copy of a hub that moved is kept on this cluster for a few days: it is deleted after it.",
                "%(count)d copies of hubs that moved are kept on this cluster for a few days: it is deleted after them.",
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


# ── The worker's side of a move (``base.tenancy.move``): no operations, the platform's own steps on control ─────────


@contextmanager
def _control_transaction():
    """A transaction of control's own, whatever context the worker runs in."""
    from base.tenancy.context import use_control

    with use_control(), atomic():
        yield


def hubs_moving() -> list[UUID]:
    """The hubs asked to move, the longest asked first."""
    return list(Hub.objects.filter(moving_to__isnull=False).order_by("updated_at", "pk").values_list("pk", flat=True))


def moving_row(hub_id: UUID) -> Hub | None:
    """``hub_id``'s row with the cluster it is on and the one it is moving to, as it is now."""
    return Hub.objects.select_related("cluster", "moving_to").filter(pk=hub_id).first()


def move_finished(hub_id: UUID, origin: UUID | None, copy_name: str, at: dt.datetime) -> None:
    """Switch ``hub_id`` to the cluster it moved to and keep the copy it left on ``origin`` (none: the settings' own
    server), in one transaction: before it the hub is still where it was, after it where it moved."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        hub.cluster_id = hub.moving_to_id
        hub.moving_to = None
        hub.last_error = ""
        hub.save(update_fields=["cluster", "moving_to", "last_error", "updated_at"])
        MovedCopy.objects.update_or_create(
            cluster_id=origin, db_name=copy_name, defaults={"hub_id": hub_id, "moved_at": at}
        )


def move_failed(hub_id: UUID, error: str) -> None:
    """The move of ``hub_id`` failed and was undone: ready where it was, with why."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(moving_to=None, last_error=error[:2000], updated_at=timezone.now())


def move_stuck(hub_id: UUID, error: str) -> None:
    """The move of ``hub_id`` failed and could not be undone yet: still moving (its host closed), tried again."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(last_error=error[:2000], updated_at=timezone.now())


def pending_copy(hub_id: UUID) -> MovedCopy | None:
    """The copy that holds ``hub_id``'s data while its move goes on (no ``moved_at`` yet), if any."""
    return MovedCopy.objects.select_related("cluster").filter(hub_id=hub_id, moved_at__isnull=True).first()


def copy_pending(hub_id: UUID, cluster_id: UUID | None, db_name: str) -> None:
    """Note, before the rename, that ``hub_id``'s data is about to be in the copy ``db_name`` on ``cluster_id``."""
    with _control_transaction():
        MovedCopy.objects.update_or_create(
            cluster_id=cluster_id, db_name=db_name, defaults={"hub_id": hub_id, "moved_at": None}
        )


def copies_due(before: dt.datetime) -> list[MovedCopy]:
    """The moved copies left behind by ``before`` (never one whose move still goes on), the oldest first, with their
    cluster."""
    return list(MovedCopy.objects.select_related("cluster").filter(moved_at__lte=before).order_by("moved_at", "pk"))


def forget_copy(cluster_id: UUID | None, db_name: str) -> None:
    """The moved copy ``db_name`` on ``cluster_id`` (none: the settings' own server) is gone: its row goes too."""
    with _control_transaction():
        MovedCopy.objects.filter(cluster_id=cluster_id, db_name=db_name).delete()
