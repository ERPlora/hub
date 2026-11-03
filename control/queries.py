"""Control's queries: the size of the hubs' own databases, as the Hub admin shows it (round 2026-10-30b of PLAN-DB,
decision 1 of Ioan; tranche S7, part 1).

``control.cluster.sizes`` measures the databases with ``pg_database_size`` over the server's catalogue, never opening
any of them (a connection to a hub's database is its alias's, and to a template's would block its next clone):

- on the settings' own server (the hubs on no cluster), through control's own connection, in the query's transaction;
- on a cluster, through one short direct connection to its maintenance database (``postgres``) on its writer, as the
  cluster's app role (``base.tenancy.credentials``: the web, where the admin runs, has no other) with the default
  connection's TLS and timeout, closed at once. A cluster without any hub's database is not reached at all.

Only the hubs with a database of their own are measured: one that still shares control's (``db_name`` empty) and a
purged demo have none. Each size is kept :data:`SIZE_TTL_SECONDS` in the cache (Valkey in AWS), database by database,
so a new hub is measured on the next look without measuring the others again; a cache that does not answer only costs
a measure, said in the log. A database that is not on the server is left out, never cached. A server that cannot be
reached, or a secret that does not resolve, is ``control.cluster_unreachable`` (503) with its reason.

The worker's metrics (``base.metrics``, hub#488; PLAN-AWS §8, PLAN-DB §6 and §8) read the registry's health here too:
:func:`registry_health` is a plain read, not an operation (no hub and no user: the worker's own measure, like
``base.services.hubs_to_serve``), on control's database (the caller opens ``use_control``).
"""

import datetime as dt
import logging
from dataclasses import dataclass

import psycopg
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connection, connections
from django.db.models import Count, Min, Q
from django.db.models.functions import Coalesce
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import INTERNAL, operation

from base.registry import PREPARING_STATUSES, internal_only
from base.tenancy.connections import NON_LIBPQ_OPTIONS
from base.tenancy.credentials import APP, CredentialsUnavailable, credentials_for
from base.tenancy.ops import MAINTENANCE_DATABASE
from control.models import Cluster, Hub
from control.schemas import ClusterSizesIn, ClusterSizesOut

logger = logging.getLogger(__name__)

#: How long a database's size is kept before it is measured again.
SIZE_TTL_SECONDS = 600
SIZE_KEY_PREFIX = "control.database_size"
#: The catalogue's answer: no database is opened, and one that is not on the server is not in it.
SIZES_SQL = "SELECT datname, pg_database_size(datname) FROM pg_database WHERE datname = ANY(%s)"


def platform_staff_only(ctx: OperationContext) -> None:
    """The platform, or its staff in the Hub admin (support included: it only reads); never a customer."""
    if getattr(ctx.actor, "is_staff", False):
        return
    internal_only(ctx)


def _key(cluster: Cluster | None, name: str) -> str:
    """The cache key of ``name``'s size on ``cluster``'s server: the server is its hash tag (``{<id>}``), one slot of the
    Valkey cluster for every database of one server, read and kept in one call each (``base/cache.py``)."""
    return f"{SIZE_KEY_PREFIX}:{{{cluster.pk if cluster is not None else 'settings'}}}:{name}"


def _cached(what: str, call, default):
    """``call()`` on the cache, or ``default`` when it does not answer: the sizes are measured again then."""
    try:
        return call()
    except Exception:  # whatever the cache backend raises when it is away: said in the log, the server answers
        logger.warning("control: the cache could not %s the databases' sizes.", what, exc_info=True)
        return default


def _server_conninfo(cluster: Cluster) -> dict:
    """The direct connection to ``cluster``'s maintenance database, as its app role, in libpq's terms."""
    default = connections.settings[DEFAULT_DB_ALIAS]
    found = credentials_for(cluster, APP)
    options = {key: value for key, value in default["OPTIONS"].items() if key not in NON_LIBPQ_OPTIONS}
    return {
        **options,
        "dbname": MAINTENANCE_DATABASE,
        "host": cluster.host,
        "port": cluster.port,
        "user": found.user,
        "password": found.password,
    }


def _unreachable(cluster: Cluster | None, reason: object) -> OperationError:
    where = cluster.name if cluster is not None else gettext("the control database's server")
    return OperationError(
        gettext("The sizes of the databases on %(cluster)s could not be read: %(reason)s")
        % {"cluster": where, "reason": reason},
        code="control.cluster_unreachable",
        status=503,
    )


