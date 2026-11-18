"""The frames a Hub page may show: its own (the website editor's preview) and YouTube's privacy-enhanced player, where a
module's help video plays. Nothing else may be framed."""

import pytest

from config.tests import test_settings

#: settings.py run again with only the given environment, the fixture of the settings tests.
load_settings = test_settings.load_settings


@pytest.mark.parametrize("env", [test_settings.PRODUCTION_ENV, test_settings.DEVELOPMENT_ENV], ids=["production", "development"])
def test_a_page_frames_only_itself_and_youtube_s_player_without_cookies(load_settings, env):
    csp = load_settings(**env)["SECURE_CSP"]
    assert csp["frame-src"] == ["'self'", "https://www.youtube-nocookie.com"]
    assert csp["frame-ancestors"] == ["'none'"]
