"""Guardrails of the test suite itself: rules (i), (j) and (k) of the Hub's guardrails, which walk every test module
like (f) of ``tests/test_guardrails.py`` (``suite_files``).

(i) The tests read who is connected to a database in one place (``sessions_by_hand``): ``base/tenancy/tests/hubs.py``,
    which counts only clients' sessions. A count of its own also counts the server's processes on that database, an
    autovacuum worker among them, and falls now and then with nothing broken (hub#819).
(j) A test double that answers each request in a thread of its own runs on ``base/tests/quiet_server.py``
    (``threaded_servers``): ``ThreadingHTTPServer`` makes those threads daemon, and one printing that its client went
    as the interpreter closes aborts it, code 134 after every test has passed (hub#840).
(k) A lease the tests write for another worker is written from the real clock, never until a fixed moment
    (``fixed_leases``): the worker claims a row by ``timezone.now()`` (``base/tenancy/recovery.py``, ``restore.py``), so
    a lease held until ``AT`` + 5 min is let go once the real clock passes it, and the test falls from then on in
    ``main`` and in every branch (hub#1351). Like (f), over the suite.
"""

import ast
import re
from pathlib import PurePosixPath

import pytest
from test_guardrails import HUB_DIR, _offenders, _receiver_name, suite_files

# ── (i) The tests read who is connected to a database in one place (hub#819) ─────────────────────────────────────────

#: The one reading of ``pg_stat_activity`` by database in the suite; this very file only names it in its controls.
SESSIONS_READERS = frozenset({"base/tenancy/tests/hubs.py", "tests/test_guardrails_suite.py"})
SESSIONS_BY_HAND = re.compile(
    r"""pg_stat_activity\b.{0,40}?\bdatname\s*=\s*%s(?![\s"']*AND\s+wait_event_type)""", re.DOTALL
)


