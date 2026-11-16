"""What the real sessions of ``test_session_databases.py`` select, one test at a time. No ``test_*.py``: a normal run
never collects it, only a session that names it. Reports what it saw to the file its session says, as JSON."""

import json
import os
import time
from pathlib import Path

import pytest
from django.db import DEFAULT_DB_ALIAS, connections

from base.tenancy.tests import hubs

#: As long as the other session may take to have its databases, on a loaded machine.
MEETING_TIMEOUT = 300


def _control() -> str:
    return connections[DEFAULT_DB_ALIAS].settings_dict["NAME"]


def test_meet_the_other_session(hub_databases):
    """With neither a ``django_db`` mark nor ``db``. Both sessions hold their databases at the same moment: each waits
    for the other to have built its own, and only then checks that its own are still there."""
    report = {"default": _control(), "template": hub_databases.template, "a": hub_databases.a, "b": hub_databases.b}
    Path(os.environ["SESSION_PROBE_REPORT"]).write_text(json.dumps(report))
    other = Path(os.environ["SESSION_PROBE_OTHER"])
    deadline = time.monotonic() + MEETING_TIMEOUT
    while not other.exists():
        assert time.monotonic() < deadline, "The other session never got its databases."
        time.sleep(0.2)

    for name in (hub_databases.template, hub_databases.a, hub_databases.b):
        assert hubs.table_names(name)


def test_ask_for_the_test_database(django_db_setup):
    """With neither a ``django_db`` mark nor ``db``: as ``db_dsn``, ``listen`` or ``shared_schema`` ask for it."""
    Path(os.environ["SESSION_PROBE_REPORT"]).write_text(json.dumps({"default": _control()}))


@pytest.mark.django_db
def test_marked_and_asking_for_the_test_database(django_db_setup):
    """What pytest-django makes the test database for by itself."""


@pytest.mark.parametrize(
    "alias",
    [
        pytest.param(hubs.HUB_A_ALIAS, marks=pytest.mark.django_db(databases=("default", hubs.HUB_A_ALIAS)), id="a"),
        pytest.param(hubs.HUB_B_ALIAS, marks=pytest.mark.django_db(databases=("default", hubs.HUB_B_ALIAS)), id="b"),
    ],
)
def test_marked_with_a_hub_s_alias_alone(alias):
    """Names a hub's alias in its mark and asks for no fixture that makes it, as ``base/tests/test_shell.py``'s did
    with ``hubs.HUB_DATABASES`` (hub#1007): what the alias reaches, by asking its server."""
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT current_database()")
        reached = cursor.fetchone()[0]
    Path(os.environ["SESSION_PROBE_REPORT"]).write_text(json.dumps(reached))


@pytest.mark.django_db(databases=("default",))
def test_marked_with_no_hub_s_alias_alone():
    """Names its databases in its mark, none of them a hub's: which of the hubs' aliases it finds registered."""
    registered = sorted({hubs.HUB_A_ALIAS, hubs.HUB_B_ALIAS} & set(connections.settings))
    Path(os.environ["SESSION_PROBE_REPORT"]).write_text(json.dumps(registered))


def test_without_the_database_first():
    """Asks for no database, as the first test xdist hands a worker may: the checks of ``conftest.py`` run after it, as
    after every test."""


def test_without_the_database_that_reads_the_pool():
    """Reads the pool of ``default`` without the database, as any code may: Django makes it the first time it is read,
    on the database's name of that moment (hub#1332)."""
    assert connections[DEFAULT_DB_ALIAS].pool is not None


def test_then_one_with_the_database_says_which_it_reaches(django_db_setup, django_db_blocker):
    """After those, as the tenancy's tests that commit control's rows (``django_db_blocker``, no ``django_db`` mark, so
    pytest-django never moves them first): which database a query of ``default`` reaches, and which one the settings
    name."""
    with django_db_blocker.unblock(), connections[DEFAULT_DB_ALIAS].cursor() as cursor:
        cursor.execute("SELECT current_database()")
        reached = cursor.fetchone()[0]
    Path(os.environ["SESSION_PROBE_REPORT"]).write_text(json.dumps({"default": _control(), "reached": reached}))
