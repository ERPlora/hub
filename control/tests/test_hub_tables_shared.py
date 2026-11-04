"""The contract of S5: the hubs' apps' tables left in control's database get ``<table>_shared_20261101``.

Since the cut (PLAN-DB, round 2026-11-01c) no business uses them, yet nothing tells their rows from live data. The
migration ``control/0007`` renames them, never dropping one. What decides which tables are left over is the routers
and the inventory, so the suite's control database, whose ``LegacyTablesRouter`` keeps those tables on purpose, stays
as it is with no test-only branch in the migration: the tests here ask for production's routers themselves.

The renames of a test with a test case roll back with it (PostgreSQL's DDL is transactional). A test that needs them
committed, or another database, works on a database of its own.
"""

import importlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from django.apps import apps
from django.db import OperationalError, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test.utils import CaptureQueriesContext
from psycopg import sql

from base.tenancy import connections as tenancy_connections
from base.tenancy import inventory, names
from base.tenancy.tests import hubs
from control.models import Hub

MIGRATION = "0007_hub_tables_renamed_shared"
BEFORE = "0006_hub_activity"
SUFFIX = "_shared_20261101"
LEGACY_ROUTER = "base.tenancy.tests.legacy.LegacyTablesRouter"
#: Control's own tables, Django's and the outbox's: none of them is ever renamed.
KEPT = {
    "auth_user",
    "base_eventdelivery",
    "base_hub",
    "base_membership",
    "control_cluster",
    "django_migrations",
    "django_session",
    "live_outboxevent",
}
FOREIGN_KEYS = """
    SELECT child.relname, parent.relname FROM pg_constraint c
    JOIN pg_class child ON child.oid = c.conrelid
    JOIN pg_class parent ON parent.oid = c.confrelid
    JOIN pg_namespace n ON n.oid = child.relnamespace
    WHERE c.contype = 'f' AND n.nspname = 'public'
"""


def migration():
    return importlib.import_module(f"control.migrations.{MIGRATION}")


def hub_tables() -> set[str]:
    """Every table the inventory calls a hub's, as the tests read it on their own."""
    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and inventory.classify(model) == inventory.HUB
    }


def shared(table: str) -> str:
    return f"{table}{SUFFIX}"


def tables(on=connection) -> set[str]:
    with on.cursor() as cursor:
        return set(on.introspection.table_names(cursor))


def foreign_keys(on=connection) -> set[tuple[str, str]]:
    with on.cursor() as cursor:
        cursor.execute(FOREIGN_KEYS)
        return set(cursor.fetchall())


def _state():
    return MigrationLoader(None, ignore_no_migrations=True).project_state(("control", BEFORE))


def forwards(on=connection) -> None:
    """The migration's operation as ``migrate`` runs it, the routers' gate included."""
    state = _state()
    with on.schema_editor(atomic=False) as editor:
        migration().Migration.operations[0].database_forwards("control", editor, state, state)


def backwards(on=connection) -> None:
    state = _state()
    with on.schema_editor(atomic=False) as editor:
        migration().Migration.operations[0].database_backwards("control", editor, state, state)


@pytest.fixture
def production_routers(settings):
    """The routers of ``config.settings``: the tests' ``LegacyTablesRouter`` out."""
    settings.DATABASE_ROUTERS = [router for router in settings.DATABASE_ROUTERS if router != LEGACY_ROUTER]


@pytest.fixture
def after_the_cut(db, production_routers):
    """Control as production's is since the cut: no ready business without its own database (the suite's ``a`` and
    ``b`` are, so they are cancelled, as ``yfn`` is in production)."""
    Hub.objects.filter(db_name="", is_demo=False, status=Hub.Status.READY).update(status=Hub.Status.CANCELLED)


# ── What it renames, and what it leaves ───────────────────────────────────────────────────────────────────────────


def test_every_hub_table_left_in_control_gets_its_shared_name_and_no_other_table_moves(after_the_cut):
    found = tables()
    assert hub_tables() <= found

    forwards()

    assert tables() == (found - hub_tables()) | {shared(table) for table in hub_tables()}
    assert KEPT <= tables()


