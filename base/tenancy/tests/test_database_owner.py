"""A database of the cluster exists and belongs to its owner, whatever a former run left behind."""

import os

import pytest
from psycopg import sql

from base.tenancy.database_owner import _ensure_database
from base.tests.test_bootstrap import drop_prefixed, superuser


@pytest.fixture
def prefix():
    prefix = f"test_bso_{os.getpid()}_"
    drop_prefixed(prefix)
    try:
        with superuser() as conn:
            for role in ("owner", "former"):
                conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(prefix + role)))
        yield prefix
    finally:
        drop_prefixed(prefix)


def owner_of(conn, database: str) -> str:
    return conn.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", [database]
    ).fetchone()[0]


class LookedBeforeAnotherRun:
    """A connection whose first look at ``pg_database`` came just before another run created the database."""

    def __init__(self, conn):
        self.conn = conn
        self.looked = False

    def execute(self, query, params=None):
        if not self.looked and "pg_database" in str(query):
            self.looked = True
            return self.conn.execute("SELECT 1 WHERE false")
        return self.conn.execute(query, params)


def test_a_missing_database_is_created_with_its_owner(prefix):
    with superuser() as conn:
        assert _ensure_database(conn, prefix + "db", prefix + "owner") == ("created", f"owner {prefix}owner")
        assert owner_of(conn, prefix + "db") == prefix + "owner"


def test_a_database_of_its_owner_is_left_as_it_is(prefix):
    with superuser() as conn:
        _ensure_database(conn, prefix + "db", prefix + "owner")
        assert _ensure_database(conn, prefix + "db", prefix + "owner") == ("exists", f"owner {prefix}owner")


def test_a_database_of_another_role_is_handed_to_its_owner(prefix):
    with superuser() as conn:
        _ensure_database(conn, prefix + "db", prefix + "former")
        assert _ensure_database(conn, prefix + "db", prefix + "owner") == (
            "updated",
            f"owner {prefix}owner, was {prefix}former",
        )
        assert owner_of(conn, prefix + "db") == prefix + "owner"


def test_a_database_another_run_created_meanwhile_is_found_not_failed(prefix):
    with superuser() as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(prefix + "db"), sql.Identifier(prefix + "owner")
            )
        )
        outcome = _ensure_database(LookedBeforeAnotherRun(conn), prefix + "db", prefix + "owner")
    assert outcome == ("exists", f"owner {prefix}owner")
