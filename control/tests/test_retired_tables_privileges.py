"""``control/0008``: the app's role loses the tables ``control/0007`` retired (hub#621).

Run against real roles, as ``base/tests/test_bootstrap.py`` does: a bootstrapped cluster with a per-process prefix, so
its control database is ``<prefix>hub`` and its app's role ``<prefix>hub_app``, the shape of pre's ``pre_hub`` and
``pre_hub_app``. The tables are made by its migrator, so they carry the default privileges production's carry.
"""

import importlib
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from django.apps import apps as global_apps
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.state import ProjectState

from base.tenancy import bootstrap, names
from base.tenancy import connections as tenancy_connections
from base.tenancy.tests import hubs
from base.tests.test_bootstrap import VARIABLES, Cluster, allowed, create_master, drop_prefixed, superuser

MIGRATION = "0008_retired_tables_no_app_access"
RENAME = "0007_hub_tables_renamed_shared"
LEGACY_ROUTER = "base.tenancy.tests.legacy.LegacyTablesRouter"
BEFORE = "0006_hub_activity"
#: A table of a hub's app (``base.tenancy.inventory``), as ``control/0007`` finds it in control and what it leaves.
HUB_TABLE = "printing_printer"
RETIRED = f"{HUB_TABLE}_shared_20261101"
OTHER_RETIRED = "printing_printdevice_shared_20261101"
#: Every privilege ``has_table_privilege`` takes on a table (``MAINTAIN`` since PostgreSQL 17).
EVERY_PRIVILEGE = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN")
ANY_PRIVILEGE = ", ".join(EVERY_PRIVILEGE)


def migration():
    return importlib.import_module(f"control.migrations.{MIGRATION}")


@pytest.fixture
def cluster():
    prefix = f"test_rtp_{os.getpid()}_"
    drop_prefixed(prefix)
    try:
        bootstrapped = Cluster(
            prefix=prefix,
            names=bootstrap.Names.with_prefix(prefix),
            passwords={role: f"pw-{role}" for role in VARIABLES},
            master=create_master(prefix),
        )
        bootstrapped.rerun()
        yield bootstrapped
    finally:
        drop_prefixed(prefix)


def make_tables(cluster: Cluster, *tables: str) -> None:
    """``tables``, made by the migrator: the default privileges give them what production's have."""
    with cluster.connect("hub_migrator", cluster.names.control) as conn:
        for table in tables:
            conn.execute(f'CREATE TABLE "{table}" (id int)')


def what_the_app_can_do(cluster: Cluster, table: str) -> dict[str, bool]:
    """Each statement of the app's role on ``table``, run for real."""
    statements = {
        "SELECT": f'SELECT * FROM "{table}"',
        "INSERT": f'INSERT INTO "{table}" VALUES (1)',
        "UPDATE": f'UPDATE "{table}" SET id = 2',
        "DELETE": f'DELETE FROM "{table}"',
    }
    with cluster.connect("hub_app", cluster.names.control) as conn:
        return {name: allowed(conn, statement) for name, statement in statements.items()}


def the_admin_reads(cluster: Cluster, table: str) -> bool:
    with cluster.connect("hub_admin", cluster.names.control) as conn:
        return allowed(conn, f'SELECT * FROM "{table}"')


ALL_ALLOWED = {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": True}
NONE_ALLOWED = {"SELECT": False, "INSERT": False, "UPDATE": False, "DELETE": False}


# ── The deploy: ``manage.py migrate`` as ``hub-migrate`` runs it, the migrator's role and production's settings ──────


def run_migrate(cluster: Cluster, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "manage.py", "migrate", *args, "--noinput", "--verbosity", "0"],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "DB_NAME": cluster.names.control,
            "DB_USER": cluster.role("hub_migrator"),
            "DB_PASSWORD": cluster.passwords["hub_migrator"],
        },
        capture_output=True,
        text=True,
        timeout=600,
    )


def migrate(cluster: Cluster, *args: str) -> None:
    done = run_migrate(cluster, *args)
    assert done.returncode == 0, done.stderr[-3000:]


def test_the_deploy_takes_the_retired_tables_from_the_app_and_stepping_back_returns_them(cluster):
    migrate(cluster, "control", BEFORE)
    make_tables(cluster, HUB_TABLE)
    assert what_the_app_can_do(cluster, HUB_TABLE) == ALL_ALLOWED

    migrate(cluster, "control")

    assert what_the_app_can_do(cluster, RETIRED) == NONE_ALLOWED
    assert the_admin_reads(cluster, RETIRED)

    migrate(cluster, "control", BEFORE)

    assert what_the_app_can_do(cluster, HUB_TABLE) == ALL_ALLOWED


