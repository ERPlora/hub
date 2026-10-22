"""The Hub's schema migrator (CLAUDE.md «Tenencia del Hub»; PLAN-DB; aws-next README, «Contrato»).

``manage.py migrate_hubs`` (the ``hub-migrate`` task of every deploy) runs it. Phase 1 has no hub
databases: it migrates the control database (``default``) only, under a session advisory lock, so
two overlapping deploys never migrate at once (the second waits, then finds nothing to apply).
Phase 2 adds the templates (``hub_template_<vertical>``) and then every hub behind, each through
its direct ``hub_<hex>__ddl`` connection, expand/contract, with the schema lock per hub (PLAN-DB).
``pending_control`` is ``migrate_hubs --check``: what a run would apply, applying nothing.

``migrate_apps`` (phase 2, S1) brings some apps of one hub's or template's database to the code's leaf, through that
database's migrator alias (``<db_name>__ddl``): the tests' template is built with it, and S3's ``ensure_schema`` (the
schema lock, ``schema_apps``) wraps it. The ``TenantRouter`` keeps control's models out of it.

The only module of ``base/`` and ``apps/`` that names a connection by hand and takes a session
advisory lock (``tests/test_guardrails.py``): the control database is reached directly, never
through PgBouncer, so a session lock holds for as long as this function runs.
"""

import hashlib
import logging

from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from base.tenancy import names

logger = logging.getLogger(__name__)

CONTROL_ALIAS = DEFAULT_DB_ALIAS
LOCK_NAME = "erplora.migrate_hubs"
#: A stable signed 64-bit key: the first 8 bytes of the name's blake2b.
LOCK_KEY = int.from_bytes(
    hashlib.blake2b(LOCK_NAME.encode(), digest_size=8).digest(), "big", signed=True
)


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
    labels = set(app_labels)
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] in labels]
    plan = executor.migration_plan(targets)
    if any(backwards for _migration, backwards in plan):
        raise ValueError(f"migrate_apps never steps back: {ddl_alias} is ahead of the code for {sorted(labels)}.")
    if not plan:
        return []
    executor.migrate(targets, plan=plan)
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]