def test_the_list_comes_from_the_inventory_and_nothing_of_control_is_in_it(production_routers):
    listed = set(migration().left_behind("default"))

    assert listed == hub_tables()
    assert not KEPT & listed


def test_a_table_no_model_names_and_the_saas_shared_schema_are_left_alone(after_the_cut):
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE nobody_knows_this (id int)")
        cursor.execute("CREATE SCHEMA IF NOT EXISTS shared")
        cursor.execute("CREATE TABLE IF NOT EXISTS shared.app_of_the_test (id int)")
        cursor.execute("CREATE TABLE shared.printing_printer (id int)")

    forwards()

    assert "nobody_knows_this" in tables()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('shared.app_of_the_test') IS NOT NULL, to_regclass('shared.printing_printer') IS NOT "
            "NULL, to_regclass(%s) IS NULL",
            [f"shared.{shared('printing_printer')}"],
        )
        assert cursor.fetchone() == (True, True, True)


def test_it_only_ever_renames(after_the_cut):
    with CaptureQueriesContext(connection) as queries:
        forwards()
        backwards()

    written = [
        query["sql"].upper()
        for query in queries.captured_queries
        if query["sql"].upper().startswith(("DROP", "TRUNCATE", "DELETE", "ALTER", "CREATE"))
    ]
    assert written
    assert all(statement.startswith("ALTER TABLE") and " RENAME TO " in statement for statement in written)


# ── Only in control ───────────────────────────────────────────────────────────────────────────────────────────────


def test_a_hubs_real_database_is_never_renamed(hub_databases, django_db_blocker, production_routers):
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        ddl = connections[tenancy_connections.register_ddl_alias(name)]
        found = hubs.table_names(name)
        assert hub_tables() & found

        MigrationExecutor(ddl).migrate([("control", MIGRATION)])
        assert hubs.table_names(name) == found

        # Past the routers' gate of ``RunPython``: its own list is empty on a hub's alias too.
        assert migration().left_behind(ddl.alias) == []
        with ddl.schema_editor(atomic=False) as editor:
            migration().forwards(_state().apps, editor)
        assert hubs.table_names(name) == found
        ddl.close()


def test_under_the_suites_routers_the_tables_it_keeps_on_purpose_are_not_left_over(db):
    found = tables()
    assert hub_tables() <= found

    forwards()

    assert tables() == found


# ── The name ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_longest_table_of_the_inventory_fits_and_no_two_end_up_with_one_name():
    renamed = [migration().shared_name(table) for table in sorted(hub_tables())]

    assert max(len(name.encode()) for name in renamed) <= 63
    assert len(set(renamed)) == len(hub_tables())
    assert renamed == [shared(table) for table in sorted(hub_tables())]


def test_a_name_postgres_would_cut_stops_it_before_any_rename(after_the_cut, monkeypatch):
    long_name = "x" * 48
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{long_name}" (id int)')
    module = migration()
    real = module.left_behind
    monkeypatch.setattr(module, "left_behind", lambda alias: [*real(alias), long_name])
    found = tables()

    with pytest.raises(module.HubTablesNotRenamed) as refused:
        forwards()

    assert refused.value.code == "control.shared_name_too_long"
    assert tables() == found


# ── Idempotent, reversible, keys intact ───────────────────────────────────────────────────────────────────────────


def test_running_it_twice_changes_nothing(after_the_cut):
    forwards()
    once = tables()

    forwards()

    assert tables() == once


def test_a_table_that_is_not_there_is_no_failure(after_the_cut):
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE printing_printer RENAME TO out_of_the_way")

    forwards()

    assert {"out_of_the_way", shared("base_hubuser")} <= tables()
    assert shared("printing_printer") not in tables()


def test_a_shared_name_already_taken_stops_nothing_and_both_tables_stay(after_the_cut):
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{shared("printing_printer")}" (id int)')

    forwards()

    assert {"printing_printer", shared("printing_printer"), shared("base_hubuser")} <= tables()


