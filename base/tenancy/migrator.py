"""The Hub's schema migrator (CLAUDE.md «Tenencia del Hub»; PLAN-DB §7; aws-next README, «Contrato»).

``manage.py migrate_hubs`` (the ``hub-migrate`` task of every deploy) runs it, in this order:

1. the control database (``default``), under a session advisory lock, so two overlapping deploys never migrate it at
   once (the second waits, then finds nothing to apply): ``migrate_control``;
2. the templates, as canaries, on every server the hubs live on (``clusters_to_migrate``: ``CREATE DATABASE …
   TEMPLATE`` clones only within one): ``<control>_template``, the platform alone, and one
   ``<control>_template_<vertical>`` per vertical of ``base.catalog``, cloned from it, with the tables of that
   vertical's apps and every app off (PLAN-DB round 2026-10-30, proposal (h)) (``templates``, ``ensure_template``).
   One missing is created; one whose list changed is brought up to date, never rebuilt;
3. every hub with a database of its own that is behind the code (``is_behind``, from ``Hub.schema_apps``: a deploy
   without migrations opens none), each on its own server, ERPlora's own first, then at most ``HUB_WORKERS`` at once:
   ``migrate_hubs_behind``.

``ensure_schema(hub, add=())`` is the only function that changes a hub's schema (PLAN-DB §7): through the hub's direct
``<db_name>__ddl`` alias, under the schema lock of that database (``pg_try_advisory_lock(hashtext('erplora.schema'))``:
the key lives in each database, so it is per hub), it brings the platform (``base``, ``live``), the apps the hub's
database already has and ``add`` (closed by ``requires``) to the code's leaf with ``migrate_apps``, then writes down in
control what that database has (``Hub.schema_apps``: its ``django_migrations`` rules) and ``schema_state = current``.
It never steps back and never deletes a table. ``pending_control``, ``pending_template`` and ``is_behind`` are
``migrate_hubs --check``: what a run would apply, applying nothing.

The only module of ``base/`` and ``apps/`` that names a connection by hand and takes session advisory locks
(``tests/test_guardrails.py``): the control database and the hubs' ``__ddl`` aliases are reached directly, never through
PgBouncer, so a session lock holds for as long as its function runs. ``CREATE DATABASE`` (a missing template) goes
through a direct autocommit connection to that server's ``postgres`` database, a database's name only as
``sql.Identifier`` (``base.tenancy.names``). On a hub's or a template's server the migrator connects with its own
credentials (``migrator_credentials``: ``hub_migrator``'s in the ``hub-migrate`` task and the worker).
"""

import copy
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field

import decouple
import psycopg
from django.apps import apps as django_apps
from django.conf import settings as django_settings
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, Error, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q
from django.utils import timezone
from psycopg import errors as pg_errors
from psycopg import sql

from base import catalog
from base.tenancy import bootstrap, inventory, names
from base.tenancy import connections as tenancy_connections
from control.models import Cluster, Hub

logger = logging.getLogger(__name__)

CONTROL_ALIAS = DEFAULT_DB_ALIAS
LOCK_NAME = "erplora.migrate_hubs"
#: A stable signed 64-bit key: the first 8 bytes of the name's blake2b.
LOCK_KEY = int.from_bytes(
    hashlib.blake2b(LOCK_NAME.encode(), digest_size=8).digest(), "big", signed=True
)

