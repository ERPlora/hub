"""``hub_migrator`` may end the sessions of a database it drops (review of hub#471, I3; PLAN-DB §6, «Baja»).

``DROP DATABASE … WITH (FORCE)`` (a demo that ended, ``base.tenancy.ops.drop_database``) terminates whoever is
connected to it: a session of ``hub_app`` through PgBouncer, an open page's live stream. A role that is no superuser may
only signal another role's backend as a member of ``pg_signal_backend``, so the bootstrap makes ``hub_migrator`` one
(idempotent, as every step). The master here is RDS-like: no superuser, ``CREATEROLE`` and ``pg_signal_backend`` with
its ADMIN option, as ``rds_superuser`` holds it (to be checked on Aurora in ``pre``, PLAN-DB cabecera (o)).
"""

import os

import psycopg
import pytest
from psycopg import sql

from base.tenancy import bootstrap
from base.tests.test_bootstrap import VARIABLES, connect_as, create_master, drop_prefixed, superuser

pytestmark = pytest.mark.django_db


@pytest.fixture(scope="module")
def cluster():
    prefix = f"test_bss_{os.getpid()}_"
    drop_prefixed(prefix)
    try:
        conninfo = create_master(prefix)
        names = bootstrap.Names.with_prefix(prefix)
        passwords = {role: f"pw-{role}" for role in VARIABLES}
        steps = bootstrap.bootstrap(passwords=passwords, names=names, conninfo=conninfo, require_extensions=False)
        yield names, passwords, conninfo, steps
    finally:
        drop_prefixed(prefix)


def is_member(role: str, of: str) -> bool:
    with superuser() as conn:
        return conn.execute("SELECT pg_has_role(%s, %s, 'MEMBER')", [role, of]).fetchone()[0]


def test_the_migrator_may_end_the_sessions_of_a_database_it_drops(cluster):
    names, _passwords, _conninfo, steps = cluster

    assert is_member(names.hub_migrator, "pg_signal_backend")
    assert [str(step) for step in steps if "pg_signal_backend" in step.subject] == [
        f"pg_signal_backend for {names.hub_migrator}: created"
    ]


def test_a_second_run_finds_it_granted(cluster):
    names, passwords, conninfo, _steps = cluster

    again = bootstrap.bootstrap(passwords=passwords, names=names, conninfo=conninfo, require_extensions=False)

    assert [str(step) for step in again if "pg_signal_backend" in step.subject] == [
        f"pg_signal_backend for {names.hub_migrator}: exists"
    ]


def test_a_demo_with_an_app_session_open_is_dropped_by_the_migrator(cluster):
    names, passwords, _conninfo, _steps = cluster
    demo = names.control + "_demo_probe"
    with connect_as(names.hub_migrator, passwords["hub_migrator"], "postgres") as migrator:
        migrator.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(demo), sql.Identifier(names.template))
        )
        migrator.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(demo), sql.Identifier(names.hub_app)))
        visitor = connect_as(names.hub_app, passwords["hub_app"], demo)
        try:
            migrator.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(demo)))
        finally:
            visitor.close()
        assert migrator.execute("SELECT 1 FROM pg_database WHERE datname = %s", [demo]).fetchone() is None


def test_without_it_the_drop_of_a_database_in_use_is_refused(cluster):
    """Why the step exists: the same drop, with the migrator out of ``pg_signal_backend``, is refused."""
    names, passwords, conninfo, _steps = cluster
    demo = names.control + "_demo_refused"
    with superuser() as conn:
        conn.execute(
            sql.SQL("REVOKE pg_signal_backend FROM {} GRANTED BY {}").format(
                sql.Identifier(names.hub_migrator), sql.Identifier(conninfo["user"])
            )
        )
    assert not is_member(names.hub_migrator, "pg_signal_backend")
    try:
        with connect_as(names.hub_migrator, passwords["hub_migrator"], "postgres") as migrator:
            migrator.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(demo), sql.Identifier(names.template))
            )
            migrator.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(demo), sql.Identifier(names.hub_app))
            )
            visitor = connect_as(names.hub_app, passwords["hub_app"], demo)
            try:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    migrator.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(demo)))
            finally:
                visitor.close()
    finally:
        with superuser() as conn:
            conn.execute(sql.SQL("GRANT pg_signal_backend TO {}").format(sql.Identifier(names.hub_migrator)))
