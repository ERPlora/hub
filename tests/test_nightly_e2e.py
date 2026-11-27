"""Tests of scripts/nightly_e2e.py: the command that starts a night, its settings, its lock and its output.

The nights run as GitHub Actions or a person runs them, with the doubles of tests/nightly_doubles.py: real git, fake
tools.
"""

import re
import subprocess
from pathlib import Path

import pytest
from nightly_doubles import NOTHING_RUNS, OPEN_ISSUE, fresh_world, nightly_e2e


@pytest.fixture
def world(tmp_path):
    yield from fresh_world(tmp_path)


def test_a_green_night_ends_green_and_out_of_github_actions_writes_only_to_its_log(world):
    assert world.green() == 0
    assert world.gh(r"^gh issue (create|comment|close|edit|reopen)") == 0
    assert "night over: success" not in world.out()
    assert "night over: success" in world.night_logs()[0].read_text()


def test_in_github_actions_the_night_also_writes_to_the_jobs_log(world):
    assert world.green(GITHUB_ACTIONS="true") == 0
    assert world.out().count("night over: success") == 1
    folder = re.search(r" nightly-e2e: night in (.*), Hub on ", world.out()).group(1)
    assert Path(folder, "night.log").read_text().count("night over: success") == 1



def test_a_night_never_writes_to_github_whatever_its_result(world):
    assert world.night(OPEN_ISSUES=OPEN_ISSUE) == 1
    assert world.read("gh") == ""
    assert world.green(OPEN_ISSUES=OPEN_ISSUE) == 0
    assert world.read("gh") == ""


@pytest.mark.parametrize("arguments", [["--bogus"], ["--spec"], ["--spec", "../../etc/passwd"],
                                       ["--spec", "tests/e2e/a b.spec.ts"], ["--spec", "tests/e2e/x.ts"],
                                       ["--spec", "tests/e2e/../x.spec.ts"], ["--shard"], ["--shard", "0/4"],
                                       ["--shard", "5/4"], ["--shard", "1/0"], ["--shard", "x/4"], ["--shard", "2"],
                                       ["--shard", "1/4/2"], ["--shard", "01/4"], ["--no-publish"], ["install-launchd"]])
def test_wrong_arguments_are_refused_and_nothing_runs(world, arguments):
    assert world.night(*arguments) == 2
    assert "usage: nightly_e2e.py" in world.out()
    assert world.calls_re(NOTHING_RUNS) == 0
    assert world.read("calls") == ""


@pytest.mark.parametrize("settings", [{"NIGHTLY_HUB_PORT": "80x"}, {"NIGHTLY_HUB_PORT": "1023"},
                                      {"NIGHTLY_HUB_PORT": "65527"}, {"NIGHTLY_KEEP_RUNS": "0"},
                                      {"NIGHTLY_MAX_MINUTES": "-1"}, {"NIGHTLY_START_SECONDS": "x"}])
def test_wrong_settings_are_refused_and_nothing_runs(world, settings):
    assert world.night(**settings) == 2
    assert world.read("calls") == ""


def test_the_edges_of_the_port_range_are_accepted(world):
    assert world.green(NIGHTLY_HUB_PORT="1024") == 0
    assert world.green(NIGHTLY_HUB_PORT="65526") == 0


# --- one night at a time ------------------------------------------------------------------------------------------
def test_a_night_while_another_runs_stops_at_once_and_a_gone_ones_lock_is_taken_over(world):
    (world.nightly / "lock").mkdir(parents=True)
    holder = subprocess.Popen(["sleep", "60"])
    try:
        (world.nightly / "lock" / "pid").write_text(f"{holder.pid}\n")
        assert world.night() == 3
        assert f"another night is running (pid {holder.pid})" in world.out()
        assert world.calls_re(NOTHING_RUNS) == 0
        assert (world.nightly / "lock" / "pid").read_text().strip() == str(holder.pid)
    finally:
        holder.kill()
        holder.wait()
    assert world.green() == 0
    assert f"the night of pid {holder.pid} is gone: taking its lock over" in world.out()
    assert world.calls_re(r"^e2e hub ") == 1
    assert not (world.nightly / "lock").exists()


def test_a_lock_left_as_a_file_is_taken_over(world):
    world.nightly.mkdir(parents=True)
    (world.nightly / "lock").write_text("not a folder\n")
    assert world.green() == 0
    assert "the night of pid ? is gone: taking its lock over" in world.out()
    assert not (world.nightly / "lock").exists()


def test_only_the_newest_nights_are_kept(world):
    for old in ("20200101-000000-1", "20200102-000000-1", "20200103-000000-1"):
        (world.nightly / "runs" / old).mkdir(parents=True)
    assert world.green(NIGHTLY_KEEP_RUNS="2") == 0
    kept = sorted(path.name for path in (world.nightly / "runs").iterdir())
    assert len(kept) == 2
    assert kept[0] == "20200103-000000-1"


def test_a_nightly_dir_whose_hub_is_a_checkout_is_refused(world):
    assert world.night(NIGHTLY_DIR=str(world.erplora)) == 2
    assert (world.hub / ".env").read_text() == "LOCAL_SETTING=hub\n"
    assert world.calls_re(NOTHING_RUNS) == 0


# --- the module ---------------------------------------------------------------------------------------------------
def test_the_arguments_name_the_shard_and_the_specs():
    parsed = nightly_e2e.parse(["--shard", "2/8", "--spec", "tests/e2e/a.spec.ts", "--spec", "tests/e2e/b.spec.ts"])
    assert (parsed.shard, parsed.specs) == ("2/8", ["tests/e2e/a.spec.ts", "tests/e2e/b.spec.ts"])
    assert (nightly_e2e.parse([]).shard, nightly_e2e.parse([]).specs) == ("", [])
    assert nightly_e2e.parse(["--shard", "8/8"]).shard == "8/8"
    assert nightly_e2e.parse(["--shard", "1/12"]).shard == "1/12"


def test_the_settings_default_to_the_nights_and_the_clone_beside_the_saas():
    settings = nightly_e2e.settings_from({"HUB_REPO": "/work/erplora/hub/", "HOME": "/home/someone"})
    assert (settings.erplora_root, settings.saas_repo) == ("/work/erplora", "/work/erplora/saas")
    assert settings.nightly_dir == "/home/someone/.erplora/hub-nightly-e2e"
    assert (settings.port, settings.max_minutes, settings.start_seconds, settings.keep_runs) == (9770, 360, 300, 7)
