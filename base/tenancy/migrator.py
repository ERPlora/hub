"""The Hub's schema migrator (CLAUDE.md «Tenencia del Hub»; PLAN-DB; aws-next README, «Contrato»).

``manage.py migrate_hubs`` (the ``hub-migrate`` task of every deploy) runs it. Phase 1 has no hub
databases: it migrates the control database (``default``) only, under a session advisory lock, so
two overlapping deploys never migrate at once (the second waits, then finds nothing to apply).
Phase 2 adds the templates (``hub_template_<vertical>``) and then every hub behind, each through
its direct ``hub_<hex>__ddl`` connection, expand/contract, with the schema lock per hub (PLAN-DB).
``pending_control`` is ``migrate_hubs --check``: what a run would apply, applying nothing.

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
