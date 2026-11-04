"""What the tests call «nobody connected» (``hubs.client_sessions_on``, ``hubs.assert_nobody_on``): a connection our
code left open fails, whatever else the server is doing on that database does not."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import pytest

from base.tenancy.tests import hubs
from base.tenancy.tests.hubs import committed_database, make_database, new_database  # noqa: F401 (fixtures)

#: How long a parallel worker may take to start on a loaded machine.
WORKER_START_WAIT = 30


@contextmanager
def a_process_of_the_server_on(name: str) -> Iterator[psycopg.Connection]:
    """A process of the server on the database ``name`` that no client opened, listed with its ``datname`` like a
    session; yields the only client on it. An autovacuum worker is that, but no test can summon one: a parallel worker
    is the same thing to ``pg_stat_activity``."""
    with hubs._maintenance(name) as leader, hubs._maintenance() as watcher:
        pid = leader.info.backend_pid
        leader.execute("SET debug_parallel_query = on")
        leader.pgconn.send_query(b"SELECT pg_sleep(60)")
        deadline = time.monotonic() + WORKER_START_WAIT
        query = "SELECT 1 FROM pg_stat_activity WHERE leader_pid = %s AND backend_type = 'parallel worker'"
        while not watcher.execute(query, [pid]).fetchone():
            assert time.monotonic() < deadline, "no parallel worker came: the control proves nothing"
            time.sleep(hubs.SESSIONS_END_POLL)
        try:
            yield leader
        finally:
            watcher.execute("SELECT pg_cancel_backend(%s)", [pid])
            while leader.pgconn.get_result() is not None:
                pass


def test_a_process_of_the_server_on_a_database_is_nobodys_session(new_database):
    """hub#819's CI (``assert 2 == 1``, ``assert 1 == 0``): an autovacuum worker on ``pg_database``, working from a
    database just made, counted as a session on it, and no connection of ours was left open."""
    with a_process_of_the_server_on(new_database) as leader:
        assert [row[0] for row in hubs.client_sessions_on(new_database)] == [leader.info.backend_pid]


def test_nobody_on_waits_for_a_session_that_ends_a_moment_after_it_is_asked(new_database):
    """The race of hub#484's CI (``assert 1 == 0``): a client's ``close()`` returns before its server process has left
    ``pg_stat_activity``. Here a real session ends half a second after the check starts: an instant count still sees
    it, and the check waits for it to go."""
    with hubs._maintenance(new_database) as conn:
        assert [row[0] for row in hubs.client_sessions_on(new_database)] == [conn.info.backend_pid]
        closing = threading.Timer(0.5, conn.close)
        closing.start()
        try:
            hubs.assert_nobody_on(new_database)
        finally:
            closing.cancel()
            closing.join()


def test_nobody_on_still_fails_after_its_wait_on_a_session_left_open_naming_it(new_database):
    with hubs._maintenance(new_database) as conn:
        started = time.monotonic()
        with pytest.raises(AssertionError, match=rf"\b{conn.info.backend_pid}\b"):
            hubs.assert_nobody_on(new_database, wait=0.5)
        waited = time.monotonic() - started

    assert waited >= 0.5