def measure(cluster: Cluster | None, names: list[str]) -> dict[str, int]:
    """The size in bytes of each of ``names`` that is on the server of ``cluster`` (none: the settings' own)."""
    if cluster is None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(SIZES_SQL, [names])
                return dict(cursor.fetchall())
        except DatabaseError as failed:
            raise _unreachable(None, failed) from failed
    try:
        with psycopg.connect(**_server_conninfo(cluster), autocommit=True) as conn:
            return dict(conn.execute(SIZES_SQL, [names]).fetchall())
    except (CredentialsUnavailable, psycopg.Error) as failed:
        raise _unreachable(cluster, failed) from failed


# Not an assistant tool: the platform's staff, in the Hub admin.
@operation(
    "control.cluster.sizes", kind="query", permission=None, input=ClusterSizesIn, output=ClusterSizesOut, ai=INTERNAL
)
def cluster_sizes(ctx: OperationContext, data: ClusterSizesIn) -> dict:
    """The size of each own database of the hubs on ``data.cluster`` (none: on the settings' own server)."""
    platform_staff_only(ctx)
    cluster = None
    if data.cluster is not None:
        cluster = Cluster.objects.filter(pk=data.cluster).first()
        if cluster is None:
            raise NotFound(gettext("No cluster has this id."))
    names = sorted(
        set(
            Hub.objects.filter(cluster=cluster)
            .exclude(db_name="")
            .exclude(status=Hub.Status.PURGED)
            .values_list("db_name", flat=True)
        )
    )
    if not names:
        return {"databases": {}}
    keys = {name: _key(cluster, name) for name in names}
    kept = _cached("read", lambda: cache.get_many(list(keys.values())), {})
    sizes = {name: kept[key] for name, key in keys.items() if key in kept}
    missing = [name for name in names if name not in sizes]
    if missing:
        measured = measure(cluster, missing)
        if measured:
            _cached(
                "keep",
                lambda: cache.set_many({keys[name]: size for name, size in measured.items()}, SIZE_TTL_SECONDS),
                None,
            )
        sizes |= measured
    return {"databases": dict(sorted(sizes.items()))}


# ── The registry's health, for the worker's metrics ──

#: A demo still open: being prepared or ready (``base.services.OPEN_DEMO_STATUSES``); once its time is up it ended.
_OPEN_DEMO_STATUSES = (*PREPARING_STATUSES, Hub.Status.READY)
#: A demo the reaper marked as ended and has not purged yet.
_ENDING_DEMO_STATUSES = (Hub.Status.EXPIRED, Hub.Status.DROPPING)


@dataclass(frozen=True)
class RegistryHealth:
    """What the registry says at one moment: since when the oldest hub still being prepared waits (``None``: none),
    how many hubs failed, and since when the oldest demo that ended waits to be dropped (``None``: none)."""

    oldest_preparing_since: dt.datetime | None
    failed: int
    oldest_ended_demo_since: dt.datetime | None


def registry_health(now: dt.datetime) -> RegistryHealth:
    """The registry's health at ``now``, in one query.

    A hub still being prepared (requested, creating, migrating, seeding, or failed and retried) waits since its row last
    changed (``updated_at``: each step of its preparation, each failure, and ``base.hub.restore``, which brings a
    business that left back to ``requested``, born long before); a demo whose time is up is not one of them but an
    ended demo, which waits to be dropped since its end (``expires_at``; one expired without it, since it last changed)
    until the reaper purges it, as ``base.services.reap_demos`` takes them.
    """
    demo_over = Q(is_demo=True, expires_at__lte=now)
    row = Hub.objects.aggregate(
        oldest_preparing_since=Min("updated_at", filter=Q(status__in=PREPARING_STATUSES) & ~demo_over),
        failed=Count("pk", filter=Q(status=Hub.Status.FAILED) & ~demo_over),
        oldest_ended_demo_since=Min(
            Coalesce("expires_at", "updated_at"),
            filter=Q(is_demo=True)
            & (Q(status__in=_ENDING_DEMO_STATUSES) | Q(status__in=_OPEN_DEMO_STATUSES, expires_at__lte=now)),
        ),
    )
    return RegistryHealth(**row)