def test_a_deploy_that_cannot_close_one_fails_closes_none_and_records_nothing(cluster):
    # The migration's own transaction: ``as_migrator`` below brings one of the test's.
    foreign = f"foreign_{RETIRED}"
    migrate(cluster, "control", BEFORE)
    make_tables(cluster, HUB_TABLE)
    with superuser(cluster.names.control) as conn:
        conn.execute(f'CREATE TABLE "{foreign}" (id int)')
        conn.execute(f'GRANT SELECT ON "{foreign}" TO "{cluster.role("hub_migrator")}"')
        conn.execute(f'GRANT INSERT ON "{foreign}" TO "{cluster.role("hub_app")}"')

    done = run_migrate(cluster, "control")

    assert done.returncode != 0
    assert "RetiredTablesStillOpen" in done.stderr
    assert what_the_app_can_do(cluster, RETIRED) == ALL_ALLOWED
    with superuser(cluster.names.control) as conn:
        recorded = conn.execute("SELECT 1 FROM django_migrations WHERE app = 'control' AND name = %s", [MIGRATION])
        assert recorded.fetchone() is None


# ── The migration's steps, as the migrator, on the cluster's control database ─────────────────────────────────────


@pytest.fixture
def as_migrator(cluster, django_db_blocker):
    """Run a step of the migration in a transaction of its own, as ``hub-migrate``'s role, where the deploy runs it."""
    alias = f"{cluster.prefix}control"

    def run(step) -> None:
        with django_db_blocker.unblock(), connections[alias].schema_editor() as editor:
            step(global_apps, editor)

    default = connections.settings[DEFAULT_DB_ALIAS]
    connections.settings[alias] = {
        **default,
        "NAME": cluster.names.control,
        "USER": cluster.role("hub_migrator"),
        "PASSWORD": cluster.passwords["hub_migrator"],
        # Django keeps a pool per alias, past this test and its database.
        "OPTIONS": {option: value for option, value in default["OPTIONS"].items() if option != "pool"},
    }
    try:
        yield run
    finally:
        connections[alias].close()
        del connections[alias]
        del connections.settings[alias]


def acl(cluster: Cluster, table: str) -> set[str]:
    """Who holds what on ``table``, each entry as the server writes it; their order means nothing."""
    with superuser(cluster.names.control) as conn:
        return set(conn.execute("SELECT relacl::text[] FROM pg_class WHERE relname = %s", [table]).fetchone()[0])


def the_app_holds_anything(cluster: Cluster, table: str) -> bool:
    with superuser(cluster.names.control) as conn:
        return conn.execute(
            "SELECT has_table_privilege(%s, %s, %s)", [cluster.role("hub_app"), table, ANY_PRIVILEGE]
        ).fetchone()[0]


def test_every_retired_table_closes_and_no_other_does(cluster, as_migrator):
    alive = "control_cluster_like"
    same_start = f"{RETIRED}_notes"
    another_date = f"{HUB_TABLE}_shared_20261102"
    make_tables(cluster, RETIRED, OTHER_RETIRED, alive, same_start, another_date)

    as_migrator(migration().forwards)

    assert what_the_app_can_do(cluster, RETIRED) == NONE_ALLOWED
    assert what_the_app_can_do(cluster, OTHER_RETIRED) == NONE_ALLOWED
    assert what_the_app_can_do(cluster, alive) == ALL_ALLOWED
    assert what_the_app_can_do(cluster, same_start) == ALL_ALLOWED
    assert what_the_app_can_do(cluster, another_date) == ALL_ALLOWED


def test_it_takes_whatever_the_app_held_not_only_what_the_default_privileges_gave(cluster, as_migrator):
    make_tables(cluster, RETIRED)
    with cluster.connect("hub_migrator", cluster.names.control) as conn:
        conn.execute(f'GRANT ALL ON "{RETIRED}" TO "{cluster.role("hub_app")}"')
    assert the_app_holds_anything(cluster, RETIRED)

    as_migrator(migration().forwards)

    assert not the_app_holds_anything(cluster, RETIRED)


def test_support_keeps_reading_them_and_only_reading(cluster, as_migrator):
    # hub_admin's pg_dump of control (PLAN-DB §10) needs SELECT on every table it dumps; these keep rows nobody deleted.
    make_tables(cluster, RETIRED)

    as_migrator(migration().forwards)

    assert the_admin_reads(cluster, RETIRED)
    with cluster.connect("hub_admin", cluster.names.control) as conn:
        assert not allowed(conn, f'INSERT INTO "{RETIRED}" VALUES (1)')


