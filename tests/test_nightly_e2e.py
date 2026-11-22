"""Tests of scripts/nightly_e2e.py: the command that starts a night, its settings, its lock, its output and the
launchd agent that runs it every night.

The nights run as launchd or a person runs them, with the doubles of tests/nightly_doubles.py: real git, fake tools.
"""

import os
import plistlib
import re
import subprocess
from pathlib import Path

import pytest
from nightly_doubles import NOTHING_RUNS, World, fresh_world, git, nightly_e2e


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



def test_an_unpublished_night_calls_no_gh(world):
    assert world.night("--no-publish") == 1
    assert world.read("gh") == ""


@pytest.mark.parametrize("arguments", [["--bogus"], ["--spec"], ["--spec", "../../etc/passwd"],
                                       ["--spec", "tests/e2e/a b.spec.ts"], ["--spec", "tests/e2e/x.ts"],
                                       ["--spec", "tests/e2e/../x.spec.ts"], ["uninstall-launchd", "--at", "04:05"],
                                       ["install-launchd", "--at"], ["install-launchd", "--no-publish"]])
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


# --- install-launchd ----------------------------------------------------------------------------------------------
def agent(world: World) -> dict:
    with open(world.home / "Library" / "LaunchAgents" / "com.erplora.hub.nightly-e2e.plist", "rb") as plist:
        return plistlib.load(plist)


def test_install_launchd_writes_the_agent_and_loads_it(world):
    assert world.night("install-launchd") == 0
    written = agent(world)
    assert written["Label"] == "com.erplora.hub.nightly-e2e"
    assert written["ProgramArguments"] == [f"{world.hub}/scripts/nightly_e2e.py"]
    assert written["StartCalendarInterval"] == {"Hour": 2, "Minute": 17}
    assert written["RunAtLoad"] is False
    assert written["EnvironmentVariables"]["PATH"] == f"{world.root / 'bin'}:{os.environ['PATH']}"
    assert written["EnvironmentVariables"]["HUB_REPO"] == str(world.hub)
    assert written["EnvironmentVariables"]["ERPLORA_ROOT"] == str(world.erplora)
    assert written["StandardOutPath"] == f"{world.nightly}/launchd.log"
    assert world.calls_re(rf"^launchctl bootout gui/{os.getuid()}/com\.erplora\.hub\.nightly-e2e$") == 1
    plist = world.home / "Library" / "LaunchAgents" / "com.erplora.hub.nightly-e2e.plist"
    assert world.calls(f"launchctl bootstrap gui/{os.getuid()} {plist}") == 1
    assert world.calls_re(r"^(uv|pnpm|node|e2e) ") == 0
    assert "<!-- Written by nightly_e2e.py install-launchd" in plist.read_text()


def test_at_sets_the_hour_and_a_wrong_one_is_refused(world):
    world.night("install-launchd", "--at", "04:05")
    assert agent(world)["StartCalendarInterval"] == {"Hour": 4, "Minute": 5}
    assert world.night("install-launchd", "--at", "23:59") == 0
    for at in ("25:00", "4", "04:60", "x", "24:00"):
        assert world.night("install-launchd", "--at", at) == 2


def test_install_launchd_from_a_linked_worktree_is_refused(world):
    world.night("install-launchd")
    git("-C", str(world.hub), "worktree", "add", "-q", "--detach", str(world.root / "linked"))
    assert world.night("install-launchd", HUB_REPO=str(world.root / "linked")) == 2
    assert "main checkout" in world.out()
    assert agent(world)["ProgramArguments"] == [f"{world.hub}/scripts/nightly_e2e.py"]
    assert world.green(HUB_REPO=str(world.root / "linked")) == 0
    assert world.calls("e2e sees .env LOCAL_SETTING=hub") == 1


def test_install_launchd_without_the_script_or_launchd_fails(world):
    (world.hub / "scripts" / "nightly_e2e.py").chmod(0o644)
    assert world.night("install-launchd") == 4
    assert "is missing or not executable" in world.out()
    (world.hub / "scripts" / "nightly_e2e.py").chmod(0o755)
    assert world.night("install-launchd", FAKE_LAUNCHCTL_EXIT="5") == 1
    assert "launchctl bootstrap" in world.out()
    plist = world.home / "Library" / "LaunchAgents" / "com.erplora.hub.nightly-e2e.plist"
    plist.unlink()
    plist.mkdir()
    assert world.night("install-launchd") == 1
    assert "cannot write" in world.out()


def test_uninstall_launchd_unloads_the_agent_and_removes_it(world):
    world.night("install-launchd")
    assert world.night("uninstall-launchd") == 0
    assert world.calls_re(rf"^launchctl bootout gui/{os.getuid()}/com\.erplora\.hub\.nightly-e2e$") == 1
    assert not (world.home / "Library" / "LaunchAgents" / "com.erplora.hub.nightly-e2e.plist").exists()


# --- the module ---------------------------------------------------------------------------------------------------
def test_the_arguments_name_the_command_the_publishing_and_the_specs():
    parsed = nightly_e2e.parse(["--no-publish", "--spec", "tests/e2e/a.spec.ts", "--spec", "tests/e2e/b.spec.ts"])
    assert (parsed.command, parsed.publish, parsed.specs) == ("night", False, ["tests/e2e/a.spec.ts",
                                                                                "tests/e2e/b.spec.ts"])
    assert nightly_e2e.parse([]).publish is True
    assert nightly_e2e.parse(["install-launchd"]).at == "02:17"
    assert nightly_e2e.parse(["install-launchd", "--at", "04:05"]).at == "04:05"


def test_the_settings_default_to_the_nights_and_the_clone_beside_the_saas():
    settings = nightly_e2e.settings_from({"HUB_REPO": "/work/erplora/hub/", "HOME": "/home/someone"})
    assert (settings.erplora_root, settings.saas_repo) == ("/work/erplora", "/work/erplora/saas")
    assert settings.nightly_dir == "/home/someone/.erplora/hub-nightly-e2e"
    assert (settings.port, settings.max_minutes, settings.start_seconds, settings.keep_runs) == (9770, 360, 300, 7)
    assert settings.gh_repo == "ERPlora/hub"
    assert nightly_e2e.settings_from({"HUB_REPO": "/h", "HOME": "/x", "GH_REPO": "a/b"}).gh_repo == "a/b"
