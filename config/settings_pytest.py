"""Settings of the test run (``pytest.ini``): ``config.settings`` with Vite's default port.

A second checkout carries ``VITE_DEV_PORT`` in its shell or its ``.env`` (tests/e2e/README.md «Varias
ejecuciones a la vez»), and pytest-django loads the settings before any conftest runs, so the port is
pinned here, in the environment, which wins over ``.env`` in python-decouple: the tests that pin 5173
(the SPA's dev HTML, ``LIVE["vite"]``) hold whatever the developer sets. ``VITE_DEV_PORT`` itself is
tested by re-running ``config/settings.py`` (``config/tests/test_settings.py``).
"""

import os

os.environ["VITE_DEV_PORT"] = "5173"

from config.settings import *  # noqa: E402, F403
