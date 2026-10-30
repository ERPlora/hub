"""The Hub's schema migrator (CLAUDE.md «Tenencia del Hub»; PLAN-DB §7; aws-next README, «Contrato»).

``manage.py migrate_hubs`` (the ``hub-migrate`` task of every deploy) runs it, in this order:

1. the control database (``default``), under a session advisory lock, so two overlapping deploys never migrate it at
   once (the second waits, then finds nothing to apply): ``migrate_control``;
2. the templates, as canaries (``templates``, ``ensure_template``): ``<control>_template``, the platform alone, and one
   ``<control>_template_<vertical>`` per vertical of ``base.catalog``, cloned from it, with the tables of that
   vertical's apps and every app off (PLAN-DB round 2026-10-30, proposal (h)). One missing is created; one whose list
   changed is brought up to date, never rebuilt;
3. every hub with a database of its own that is behind the code (``is_behind``, from ``Hub.schema_apps``: a deploy
   without migrations opens none), ERPlora's own first, then at most ``HUB_WORKERS`` at once: ``migrate_hubs_behind``.

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
through a direct autocommit connection to the ``postgres`` database with the migrator's credentials (``default``'s in
the ``hub-migrate`` task: ``hub_migrator``), a database's name only as ``sql.Identifier`` (``base.tenancy.names``).
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

import psycopg
from decouple import config
from django.apps import apps as django_apps
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
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
    """An app whose tables still reference control's users: no hub's database can hold them yet."""

    code = "app_not_portable"


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
    migrator_password: str
    control: str
    cluster_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Template:
    """A template every new hub is cloned from: its database, its apps and, for a vertical's, the template it is
    cloned from when missing and its vertical's apps it cannot hold yet (``portable_apps``)."""

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


def code_leaves() -> dict[str, str]:
    """``{app label: its leaf migration}`` in this code."""
    return dict(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())


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

    Phase 1 links some modules to control's users (``settings.AUTH_USER_MODEL``: staff, attendance, task,
    whatsapp_inbox and what depends on them): their tables cannot live in a hub's database until the hub's own staff
    comes (PLAN-DB round 2026-10-22, «Tests»), so no template and no ``add=`` holds them yet.
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
            f"{', '.join(blocked)} cannot be created in a hub's database yet: their tables still reference "
            "control's users (PLAN-DB round 2026-10-22, «Tests»)."
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


def is_behind(hub, leaves: dict[str, str] | None = None) -> bool:
    """Whether ``hub``'s database may lack a migration of this code, as control knows it (``Hub.schema_apps``).

    Behind: marked so, or the platform or any app it has not at the code's leaf (never confirmed counts). A label the
    code does not know (a rollback's) is ignored. Opens no database.
    """
    if hub.schema_state == Hub.SchemaState.BEHIND:
        return True
    leaves = code_leaves() if leaves is None else leaves
    recorded = hub.schema_apps or {}
    labels = set(platform_apps()) | {label for label in recorded if label in leaves}
    return any(recorded.get(label) != leaves.get(label) for label in labels)


# ── The servers: the settings' own and control's clusters ─────────────────────────────────────────────────────


