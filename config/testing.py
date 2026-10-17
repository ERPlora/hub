"""Connections left with a session setting changed, for the autouse fixture of ``conftest.py``.

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
from psycopg.pq import TransactionStatus

#: What a session set and did not put back. Django's own time zone, which it sets on every new
#: connection, is no change.
CHANGED = (
    "SELECT name, current_setting(name) FROM pg_settings WHERE source = 'session' "
    "AND setting IS DISTINCT FROM reset_val AND NOT (name = 'TimeZone' AND setting = %s)"
)


def _changed(conn, time_zone: str) -> list[tuple[int, str, str]]:
    pid = conn.info.backend_pid
    rows = conn.execute(CHANGED, [time_zone]).fetchall()
    if not conn.autocommit:
        conn.rollback()
    return [(pid, name, value) for name, value in rows]


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
    pool = wrapper.pool
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
    ``lock_timeout`` left by flow failed inventory's lock waits, FIX-FLOW-DETAIL-RACE). The connection
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
