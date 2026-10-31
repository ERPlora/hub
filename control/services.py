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
- A cluster any hub's row still points at (a purged demo's included: the foreign key protects it) is never deleted.

Each locks the cluster's row first, as the placement does, so a hub placed at the same time is either counted or
placed after.
"""

from uuid import UUID

from django.db import IntegrityError
from django.utils.translation import gettext, ngettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event

from base.registry import internal_only
from base.tenancy.credentials import APP, CredentialsUnavailable, credentials_for
from control import events
from control.models import Cluster, Hub
from control.schemas import ClusterDeletedOut, ClusterIdIn, ClusterIn, ClusterOut, ClusterUpdateIn

#: What a cluster is registered with (``ClusterIn``), in the model's own names.
CLUSTER_FIELDS = tuple(ClusterIn.model_fields)
#: Which server it is: never changed under the hubs on it.
WRITER_FIELDS = ("host", "port")


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


def _name_free(name: str, *, besides: UUID | None = None) -> None:
    if Cluster.objects.filter(name=name).exclude(pk=besides).exists():
        raise _name_taken(name)


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
    """Save ``cluster`` in a savepoint: a name another cluster took meanwhile is the same refusal as one taken before."""
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
    _name_free(data.name)
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
    if "name" in changed:
        _name_free(wanted["name"], besides=cluster.pk)
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
    held = Hub.objects.filter(cluster=cluster).count()
    if held:
        raise Conflict(
            ngettext(
                "%(count)d hub is on this cluster: a cluster is only deleted once no hub is on it.",
                "%(count)d hubs are on this cluster: a cluster is only deleted once no hub is on it.",
                held,
            )
            % {"count": held},
            code="control.cluster_holds_hubs",
        )
    cluster.delete()
    _record(ctx, events.CLUSTER_DELETED, cluster, data.id)
    return {"id": data.id}
