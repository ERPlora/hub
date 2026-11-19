"""What the modules read: LIVE's operations and SPA, the image's release and the WORKBOOK translation model."""

from django.conf import settings

from config.tests.settings_env import BASE_DIR, DEVELOPMENT_ENV, PRODUCTION_ENV


def test_live_settings():
    live = settings.LIVE
    assert live["context_builder"] == "base.operations.HubContextBuilder"
    assert live["control_alias"] == "default"
    spa = live["spa"]
    assert spa["entry"] == "frontend/main.ts"
    assert spa["manifest"] == BASE_DIR / "frontend" / "dist" / ".vite" / "manifest.json"
    # THEME_PALETTES of packages/ui/src/shell/theme.ts: any other ep_palette cookie paints the default.
    assert spa["palettes"] == [
        "erplora",
        "terracotta",
        "corporate",
        "minimal",
        "forest",
        "ocean",
        "violet",
    ]
    assert spa["palette_default"] == "erplora"
    # Vite runs from the hub's own directory: the repo is its own pnpm workspace (no erplora-next root),
    # on the port this run read (config/settings_pytest.py pins 5173).
    assert live["vite"] == {
        "command": ["env", "VITE_DEV_PORT=5173", "pnpm", "run", "dev"],
        "cwd": str(BASE_DIR),
    }


def test_the_release_comes_from_the_image(load_settings):
    # The build fixes APP_VERSION (the commit's sha) and APP_RELEASED_AT (its time) in the image.
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert (loaded["APP_VERSION"], loaded["APP_RELEASED_AT"]) == ("", "")
    loaded = load_settings(
        **PRODUCTION_ENV,
        APP_VERSION="4da2a10",
        APP_RELEASED_AT="2026-10-13T20:50:00+02:00",
    )
    assert (loaded["APP_VERSION"], loaded["APP_RELEASED_AT"]) == (
        "4da2a10",
        "2026-10-13T20:50:00+02:00",
    )


def test_the_workbook_translation_model_has_a_default_and_comes_from_the_environment(
    load_settings,
):
    assert (
        load_settings(**DEVELOPMENT_ENV)["WORKBOOK_TRANSLATION_MODEL"]
        == "claude-haiku-5-5"
    )
    loaded = load_settings(
        **DEVELOPMENT_ENV, WORKBOOK_TRANSLATION_MODEL="claude-opus-5-5"
    )
    assert loaded["WORKBOOK_TRANSLATION_MODEL"] == "claude-opus-5-5"
