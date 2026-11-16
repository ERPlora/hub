"""What the fixtures of ``conftest.py`` check on the test databases: connections left with a session setting changed,
connections left with their own ``ensure_connection`` (``database_block_left_as_found``), a database kept by
``--reuse-db`` that lost its factory data (``lost_its_factory_data``) and a pool made before the session had its test
database (``close_pools_made_before_the_test_database``).

The control database's pool (``DATABASES["default"]["OPTIONS"]["pool"]``) hands a connection out again
as its last user left it, so a session ``SET`` (a lock or statement timeout, a time zone, a role…) made
in one test reached whichever test took that connection next: a 300 ms ``lock_timeout`` left by a test of
flow failed inventory's and staff's lock waits in the deploy of e0a2e79. The code sets none (its limits
are ``SET LOCAL`` or the role's, ``base/tenancy/bootstrap.py``), so the tests are where one is caught.

Not the pool's ``reset``: with one, psycopg hands every connection back from a worker thread, after the
caller has moved on, and when Django drops the test database it hands back its own connection and closes
the pool at once; psycopg then drops the pending hand-back without closing the connection, and
``DROP DATABASE`` waits 5 s for it and fails (measured: every run, 8.7 s instead of 3.4 s).
"""

import pytest
from django.db import DEFAULT_DB_ALIAS, connections
from psycopg import OperationalError, errors
from psycopg.pq import TransactionStatus

#: A table the migrations plant factory rows in, the tax app's catalogue. The flush of a transactional test empties
#: every table at once, so this one speaks for all of them (``config/tests/test_reuse_db.py`` holds it to that).
FACTORY_TABLE = "tax_taxcategory"

#: What a session set and did not put back. Django's own time zone, which it sets on every new
#: connection, is no change.
CHANGED = (
    "SELECT name, current_setting(name) FROM pg_settings WHERE source = 'session' "
    "AND setting IS DISTINCT FROM reset_val AND NOT (name = 'TimeZone' AND setting = %s)"
)


def lost_its_factory_data(database: str) -> bool:
    """Whether the test database ``database``, kept by ``--reuse-db``, has no factory data left.

    A ``django_db(transaction=True)`` test empties every table when it ends, the rows the migrations planted too. Those
    migrations stay applied, so ``migrate`` never plants them again: only making the database again brings them back.
    Without the database or the table nothing is lost: the ``migrate`` of ``--reuse-db`` makes them, rows included, and
    says so itself if the server cannot be reached.
    """
    from base.tenancy.tests import hubs

    try:
        with hubs._maintenance(database) as conn:
            return conn.execute(f"SELECT NOT EXISTS (SELECT FROM {FACTORY_TABLE})").fetchone()[0]
    except (OperationalError, errors.UndefinedTable):
        return False


def _changed(conn, time_zone: str) -> list[tuple[int, str, str]]:
    pid = conn.info.backend_pid
    rows = conn.execute(CHANGED, [time_zone]).fetchall()
    if not conn.autocommit:
        conn.rollback()
    return [(pid, name, value) for name, value in rows]


def existing_pool(wrapper):
    """The pool of ``wrapper``'s alias if one was made, else ``None``: never makes one.

    Django makes it the first time ``wrapper.pool`` is read, on the database's name of that moment, and keeps it when
    ``create_test_db`` renames the alias to the test database. Read after the first test of an xdist worker that had no
    database, that name was the developer's, and the whole worker, its ``migrate`` included, read and wrote the
    developer's database (hub#1332)."""
    return type(wrapper)._connection_pools.get(wrapper.alias)


def close_pools_made_before_the_test_database() -> None:
    """Close every pool made before the session had its test database, with this thread's connection, as Django closes
    them before it clones or drops a test database (``create_test_db`` does not): whatever read ``connection.pool``
    before then made it on the developer's database, and the next connection would be taken from it."""
    for alias in connections:
        wrapper = connections[alias]
        if existing_pool(wrapper) is not None:
            wrapper.close()
            wrapper.close_pool()


