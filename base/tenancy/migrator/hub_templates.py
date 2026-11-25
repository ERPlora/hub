"""The templates every new hub is cloned from: which they are, and making each or bringing it up to date on its
server, where a missing one is cloned (``CREATE DATABASE … TEMPLATE``, through the server's own ``postgres``
database) and given its source's access."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from psycopg import errors as pg_errors
from psycopg import sql

from base import catalog
from base.tenancy import bootstrap, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.migrator import app_sets, schema, servers

logger = logging.getLogger("base.tenancy.migrator")  # logged as the migrator, whose steps these are

#: Where ``CREATE DATABASE`` runs: every database's own catalog is reached from any, and this one always exists.
OPS_DATABASE = "postgres"
#: Cloning a template fails while anyone is connected to its source (55006, after PostgreSQL's own 5 s wait): it is
#: tried this many times, this many seconds apart.
CLONE_ATTEMPTS = 5
CLONE_RETRY_DELAY = 2.0
#: The privileges of a database (``aclexplode``'s ``privilege_type``): the only words that reach a GRANT.
DATABASE_PRIVILEGES = frozenset({"CONNECT", "CREATE", "TEMPORARY"})


class TemplateMissing(RuntimeError):
    """A platform's template that is not on its server: only db-bootstrap makes one, with its roles and grants."""

    code = "template_missing"


@dataclass(frozen=True)
class Template:
    """A template every new hub is cloned from: its database, its apps and, for a vertical's, the template it is
    cloned from when missing and its vertical's apps it cannot hold (``portable_apps``: none today)."""

    db_name: str
    apps: tuple[str, ...]
    source: str | None = None
    left_out: tuple[str, ...] = ()


def templates(control: str | None = None) -> list[Template]:
    """The templates of this deployment: the platform's, then one per vertical of ``base.catalog``, cloned from it;
    named after ``control`` (default: this control database).

    Each carries every portable app's tables (:func:`portable_apps`): a hub made from one gets them with the clone, and
    its sign-up migrates nothing. Turning an app on makes tables only for an app its hub's template had not.

    :func:`ensure_template` never rebuilds a template, it migrates it where it is: the first deployment that adds the
    portable apps to an existing template migrates each one live (about a minute on Fargate). A sign-up meanwhile finds
    the template in use, its clone is refused (``55006``) as ``clone_failed``, and it is tried again 60 s later
    (``services.PROVISION_RETRY_SECONDS``). It happens once."""
    control = tenancy_connections.control_name() if control is None else control
    platform = Template(
        db_name=names.template_db_name(control), apps=tuple(sorted(set(app_sets.platform_apps()) | set(app_sets.portable_apps())))
    )
    portable = set(app_sets.portable_apps())
    verticals = []
    for vertical in catalog.known_verticals():
        wanted = set(catalog.template_apps(vertical))
        verticals.append(
            Template(
                db_name=names.template_db_name(control, vertical),
                apps=tuple(sorted(set(platform.apps) | (wanted & portable))),
                source=platform.db_name,
                left_out=tuple(sorted(wanted - portable)),
            )
        )
    return [platform, *verticals]


def apps_every_hub_gets() -> tuple[str, ...]:
    """The apps whose tables every template carries (:func:`templates`): every portable one, so a hub made from one has
    them with the clone and its sign-up migrates nothing. Turning an app on makes tables only for an app its hub's
    template had not (one ported later), through the worker's :func:`ensure_schema`; ``migrate_hubs`` never adds an app
    to a hub already made."""
    return app_sets.portable_apps()


def ensure_template(
    template: Template, *, target: servers.ClusterTarget | None = None, lock_wait: float = schema.SCHEMA_LOCK_WAIT
) -> list[str]:
    """Bring ``template`` on ``target`` (default: the settings' own server) to the code's leaf: its apps and the ones
    it already has; return what it applied. A vertical's missing one is cloned from its ``source``, and its access is
    made its source's (a clone copies no grant of the database); a platform's missing one is ``TemplateMissing``.
    It is never rebuilt: an app that left its list keeps its tables, at the leaf. Nobody stays connected to it
    afterwards, so it can be cloned."""
    target = servers.cluster_target(None) if target is None else target
    if not database_exists(template.db_name, target=target):
        if template.source is None:
            raise TemplateMissing(
                f"{template.db_name} does not exist on {servers.server_of(target)}: run db-bootstrap there "
                "(manage.py bootstrap_databases), the only one that makes a platform's template, with its roles, "
                "grants and default privileges."
            )
        _clone(template.db_name, template.source, target)
    if template.source is not None:
        _copy_access(template.db_name, template.source, target)
    applied, _has = schema._migrate_database(template.db_name, target, lambda found: set(template.apps) | found, lock_wait)
    return applied


