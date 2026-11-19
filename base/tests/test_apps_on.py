"""Which apps are on has a module of its own: ``base.relay`` loads ``base.services``, which loads ``base.blueprint``,
and both the relay and the blueprints ask which apps are on. Whichever of the three loads first, the Hub starts, and
nothing the writes and reads of base load asks the relay anything, so the relay's own imports may come in any order."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

REPO = Path(__file__).resolve().parents[2]
FIRST_TO_LOAD = ("base.relay", "base.services", "base.blueprint")

# live is the first installed app and its ready() discovers the queries and services of every app, so the module is
# loaded right before it; had one of the others been loaded earlier, the module would not be the first.
LOAD_FIRST = """
import importlib
import sys

import django
from live.apps import LiveConfig

first, others = {first!r}, {others!r}
discover = LiveConfig.ready


def ready(self):
    loaded = [name for name in others if name in sys.modules]
    if loaded:
        raise SystemExit(f"loaded before {{first}}: {{loaded}}")
    importlib.import_module(first)
    discover(self)


LiveConfig.ready = ready
django.setup()
"""

# The relay as it is when its first import is base.services: loading, with nothing of its own defined yet.
RELAY_STILL_EMPTY = """
import sys
import types

import django
from live.apps import LiveConfig

discover = LiveConfig.ready


def ready(self):
    sys.modules["base.relay"] = types.ModuleType("base.relay")
    import base.queries
    import base.services

    del sys.modules["base.relay"]
    discover(self)


LiveConfig.ready = ready
django.setup()
"""


def start(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": settings.SETTINGS_MODULE},
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("first", FIRST_TO_LOAD)
def test_the_hub_starts_whichever_of_relay_services_and_blueprint_loads_first(first):
    started = start(LOAD_FIRST.format(first=first, others=FIRST_TO_LOAD))

    assert started.returncode == 0, started.stderr


def test_the_writes_and_reads_of_base_load_while_the_relay_has_nothing_of_its_own_yet():
    started = start(RELAY_STILL_EMPTY)

    assert started.returncode == 0, started.stderr
