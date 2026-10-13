"""Fixtures shared by every hub-next test."""

import json

import pytest

ENTRY = "frontend/main.ts"


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
