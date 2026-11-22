"""Every short video a module declares for a task (``Help.flow_videos``) shows in its help window, in every language.

Each flow id it declares is a flow of the module's WORKBOOK.md that its help publishes: one the WORKBOOK does not have,
or one the window leaves out (not done yet, on no tab, or in the part only who maintains the module reads), would carry
a video nobody sees. The made-up module below shows the check catching each case.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from live.meta import Help

from base.queries import app_help
from base.tests.help_workbooks import ready_tables

FLOW = re.compile(r"^### +([A-Z][A-Z0-9_]*-F\d+)\b", re.MULTILINE)
LANGUAGES = [code for code, _name in settings.LANGUAGES]
WITH_VIDEOS = [config.label for config in app_help.module_configs() if config.help and config.help.flow_videos]
VIDEO = "L4LipaZOq40"


def video_problems(config, language: str) -> list[str]:
    """The flows ``config`` declares videos for that its help does not publish in ``language``, each with why."""
    _served, read = app_help.help_of(config, language)
    published = {flow.id for flow in read.flows}
    written = set(FLOW.findall((Path(config.path) / "WORKBOOK.md").read_text(encoding="utf-8")))
    return [
        f"{flow} has videos but is {'not a flow of its WORKBOOK.md' if flow not in written else 'not published in its help'}"
        for flow in config.help.flow_videos
        if flow not in published
    ]


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", WITH_VIDEOS)
def test_a_module_s_task_videos_are_of_flows_its_help_publishes(label, language):
    config = next(config for config in app_help.module_configs() if config.label == label)
    assert video_problems(config, language) == []


@pytest.mark.parametrize(
    ("flow", "problem"),
    [
        ("TABLE-F09", "TABLE-F09 has videos but is not a flow of its WORKBOOK.md"),
        ("TABLE-F04", "TABLE-F04 has videos but is not published in its help"),
        ("TABLE-F06", "TABLE-F06 has videos but is not published in its help"),
    ],
    ids=["missing", "not-done", "maintainers-part"],
)
@pytest.mark.parametrize("language", LANGUAGES)
def test_it_catches_a_video_of_a_flow_the_window_does_not_show(monkeypatch, tmp_path, language, flow, problem):
    flows = {"TABLE-F01": {"es": [VIDEO]}, flow: {"es": [VIDEO]}}
    table = ready_tables(monkeypatch, tmp_path, Help(flow_videos=flows))
    assert video_problems(table, language) == [problem]


def test_a_video_of_a_published_flow_passes(monkeypatch, tmp_path):
    table = ready_tables(monkeypatch, tmp_path, Help(flow_videos={"TABLE-F02": {"es": [VIDEO], "en": [VIDEO]}}))
    assert video_problems(table, "en") == []
