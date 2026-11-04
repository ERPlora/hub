"""``base_outbox_pending`` on every database with an outbox (hub#751).

``base/0006`` creates the index with a ``RunSQL`` that names no model. Under production's routers ``base`` counts as a
hub's, so a control database made from scratch skips it and still records the migration: its relay then reads the whole
outbox on every tick. ``base/0023`` gives control the index. The suite's ``LegacyTablesRouter`` lets every operation
through, which is why nobody saw it: these tests run ``manage.py migrate`` with production's settings, on a control
database of their own.
"""

import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from django.apps import apps
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import inventory, names
from base.tenancy.tests import hubs

INDEX = "base_outbox_pending"
MIGRATION = "0023_control_outbox_pending_index"
BEFORE = "0022_app_activation_creating"
DEFINITION = (
    "CREATE INDEX base_outbox_pending ON public.live_outboxevent USING btree (created_at, id) "
    "WHERE (delivered_at IS NULL)"
)
#: How long ``manage.py`` may take to reach the statement: its start on a loaded machine.
BUILD_STARTS_WITHIN = 300.0


def _migrate_command(*args: str) -> list[str]:
    return [sys.executable, "manage.py", "migrate", *args, "--noinput", "--verbosity", "0"]


def _deploy_options(database: str) -> dict:
    """Production's settings, on ``database``."""
    return {
        "cwd": Path(__file__).resolve().parents[2],
        "env": {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "DB_NAME": database},
        "text": True,
    }


def migrate(database: str, *args: str) -> None:
    done = subprocess.run(_migrate_command(*args), capture_output=True, timeout=600, **_deploy_options(database))
    assert done.returncode == 0, done.stderr[-3000:]


def the_index(database: str) -> tuple[str, bool, int] | None:
    """The index's definition, whether it is valid and its identity, or ``None``."""
    with hubs._maintenance(database) as conn:
        return conn.execute(
            "SELECT pg_get_indexdef(indexrelid), indisvalid, indexrelid::bigint FROM pg_index "
            "WHERE indexrelid = to_regclass(%s)",
            [INDEX],
        ).fetchone()


def indexes_of_the_tables_control_and_a_hub_share(database: str) -> list[tuple[str, str, str]]:
    shared = [
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if inventory.classify(model) == inventory.CONTEXTUAL
    ]
    with hubs._maintenance(database) as conn:
        return conn.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = ANY(%s) ORDER BY tablename, indexname",
            [shared],
        ).fetchall()


def record_an_event(conn: psycopg.Connection, scope_key: str = "registry") -> None:
    conn.execute(
        "INSERT INTO live_outboxevent (id, scope_kind, scope_key, name, payload, actor, created_at) "
        "VALUES (%s, 'control', %s, 'base.hub.created', '{}', '', now())",
        [uuid.uuid7(), scope_key],
    )


def leave_an_invalid_index(database: str) -> None:
    """Two pending events and what a build cut halfway leaves under the name: an invalid index, serving no query."""
    with hubs._maintenance(database) as conn:
        record_an_event(conn)
        record_an_event(conn)
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                sql.SQL("CREATE UNIQUE INDEX CONCURRENTLY {} ON live_outboxevent (scope_key)").format(
                    sql.Identifier(INDEX)
                )
            )
    assert the_index(database)[1] is False


def wait_for_the_statement_behind_a_write(database: str, process: subprocess.Popen) -> None:
    """Until the first statement of ``process`` on the index is waiting for the write still open on the outbox."""
    deadline = time.monotonic() + BUILD_STARTS_WITHIN
    with hubs._maintenance() as conn:
        while time.monotonic() < deadline:
            assert process.poll() is None, f"The migration ended before its statement: {process.stderr.read()[-3000:]}"
            waiting = conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = 'Lock' "
                "AND query LIKE %s",
                [database, f"%INDEX%{INDEX}%"],
            ).fetchone()[0]
            if waiting:
                return
            time.sleep(0.1)
    pytest.fail(f"The statement on the index did not start within {BUILD_STARTS_WITHIN:g} s.")