def discard_changed_sessions() -> list[tuple[int, str, str]]:
    """The session settings left changed, as ``(backend pid, name, value)``, on this thread's connection
    and on the free connections of the control pool: what the next test to take one would inherit. Each
    such connection is closed, so that the pool replaces it and nothing reaches the next test."""
    wrapper = connections[DEFAULT_DB_ALIAS]
    time_zone = wrapper.timezone_name
    found: list[tuple[int, str, str]] = []
    own = wrapper.connection
    if own is not None and own.info.transaction_status == TransactionStatus.IDLE:
        if changed := _changed(own, time_zone):
            found += changed
            own.close()
            wrapper.close()  # hands the closed connection back: the pool discards it
    pool = existing_pool(wrapper)
    if pool is not None and not pool.closed:
        # The pool hands out the oldest free connection and takes a returned one at the back: as many
        # turns as free connections see each of them once.
        for _ in range(pool.get_stats()["pool_available"]):
            conn = pool.getconn(timeout=1)
            try:
                if changed := _changed(conn, time_zone):
                    found += changed
                    conn.close()
            finally:
                pool.putconn(conn)
    return sorted(found)


def session_settings_left_as_found():
    """The autouse fixture of ``conftest.py``: fails the test that leaves a database connection with a
    session setting changed, which the pool would hand to the next test as it is (a 300 ms
    ``lock_timeout`` left by a test of ``apps/flow`` fails inventory's lock waits). The connection
    is discarded, so the next test starts clean."""
    yield
    if left := discard_changed_sessions():
        changed = ", ".join(f"{name} = {value} (backend {pid})" for pid, name, value in left)
        pytest.fail(
            f"left a database connection with its session changed: {changed}. A session SET reaches "
            "whichever test takes that connection next: use SET LOCAL inside the transaction, or put "
            "it back before the connection is handed back.",
            pytrace=False,
        )


#: The method pytest-django blocks for a test without the database, on the connections' class
#: (``BaseDatabaseWrapper.ensure_connection``), as Django's ``SimpleTestCase`` does.
BLOCKED = "ensure_connection"


def discard_hidden_blocks() -> list[str]:
    """The aliases of this thread's connections that keep their own ``ensure_connection``, over their class's: what
    ``monkeypatch.setattr(connection, "ensure_connection", …)`` leaves when it is undone, the real method it read while
    the test had the database. Each one is removed, so the connection answers with its class's again, blocked or not as
    pytest-django says.

    Only that method: Django's ``SimpleTestCase`` puts back ``connect``, ``cursor``… on the connections a test does not
    use, on the connection itself, and those still go through ``ensure_connection``."""
    found: list[str] = []
    for wrapper in connections.all(initialized_only=True):
        if BLOCKED in vars(wrapper):
            found.append(wrapper.alias)
            delattr(wrapper, BLOCKED)
    return sorted(found)


@pytest.hookimpl(wrapper=True)
def database_block_left_as_found(item, nextitem):
    """The ``pytest_runtest_teardown`` of ``conftest.py``: once every fixture of the test is torn down, ``monkeypatch``
    included, fails the test that left a connection with its own ``ensure_connection`` (hub#822).

    A test that patches it on the connection itself gets back, at the undo, the real method it read while it had the
    database, now on the connection: it hides pytest-django's block, and a later test of the same process without the
    database queries instead of failing (it passes on one machine and fails in another worker of ``-n 4``). The
    method is removed, so the next test starts clean."""
    try:
        return (yield)
    finally:
        if left := discard_hidden_blocks():
            pytest.fail(
                f"left its own {BLOCKED} on the database connection {', '.join(left)}: patching the connection leaves "
                "the real method on it at the undo, which hides pytest-django's block from every later test without "
                "the database in the process. Patch its class instead, type(connections[alias]).",
                pytrace=False,
            )
