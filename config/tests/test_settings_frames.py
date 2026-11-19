"""The frames a Hub page may show: its own (the website editor's preview) and YouTube's privacy-enhanced player, where a
module's help video plays. Nothing else may be framed."""

import pytest

from config.tests import settings_env


@pytest.mark.parametrize("env", [settings_env.PRODUCTION_ENV, settings_env.DEVELOPMENT_ENV], ids=["production", "development"])
def test_a_page_frames_only_itself_and_youtube_s_player_without_cookies(load_settings, env):
    csp = load_settings(**env)["SECURE_CSP"]
    assert csp["frame-src"] == ["'self'", "https://www.youtube-nocookie.com"]
    assert csp["frame-ancestors"] == ["'none'"]
