"""Without Valkey, what one process of the Hub forgets of the cache is forgotten for the others of the same database.

The worker and the web server are separate processes. When the worker turns a business's app on, it forgets what the
cache keeps of that business's apps at its COMMIT (``base.activation.forget``); the next request any other process
serves has to see the app on. In AWS the cache is Valkey, shared by every process. Without it (local development, the
e2e), the settings give a cache on the machine's disk, one per control database, so both processes still share it.

Each "process" here is a real one: the settings and the forgetting run in a separate Python, with the environment of a
Hub without Valkey.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from django.core.cache import CacheHandler
from live.context import Scope

from base import activation
from base.activation import CREATING, ON, Activation
from base.tenancy.context import HUB_SCOPE_KIND

HUB_DIR = Path(__file__).resolve().parents[2]
HOST = "acme"
SCOPE = Scope(HUB_SCOPE_KIND, HOST)

#: What the settings give a process of this environment as its cache.
READ_CACHES = "import json; from django.conf import settings; print(json.dumps(settings.CACHES))"
#: What the worker runs at the COMMIT of the change that turns an app on.
FORGET = "import sys, django; django.setup(); from base import activation; activation.forget(sys.argv[1])"


def environment(database: str) -> dict[str, str]:
    """A Hub process's environment without Valkey (development: no production secrets), on control database
    ``database``."""
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DEBUG": "True",
        "VALKEY_URL": "",
        "DB_NAME": database,
    }


def in_another_process(code: str, database: str, *args: str) -> str:
    done = subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=HUB_DIR,
        env=environment(database),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def unique() -> str:
    return f"cache_processes_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def caches_of():
    """The caches the settings give a process on a control database, read in another process; whatever they kept on
    disk is removed after."""
    seen: list[dict] = []

    def caches(database: str) -> dict:
        seen.append(json.loads(in_another_process(READ_CACHES, database)))
        return seen[-1]

    yield caches
    for caches_seen in seen:
        if location := caches_seen["default"].get("LOCATION"):
            shutil.rmtree(location, ignore_errors=True)


@pytest.fixture
def rows(monkeypatch):
    """The business's rows of its apps, as the database has them: Printing still getting its tables."""
    rows = {"printing": Activation(CREATING, True), "sale": Activation(ON, True)}
    monkeypatch.setattr(activation, "states_of", lambda scope: dict(rows))
    return rows


def test_an_app_the_worker_turns_on_is_on_for_the_next_request_of_another_process(caches_of, rows, monkeypatch):
    database = unique()
    web = CacheHandler(caches_of(database))["default"]
    monkeypatch.setattr(activation, "cache", web)
    web.clear()
    assert activation.off_apps(SCOPE) == {"printing"}
    assert activation.creating_apps(SCOPE) == {"printing"}

    # The worker made Printing's tables, wrote it on and committed; then it forgot, in its own process.
    rows["printing"] = Activation(ON, True)
    in_another_process(FORGET, database, HOST)

    assert activation.off_apps(SCOPE) == frozenset()
    assert activation.creating_apps(SCOPE) == frozenset()


def test_the_processes_of_another_control_database_keep_a_cache_of_their_own(caches_of):
    # Two stacks on one machine (two checkouts, two e2e runs) each have their own businesses under the same slugs.
    database = unique()
    here, again, there = caches_of(database), caches_of(database), caches_of(f"{database}_other")
    assert here == again
    assert here["default"]["BACKEND"] == there["default"]["BACKEND"] == "base.cache.ClusterFileBasedCache"
    assert here["default"]["LOCATION"] == str(Path(tempfile.gettempdir(), "erplora-hub-cache", database))
    assert here["default"]["LOCATION"] != there["default"]["LOCATION"]