def migrator_credentials(cluster) -> tuple[str, str]:
    """The migrator's user and password on ``cluster`` (``None``: the settings' own server).

    The environment's ``DB_MIGRATOR_USER``/``DB_MIGRATOR_PASSWORD`` (the worker's and the ``hub-migrate`` task's,
    aws ``apps.tf``), else ``default``'s (local development and the tests, where one role does everything). A
    cluster's own secret (``Cluster.secret_name``) plugs in here.
    """
    settings = connections.settings[DEFAULT_DB_ALIAS]
    return (
        config("DB_MIGRATOR_USER", default=settings["USER"]),
        config("DB_MIGRATOR_PASSWORD", default=settings["PASSWORD"]),
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
    """The migrator's alias of ``db_name`` on ``target``: direct, no pool, closed after use.

    ``<db_name>__ddl`` on the settings' own server (``base.tenancy.connections.register_ddl_alias``'s);
    ``<db_name>__<cluster>__ddl`` on a cluster, where a template has the same name as on any other.
    """
    names.validate(db_name, control=target.control)
    cluster = "" if target.cluster_id is None else f"__{target.cluster_id.hex}"
    alias = f"{db_name}{cluster}{names.DDL_SUFFIX}"
    reach = {"HOST": target.host, "PORT": target.port, "USER": target.migrator_user}

    def build() -> dict:
        settings = copy.deepcopy(connections.settings[DEFAULT_DB_ALIAS]) | reach | {
            "NAME": db_name,
            "PASSWORD": target.migrator_password,
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
        }
        settings["OPTIONS"].pop("pool", None)
        return settings

    tenancy_connections._register(alias, build)
    registered = connections.settings[alias]
    if {key: str(registered[key]) for key in reach} != {key: str(value) for key, value in reach.items()}:
        raise tenancy_connections.HubAliasConflict(
            f"{alias} already reaches {registered['USER']}@{registered['HOST']}:{registered['PORT']} in this "
            f"process, not the migrator's {target.migrator_user}@{target.host}:{target.port}."
        )
    return alias


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
    installed = {config.label for config in django_apps.get_app_configs()}
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
    """Create ``template`` on ``target`` (default: the settings' own server) if it is missing (a clone of its
    ``source``, if any) and bring its apps, and the ones it already has, to the code's leaf; return what it applied.
    It is never rebuilt: an app that left its list keeps its tables, at the leaf. Nobody stays connected to it
    afterwards, so it can be cloned."""
    target = cluster_target(None) if target is None else target
    if not database_exists(template.db_name, target=target):
        _create_database(template.db_name, source=template.source, target=target)
    applied, _has = _migrate_database(template.db_name, target, lambda found: set(template.apps) | found, lock_wait)
    return applied


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
        connections[alias].close()


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
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext('erplora.schema'))")
    finally:
        # Closing ends the session, and with it any lock it still held.
        connection.close()


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


def _create_database(db_name: str, *, source: str | None, target: ClusterTarget) -> None:
    control = target.control
    if source is None:
        statement = sql.SQL("CREATE DATABASE {}").format(names.identifier(db_name, control=control))
    else:
        statement = sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            names.identifier(db_name, control=control), names.identifier(source, control=control)
        )
    with _ops(target) as conn:
        try:
            conn.execute(statement)
        except pg_errors.DuplicateDatabase:
            logger.info("migrate_hubs: %s was created meanwhile by another run.", db_name)


# ── The hubs' pass of migrate_hubs ─────────────────────────────────────────────────────────────────────────────


def hubs_with_a_database() -> list:
    """The hubs whose own database ``migrate_hubs`` keeps at the leaf: ERPlora's own first, then by slug."""
    return list(
        Hub.objects.exclude(db_name="")
        .filter(status__in=MIGRATED_STATUSES)
        .select_related("cluster")
        .order_by("-is_platform", "slug")
    )


def hubs_behind() -> list:
    """Of ``hubs_with_a_database``, the ones behind the code (``is_behind``); opens none of their databases."""
    leaves = code_leaves()
    return [hub for hub in hubs_with_a_database() if is_behind(hub, leaves)]


def migrate_hubs_behind(*, workers: int = HUB_WORKERS) -> HubsPass:
    """``ensure_schema`` of every hub behind: ERPlora's own first, then the rest ``workers`` at a time. A hub that
    fails is marked ``behind`` (its traceback logged) and the others go on."""
    every = hubs_with_a_database()
    leaves = code_leaves()
    behind = [hub for hub in every if is_behind(hub, leaves)]
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
    for attempt in range(1, LOCK_TIMEOUT_ATTEMPTS + 1):
        try:
            ensure_schema(hub)
            return None
        except Exception as error:
            if _is_lock_timeout(error) and attempt < LOCK_TIMEOUT_ATTEMPTS:
                logger.warning("migrate_hubs: %s hit a lock timeout (attempt %d), trying again.", hub.slug, attempt)
                continue
            logger.exception("migrate_hubs: the hub %s (%s) was left behind.", hub.slug, hub.db_name)
            _mark_behind(hub)
            return f"{type(error).__name__}: {error}"
    raise AssertionError("unreachable: the last attempt returns")


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