#: How long a run waits for another to release a database's schema lock, in seconds (PLAN-DB §7: 120 s).
SCHEMA_LOCK_WAIT = 120.0
SCHEMA_LOCK_POLL = 0.5
#: PLAN-DB §7, «Conexión»: the migrator's session on a hub's or a template's database.
SESSION_LIMITS = {
    "lock_timeout": "5s",
    "statement_timeout": "5min",
    "idle_in_transaction_session_timeout": "5min",
}
#: Hubs migrated at once: as many ``__ddl`` connections (PLAN-DB §5, the budget; plan 2026-10-22, decision 5).
HUB_WORKERS = 4
#: A hub's run cut by ``lock_timeout`` (a table held by its traffic) is tried this many times (PLAN-DB §7).
LOCK_TIMEOUT_ATTEMPTS = 3
#: The hubs whose database is complete: ready, or kept after leaving (a cancelled business, an expired demo until
#: its purge). One being created is the worker's, which runs ``ensure_schema`` itself; a failed one has no
#: complete database; a purged one has none.
MIGRATED_STATUSES = (Hub.Status.READY, Hub.Status.CANCELLED, Hub.Status.EXPIRED)
#: Where ``CREATE DATABASE`` runs: every database's own catalog is reached from any, and this one always exists.
OPS_DATABASE = "postgres"
#: Cloning a template fails while anyone is connected to its source (55006, after PostgreSQL's own 5 s wait): it is
#: tried this many times, this many seconds apart (PLAN-DB §6).
CLONE_ATTEMPTS = 5
CLONE_RETRY_DELAY = 2.0
#: The privileges of a database (``aclexplode``'s ``privilege_type``): the only words that reach a GRANT.
DATABASE_PRIVILEGES = frozenset({"CONNECT", "CREATE", "TEMPORARY"})


class HubWithoutDatabase(RuntimeError):
    """A hub that still shares control's database (``db_name=""``): it has no schema of its own to change."""

    code = "hub_without_database"


class SchemaLocked(RuntimeError):
    """Another run held the database's schema lock for longer than this one could wait."""

    code = "schema_locked"


class UnknownApp(LookupError):
    """An app this code does not have."""

    code = "unknown_app"


class AppNotPortable(ValueError):
    """An app whose tables reference a model of control's database: no hub's database can hold them. None since
    tenancy W10 (the people of a business are its own, ``base.HubUser``); ``tests/test_guardrails.py`` «(h)» keeps it
    so."""

    code = "app_not_portable"


class TemplateMissing(RuntimeError):
    """A platform's template that is not on its server: only db-bootstrap makes one, with its roles and grants."""

    code = "template_missing"


class MigratorCredentialsMissing(RuntimeError):
    """``DB_MIGRATOR_USER``/``DB_MIGRATOR_PASSWORD`` are not set: the migrator never runs as ``default``'s role."""

    code = "migrator_credentials_missing"


@dataclass(frozen=True)
class CodeMigrations:
    """This code's migrations: every app's leaf and every node of the graph."""

    leaves: dict[str, str]
    nodes: frozenset[tuple[str, str]]


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


@dataclass(frozen=True)
class Template:
    """A template every new hub is cloned from: its database, its apps and, for a vertical's, the template it is
    cloned from when missing and its vertical's apps it cannot hold (``portable_apps``: none since tenancy W10)."""

    db_name: str
    apps: tuple[str, ...]
    source: str | None = None
    left_out: tuple[str, ...] = ()


