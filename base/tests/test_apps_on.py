"""Which apps are on has a module of its own: ``base.relay`` loads ``base.services``, which loads ``base.blueprint``,
and both the relay and the blueprints ask which apps are on. Whichever of the three loads first, the Hub starts."""

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


@pytest.mark.parametrize("first", FIRST_TO_LOAD)
def test_the_hub_starts_whichever_of_relay_services_and_blueprint_loads_first(first):
    started = subprocess.run(
        [sys.executable, "-c", LOAD_FIRST.format(first=first, others=FIRST_TO_LOAD)],
        cwd=REPO,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": settings.SETTINGS_MODULE},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert started.returncode == 0, started.stderr