def test_taking_it_back_returns_every_name_and_the_keys_point_where_they_did(after_the_cut):
    found, keys = tables(), foreign_keys()
    between_them = {(child, parent) for child, parent in keys if child in hub_tables() and parent in hub_tables()}
    assert between_them

    forwards()

    renamed = {
        (shared(child) if child in hub_tables() else child, shared(parent) if parent in hub_tables() else parent)
        for child, parent in keys
    }
    assert foreign_keys() == renamed

    backwards()

    assert tables() == found
    assert foreign_keys() == keys


def test_stepping_back_from_a_run_that_stopped_halfway_returns_what_it_had_renamed(after_the_cut, monkeypatch):
    found = tables()
    migration().rename(connection, [("printing_printer", shared("printing_printer"))])
    module = migration()
    real = module.left_behind
    # A table of an app that came after S5: on this database under neither name.
    monkeypatch.setattr(module, "left_behind", lambda alias: [*real(alias), "a_table_this_database_never_had"])

    backwards()

    assert tables() == found


def test_taking_it_back_never_overwrites_a_table_that_came_back(after_the_cut):
    forwards()
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE printing_printer (id int)")

    backwards()

    assert {"printing_printer", shared("printing_printer"), "base_hubuser"} <= tables()


def test_rows_survive_both_ways(after_the_cut):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO base_hub_identity (hub_id) VALUES (%s)", [uuid.uuid7()])
        cursor.execute("SELECT count(*) FROM base_hub_identity")
        rows = cursor.fetchone()[0]

        forwards()
        cursor.execute(f'SELECT count(*) FROM "{shared("base_hub_identity")}"')
        assert cursor.fetchone()[0] == rows

        backwards()
        cursor.execute("SELECT count(*) FROM base_hub_identity")
        assert cursor.fetchone()[0] == rows


# ── A business that was never cut ─────────────────────────────────────────────────────────────────────────────────


def test_a_ready_business_without_its_database_stops_it_and_nothing_is_renamed(db, production_routers):
    # The suite's ``a`` and ``b``: ready, ``db_name`` empty, as an environment that was never cut.
    assert Hub.objects.filter(db_name="", is_demo=False, status=Hub.Status.READY).exists()
    found = tables()

    with pytest.raises(migration().HubTablesNotRenamed) as refused:
        forwards()

    assert refused.value.code == "control.hub_not_cut"
    assert {"a", "b"} <= set(refused.value.slugs)
    assert tables() == found


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"status": Hub.Status.CANCELLED}, id="cancelled"),
        pytest.param({"status": Hub.Status.READY, "is_demo": True}, id="a demo, which ends on its own"),
        pytest.param({"status": Hub.Status.READY, "db_name": "hub_0123"}, id="one with its database"),
    ],
)
def test_who_does_not_stop_it(after_the_cut, fields):
    Hub.objects.create(slug=f"t-{uuid.uuid4().hex[:12]}", **fields)

    forwards()

    assert shared("printing_printer") in tables()


def test_with_nothing_left_over_a_business_without_its_database_stops_no_deploy(db, production_routers, monkeypatch):
    # A database made after S5 holds none of the tables the inventory names: there is nothing to rename under anyone.
    assert Hub.objects.filter(db_name="", is_demo=False, status=Hub.Status.READY).exists()
    monkeypatch.setattr(migration(), "left_behind", lambda alias: ["a_table_this_database_never_had"])

    forwards()


# ── Who runs it ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_table_of_another_owner_stops_it_before_any_rename(after_the_cut):
    found = tables()
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE pg_monitor")  # one every PostgreSQL has, which owns none of them

    with pytest.raises(migration().HubTablesNotRenamed) as refused:
        forwards()

    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    assert refused.value.code == "control.table_of_another_owner"
    assert tables() == found


# ── How long it holds a lock ──────────────────────────────────────────────────────────────────────────────────────


