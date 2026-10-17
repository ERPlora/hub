"""Fixtures shared by every hub-next test."""

import json

import pytest

from config import testing

ENTRY = "frontend/main.ts"


# Fails the test that leaves a database connection with a session setting changed (config/testing.py).
session_settings_left_as_found = pytest.fixture(autouse=True)(testing.session_settings_left_as_found)

#: The hubs every test that uses the database finds in the registry, as ``manage.py seed_local_hubs`` leaves them.
LOCAL_HUBS = ("a", "b")


@pytest.fixture(autouse=True)
def local_hubs(request):
    """The local hubs ``a`` and ``b``, ready, in the registry (``base.Hub``) of every test that uses the database.

    The host gate (``base.middleware``) answers 404 to a slug without a row, so a test on ``a.localhost`` needs it,
    as the developer's database has it after ``seed_local_hubs``. A test without the database gets nothing (and a
    test without it that asks ``a.localhost`` for a hub's page fails: it must say ``django_db``).
    """
    marked = request.node.get_closest_marker("django_db") is not None
    if not (marked or {"db", "transactional_db"} & set(request.fixturenames)):
        return
    request.getfixturevalue("transactional_db" if "transactional_db" in request.fixturenames else "db")
    from base.models import Hub

    for slug in LOCAL_HUBS:
        Hub.objects.get_or_create(slug=slug, defaults={"status": Hub.Status.READY})


@pytest.fixture
def spa_manifest(settings, tmp_path):
    """A Vite build manifest for the SPA entry, as `vite build` writes it."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                ENTRY: {
                    "file": "assets/main-abc123.js",
                    "src": ENTRY,
                    "isEntry": True,
                    "css": ["assets/main-def456.css"],
                    "imports": ["_vendor-789.js"],
                },
                "_vendor-789.js": {"file": "assets/vendor-789.js"},
            }
        )
    )
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "manifest": manifest}}
    return manifest