@contextmanager
def _a_database(name: str):
    with hubs._maintenance() as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield name
    finally:
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def control_from_scratch(django_db_setup):
    """A control database as a new installation makes it: empty, then ``migrate`` with production's settings."""
    with _a_database(f"{connection.settings_dict['NAME']}_i751") as name:
        migrate(name)
        yield name


@pytest.fixture
def control_without_the_index(control_from_scratch):
    """That database as ``base/0023`` finds it on a new installation: no index, an empty outbox, not applied yet."""
    with hubs._maintenance(control_from_scratch) as conn:
        conn.execute(sql.SQL("DROP INDEX IF EXISTS {}").format(sql.Identifier(INDEX)))
        conn.execute("TRUNCATE live_outboxevent CASCADE")
        conn.execute("DELETE FROM django_migrations WHERE app = 'base' AND name = %s", [MIGRATION])
    return control_from_scratch


def test_a_control_database_made_from_scratch_has_the_index_its_relay_needs(control_from_scratch):
    index = the_index(control_from_scratch)

    assert index is not None
    assert index[:2] == (DEFINITION, True)


def test_control_and_a_hub_have_the_same_indexes_on_the_tables_they_share(control_from_scratch, hub_databases):
    """The class of this bug: an operation that names no model reaches a hub's database and never control's."""
    in_control = indexes_of_the_tables_control_and_a_hub_share(control_from_scratch)

    assert in_control
    assert in_control == indexes_of_the_tables_control_and_a_hub_share(hub_databases.a)


@pytest.mark.parametrize("cut_build", [False, True], ids=["no index yet", "an invalid index to replace"])
def test_a_write_goes_on_while_the_index_is_being_built(control_without_the_index, cut_build):
    """A control database with data gets the index under its traffic: nobody's write waits for the build, nor for the
    drop of what a build cut halfway left."""
    database = control_without_the_index
    if cut_build:
        leave_an_invalid_index(database)
    process = None
    with hubs._maintenance(database) as open_write, hubs._maintenance(database) as new_write:
        new_write.execute("SET lock_timeout = '2s'")
        try:
            with open_write.transaction():
                record_an_event(open_write, "open")
                process = subprocess.Popen(
                    _migrate_command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_deploy_options(database)
                )
                wait_for_the_statement_behind_a_write(database, process)

                record_an_event(new_write, "new")

            _, errors = process.communicate(timeout=600)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()

    assert process.returncode == 0, errors[-3000:]
    assert the_index(database)[:2] == (DEFINITION, True)
    with hubs._maintenance(database) as conn:
        conn.execute("SET enable_seqscan = off")
        pending = conn.execute("SELECT count(*) FROM live_outboxevent WHERE delivered_at IS NULL").fetchone()[0]
    assert pending == (4 if cut_build else 2)


def test_an_index_a_failed_build_left_invalid_is_built_again(control_without_the_index):
    """A build cut halfway leaves an invalid index under the name, serving no query: the next deploy replaces it."""
    database = control_without_the_index
    leave_an_invalid_index(database)

    migrate(database)

    assert the_index(database)[:2] == (DEFINITION, True)


def test_stepping_back_keeps_the_index_and_going_forward_again_changes_nothing(control_from_scratch):
    """It may not be this migration's: on a control database of before hub#602 and on a hub's it is ``base/0006``'s."""
    database = control_from_scratch
    index = the_index(database)
    assert index is not None

    migrate(database, "base", BEFORE)
    assert the_index(database) == index

    migrate(database)
    assert the_index(database) == index


def test_a_hubs_database_keeps_its_own_index_and_no_statement_touches_it(hub_databases, django_db_blocker):
    """A hub's database has the index from ``base/0006``. Its outbox takes every sale: only reading the catalog takes no
    lock on it, and stepping ``base`` back through ``0006`` still finds the index to drop."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        ddl = connections[tenancy_connections.register_ddl_alias(name)]
        index = the_index(name)
        assert index[:2] == (DEFINITION, True)

        with CaptureQueriesContext(ddl) as statements:
            MigrationExecutor(ddl).migrate([("base", BEFORE)])
            MigrationExecutor(ddl).migrate([("base", MIGRATION)])

        ddl.close()
        assert the_index(name) == index
        assert not [query["sql"] for query in statements if " INDEX " in query["sql"].upper()]
