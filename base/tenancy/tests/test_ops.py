"""The migrator's maintenance connection: making and dropping a hub's database (PLAN-DB §6; round 2026-10-30, S2a).

``base.tenancy.ops`` reaches the server directly as the migrator (``DB_MIGRATOR_USER``; the default connection's role
where it is not set: local development and these tests), never through PgBouncer and never on a Django alias:
``CREATE DATABASE`` and ``DROP DATABASE`` cannot run in a transaction. A hub's database is a clone of its template,
private (no ``PUBLIC``) and open to the environment's ``hub_app`` and ``hub_admin``; making it twice makes it once,
a template in use is waited for a bounded while, and a drop takes only the database it names.
"""

import uuid

import psycopg
import pytest
from django.db import connections as django_connections
from psycopg import sql

from base.tenancy import bootstrap, names, ops
from base.tenancy import connections as tenancy_connections
from base.tenancy.tests import hubs

pytestmark = pytest.mark.usefixtures("hub_databases")


def databases() -> set[str]:
    """The databases of this session's control database (other sessions make and drop theirs meanwhile)."""
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


@pytest.fixture
def made(hub_databases):
    """Names of hub databases a test makes; dropped after it, whatever happened."""
    control = hub_databases.control
    made_names: list[str] = []

    def new(*, demo: bool = False) -> str:
        build = names.demo_db_name if demo else names.hub_db_name
        made_names.append(name := build(control, uuid.uuid7()))
        return name

    yield new
    with hubs._maintenance() as conn:
        for name in made_names:
            hubs._drop(conn, name, control)


def test_the_maintenance_connection_is_the_migrators_to_postgres_in_autocommit_and_closed_after(settings):
    default = django_connections.settings["default"]
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = default["USER"], default["PASSWORD"]

    with ops.connect_ops() as conn:
        assert conn.info.dbname == "postgres"
        assert conn.autocommit is True
        assert conn.execute("SELECT current_user").fetchone()[0] == default["USER"]

    assert conn.closed


def test_the_migrators_role_reaches_the_maintenance_connection_and_a_hubs_ddl_alias(settings, hub_databases):
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "hub_migrator", "its-password"

    conninfo = tenancy_connections.migrator_conninfo("postgres")
    alias = tenancy_connections.register_ddl_alias(hub_databases.a)
    ddl = django_connections.settings[alias]

    assert (conninfo["user"], conninfo["password"], conninfo["dbname"]) == ("hub_migrator", "its-password", "postgres")
    assert "pool" not in conninfo
    assert (ddl["USER"], ddl["PASSWORD"]) == ("hub_migrator", "its-password")


def test_without_a_migrators_role_the_default_connections_is_used(settings):
    settings.DB_MIGRATOR_USER, settings.DB_MIGRATOR_PASSWORD = "", ""
    default = django_connections.settings["default"]

    conninfo = tenancy_connections.migrator_conninfo("postgres")

    assert (conninfo["user"], conninfo["password"]) == (default["USER"], default["PASSWORD"])


def test_a_clone_is_a_copy_of_its_template_and_a_second_one_makes_nothing(hub_databases, made):
    name = made()

    assert ops.clone_database(name, template=hub_databases.template) is True
    assert hubs.table_names(name) == hubs.table_names(hub_databases.template)
    assert ops.clone_database(name, template=hub_databases.template) is False
    assert name in databases()


def test_a_clone_is_private_and_open_to_the_environments_app_and_admin_roles(hub_databases, made):
    prefix = f"zz{uuid.uuid4().hex[:8]}_"
    roles = bootstrap.Names.with_prefix(prefix)
    name = made()
    with hubs._maintenance() as conn:
        for role in (roles.hub_app, roles.hub_admin):
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
    try:
        ops.clone_database(name, template=hub_databases.template, roles=roles)
        with hubs._maintenance() as conn:
            granted = {
                (role, privilege): conn.execute(
                    "SELECT has_database_privilege(%s, %s, %s)", [role, name, privilege]
                ).fetchone()[0]
                for role in (roles.hub_app, roles.hub_admin)
                for privilege in ("CONNECT", "TEMPORARY")
            }
            acl = conn.execute("SELECT datacl::text[] FROM pg_database WHERE datname = %s", [name]).fetchone()[0]
    finally:
        with hubs._maintenance() as conn:
            hubs._drop(conn, name, hub_databases.control)
            for role in (roles.hub_app, roles.hub_admin):
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

    assert all(granted.values()), granted
    # No entry for PUBLIC (``=…/owner``): only the owner and the two roles.
    assert not [entry for entry in acl if entry.startswith("=")], acl