def test_each_table_commits_alone_so_a_stuck_one_keeps_the_rest_and_the_next_run_finishes(
    hub_databases, django_db_blocker, monkeypatch
):
    assert migration().Migration.atomic is False
    monkeypatch.setattr(migration(), "LOCK_TIMEOUT", "100ms")
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        ddl = connections[tenancy_connections.register_ddl_alias(name)]
        first, stuck, last = sorted(hub_tables() & hubs.table_names(name))[:3]
        pairs = [(table, shared(table)) for table in (first, stuck, last)]
        settings = connections.settings["default"]
        with psycopg.connect(
            dbname=name, user=settings["USER"], password=settings["PASSWORD"], host=settings["HOST"], port=settings["PORT"]
        ) as holder:
            holder.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(stuck)))
            with ddl.cursor() as cursor:
                # Without its own lock_timeout the rename fails here, by another code, instead of hanging the suite.
                cursor.execute("SET statement_timeout = '10s'")

            with pytest.raises(OperationalError) as stopped:
                migration().rename(ddl, pairs)

            assert stopped.value.__cause__.sqlstate == psycopg.errors.LockNotAvailable.sqlstate
            holder.rollback()
            # Seen from another connection, so committed.
            found = hubs.table_names(name)
            assert {shared(first), stuck, last} <= found
            assert first not in found

        migration().rename(ddl, pairs)

        found = hubs.table_names(name)
        assert {shared(first), shared(stuck), shared(last)} <= found
        assert not {first, stuck, last} & found
        ddl.close()


# ── The deploy: ``manage.py migrate`` with production's settings on a control database as S5 left it ──────────────


def _manage(database: str, settings_module: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "manage.py", "migrate", *args, "--noinput", "--verbosity", "0"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DJANGO_SETTINGS_MODULE": settings_module, "DB_NAME": database},
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.fixture
def control_as_s5_left_it(django_db_blocker):
    """A control database with every hub's table and everything up to ``control/0006`` applied, in production's state
    today: made by the tests' settings, the migration's record taken out. Dropped after the test."""
    name = f"{connection.settings_dict['NAME']}_s5ctl"
    with django_db_blocker.unblock():
        with hubs._maintenance() as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            made = _manage(name, "config.settings_pytest")
            assert made.returncode == 0, made.stderr[-3000:]
            # What came after it steps back first, or its record gone would leave them applied before their dependency.
            stepped = _manage(name, "config.settings_pytest", "control", MIGRATION)
            assert stepped.returncode == 0, stepped.stderr[-3000:]
            with hubs._maintenance(name) as conn:
                conn.execute("DELETE FROM django_migrations WHERE app = 'control' AND name = %s", [MIGRATION])
                conn.execute("INSERT INTO base_hub_identity (hub_id) VALUES (%s)", [uuid.uuid7()])
            yield name
        finally:
            with hubs._maintenance() as conn:
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.django_db
def test_the_deploy_renames_them_a_second_run_changes_nothing_and_stepping_back_returns_the_names(control_as_s5_left_it):
    name = control_as_s5_left_it
    found = hubs.table_names(name)
    assert hub_tables() <= found

    deployed = _manage(name, "config.settings")

    assert deployed.returncode == 0, deployed.stderr[-3000:]
    renamed = hubs.table_names(name)
    assert renamed == (found - hub_tables()) | {shared(table) for table in hub_tables()}
    with hubs._maintenance(name) as conn:
        assert conn.execute(f'SELECT count(*) FROM "{shared("base_hub_identity")}"').fetchone()[0] == 1
    stepped = _manage(name, "config.settings", "control", MIGRATION)
    assert stepped.returncode == 0, stepped.stderr[-3000:]
    with hubs._maintenance(name) as conn:
        conn.execute("DELETE FROM django_migrations WHERE app = 'control' AND name = %s", [MIGRATION])

    again = _manage(name, "config.settings")

    assert again.returncode == 0, again.stderr[-3000:]
    assert hubs.table_names(name) == renamed

    back = _manage(name, "config.settings", "control", BEFORE)

    assert back.returncode == 0, back.stderr[-3000:]
    assert hubs.table_names(name) == found
    with hubs._maintenance(name) as conn:
        assert conn.execute("SELECT count(*) FROM base_hub_identity").fetchone()[0] == 1