def sessions_by_hand(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every read of ``pg_stat_activity`` by the name of a database. Who waits for a lock
    (``wait_event_type``, the concurrency tests') is another question, and stays theirs."""
    return [
        (source.count("\n", 0, found.start()) + 1, "pg_stat_activity by database")
        for found in SESSIONS_BY_HAND.finditer(source)
    ]


def test_the_sessions_scanner_sees_a_count_by_hand_and_leaves_the_lock_waits_alone():
    one_line = 'conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", [name])\n'
    split = 'x = 1\ncursor.execute(\n    "SELECT pid FROM pg_stat_activity "\n    "WHERE datname = %s", [name]\n)\n'
    locks = (
        '"SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"\n'
        '" AND wait_event_type = \'Lock\' AND pid <> pg_backend_pid()"\n'
    )

    locks_by_name = (
        '"SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND wait_event_type = \'Lock\' "\n'
        '"SELECT count(*) FROM pg_stat_activity WHERE datname = %s "\n"  AND wait_event_type = \'Lock\'"\n'
    )

    assert sessions_by_hand(one_line) == [(1, "pg_stat_activity by database")]
    assert sessions_by_hand(split) == [(3, "pg_stat_activity by database")]
    assert sessions_by_hand(locks) == []
    assert sessions_by_hand(locks_by_name) == []


def test_no_test_counts_the_sessions_on_a_database_by_hand():
    files = suite_files(HUB_DIR)
    # A walk gone blind, or a reader that moved, would let the check pass.
    assert {PurePosixPath(path) for path in SESSIONS_READERS} <= set(files)
    assert sessions_by_hand((HUB_DIR / "base/tenancy/tests/hubs.py").read_text())

    offenders = _offenders(
        lambda path: [] if str(path) in SESSIONS_READERS else sessions_by_hand((HUB_DIR / path).read_text()), files
    )

    assert offenders == [], (
        "`pg_stat_activity` lists the server's own processes too: an autovacuum worker on the database makes such a "
        f"count fall now and then with nothing broken. Use hubs.client_sessions_on or hubs.assert_nobody_on: {offenders}"
    )


# ── (j) A test double that answers in threads runs on the quiet server (hub#840) ──────────────────────────────────────

#: The threaded servers of the suite that are not on ``base/tests/quiet_server.py``, and why none of them leaves a
#: request thread printing that its client went as the interpreter closes. A path without one any more leaves it.
THREADED_SERVERS = {
    "base/tests/quiet_server.py": "the quiet server itself",
    "apps/flow/tests/local_https.py": "joins its request threads (daemon_threads = False) and keeps what they raise",
    "apps/verifactu/tests/test_slow_gateway.py": "its client waits 45 s for an answer that comes in 6 s: none is cut",
    "tests/test_guardrails_suite.py": "names them in its controls",
}
THREADED_SERVER = re.compile(r"\bThreading\w*(?:Server|MixIn)\b|\bdaemon_threads\s*=\s*True\b")


def threaded_servers(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every server that answers each request in a thread of its own: ``ThreadingHTTPServer`` and
    its kin make those threads daemon by default. A server of one thread (``HTTPServer``) answers in the thread that
    serves, which stopping it waits for: none outlives the test."""
    return [(source.count("\n", 0, found.start()) + 1, found.group()) for found in THREADED_SERVER.finditer(source)]


@pytest.mark.parametrize(
    "source",
    [
        'ThreadingHTTPServer(("127.0.0.1", 0), Handler)',
        "class Mine(ThreadingHTTPServer):",
        "from http.server import ThreadingHTTPServer as Server",
        'socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)',
        "class Mine(socketserver.ThreadingMixIn, HTTPServer):",
        "self._server.daemon_threads = True",
    ],
)
def test_the_threaded_server_scanner_sees_every_way_of_one(source):
    assert threaded_servers(f"x = 1\n{source}\n") == [(2, THREADED_SERVER.search(source).group())]


@pytest.mark.parametrize(
    "source",
    [
        'QuietServer(("127.0.0.1", 0), Handler)',
        'HTTPServer(("127.0.0.1", 0), Handler)',
        "from http.server import BaseHTTPRequestHandler",
        "    daemon_threads = False",
    ],
)
def test_the_threaded_server_scanner_lets_other_servers_be(source):
    assert threaded_servers(source) == []


def test_a_double_that_answers_in_threads_runs_on_the_quiet_server():
    files = suite_files(HUB_DIR)
    # A walk gone blind, or an exception whose server moved, would let the check pass.
    assert {PurePosixPath("base/tests/fake_gateway.py"), *map(PurePosixPath, THREADED_SERVERS)} <= set(files)
    assert [path for path in THREADED_SERVERS if not threaded_servers((HUB_DIR / path).read_text())] == []

    offenders = _offenders(
        lambda path: [] if str(path) in THREADED_SERVERS else threaded_servers((HUB_DIR / path).read_text()), files
    )

    assert offenders == [], (
        "a daemon request thread that prints its client went as the interpreter closes aborts it, code 134 after "
        f"every test has passed: run the double on base.tests.quiet_server.QuietServer (hub#840): {offenders}"
    )


# ── (k) A lease the tests write is written from the real clock (hub#1351) ─────────────────────────────────────────────

#: The column the worker claims a row by, against its clock (``hub_due``, ``RestoredCopy``, ``CopyRecovery``).
LEASE_FIELD = "lease_until"
#: What builds a fixed moment: ``datetime(…)`` and ``datetime.fromisoformat(…)``.
FIXED_MOMENT_CALLS = frozenset({"datetime", "fromisoformat"})


def _is_fixed(value: ast.AST, fixed: set[str]) -> bool:
    """Whether ``value`` is built from a fixed moment: a ``datetime(…)`` of its own, or a name bound to one."""
    for node in ast.walk(value):
        if isinstance(node, ast.Call) and _receiver_name(node.func) in FIXED_MOMENT_CALLS:
            return True
        if isinstance(node, ast.Name | ast.Attribute) and _receiver_name(node) in fixed:
            return True
    return False


def _bind_fixed(statements, fixed: set[str]) -> set[str]:
    """``fixed`` and the names ``statements`` bind, in their order, to a fixed moment: ``AT = dt.datetime(…)``,
    ``THEN = AT - dt.timedelta(days=2)``, ``until = AT + dt.timedelta(minutes=1)``."""
    fixed = set(fixed)
    for statement in statements:
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets, value = [statement.target], statement.value
        else:
            continue
        if _is_fixed(value, fixed):
            fixed.update(target.id for target in targets if isinstance(target, ast.Name))
    return fixed


def fixed_leases(source: str) -> list[tuple[int, str]]:  # noqa: C901
    """``(line, what)`` for every lease ``source`` writes until a fixed moment: ``lease_until=`` in a call (``create``,
    ``update``, a helper's), ``"lease_until": …`` in a dict or ``….lease_until = …``, built from a ``datetime(…)`` or
    from a name bound to one in the body of the module, of a class or of the function that writes it.

    The worker claims a row by the clock: ``timezone.now()`` on purpose in ``base/tenancy/recovery.py`` and
    ``restore.py`` (an earlier step of the tick may have outlasted the lease), its tick's ``now`` elsewhere. A lease
    another worker «holds» until a fixed moment is held only until the real clock passes it, and from then on the test
    falls in ``main`` and in every branch (hub#1351: ``AT``, 09:00 of the day it was written, plus 5 minutes). A lease
    written from the real clock (``timezone.now() ± …``, or a ``now`` the test read from it) holds for either clock.
    Known limit, as (a)'s: it reads names, not values, so a fixed moment that comes in as an argument is not seen.
    """
    tree = ast.parse(source)
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    fixed = _bind_fixed([*tree.body, *(statement for node in classes for statement in node.body)], set())
    found: set[tuple[int, str]] = set()

    def scan(scope: ast.AST, names: set[str]) -> None:
        def note(value: ast.AST) -> None:
            if _is_fixed(value, names):
                found.add((value.lineno, f"{LEASE_FIELD}={ast.unparse(value)}"))

        for node in ast.walk(scope):
            if isinstance(node, ast.keyword) and node.arg == LEASE_FIELD:
                note(node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == LEASE_FIELD:
                        note(value)
            elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Attribute) and target.attr == LEASE_FIELD for target in node.targets
            ):
                note(node.value)

    scan(tree, fixed)
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            bound = sorted(
                (node for node in ast.walk(function) if isinstance(node, ast.Assign | ast.AnnAssign)),
                key=lambda node: (node.lineno, node.col_offset),
            )
            scan(function, _bind_fixed(bound, fixed))
    return sorted(found)


FIXED_LEASE_OFFENDER = """\
AT = dt.datetime(2026, 11, 12, 9, 0, tzinfo=dt.UTC)
THEN: dt.datetime = AT - dt.timedelta(days=2)
def test_a(recoveries, copy):
    recoveries.ask(copy, lease_owner="other:1", lease_until=AT + dt.timedelta(minutes=5))
def test_b(hub):
    HubDue.objects.filter(pk=hub.pk).update(lease_until=THEN)
class TestCopies:
    MOMENT = datetime(2026, 11, 9, 14, 30, tzinfo=UTC)
    def test_c(self, hub):
        RestoredCopy.objects.create(hub=hub, lease_owner="w1", lease_until=self.MOMENT)
def test_d(row):
    row.lease_until = dt.datetime.fromisoformat("2026-11-12T09:05:00+00:00")
def test_e(hub):
    held = {"lease_owner": "w1", "lease_until": dt.datetime(2026, 11, 12, 9, 5, tzinfo=dt.UTC)}
def test_f(hub):
    until = AT + dt.timedelta(minutes=1)
    HubDue.objects.create(hub=hub, lease_until=until)
"""
FIXED_LEASE_LOOKALIKES = """\
\"\"\"lease_until=AT + 5 minutes is held only until the real clock passes it.\"\"\"
AT = dt.datetime(2026, 11, 12, 9, 0, tzinfo=dt.UTC)
def test_a(recoveries, copy):
    recoveries.ask(copy, lease_owner="other:1", lease_until=timezone.now() + dt.timedelta(minutes=5))
def test_b(hub):
    now = timezone.now()
    HubDue.objects.create(hub=hub, due_at=AT, lease_until=now + dt.timedelta(seconds=60), lease_owner="w1")
def test_c(hub):
    HubDue.objects.filter(pk=hub.pk).update(lease_until=None, due_at=AT)
def test_d(row):
    row.lease_until = timezone.now() - dt.timedelta(seconds=1)
    row.done_at = AT
    assert {"lease_until": None, "done_at": AT}
def test_e(hub):
    for lease_until in (timezone.now() + dt.timedelta(seconds=60), None):
        RestoredCopy.objects.create(hub=hub, restore_point=AT, lease_until=lease_until)
def test_f():
    until = AT
    assert until
def test_g(hub):
    until = timezone.now() + dt.timedelta(minutes=1)
    HubDue.objects.create(hub=hub, lease_until=until)
"""


def test_the_lease_scanner_sees_a_lease_written_until_a_fixed_moment():
    assert fixed_leases(FIXED_LEASE_OFFENDER) == [
        (4, "lease_until=AT + dt.timedelta(minutes=5)"),
        (6, "lease_until=THEN"),
        (10, "lease_until=self.MOMENT"),
        (12, "lease_until=dt.datetime.fromisoformat('2026-11-12T09:05:00+00:00')"),
        (14, "lease_until=dt.datetime(2026, 11, 12, 9, 5, tzinfo=dt.UTC)"),
        (17, "lease_until=until"),
    ]


def test_the_lease_scanner_lets_a_lease_written_from_the_clock_be():
    assert fixed_leases(FIXED_LEASE_LOOKALIKES) == []


def test_no_test_writes_a_lease_until_a_fixed_moment():
    files = suite_files(HUB_DIR)
    # A walk gone blind would let the check pass: it reaches the tests that write the leases the worker claims.
    assert {
        PurePosixPath("base/tenancy/tests/test_recovery.py"),
        PurePosixPath("base/tenancy/tests/test_move.py"),
        PurePosixPath("base/tenancy/tests/test_restore_aside.py"),
        PurePosixPath("control/tests/test_freeze.py"),
    } <= set(files)

    offenders = _offenders(lambda path: fixed_leases((HUB_DIR / path).read_text()), files)

    assert offenders == [], (
        "the worker claims a row by the clock, so a lease written until a fixed moment is held only until the real "
        "clock passes it, and from then on the test falls in main and in every branch (hub#1351): write it from "
        f"timezone.now(), or from a `now` the test read from it: {offenders}"
    )
