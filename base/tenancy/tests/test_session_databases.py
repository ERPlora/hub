"""A session's databases are its own, whatever test it selects.

pytest-django makes the test database only for a selection with a ``django_db`` mark or a ``db`` fixture. A test that
asks for ``hub_databases`` without either, run alone, went on with the developer's ``default`` and the names derived
from it, the same for every such session: one dropped the other's databases while it was using them.

What is checked here is how a session starts, so these tests start real ones (``session_probe.py`` holds what they
select). Each has its own ``TEST_DB_NAME``.
"""

import json
import os
import subprocess
import sys
import uuid

import pytest
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections
from psycopg import sql

from base.tenancy import names
from base.tenancy.tests import hubs

PROBE = "base/tenancy/tests/session_probe.py"
#: Well past what a session takes on a loaded machine: only a session that hangs gets here.
SESSION_TIMEOUT = 900
KEPT_TABLE = "kept_from_the_last_run"


def _databases_of(session: str) -> set[str]:
    with hubs._maintenance() as conn:
        return {
            row[0] for row in conn.execute("SELECT datname FROM pg_database WHERE starts_with(datname, %s)", [session])
        }


@pytest.fixture
def session_name():
    """``session_name()``: a ``TEST_DB_NAME`` of its own; what a failed session leaves under it is dropped after the test."""
    made = []

    def make() -> str:
        made.append(f"test_solo_{uuid.uuid4().hex[:8]}")
        return made[-1]

    yield make
    for session in made:
        leftovers = _databases_of(session)
        with hubs._maintenance() as conn:
            for name in leftovers:
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _start(session: str, test: str, log, *options: str, **probe_env: str) -> subprocess.Popen:
    """A real pytest session with ``TEST_DB_NAME=session`` that selects only ``test`` of the probe."""
    # PYTEST_*: what the session around this one (its xdist worker, its current test) says of itself.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    with log.open("w") as output:
        return subprocess.Popen(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *options, f"{PROBE}::{test}"],
            cwd=settings.BASE_DIR,
            env=env | {"TEST_DB_NAME": session} | probe_env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )


def _assert_passed(sessions: dict) -> None:
    """Every session of ``{log: process}`` passed; if not, what it printed is the failure's message."""
    try:
        codes = {log: process.wait(timeout=SESSION_TIMEOUT) for log, process in sessions.items()}
    finally:
        for process in sessions.values():
            process.kill()
    assert set(codes.values()) == {0}, "\n\n".join(f"exit {code}:\n{log.read_text()}" for log, code in codes.items())


def test_two_sessions_at_once_each_run_a_lone_test_on_its_own_databases(session_name, tmp_path):
    first, second = session_name(), session_name()
    reports = {first: tmp_path / f"{first}.json", second: tmp_path / f"{second}.json"}

    _assert_passed(
        {
            tmp_path / f"{session}.log": _start(
                session,
                "test_meet_the_other_session",
                tmp_path / f"{session}.log",
                SESSION_PROBE_REPORT=str(reports[session]),
                SESSION_PROBE_OTHER=str(reports[other]),
            )
            for session, other in ((first, second), (second, first))
        }
    )

    for session, report in reports.items():
        assert json.loads(report.read_text()) == {
            "default": session,
            "template": names.template_db_name(session, hubs.TEMPLATE_VERTICAL),
            "a": names.hub_db_name(session, hubs.HUB_A_ID),
            "b": names.hub_db_name(session, hubs.HUB_B_ID),
        }
    assert _databases_of(first) == set()
    assert _databases_of(second) == set()


@pytest.mark.parametrize(
    ("options", "kept"),
    [(("--reuse-db",), True), (("--reuse-db", "--create-db"), False)],
    ids=["reuse-db", "reuse-db-and-create-db"],
)
def test_a_lone_test_follows_the_session_s_options_on_its_database(session_name, tmp_path, options, kept):
    session = session_name()
    report, log = tmp_path / "report.json", tmp_path / "session.log"
    with hubs._maintenance() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(session)))
    with hubs._maintenance(session) as conn:
        conn.execute(sql.SQL("CREATE TABLE {} ()").format(sql.Identifier(KEPT_TABLE)))

    _assert_passed(
        {log: _start(session, "test_ask_for_the_test_database", log, *options, SESSION_PROBE_REPORT=str(report))}
    )

    assert json.loads(report.read_text()) == {"default": session}
    # Kept at the end with --reuse-db as pytest-django keeps its own; made anew with --create-db.
    assert (KEPT_TABLE in hubs.table_names(session)) is kept


def test_a_session_with_a_marked_test_makes_its_database_once(session_name, tmp_path):
    session, log = session_name(), tmp_path / "session.log"

    # -vv over the session's -q, and -s: Django says «Creating test database» on the output for each one it makes.
    _assert_passed({log: _start(session, "test_marked_and_asking_for_the_test_database", log, "-vv", "-s")})

    assert log.read_text().count("Creating test database") == 1
    assert _databases_of(session) == set()


def test_a_lone_test_that_names_the_hubs_aliases_in_its_mark_reaches_their_databases(session_name, tmp_path):
    session, report, log = session_name(), tmp_path / "report.json", tmp_path / "session.log"

    # Alone, no earlier test of the session made the hubs' databases (hub#1007): pytest-django refused the aliases.
    _assert_passed({log: _start(session, "test_marked_with_the_hubs_aliases_alone", log, SESSION_PROBE_REPORT=str(report))})

    assert json.loads(report.read_text()) == {
        "a": names.hub_db_name(session, hubs.HUB_A_ID),
        "b": names.hub_db_name(session, hubs.HUB_B_ID),
    }
    assert _databases_of(session) == set()


def test_the_hubs_databases_refuse_any_other_control_database_before_reaching_the_server(monkeypatch):
    monkeypatch.setitem(connections.settings[DEFAULT_DB_ALIAS], "NAME", "hub")
    monkeypatch.setattr(hubs, "_maintenance", lambda *args: pytest.fail("the server was reached"))

    with pytest.raises(AssertionError, match="'hub'"):
        hubs.build()
