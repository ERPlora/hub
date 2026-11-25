"""The database clusters the hubs' databases are on: registered, edited, closed to new hubs and deleted by the
platform's admins."""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q
from django.utils.translation import gettext, ngettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event

from base.tenancy.credentials import APP, CredentialsUnavailable, credentials_for
from control import events
from control.models import Cluster, Hub, LeftoverDatabase, MovedCopy, RestoredCopy
from control.schemas import ClusterDeletedOut, ClusterIdIn, ClusterIn, ClusterOut, ClusterUpdateIn
from control.services.actor import platform_admin_only

#: What a cluster is registered with (``ClusterIn``), in the model's own names.
CLUSTER_FIELDS = tuple(ClusterIn.model_fields)
#: Which server it is: never changed under the hubs on it.
WRITER_FIELDS = ("host", "port")


def living_hubs(cluster: Cluster):
    """The hubs on ``cluster`` that still have, or will have, a database there: all but the purged demos."""
    return Hub.objects.filter(cluster=cluster).exclude(status=Hub.Status.PURGED)


def _holds_anything(cluster: Cluster) -> bool:
    """Whether a database of a hub is, or is about to be, on ``cluster``: a living hub, one on its way there, or a
    copy or a leftover of a move kept there, a separate copy there or one still to make from it."""
    return (
        living_hubs(cluster).exists()
        or Hub.objects.filter(Q(moving_to=cluster) | Q(move_scheduled_to=cluster) | Q(restoring_from=cluster)).exists()
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
    held = Hub.objects.filter(
        Q(cluster=cluster) | Q(moving_to=cluster) | Q(move_scheduled_to=cluster) | Q(restoring_from=cluster)
    ).count()
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
