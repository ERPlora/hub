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
- ``control.hub.restore`` asks the worker to put a ready hub's database back as it was at a moment (hub#1198,
  ``base.tenancy.restore``): from the copy of it on a temporary cluster (a point-in-time restore of its own, registered
  closed to new hubs, with no hub on it), small enough for a copy. Its host answers 503 «maintenance» until the worker
  is done. The worker refuses it, nothing changed, while the hub's database has a production VeriFactu record the copy
  lacks or has otherwise (it reads both with the migrator, which the web does not have; it only reads).
- ``control.hub.restore_aside`` asks the worker for a separate copy of a ready hub's database as it was at a moment
  (hub#1213, layer 1; ``base.tenancy.restore``), from the same copy and under the same conditions, made on the hub's
  own cluster as ``<control>_copy_<hex>`` (a ``RestoredCopy`` row): the business is never closed nor changed, so its
  fiscal records stop nothing, and the copy is no business, closed to the app: nothing in it reaches the tax authority.

Each locks the cluster's row first, as the placement does, so a hub placed at the same time is either counted or
placed after.

``control.freeze.set`` freezes the platform for a database upgrade with Blue/Green, or lifts its freeze (hub#930;
PLAN-DB round 2026-11-04e, «Congelar»): while frozen the worker makes, drops and moves no database and makes no app's
tables, and ``migrate_hubs`` refuses to start, while the relay, the tasks and the sends to the AEAT go on. It is
idempotent: frozen again, the freeze in course is kept as it was (who, since when, why); lifted again, nothing changes.
Only a real change records its event. Its one row is locked first, so two admins at once change it once.
"""

import datetime as dt
import uuid
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
from base.tenancy import names
from base.tenancy.connections import control_name
from base.tenancy.credentials import APP, CredentialsUnavailable, credentials_for
from control import events, queries
from control.models import (
    Cluster,
    CopyRecovery,
    Freeze,
    Hub,
    HubDue,
    LeftoverDatabase,
    MovedCopy,
    RestoredCopy,
)
from control.schemas import (
    ClusterDeletedOut,
    ClusterIdIn,
    ClusterIn,
    ClusterOut,
    ClusterUpdateIn,
    CopyRecoverIn,
    CopyRecoveryOut,
    FreezeIn,
    FreezeOut,
    HubIdIn,
    HubMoveIn,
    HubMoveOut,
    HubRestoreIn,
    HubRestoreOut,
    RestoredCopyOut,
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
    copy or a leftover of a move kept there, a separate copy there or one still to make from it."""
    return (
        living_hubs(cluster).exists()
        or Hub.objects.filter(Q(moving_to=cluster) | Q(restoring_from=cluster)).exists()
        or MovedCopy.objects.filter(cluster=cluster).exists()
        or LeftoverDatabase.objects.filter(cluster=cluster).exists()
        or RestoredCopy.objects.filter(Q(cluster=cluster) | Q(source=cluster)).exists()
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
    held = Hub.objects.filter(Q(cluster=cluster) | Q(moving_to=cluster) | Q(restoring_from=cluster)).count()
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
    aside = RestoredCopy.objects.filter(Q(cluster=cluster) | Q(source=cluster)).count()
    if aside:
        raise Conflict(
            ngettext(
                "%(count)d separate copy of a hub is on this cluster or still to be made from it: it is deleted once "
                "the copy is made or dropped.",
                "%(count)d separate copies of hubs are on this cluster or still to be made from it: it is deleted once "
                "the copies are made or dropped.",
                aside,
            )
            % {"count": aside},
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
    if hub.restoring_from_id is not None:
        raise _restoring()
    if hub.cluster_id == target.pk:
        raise _move_refused(gettext("This hub is on that cluster already."), "control.hub_already_there")
    if not target.is_open:
        raise _move_refused(gettext("That cluster is closed to new hubs."), "control.cluster_closed")
    if not _room_for_one_more(target):
        raise _move_refused(gettext("That cluster has no room for another hub."), "control.cluster_full")
    size = queries.measure(hub.cluster, [hub.db_name]).get(hub.db_name)
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
    """Ask the worker to undo the move of ``data.id``, started or not: the hub is marked (``move_undo_asked_at``) and the
    worker puts it back on its origin. No note of a copy is made nor taken here: an older copy of the same hub on its
    server is never taken for its data (review of W8, round 3)."""
    platform_admin_only(ctx)
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    if hub.moving_to_id is None:
        raise _move_refused(gettext("This hub is not moving."), "control.hub_not_moving")
    hub.move_undo_asked_at = timezone.now()
    hub.last_error = "move_cancelled: the move was cancelled in the Hub admin."
    hub.save(update_fields=["move_undo_asked_at", "last_error", "updated_at"])
    record_event(ctx, events.HUB_MOVE_CANCEL_REQUESTED, {"id": str(hub.pk), "slug": hub.slug})
    return {"id": hub.pk, "slug": hub.slug, "cluster": hub.cluster_id, "moving_to": hub.moving_to_id}


def _restoring() -> Conflict:
    return _move_refused(gettext("This hub is being restored from a copy."), "control.hub_restoring")


def _copy_to_restore(hub: Hub, source: Cluster) -> None:
    """Refuse unless the copy of ``hub``'s database is on ``source`` under its name, small enough for a copy (as a move:
    ``MOVE_MAX_BYTES``)."""
    size = queries.measure(source, [hub.db_name]).get(hub.db_name)
    if size is None:
        raise _move_refused(
            gettext("The hub's database is not on that cluster: there is no copy to restore it from."),
            "control.restore_copy_missing",
        )
    if size > MOVE_MAX_BYTES:
        raise _move_refused(
            gettext("This hub's database is too large to restore with a copy."), "control.hub_too_large"
        )


def _restorable(data: HubRestoreIn) -> tuple[Hub, Cluster]:
    """The ready hub ``data.hub`` and the temporary cluster ``data.cluster``, both locked, when a copy of its database
    as it was at ``data.at`` can be taken from that cluster: what a restore in place and a copy aside both ask."""
    hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=data.hub).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    source = _locked(data.cluster)
    if hub.status != Hub.Status.READY or not hub.db_name:
        raise _move_refused(
            gettext("Only a ready hub with a database of its own is restored."), "control.hub_not_restorable"
        )
    if hub.is_demo:
        raise _move_refused(gettext("A demo is not restored: it ends on its own."), "control.hub_is_demo")
    if hub.moving_to_id is not None:
        raise _move_refused(gettext("This hub is already moving."), "control.hub_moving")
    if hub.restoring_from_id is not None:
        raise _restoring()
    if hub.cluster_id == source.pk:
        raise _move_refused(
            gettext("The copy comes from a temporary cluster restored to that moment, never from the hub's own."),
            "control.restore_from_own_cluster",
        )
    if source.is_open:
        raise _move_refused(
            gettext("A copy is restored only from a cluster closed to new hubs: a temporary one."),
            "control.cluster_open",
        )
    if living_hubs(source).exists():
        raise _move_refused(
            gettext("Hubs live on that cluster: the copy comes from a temporary one with none."),
            "control.cluster_holds_hubs",
        )
    if data.at > timezone.now():
        message = gettext("That moment has not come yet.")
        raise InvalidPayload(message, code="control.restore_point_ahead", fields={"at": message})
    _copy_to_restore(hub, source)
    return hub, source


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.hub.restore", kind="command", permission=None, input=HubRestoreIn, output=HubRestoreOut, ai=INTERNAL
)
def hub_restore(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Ask the worker to put the ready hub ``data.hub``'s database back as it was at ``data.at``, from its copy on the
    temporary cluster ``data.cluster``."""
    platform_admin_only(ctx)
    hub, source = _restorable(data)
    hub.restoring_from = source
    hub.restore_point = data.at
    hub.last_error = ""
    hub.save(update_fields=["restoring_from", "restore_point", "last_error", "updated_at"])
    record_event(
        ctx,
        events.HUB_RESTORE_REQUESTED,
        {"id": str(hub.pk), "slug": hub.slug, "from": str(source.pk), "at": data.at.isoformat()},
    )
    return {
        "id": hub.pk,
        "slug": hub.slug,
        "cluster": hub.cluster_id,
        "restoring_from": source.pk,
        "restore_point": data.at,
    }


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.hub.restore_aside",
    kind="command",
    permission=None,
    input=HubRestoreIn,
    output=RestoredCopyOut,
    ai=INTERNAL,
)
def hub_restore_aside(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Ask the worker for a separate copy of the ready hub ``data.hub``'s database as it was at ``data.at``, from its
    copy on the temporary cluster ``data.cluster``, made on the hub's own cluster; the hub is not touched."""
    platform_admin_only(ctx)
    hub, source = _restorable(data)
    copy_id = uuid.uuid7()
    copy = RestoredCopy.objects.create(
        id=copy_id,
        hub=hub,
        cluster=hub.cluster,
        source=source,
        restore_point=data.at,
        db_name=names.copy_db_name(control_name(), copy_id),
        asked_by=_who(ctx),
    )
    record_event(
        ctx,
        events.HUB_RESTORE_ASIDE_REQUESTED,
        {
            "id": str(copy.pk),
            "hub": str(hub.pk),
            "slug": hub.slug,
            "from": str(source.pk),
            "at": data.at.isoformat(),
            "database": copy.db_name,
        },
    )
    return {
        "id": copy.pk,
        "hub": hub.pk,
        "slug": hub.slug,
        "db_name": copy.db_name,
        "cluster": copy.cluster_id,
        "source": source.pk,
        "restore_point": data.at,
        "status": copy.status,
    }


# Not an assistant tool: the platform's admins, in the Hub admin.
@operation(
    "control.copy.recover",
    kind="command",
    permission=None,
    input=CopyRecoverIn,
    output=CopyRecoveryOut,
    ai=INTERNAL,
)
def copy_recover(ctx: OperationContext, data: CopyRecoverIn) -> dict:
    """Ask the worker to bring back into its business what the separate copy ``data.copy_id`` holds and the business
    lacks, of the apps ``data.apps`` (hub#1257; ``base.tenancy.recovery``): each record created by its app's own
    operation, in the staff member's language. Only from a made copy, of apps that say what they give back from one,
    and one recovery of a copy at a time; the business is not touched by the ask."""
    # Imported here: base.tenancy.recovery runs on control.services (its worker's side, below).
    from base.tenancy.recovery import recoverable_apps

    platform_admin_only(ctx)
    copy = RestoredCopy.objects.select_related("hub").filter(pk=data.copy_id).first()
    if copy is None:
        raise NotFound(gettext("This separate copy does not exist."))
    if copy.status != RestoredCopy.Status.MADE:
        raise Conflict(gettext("Only a separate copy that is made gives anything back."), code="control.copy_not_made")
    recoverable, apps = recoverable_apps(), list(dict.fromkeys(data.apps))
    unknown = [label for label in apps if label not in recoverable]
    if unknown:
        message = gettext("These apps give nothing back from a separate copy: %(apps)s.") % {"apps": ", ".join(unknown)}
        raise InvalidPayload(message, code="control.copy_app_not_recoverable", fields={"apps": message})
    if CopyRecovery.objects.filter(copy=copy, status=CopyRecovery.Status.ASKED).exists():
        raise Conflict(
            gettext("This separate copy is already giving something back: wait until it is done."),
            code="control.copy_recovery_pending",
        )
    recovery = CopyRecovery.objects.create(copy=copy, apps=apps, language=ctx.language or "en", asked_by=_who(ctx))
    record_event(
        ctx,
        events.COPY_RECOVERY_REQUESTED,
        {"id": str(recovery.pk), "copy": str(copy.pk), "hub": str(copy.hub_id), "slug": copy.hub.slug, "apps": apps},
    )
    return {
        "id": recovery.pk,
        "copy_id": copy.pk,
        "hub": copy.hub_id,
        "slug": copy.hub.slug,
        "apps": apps,
        "status": recovery.status,
    }


def _who(ctx: OperationContext) -> str:
    """Who changes the switch, as the Hub admin shows it: the staff member's name (or username), or the platform."""
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:150]
    return str(actor)[:150]


# Not an assistant tool: the platform's admins, in the Hub admin (Admin › Freeze).
@operation("control.freeze.set", kind="command", permission=None, input=FreezeIn, output=FreezeOut, ai=INTERNAL)
def freeze_set(ctx: OperationContext, data: FreezeIn) -> dict:
    """Freeze the platform for a database upgrade (``data.frozen``, with why) or lift its freeze; asked while already
    so, it is left as it is."""
    platform_admin_only(ctx)
    row = Freeze.objects.select_for_update().first()
    if row is None:
        # Control's migration makes it; only a database whose rows were emptied by hand lacks it. One row at most: a
        # second made at the same time is refused by its constraint, and this call fails rather than write twice.
        row = Freeze.objects.create()
    if row.frozen == data.frozen:
        return queries.freeze_answer(row)
    now = timezone.now()
    if data.frozen:
        row.frozen, row.reason, row.since, row.by = True, data.reason, now, _who(ctx)
        record_event(ctx, events.FREEZE_STARTED, {"reason": row.reason})
    else:
        started = row.since
        row.frozen, row.reason, row.since, row.by = False, "", now, _who(ctx)
        record_event(ctx, events.FREEZE_LIFTED, {"frozen_since": started.isoformat() if started else ""})
    row.save(update_fields=["frozen", "reason", "since", "by"])
    return queries.freeze_answer(row)


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


def hubs_restoring() -> list[UUID]:
    """The hubs asked to be restored (or whose restore is being undone), the longest asked first (hub#1198)."""
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
    # Whoever holds it: one that ran out and nobody took is still ``owner``'s (``base.services.renew_lease`` too).
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


def move_finished(
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


def restore_finished(
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


# ── The worker's side of a separate copy (``base.tenancy.restore``, hub#1213): under the row's own lease ─────────────


def copies_to_make() -> list[UUID]:
    """The separate copies still to make, the longest asked first."""
    return list(
        RestoredCopy.objects.filter(status=RestoredCopy.Status.COPYING)
        .order_by("asked_at", "pk")
        .values_list("pk", flat=True)
    )


def _claim(model, row_id: UUID, now: dt.datetime, lease: dt.timedelta, owner: str, status: str) -> bool:
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


# ── The worker's side of a recovery from a separate copy (``base.tenancy.recovery``, hub#1257): its own lease ────────


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