def test_a_rerun_of_the_bootstrap_does_not_give_them_back(cluster, as_migrator):
    make_tables(cluster, RETIRED)
    as_migrator(migration().forwards)

    cluster.rerun()

    assert what_the_app_can_do(cluster, RETIRED) == NONE_ALLOWED


def test_running_it_twice_changes_nothing(cluster, as_migrator):
    make_tables(cluster, RETIRED)
    as_migrator(migration().forwards)
    closed = acl(cluster, RETIRED)

    as_migrator(migration().forwards)

    assert acl(cluster, RETIRED) == closed


def test_stepping_back_returns_exactly_what_it_took(cluster, as_migrator):
    make_tables(cluster, RETIRED)
    before = acl(cluster, RETIRED)
    as_migrator(migration().forwards)
    assert acl(cluster, RETIRED) != before

    as_migrator(migration().backwards)

    assert acl(cluster, RETIRED) == before


def test_a_table_the_migrator_cannot_close_stops_the_deploy_and_closes_none(cluster, as_migrator):
    # PostgreSQL only warns when who revokes is not the owner: what the app still holds is read back.
    foreign = {privilege: f"foreign_{privilege.lower()}_{RETIRED}" for privilege in EVERY_PRIVILEGE}
    make_tables(cluster, RETIRED)
    with superuser(cluster.names.control) as conn:
        for privilege, table in foreign.items():
            conn.execute(f'CREATE TABLE "{table}" (id int)')
            conn.execute(f'GRANT SELECT ON "{table}" TO "{cluster.role("hub_migrator")}"')
            conn.execute(f'GRANT {privilege} ON "{table}" TO "{cluster.role("hub_app")}"')

    with pytest.raises(migration().RetiredTablesStillOpen) as stopped:
        as_migrator(migration().forwards)

    assert stopped.value.code == "control.retired_table_still_open"
    assert stopped.value.tables == sorted(foreign.values())
    assert what_the_app_can_do(cluster, RETIRED) == ALL_ALLOWED


def test_a_server_without_the_role_stops_no_deploy_and_says_so(cluster, as_migrator, monkeypatch, caplog):
    # Local development and the suite's control database: the compose Postgres's user is every role.
    make_tables(cluster, RETIRED)
    monkeypatch.setattr(migration(), "environment_roles", lambda control: bootstrap.Names.with_prefix("nobody_"))

    with caplog.at_level(logging.WARNING, logger="base.tenancy.migrator"):
        as_migrator(migration().forwards)
        as_migrator(migration().backwards)

    assert [record.getMessage().split()[0] for record in caplog.records] == ["control.retired_tables_role_missing"] * 2
    assert what_the_app_can_do(cluster, RETIRED) == ALL_ALLOWED


def test_with_nothing_retired_it_does_not_even_look_for_the_role(cluster, as_migrator, monkeypatch):
    make_tables(cluster, "still_in_use")

    def no_role_is_needed(control):
        raise AssertionError(f"asked for the roles of {control} with nothing to close")

    monkeypatch.setattr(migration(), "environment_roles", no_role_is_needed)

    as_migrator(migration().forwards)
    as_migrator(migration().backwards)

    assert what_the_app_can_do(cluster, "still_in_use") == ALL_ALLOWED


def test_a_hubs_real_database_is_never_touched(hub_databases, django_db_blocker, settings, monkeypatch):
    # TenantRouter migrates the control app on control's alias alone; a hub's database never gets this far.
    settings.DATABASE_ROUTERS = [router for router in settings.DATABASE_ROUTERS if router != LEGACY_ROUTER]

    def looked_for_tables(connection):
        raise AssertionError(f"the migration ran on {connection.alias}")

    monkeypatch.setattr(migration(), "_retired", looked_for_tables)
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        ddl = connections[tenancy_connections.register_ddl_alias(name)]
        state = ProjectState()
        operation = migration().Migration.operations[0]
        with ddl.schema_editor() as editor:
            operation.database_forwards("control", editor, state, state)
            operation.database_backwards("control", editor, state, state)
        ddl.close()


def test_it_closes_the_names_control_0007_gives():
    rename = importlib.import_module(f"control.migrations.{RENAME}")

    assert migration().SUFFIX == rename.SUFFIX
