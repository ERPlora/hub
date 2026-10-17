"""Fixtures shared by every hub-next test."""

import json

import pytest

from config import testing

ENTRY = "frontend/main.ts"


# Fails the test that leaves a database connection with a session setting changed (config/testing.py).
session_settings_left_as_found = pytest.fixture(autouse=True)(testing.session_settings_left_as_found)


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