@dataclass
class HubsPass:
    """What ``migrate_hubs_behind`` did: the hubs it migrated and the ones left behind, with the reason."""

    up_to_date: int = 0
    migrated: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def pending_control() -> list[str]:
    """What ``migrate_control`` would apply, as ``<app>.<migration>`` in order; applies nothing.

    Reads ``django_migrations`` without the lock: a run in progress shows as pending.
    """
    executor = MigrationExecutor(connections[CONTROL_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def migrate_control(*, stdout=None, verbosity: int = 1) -> int:
    """Migrate the control database under the ``migrate_hubs`` lock; return how many migrations it applied.

    Blocks while another run holds the lock. The lock lives on the same connection ``migrate``
    uses, and is released in any case; a failure is raised as it came.
    """
    connection = connections[CONTROL_ALIAS]
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
    try:
        before = set(MigrationRecorder(connection).applied_migrations())
        call_command(
            "migrate",
            interactive=False,
            database=CONTROL_ALIAS,
            stdout=stdout,
            verbosity=verbosity,
        )
        after = set(MigrationRecorder(connection).applied_migrations())
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
            released = cursor.fetchone()[0]
        if not released:
            # Something closed the connection mid-run: the lock stays with the session that took it
            # until that session ends (at the latest, when this one-off task exits).
            logger.warning(
                "migrate_hubs: the lock was no longer held by this connection when released."
            )
    return len(after - before)


def migrate_apps(ddl_alias: str, app_labels) -> list[str]:
    """Bring ``app_labels`` of the database behind ``ddl_alias`` to the code's leaf; return what it applied, in order.

    Only a migrator's alias (``…__ddl``): every other alias is refused. Their dependencies come along (Django's own
    and control's are recorded, their tables left to control's database by the ``TenantRouter``); with nothing to
    apply it does not migrate at all, and it never steps back.
    """
    if not ddl_alias.endswith(names.DDL_SUFFIX):
        raise ValueError(f"migrate_apps runs only on a migrator's alias (…{names.DDL_SUFFIX}), not on {ddl_alias!r}.")
    executor = MigrationExecutor(connections[ddl_alias])
    targets, plan = _forwards_plan(executor, app_labels, ddl_alias)
    if not plan:
        return []
    executor.migrate(targets, plan=plan)
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def _forwards_plan(executor: MigrationExecutor, app_labels, where: str) -> tuple[list, list]:
    """The leaves of ``app_labels`` in the code and the plan to them; refused if it would step back."""
    labels = set(app_labels)
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] in labels]
    plan = executor.migration_plan(targets)
    if any(backwards for _migration, backwards in plan):
        raise ValueError(f"migrate_apps never steps back: {where} is ahead of the code for {sorted(labels)}.")
    return targets, plan


# ── What a hub's database holds ────────────────────────────────────────────────────────────────────────────────


def code_migrations() -> CodeMigrations:
    """This code's migration graph: ``{app label: its leaf}`` and every ``(app label, migration)``."""
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    return CodeMigrations(leaves=dict(graph.leaf_nodes()), nodes=frozenset(graph.nodes))


def hub_apps() -> frozenset[str]:
    """Every app whose tables live in a hub's database: the platform's and every module of ``apps/``."""
    return frozenset(
        config.label
        for config in django_apps.get_app_configs()
        if config.name.startswith(inventory.HUB_MODULES_PACKAGE)
        or inventory.APP_CLASSES.get(config.label) == inventory.HUB
    )


def platform_apps() -> tuple[str, ...]:
    """What every hub's database has, whatever its apps: the apps that are a hub's whole (``base``, ``live``)."""
    installed = {config.label for config in django_apps.get_app_configs()}
    return tuple(
        sorted(label for label, kind in inventory.APP_CLASSES.items() if kind == inventory.HUB and label in installed)
    )


def _hub_classes(model) -> bool:
    return inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)


def portable_apps() -> tuple[str, ...]:
    """The hub apps whose tables reference only a hub's own, and whose migrations need no other app's.

    Every hub app since tenancy W10: staff, attendance, task and whatsapp_inbox hang a person from the business's own
    ``base.HubUser``, not from control's user. An app that linked a model of control's again (and what depends on it)
    would be left out of every template and refused by ``add=``; ``tests/test_guardrails.py`` «(h)» stops it first.
    """
    labels = hub_apps()
    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    needs = {
        label: {node[0] for leaf in graph.leaf_nodes() if leaf[0] == label for node in graph.forwards_plan(leaf)}
        & labels
        for label in labels
    }
    blocked = {
        label
        for label in labels
        for model in django_apps.get_app_config(label).get_models(include_auto_created=True)
        if _hub_classes(model)
        for field_ in model._meta.get_fields()
        if field_.is_relation and field_.concrete and field_.related_model is not None
        and inventory.classify(field_.related_model) == inventory.CONTROL
    }
    while grown := {label for label in labels - blocked if needs[label] & blocked}:
        blocked |= grown
    return tuple(sorted(labels - blocked))


