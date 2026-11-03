"""Settings of the test run (``pytest.ini``): ``config.settings`` with Vite's default port.

A second checkout carries ``VITE_DEV_PORT`` in its shell or its ``.env`` (tests/e2e/README.md «Varias
ejecuciones a la vez»), and pytest-django loads the settings before any conftest runs, so the port is
pinned here, in the environment, which wins over ``.env`` in python-decouple: the tests that pin 5173
(the SPA's dev HTML, ``LIVE["vite"]``) hold whatever the developer sets. ``VITE_DEV_PORT`` itself is
tested by re-running ``config/settings.py`` (``config/tests/test_settings.py``).

The cache is the process's memory whatever ``VALKEY_URL`` says: ``conftest.py`` empties it around every test (the
attempt counts of ``base.throttle``), which on a real Valkey would wipe whatever it holds. It refuses what the Valkey
cluster of AWS refuses (``base/cache.py``): a call on keys of different hash slots fails the test that makes it.
"""

import os

os.environ["VITE_DEV_PORT"] = "5173"

from config.settings import *  # noqa: E402, F403

CACHES = {"default": {"BACKEND": "base.cache.ClusterLocMemCache"}}

# No thread of the meter in the tests (base/meter.py), whoever imports config.asgi: they write by calling flush().
METER_ENABLED = False

# The migrator runs only with its own credentials (base.tenancy.migrator.migrator_credentials, never default's in
# production): in the tests, the one user of the tests' Postgres, as the hub-migrate task's DB_MIGRATOR_* are its.
os.environ.setdefault("DB_MIGRATOR_USER", DATABASES["default"]["USER"])  # noqa: F405
os.environ.setdefault("DB_MIGRATOR_PASSWORD", DATABASES["default"]["PASSWORD"])  # noqa: F405

# The suite's tests written before the tenancy keep their businesses' rows in control's test database
# (base/tenancy/tests/legacy.py): only here; production's control holds control's tables alone (S5).
DATABASE_ROUTERS = ["base.tenancy.tests.legacy.LegacyTablesRouter", *DATABASE_ROUTERS]  # noqa: F405