def test_roles_the_cluster_does_not_have_are_skipped_with_a_warning(hub_databases, made, caplog):
    name = made()
    roles = bootstrap.Names.with_prefix(f"zz{uuid.uuid4().hex[:8]}_")

    assert ops.clone_database(name, template=hub_databases.template, roles=roles) is True

    assert name in databases()
    assert roles.hub_app in caplog.text and "base.tenancy.ops.role_missing" in caplog.text


def test_the_environments_roles_carry_its_control_databases_prefix():
    assert ops.environment_roles("hub") == bootstrap.Names()
    assert ops.environment_roles("pre_hub") == bootstrap.Names.with_prefix("pre_")
    assert ops.environment_roles("test_hub_next") == bootstrap.Names()


def test_a_template_in_use_is_waited_for_and_then_cloned(hub_databases, made):
    name = made()
    blocker = psycopg.connect(**tenancy_connections.migrator_conninfo(hub_databases.template), autocommit=True)
    waited = []

    def wait(seconds):
        waited.append(seconds)
        blocker.close()

    assert ops.clone_database(name, template=hub_databases.template, waits=(0.5, 1.0), sleep=wait) is True
    assert waited == [0.5]
    assert name in databases()


def test_a_template_in_use_for_longer_than_the_waits_is_a_readable_failure(hub_databases, made):
    name = made()
    waited = []
    with psycopg.connect(**tenancy_connections.migrator_conninfo(hub_databases.template), autocommit=True):
        with pytest.raises(ops.DatabaseOpsError, match=r"template .* in use"):
            ops.clone_database(name, template=hub_databases.template, waits=(0.1, 0.2), sleep=waited.append)

    assert waited == [0.1, 0.2]
    assert name not in databases()


def test_a_missing_template_is_a_readable_failure_and_makes_nothing(hub_databases, made):
    name = made()
    missing = names.template_db_name(hub_databases.control, "nowhere")

    with pytest.raises(ops.DatabaseOpsError, match="nowhere"):
        ops.clone_database(name, template=missing)

    assert name not in databases()


@pytest.mark.parametrize("bad", ["postgres", "hub", "template1", 'x"; DROP DATABASE hub; --'])
def test_a_name_that_is_no_hubs_never_reaches_the_server(bad, hub_databases):
    with pytest.raises(names.InvalidDatabaseName):
        ops.clone_database(bad, template=hub_databases.template)
    with pytest.raises(names.InvalidDatabaseName):
        ops.drop_database(bad)


def test_a_template_is_never_dropped(hub_databases):
    with pytest.raises(names.InvalidDatabaseName):
        ops.drop_database(hub_databases.template)

    assert hub_databases.template in databases()


def test_a_drop_takes_its_database_only_even_with_someone_connected(hub_databases, made):
    name = made(demo=True)
    ops.clone_database(name, template=hub_databases.template)
    before = databases()
    connected = psycopg.connect(**tenancy_connections.migrator_conninfo(name), autocommit=True)

    assert ops.drop_database(name) is True

    assert databases() == before - {name}
    with pytest.raises(psycopg.OperationalError):
        connected.execute("SELECT 1")
    connected.close()


def test_dropping_a_database_that_is_not_there_drops_nothing(hub_databases, made):
    name = made(demo=True)
    before = databases()

    assert ops.drop_database(name) is False
    assert databases() == before


def test_the_apps_a_database_recorded_are_read_from_it(hub_databases):
    recorded = ops.recorded_apps(hub_databases.a)

    assert {"base", "live", *hub_databases.apps} <= recorded