def _with_requires(labels: Iterable[str]) -> set[str]:
    """``labels`` and what they require, transitively (each module's ``requires``); refused if one is unknown or no
    hub's database can hold it yet."""
    known = hub_apps()
    wanted = set(labels)
    if unknown := sorted(wanted - known):
        raise UnknownApp(f"No hub app is called {', '.join(unknown)} in this code.")
    closed: set[str] = set()
    pending = list(wanted)
    while pending:
        label = pending.pop()
        if label not in closed:
            closed.add(label)
            pending.extend(getattr(django_apps.get_app_config(label), "requires", ()) or ())
    if blocked := sorted(closed - set(portable_apps())):
        raise AppNotPortable(
            f"{', '.join(blocked)} cannot be created in a hub's database: their tables reference a model of "
            "control's database (tests/test_guardrails.py, «(h)»)."
        )
    return closed


def templates(control: str | None = None) -> list[Template]:
    """The templates of this deployment: the platform's, then one per vertical of ``base.catalog``, cloned from it;
    named after ``control`` (default: this control database)."""
    control = tenancy_connections.control_name() if control is None else control
    platform = Template(db_name=names.template_db_name(control), apps=platform_apps())
    portable = set(portable_apps())
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


def is_behind(hub, code: CodeMigrations | None = None) -> bool:
    """Whether ``hub``'s database may lack a migration of this code, as control knows it (``Hub.schema_apps``).

    Behind: marked so, or the platform or any app it has not at the code's leaf (never confirmed counts). A label or a
    migration the code does not have (a later code's, after a rollback: the database is ahead) is not behind. Opens no
    database.
    """
    if hub.schema_state == Hub.SchemaState.BEHIND:
        return True
    code = code_migrations() if code is None else code
    recorded = hub.schema_apps or {}
    for label in set(platform_apps()) | {label for label in recorded if label in code.leaves}:
        name = recorded.get(label)
        if name is None:
            return True
        if (label, name) in code.nodes and name != code.leaves[label]:
            return True
    return False


# ── The servers: the settings' own and control's clusters ─────────────────────────────────────────────────────


def migrator_credentials(cluster) -> tuple[str, str]:
    """The migrator's user and password on ``cluster`` (``None``: the settings' own server).

    The environment's ``DB_MIGRATOR_USER``/``DB_MIGRATOR_PASSWORD`` (the worker's and the ``hub-migrate`` task's,
    aws ``apps.tf``; the tests', ``config/settings_pytest.py``). Without them it refuses
    (``MigratorCredentialsMissing``): ``default`` is ``hub_app`` in the web and the worker. Only local development
    (``DEBUG``, compose's Postgres, one role for everything, as db-bootstrap's local mode) takes ``default``'s. A
    cluster's own secret (``Cluster.secret_name``) plugs in here.
    """
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


# ── Changing a database's schema ───────────────────────────────────────────────────────────────────────────────


def ensure_schema(hub, *, add: Iterable[str] = (), lock_wait: float = SCHEMA_LOCK_WAIT) -> list[str]:
    """Bring ``hub``'s own database to the code's leaf; return what it applied, as ``<app>.<migration>`` in order.

    The platform, the apps its database already has and ``add`` (with what they require) are migrated; then control's
    row learns what the database has (``schema_apps``, the last migration of each app; the labels of a code that no
    longer has them are kept) and ``schema_state = current``. ``SchemaLocked`` after ``lock_wait`` seconds if another
    run holds the database; ``HubWithoutDatabase`` for a hub still on control's, which is never touched.
    """
    if not hub.db_name:
        raise HubWithoutDatabase(
            f"The hub {hub.slug or hub.id} shares control's database: it has no schema of its own to migrate."
        )
    added = _with_requires(add) if add else set()
    target = cluster_target(hub.cluster)
    applied, has = _migrate_database(
        hub.db_name, target, lambda found: set(platform_apps()) | found | added, lock_wait
    )
    installed = {app.label for app in django_apps.get_app_configs()}
    schema_apps = {label: name for label, name in (hub.schema_apps or {}).items() if label not in installed} | has
    Hub.objects.filter(pk=hub.pk).update(
        schema_apps=schema_apps, schema_state=Hub.SchemaState.CURRENT, updated_at=timezone.now()
    )
    hub.schema_apps = schema_apps
    hub.schema_state = Hub.SchemaState.CURRENT
    return applied


