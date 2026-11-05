"""``--reuse-db`` finds the factory data whatever the run before it left (``conftest.py``, ``django_db_createdb``).

A ``django_db(transaction=True)`` test empties every table when it ends, the rows the migrations planted too. Its own
session never notices, because pytest-django runs those tests last. ``--reuse-db`` keeps that database, though, and
the next run's tests failed with nothing broken (hub#746). The steps here are that run's, in a pytest of their own.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.db import connection
from psycopg import sql

from base.tenancy.tests import hubs
from config import testing

CASES = Path(__file__).with_name("reuse_db_cases.py")

#: Seconds a run may take: making its database takes seconds, and minutes on a machine under load.
RUN_TIMEOUT = 1200


def _worker_database(database: str) -> str:
    """What the one xdist worker of ``_run_with_reuse_db`` calls ``database``."""
    return f"{database}_gw0"


def _drop(*names: str) -> None:
    with hubs._maintenance() as conn:
        for name in names:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def database():
    """The name of a database only this test uses: this session's and this xdist worker's, dropped around the test."""
    owner = f"{settings.TEST_DB_NAME}:{os.environ.get('PYTEST_XDIST_WORKER', '')}"
    name = f"test_reuse_{hashlib.sha256(owner.encode()).hexdigest()[:8]}"
    _drop(name, _worker_database(name))
    yield name
    _drop(name, _worker_database(name))


def _run_with_reuse_db(database: str, case: str) -> None:
    """Runs ``case`` of ``reuse_db_cases.py`` in a pytest that knows nothing of this one, with an xdist worker: the
    check has to look at that worker's database, whose name only the order of the fixtures gets right."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--ds=config.tests.reuse_db_settings",
            "-n",
            "1",
            "--reuse-db",
            f"{CASES}::{case}",
        ],
        cwd=settings.BASE_DIR,
        env={**environment, "TEST_DB_NAME": database},
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    assert result.returncode == 0, f"{case}:\n{result.stdout[-3000:]}\n{result.stderr[-1000:]}"


def _factory_rows(database: str) -> int:
    with hubs._maintenance(_worker_database(database)) as conn:
        return conn.execute("SELECT count(*) FROM tax_taxcategory").fetchone()[0]


def test_a_reused_database_a_transactional_test_emptied_is_created_again(database):
    _run_with_reuse_db(database, "test_a_transactional_test")
    assert _factory_rows(database) == 0, "the transactional test left the factory data: this test proves nothing"

    _run_with_reuse_db(database, "test_finds_the_factory_data")
    assert _factory_rows(database) > 0

    # A database with its factory data is reused, not made again: what it holds is still there after the next run.
    with hubs._maintenance(_worker_database(database)) as conn:
        conn.execute("CREATE TABLE still_the_same_database (id integer)")
    _run_with_reuse_db(database, "test_finds_the_factory_data")
    with hubs._maintenance(_worker_database(database)) as conn:
        assert conn.execute("SELECT to_regclass('still_the_same_database')").fetchone()[0] is not None


def test_only_a_factory_table_without_rows_counts_as_lost(database):
    table = sql.Identifier(testing.FACTORY_TABLE)
    # No database yet, or one without the table: the migrate of --reuse-db makes them, the factory data with them.
    assert not testing.lost_its_factory_data(database)
    with hubs._maintenance() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    assert not testing.lost_its_factory_data(database)

    with hubs._maintenance(database) as conn:
        conn.execute(sql.SQL("CREATE TABLE {} (id integer)").format(table))
    assert testing.lost_its_factory_data(database)

    with hubs._maintenance(database) as conn:
        conn.execute(sql.SQL("INSERT INTO {} VALUES (1)").format(table))
    assert not testing.lost_its_factory_data(database)


@pytest.mark.django_db
def test_the_migrations_plant_rows_in_the_table_that_speaks_for_the_factory_data():
    """Without them every --reuse-db run would make its database again, and nothing would fail to say so."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT EXISTS (SELECT FROM {connection.ops.quote_name(testing.FACTORY_TABLE)})")
        assert cursor.fetchone()[0]
