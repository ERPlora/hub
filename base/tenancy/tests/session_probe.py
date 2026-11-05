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