def ensure_template(
    template: Template, *, target: ClusterTarget | None = None, lock_wait: float = SCHEMA_LOCK_WAIT
) -> list[str]:
    """Bring ``template`` on ``target`` (default: the settings' own server) to the code's leaf: its apps and the ones
    it already has; return what it applied. A vertical's missing one is cloned from its ``source``, and its access is
    made its source's (a clone copies no grant of the database); a platform's missing one is ``TemplateMissing``.
    It is never rebuilt: an app that left its list keeps its tables, at the leaf. Nobody stays connected to it
    afterwards, so it can be cloned."""
    target = cluster_target(None) if target is None else target
    if not database_exists(template.db_name, target=target):
        if template.source is None:
            raise TemplateMissing(
                f"{template.db_name} does not exist on {server_of(target)}: run db-bootstrap there "
                "(manage.py bootstrap_databases), the only one that makes a platform's template, with its roles, "
                "grants and default privileges."
            )
        _clone(template.db_name, template.source, target)
    if template.source is not None:
        _copy_access(template.db_name, template.source, target)
    applied, _has = _migrate_database(template.db_name, target, lambda found: set(template.apps) | found, lock_wait)
    return applied


def server_of(target: ClusterTarget) -> str:
    """How the messages name ``target``: its cluster, or the settings' server."""
    return f"cluster {target.name}" if target.name else "the settings' server"


def pending_template(template: Template, *, target: ClusterTarget | None = None) -> list[str]:
    """What ``ensure_template`` would apply on ``target``, as ``<app>.<migration>`` in order; applies and creates
    nothing. For a missing template, everything its apps need from an empty database."""
    target = cluster_target(None) if target is None else target
    if not database_exists(template.db_name, target=target):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        plan: list[tuple[str, str]] = []
        for target in loader.graph.leaf_nodes():
            if target[0] in template.apps:
                plan += [node for node in loader.graph.forwards_plan(target) if node not in plan]
        return [f"{label}.{name}" for label, name in plan]
    alias = _ddl_alias(template.db_name, target)
    try:
        executor = MigrationExecutor(connections[alias])
        found = {label for label, _name in executor.loader.applied_migrations} & hub_apps()
        _targets, plan = _forwards_plan(executor, set(template.apps) | found, alias)
        return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]
    finally:
        _forget_alias(alias)


def _migrate_database(
    db_name: str, target: ClusterTarget, targets: Callable[[set[str]], set[str]], lock_wait: float
) -> tuple[list[str], dict[str, str]]:
    """Under ``db_name``'s schema lock on ``target``, migrate ``targets(the hub apps it has)``; return what was applied
    and, after, ``{hub app: its last migration}`` from its ``django_migrations``. The connection is closed in any
    case."""
    alias = _ddl_alias(db_name, target)
    connection = connections[alias]
    try:
        with connection.cursor() as cursor:
            for setting, value in SESSION_LIMITS.items():
                cursor.execute("SELECT set_config(%s, %s, false)", [setting, value])
        _take_schema_lock(connection, db_name, lock_wait)
        try:
            applied = migrate_apps(alias, targets(set(_last_migrations(connection))))
            return applied, _last_migrations(connection)
        finally:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext('erplora.schema'))")
            except Error:
                # Never hides why the run failed: the lock goes with the session, closed below.
                logger.warning("migrate_hubs: the schema lock of %s could not be released; closing.", db_name)
    finally:
        # Closing ends the session, and with it any lock it still held.
        _forget_alias(alias)


def _take_schema_lock(connection, db_name: str, wait: float) -> None:
    deadline = time.monotonic() + wait
    with connection.cursor() as cursor:
        while True:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext('erplora.schema'))")
            if cursor.fetchone()[0]:
                return
            left = deadline - time.monotonic()
            if left <= 0:
                raise SchemaLocked(
                    f"The schema of {db_name} is being changed by another run: waited {wait:g} s for it."
                )
            time.sleep(min(SCHEMA_LOCK_POLL, left))


