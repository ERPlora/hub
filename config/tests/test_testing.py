"""A connection handed back with a session setting changed is found and discarded (``config/testing.py``).

The control database's pool hands a connection out again as its last user left it: a test's
``SET lock_timeout = '300ms'`` (FIX-FLOW-DETAIL-RACE) reached inventory's and staff's lock waits in
the tests after it and failed them in the deploy of e0a2e79. The autouse fixture of ``conftest.py``
fails the test that leaves one, and discards it so that the next test starts clean.
"""

import threading

import pytest
from django.db import connection

from config.testing import discard_changed_sessions, session_settings_left_as_found

pytestmark = pytest.mark.django_db(transaction=True)


def handed_back_with(*statements: str) -> int:
    """Runs ``statements`` in its own thread and hands its connection back to the pool, as Django does at
    the end of a request; the backend pid of that connection."""
    pids: list[int] = []

    def body():
        try:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    thread.join(10)
    return pids[0]


def test_a_pooled_connection_handed_back_with_a_session_setting_is_found_and_discarded():
    pid = handed_back_with("SET lock_timeout = '300ms'", "SET TIME ZONE 'Europe/Madrid'")
    assert discard_changed_sessions() == [(pid, "TimeZone", "Europe/Madrid"), (pid, "lock_timeout", "300ms")]
    # Discarded: the pool never hands it out again.
    assert discard_changed_sessions() == []
    with connection.pool.connection() as conn:
        assert conn.execute("SELECT pg_backend_pid()").fetchone()[0] != pid


def test_a_setting_put_back_as_it_was_and_djangos_own_time_zone_are_not_a_change():
    handed_back_with("SET lock_timeout = '2s'", "SET lock_timeout = 0", "SET TIME ZONE 'UTC'")
    assert discard_changed_sessions() == []


def test_this_threads_own_connection_left_with_a_session_setting_is_found_and_discarded():
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '1s'")
        cursor.execute("SELECT pg_backend_pid()")
        pid = cursor.fetchone()[0]
    assert discard_changed_sessions() == [(pid, "statement_timeout", "1s")]
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid(), current_setting('statement_timeout')")
        assert cursor.fetchone()[0] != pid


def test_the_fixture_fails_the_test_that_leaves_one_and_says_what_it_left():
    check = session_settings_left_as_found()
    next(check)
    pid = handed_back_with("SET lock_timeout = '300ms'")
    with pytest.raises(pytest.fail.Exception, match=rf"lock_timeout = 300ms \(backend {pid}\)"):
        next(check)


def test_the_fixture_lets_a_test_that_leaves_none_pass():
    check = session_settings_left_as_found()
    next(check)
    handed_back_with("SET LOCAL lock_timeout = '300ms'")
    with pytest.raises(StopIteration):
        next(check)


def test_every_test_is_checked_by_the_autouse_fixture(request):
    assert "session_settings_left_as_found" in request.fixturenames
