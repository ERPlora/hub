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
"""

import logging

import psycopg
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connection, connections
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import INTERNAL, operation

from base.registry import internal_only
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
    return f"{SIZE_KEY_PREFIX}:{cluster.pk if cluster is not None else 'settings'}:{name}"


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