def _last_migrations(connection) -> dict[str, str]:
    """``{hub app: the last migration applied}`` in the database behind ``connection``."""
    recorder = MigrationRecorder(connection)
    if not recorder.has_table():
        return {}
    last: dict[str, str] = {}
    for label, name in recorder.migration_qs.filter(app__in=hub_apps()).order_by("id").values_list("app", "name"):
        last[label] = name
    return last


@contextmanager
def _ops(target: ClusterTarget) -> Iterator[psycopg.Connection]:
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


def database_exists(db_name: str, *, target: ClusterTarget | None = None) -> bool:
    """Whether the database ``db_name`` (one of this control database's names) exists on ``target`` (default: the
    settings' own server)."""
    target = cluster_target(None) if target is None else target
    names.validate(db_name, control=target.control)
    with _ops(target) as conn:
        return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name]).fetchone() is not None


def _clone(db_name: str, source: str, target: ClusterTarget) -> None:
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


def _clone_once(db_name: str, source: str, target: ClusterTarget) -> None:
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


def _copy_access(db_name: str, source: str, target: ClusterTarget) -> None:
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


# ── The hubs' pass of migrate_hubs ─────────────────────────────────────────────────────────────────────────────


def hubs_with_a_database() -> list:
    """The hubs whose own database ``migrate_hubs`` keeps at the leaf: ERPlora's own first, then by slug."""
    return list(
        Hub.objects.exclude(db_name="")
        .filter(status__in=MIGRATED_STATUSES)
        .select_related("cluster")
        .order_by("-is_platform", "slug")
    )


def migrate_hubs_behind(*, workers: int = HUB_WORKERS) -> HubsPass:
    """``ensure_schema`` of every hub behind: ERPlora's own first, then the rest ``workers`` at a time. A hub that
    fails is marked ``behind`` (its traceback logged) and the others go on."""
    every = hubs_with_a_database()
    code = code_migrations()
    behind = [hub for hub in every if is_behind(hub, code)]
    result = HubsPass(up_to_date=len(every) - len(behind))
    first = [hub for hub in behind if hub.is_platform]
    rest = [hub for hub in behind if not hub.is_platform]
    outcomes = [(hub, _migrate_hub(hub)) for hub in first]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="migrate_hubs") as pool:
        outcomes += zip(rest, pool.map(_migrate_hub_in_thread, rest), strict=True)
    for hub, failure in outcomes:
        if failure is None:
            result.migrated.append(hub.slug)
        else:
            result.failed[hub.slug] = failure
    return result


def _migrate_hub_in_thread(hub) -> str | None:
    try:
        return _migrate_hub(hub)
    finally:
        connections.close_all()  # this thread's own connections: control's goes back to its pool


def _migrate_hub(hub) -> str | None:
    """``ensure_schema(hub)``, tried again on a lock timeout; ``None`` if done, else why it was left behind."""
    attempt = 1
    while True:
        try:
            ensure_schema(hub)
            return None
        except Exception as error:
            if _is_lock_timeout(error) and attempt < LOCK_TIMEOUT_ATTEMPTS:
                logger.warning("migrate_hubs: %s hit a lock timeout (attempt %d), trying again.", hub.slug, attempt)
                attempt += 1
                continue
            logger.exception("migrate_hubs: the hub %s (%s) was left behind.", hub.slug, hub.db_name)
            _mark_behind(hub)
            return f"{type(error).__name__}: {error}"


def _mark_behind(hub) -> None:
    try:
        Hub.objects.filter(pk=hub.pk).update(schema_state=Hub.SchemaState.BEHIND, updated_at=timezone.now())
    except Exception:
        logger.exception("migrate_hubs: the hub %s could not be marked behind in control.", hub.slug)


def _is_lock_timeout(error: BaseException | None) -> bool:
    while error is not None:
        if isinstance(error, pg_errors.LockNotAvailable):
            return True
        error = error.__cause__
    return False
