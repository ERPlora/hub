"""Changing a database's schema: ``ensure_schema``, the only function that changes a hub's, and what it shares
with the templates': the migrator's session limits, the schema lock and Django's migrations of a list of apps."""

import logging
import time
from collections.abc import Callable, Iterable

from django.apps import apps as django_apps
from django.db import Error, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from base import activation
from base.tenancy import names, sequences
from base.tenancy.migrator import app_sets, servers
from control.models.hubs import Hub

logger = logging.getLogger("base.tenancy.migrator")  # logged as the migrator, whose steps these are

#: How long a run waits for another to release a database's schema lock, in seconds.
SCHEMA_LOCK_WAIT = 120.0
SCHEMA_LOCK_POLL = 0.5
#: The limits of the migrator's session on a hub's or a template's database.
SESSION_LIMITS = {
    "lock_timeout": "5s",
    "statement_timeout": "5min",
    "idle_in_transaction_session_timeout": "5min",
}


class HubWithoutDatabase(RuntimeError):
    """A hub that still shares control's database (``db_name=""``): it has no schema of its own to change."""

    code = "hub_without_database"


class SchemaLocked(RuntimeError):
    """Another run held the database's schema lock for longer than this one could wait."""

    code = "schema_locked"


def migrate_apps(ddl_alias: str, app_labels, *, heartbeat: Callable[[], object] | None = None) -> list[str]:
    """Bring ``app_labels`` of the database behind ``ddl_alias`` to the code's leaf; return what it applied, in order.

    Only a migrator's alias (``…__ddl``): every other alias is refused. Their dependencies come along (Django's own
    and control's are recorded, their tables left to control's database by the ``TenantRouter``); with nothing to
    apply it does not migrate at all, and it never steps back. ``heartbeat()`` is called before each app's first
    migration (a caller's lease renewed between apps; what it raises stops the run there).
    """
    if not ddl_alias.endswith(names.DDL_SUFFIX):
        raise ValueError(f"migrate_apps runs only on a migrator's alias (…{names.DDL_SUFFIX}), not on {ddl_alias!r}.")
    executor = MigrationExecutor(connections[ddl_alias], progress_callback=_beat_per_app(heartbeat))
    targets, plan = _forwards_plan(executor, app_labels, ddl_alias)
    if not plan:
        return []
    executor.migrate(targets, plan=plan)
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def _beat_per_app(heartbeat: Callable[[], object] | None) -> Callable[..., None] | None:
    """Django's ``progress_callback`` that calls ``heartbeat`` when the first migration of each app starts."""
    if heartbeat is None:
        return None
    started: set[str] = set()

    def progress(action: str, migration=None, fake: bool = False) -> None:
        if action == "apply_start" and migration is not None and migration.app_label not in started:
            started.add(migration.app_label)
            heartbeat()

    return progress


def _forwards_plan(executor: MigrationExecutor, app_labels, where: str) -> tuple[list, list]:
    """The leaves of ``app_labels`` in the code and the plan to them; refused if it would step back."""
    labels = set(app_labels)
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] in labels]
    plan = executor.migration_plan(targets)
    if any(backwards for _migration, backwards in plan):
        raise ValueError(f"migrate_apps never steps back: {where} is ahead of the code for {sorted(labels)}.")
    return targets, plan


def ensure_schema(
    hub,
    *,
    add: Iterable[str] = (),
    lock_wait: float = SCHEMA_LOCK_WAIT,
    heartbeat: Callable[[], object] | None = None,
) -> list[str]:
    """Bring ``hub``'s own database to the code's leaf; return what it applied, as ``<app>.<migration>`` in order.

    The platform, the apps its database already has and ``add`` (with what they require) are migrated; then ``hub``
    learns what the database has (``schema_apps``, the last migration of each app; the labels of a code that no longer
    has them are kept) and ``schema_state = current``, and so does control's row if it names that database (a cut's
    does not until its last step, ``base.hub.cut_finish``, which records it then: a cut that breaks before leaves the
    row as it was), and what any process kept of it is forgotten: an app just made is never refused by a list of before
    (``base.activation.has_tables``). ``SchemaLocked`` after ``lock_wait`` seconds if another run holds the database;
    ``HubWithoutDatabase`` for a hub still on control's, which is never touched.
    ``heartbeat``: called between apps (:func:`migrate_apps`), the worker's lease renewed while a hub is made.
    """
    if not hub.db_name:
        raise HubWithoutDatabase(
            f"The hub {hub.slug or hub.id} shares control's database: it has no schema of its own to migrate."
        )
    added = app_sets._with_requires(add) if add else set()
    target = servers.cluster_target(hub.cluster)
    applied, has = _migrate_database(
        hub.db_name, target, lambda found: set(app_sets.platform_apps()) | found | added, lock_wait, heartbeat=heartbeat
    )
    installed = {app.label for app in django_apps.get_app_configs()}
    schema_apps = {label: name for label, name in (hub.schema_apps or {}).items() if label not in installed} | has
    # Only a row that names this database learns it: a cut's records it with its name, in its last step.
    Hub.objects.filter(pk=hub.pk, db_name=hub.db_name).update(
        schema_apps=schema_apps, schema_state=Hub.SchemaState.CURRENT, updated_at=timezone.now()
    )
    hub.schema_apps = schema_apps
    hub.schema_state = Hub.SchemaState.CURRENT
    activation.forget(hub.slug)
    return applied


def _migrate_database(
    db_name: str,
    target: servers.ClusterTarget,
    targets: Callable[[set[str]], set[str]],
    lock_wait: float,
    *,
    heartbeat: Callable[[], object] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Under ``db_name``'s schema lock on ``target``, its ``django_migrations`` counter put right first, migrate
    ``targets(the hub apps it has)``; return what was applied and, after, its ``{hub app: last migration}``."""
    alias = servers._ddl_alias(db_name, target)
    connection = connections[alias]
    try:
        with connection.cursor() as cursor:
            for setting, value in SESSION_LIMITS.items():
                cursor.execute("SELECT set_config(%s, %s, false)", [setting, value])
        _take_schema_lock(connection, db_name, lock_wait)
        try:
            sequences.reset_migrations(connection)
            applied = migrate_apps(alias, targets(set(_last_migrations(connection))), heartbeat=heartbeat)
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
        servers._forget_alias(alias)


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
    for label, name in recorder.migration_qs.filter(app__in=app_sets.hub_apps()).order_by("id").values_list("app", "name"):
        last[label] = name
    return last
