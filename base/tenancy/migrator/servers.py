"""The database servers the migrator reaches directly, the settings' own and control's clusters: how it reaches
each, as its own role, and its ``__ddl`` aliases there."""

import copy
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import decouple
from django.conf import settings as django_settings
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.models import Q

from base.tenancy import names
from base.tenancy import connections as tenancy_connections
from control.models.hubs import Cluster, Hub


class MigratorCredentialsMissing(RuntimeError):
    """``DB_MIGRATOR_USER``/``DB_MIGRATOR_PASSWORD`` are not set: the migrator never runs as ``default``'s role."""

    code = "migrator_credentials_missing"


@dataclass(frozen=True)
class ClusterTarget:
    """A database server the migrator reaches directly: its writer and the migrator's credentials there.

    ``CREATE DATABASE … TEMPLATE`` clones only within one server, so each has its own templates (ruling of round
    2026-10-30b). ``control`` is the control database's name every database on it is named after
    (``base.tenancy.names``): the environment's, the same on every cluster. ``cluster_id`` is its ``control.Cluster``
    row, ``None`` for the settings' own server (``default``'s).
    """

    name: str
    host: str
    port: int
    migrator_user: str
    migrator_password: str = field(repr=False)
    control: str
    cluster_id: uuid.UUID | None = None


def migrator_credentials(cluster) -> tuple[str, str]:
    """The migrator's user and password on ``cluster`` (``None``: the settings' own server).

    The environment's ``DB_MIGRATOR_USER``/``DB_MIGRATOR_PASSWORD`` (the worker's and the ``hub-migrate`` task's,
    aws ``apps.tf``; the tests', ``config/settings_pytest.py``). Without them it refuses
    (``MigratorCredentialsMissing``): ``default`` is ``hub_app`` in the web and the worker. Only local development
    (``DEBUG``, compose's Postgres, one role for everything, as db-bootstrap's local mode) takes ``default``'s. A
    cluster with its own secret (``Cluster.secret_name``) has its own migrator: its ``…/migrator`` secret
    (``base.tenancy.credentials``; one that cannot be read refuses as well).
    """
    if cluster is not None and getattr(cluster, "secret_name", ""):
        from base.tenancy.credentials import MIGRATOR, CredentialsUnavailable, credentials_for

        try:
            found = credentials_for(cluster, MIGRATOR)
        except CredentialsUnavailable as unavailable:
            raise MigratorCredentialsMissing(str(unavailable)) from unavailable
        return found.user, found.password
    user = decouple.config("DB_MIGRATOR_USER", default="")
    password = decouple.config("DB_MIGRATOR_PASSWORD", default="")
    if user and password:
        return user, password
    if django_settings.DEBUG:
        settings = connections.settings[DEFAULT_DB_ALIAS]
        return settings["USER"], settings["PASSWORD"]
    raise MigratorCredentialsMissing(
        "DB_MIGRATOR_USER and DB_MIGRATOR_PASSWORD are not set: the migrator runs only as hub_migrator, never as "
        "the database user of the web (the hub-migrate task and the worker have them)."
    )


def cluster_target(cluster=None, *, credentials: Callable | None = None) -> ClusterTarget:
    """How the migrator reaches ``cluster``'s writer (``None``: the settings' own server)."""
    credentials = migrator_credentials if credentials is None else credentials
    user, password = credentials(cluster)
    if cluster is None:
        settings = connections.settings[DEFAULT_DB_ALIAS]
        host, port, name, cluster_id = settings["HOST"], int(settings["PORT"]), "", None
    else:
        host, port, name, cluster_id = cluster.host, int(cluster.port), cluster.name, cluster.id
    return ClusterTarget(
        name=name,
        host=host,
        port=port,
        migrator_user=user,
        migrator_password=password,
        control=tenancy_connections.control_name(),
        cluster_id=cluster_id,
    )


def clusters_to_migrate(*, credentials: Callable | None = None) -> list[ClusterTarget]:
    """The servers whose templates ``migrate_hubs`` keeps: without ``control.Cluster`` rows, the settings' own;
    with them, every open one and every closed one that still holds a living hub's database, plus the settings'
    own while a hub without a cluster lives on it. ``credentials(cluster)``: the migrator's there
    (default ``migrator_credentials``)."""
    if not Cluster.objects.exists():
        return [cluster_target(None, credentials=credentials)]
    living = Hub.objects.exclude(db_name="").exclude(status=Hub.Status.PURGED)
    rows = Cluster.objects.filter(
        Q(is_open=True) | Q(pk__in=living.filter(cluster__isnull=False).values("cluster"))
    ).order_by("name")
    targets = [cluster_target(row, credentials=credentials) for row in rows]
    if living.filter(cluster__isnull=True).exists():
        targets.insert(0, cluster_target(None, credentials=credentials))
    return targets


def _ddl_alias(db_name: str, target: ClusterTarget) -> str:
    """The migrator's alias of ``db_name`` on ``target``: direct, no pool; forgotten after use (``_forget_alias``).

    ``<db_name>__ddl`` on the settings' own server (``base.tenancy.connections.register_ddl_alias``'s);
    ``<db_name>__<cluster>__ddl`` on a cluster, where a template has the same name as on any other. It is registered
    and this thread's connection made under ``base.tenancy.connections``' lock, so another thread forgetting it in
    between never leaves this one without it.
    """
    names.validate(db_name, control=target.control)
    cluster = "" if target.cluster_id is None else f"__{target.cluster_id.hex}"
    alias = f"{db_name}{cluster}{names.DDL_SUFFIX}"
    reach = {"HOST": target.host, "PORT": target.port, "USER": target.migrator_user}
    with tenancy_connections._lock:
        registered = connections.settings.get(alias)
        if registered is None:
            settings = copy.deepcopy(connections.settings[DEFAULT_DB_ALIAS]) | reach | {
                "NAME": db_name,
                "PASSWORD": target.migrator_password,
                "CONN_MAX_AGE": 0,
                "DISABLE_SERVER_SIDE_CURSORS": True,
            }
            settings["OPTIONS"].pop("pool", None)
            connections.settings = {**connections.settings, alias: settings}
        elif {key: str(registered[key]) for key in reach} != {key: str(value) for key, value in reach.items()}:
            raise tenancy_connections.HubAliasConflict(
                f"{alias} already reaches {registered['USER']}@{registered['HOST']}:{registered['PORT']} in this "
                f"process, not the migrator's {target.migrator_user}@{target.host}:{target.port}."
            )
        connections[alias]  # this thread's connection, made while the alias is surely there
    return alias


def _forget_alias(alias: str) -> None:
    """Close this thread's connection of ``alias`` and take the alias out of the settings (under the same lock): a
    long process would otherwise keep one per hub it ever migrated. Another thread's connection stays its own."""
    try:
        connections[alias].close()
    finally:
        with tenancy_connections._lock:
            try:
                del connections[alias]
            except AttributeError:
                pass  # this thread never made one
            if alias in connections.settings:
                connections.settings = {key: value for key, value in connections.settings.items() if key != alias}


def server_of(target: ClusterTarget) -> str:
    """How the messages name ``target``: its cluster, or the settings' server."""
    return f"cluster {target.name}" if target.name else "the settings' server"
