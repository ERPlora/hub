"""A connection handed back with a session setting changed is found and discarded (``config/testing.py``).

The control database's pool hands a connection out again as its last user left it: a test's
``SET lock_timeout = '300ms'`` (FIX-FLOW-DETAIL-RACE) reached inventory's and staff's lock waits in
the tests after it and failed them in the deploy of e0a2e79. The autouse fixture of ``conftest.py``
fails the test that leaves one, and discards it so that the next test starts clean.

A connection that keeps its own ``ensure_connection`` is found and removed too: what ``monkeypatch``'s undo leaves when
a test patched the connection rather than its class, which hides pytest-django's block from every later test of the
process without the database (hub#822).
"""

import threading

import pytest
from django.db import DEFAULT_DB_ALIAS, connection, connections

from config import testing
from config.testing import (
    database_block_left_as_found,
    discard_changed_sessions,
    discard_hidden_blocks,
    session_settings_left_as_found,
)

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


def left_on_the_connection(name: str):
    """The connection of this thread keeps its method ``name`` on itself, as ``monkeypatch``'s undo leaves it."""
    wrapper = connections[DEFAULT_DB_ALIAS]
    setattr(wrapper, name, getattr(wrapper, name))
    return wrapper


def test_a_connection_left_with_its_own_ensure_connection_is_found_and_removed():
    wrapper = left_on_the_connection("ensure_connection")
    assert discard_hidden_blocks() == [DEFAULT_DB_ALIAS]
    # Removed: the method is the class's again, blocked or not as pytest-django says.
    assert "ensure_connection" not in vars(wrapper)
    assert discard_hidden_blocks() == []


def test_what_django_itself_keeps_on_a_connection_hides_no_block():
    # SimpleTestCase puts cursor, connect… back on the connections a test does not use, on the connection itself:
    # they still go through ensure_connection. A cached_property and a flag live there too.
    wrapper = left_on_the_connection("cursor")
    assert wrapper.timezone_name
    wrapper.force_debug_cursor = True
    try:
        assert discard_hidden_blocks() == []
    finally:
        del wrapper.cursor
        wrapper.force_debug_cursor = False


def test_the_check_fails_the_test_that_leaves_one_and_says_which_connection():
    check = database_block_left_as_found(None, None)
    next(check)
    wrapper = left_on_the_connection("ensure_connection")
    said = rf"own ensure_connection on the database connection {DEFAULT_DB_ALIAS}:"
    with pytest.raises(pytest.fail.Exception, match=said):
        check.send(None)
    assert "ensure_connection" not in vars(wrapper)


def test_the_check_lets_a_test_that_leaves_none_pass():
    check = database_block_left_as_found(None, None)
    next(check)
    with pytest.raises(StopIteration):
        check.send(None)


def test_every_test_is_checked_once_its_fixtures_are_torn_down(request):
    # A wrapper around pytest's own teardown, the one that undoes monkeypatch: it checks once that one is done. As a
    # plain hook, pluggy would only build the generator and no test would ever be checked.
    teardowns = request.config.hook.pytest_runtest_teardown.get_hookimpls()
    [check] = [hook for hook in teardowns if hook.function is testing.database_block_left_as_found]
    assert check.wrapper