def pending_template(template: Template, *, target: servers.ClusterTarget | None = None) -> list[str]:
    """What ``ensure_template`` would apply on ``target``, as ``<app>.<migration>`` in order; applies and creates
    nothing. For a missing template, everything its apps need from an empty database."""
    target = servers.cluster_target(None) if target is None else target
    if not database_exists(template.db_name, target=target):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        plan: list[tuple[str, str]] = []
        for target in loader.graph.leaf_nodes():
            if target[0] in template.apps:
                plan += [node for node in loader.graph.forwards_plan(target) if node not in plan]
        return [f"{label}.{name}" for label, name in plan]
    alias = servers._ddl_alias(template.db_name, target)
    try:
        executor = MigrationExecutor(connections[alias])
        found = {label for label, _name in executor.loader.applied_migrations} & app_sets.hub_apps()
        _targets, plan = schema._forwards_plan(executor, set(template.apps) | found, alias)
        return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]
    finally:
        servers._forget_alias(alias)


@contextmanager
def _ops(target: servers.ClusterTarget) -> Iterator[psycopg.Connection]:
    """A direct autocommit connection to ``target``'s ``OPS_DATABASE`` as the migrator (``CREATE DATABASE``); the rest
    of ``default``'s connection options (TLS, timeouts) as they are."""
    reach = {
        "dbname": OPS_DATABASE,
        "host": target.host,
        "port": target.port,
        "user": target.migrator_user,
        "password": target.migrator_password,
    }
    with psycopg.connect(**(bootstrap.admin_conninfo() | reach), autocommit=True) as conn:
        yield conn


def database_exists(db_name: str, *, target: servers.ClusterTarget | None = None) -> bool:
    """Whether the database ``db_name`` (one of this control database's names) exists on ``target`` (default: the
    settings' own server)."""
    target = servers.cluster_target(None) if target is None else target
    names.validate(db_name, control=target.control)
    with _ops(target) as conn:
        return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name]).fetchone() is not None


def _clone(db_name: str, source: str, target: servers.ClusterTarget) -> None:
    """``CREATE DATABASE db_name TEMPLATE source`` on ``target``, tried again while someone holds ``source`` (55006,
    ``CLONE_ATTEMPTS`` times); one another run made meanwhile (42P04) is no failure."""
    for attempt in range(1, CLONE_ATTEMPTS + 1):
        try:
            _clone_once(db_name, source, target)
            return
        except pg_errors.ObjectInUse:
            if attempt == CLONE_ATTEMPTS:
                raise
            logger.warning("migrate_hubs: %s is in use; cloning %s again (attempt %d).", source, db_name, attempt)
        time.sleep(CLONE_RETRY_DELAY)


def _clone_once(db_name: str, source: str, target: servers.ClusterTarget) -> None:
    statement = sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
        names.identifier(db_name, control=target.control), names.identifier(source, control=target.control)
    )
    with _ops(target) as conn:
        try:
            conn.execute(statement)
        except pg_errors.DuplicateDatabase:
            logger.info("migrate_hubs: %s was created meanwhile by another run.", db_name)


_ACCESS = (
    "SELECT CASE WHEN a.grantee = 0 THEN '' ELSE pg_get_userbyid(a.grantee) END, a.privilege_type, a.is_grantable "
    "FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) a "
    "WHERE d.datname = %s AND a.grantee <> d.datdba"
)


def _copy_access(db_name: str, source: str, target: servers.ClusterTarget) -> None:
    """Make who may reach ``db_name`` exactly who may reach ``source`` (its owner aside): a clone gets PUBLIC's
    default access, never its source's grants, and a template open to PUBLIC lets every role of the cluster in."""
    control = target.control
    with _ops(target) as conn:
        want = set(conn.execute(_ACCESS, [source]).fetchall())
        have = set(conn.execute(_ACCESS, [db_name]).fetchall())
        database = names.identifier(db_name, control=control)
        for grantee, privilege, _grantable in sorted(have - want):
            conn.execute(
                sql.SQL("REVOKE {} ON DATABASE {} FROM {}").format(_privilege(privilege), database, _grantee(grantee))
            )
        for grantee, privilege, grantable in sorted(want - have):
            conn.execute(
                sql.SQL("GRANT {} ON DATABASE {} TO {}{}").format(
                    _privilege(privilege),
                    database,
                    _grantee(grantee),
                    sql.SQL(" WITH GRANT OPTION") if grantable else sql.SQL(""),
                )
            )


def _privilege(privilege: str) -> sql.SQL:
    if privilege not in DATABASE_PRIVILEGES:
        raise ValueError(f"{privilege!r} is no privilege of a database.")
    return sql.SQL(privilege)


def _grantee(role: str) -> sql.Composable:
    return sql.SQL("PUBLIC") if role == "" else sql.Identifier(role)
