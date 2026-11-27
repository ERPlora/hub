"""Tests of the shape of .github/workflows/nightly.yml, the nightly browser run on GitHub Actions, and of the action
.github/actions/e2e-stack, the stack around the Hub that the nightly and the smoke of test.yml both set up.

Every spec runs every night on main, split over a matrix of jobs because one at a time they take longer than a job
may last; a last job reads every job's Playwright report and keeps the one open issue about a red night.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
ACTION = REPO / ".github" / "actions" / "e2e-stack" / "action.yml"
STACK = "./.github/actions/e2e-stack"
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
# A hosted runner's job is cut at six hours.
HOSTED_JOB_MINUTES = 360


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


@pytest.fixture(scope="module")
def nightly() -> dict:
    return load(WORKFLOWS / "nightly.yml")


@pytest.fixture(scope="module")
def action() -> dict:
    return load(ACTION)


def triggers(workflow: dict) -> dict:
    # PyYAML reads the key `on` as true (YAML 1.1).
    return workflow.get("on") or workflow.get(True) or {}


def steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def step_using(job: dict, needle: str) -> dict:
    return next((step for step in steps(job) if needle in str(step.get("run", "")) + str(step.get("uses", ""))), {})


def index_of(job: dict, needle: str) -> int:
    return steps(job).index(step_using(job, needle))


def the_shards_step(nightly: dict) -> dict:
    return step_using(nightly["jobs"]["e2e"], "scripts/nightly_e2e.py")


def test_it_runs_every_night_and_by_hand_and_never_on_a_push(nightly):
    on = triggers(nightly)
    assert set(on) == {"schedule", "workflow_dispatch"}
    assert len(on["schedule"]) == 1
    minute, hour, *every_day = on["schedule"][0]["cron"].split()
    assert every_day == ["*", "*", "*"]
    assert minute.isdigit() and hour.isdigit()


def test_one_night_at_a_time_and_none_is_cancelled_half_way(nightly):
    assert nightly["concurrency"] == {"group": "nightly-${{ github.repository }}", "cancel-in-progress": False}


def test_the_workflow_only_reads_and_only_the_report_writes_issues(nightly):
    assert nightly["permissions"] == {"contents": "read"}
    assert set(nightly["jobs"]) == {"e2e", "report"}
    assert nightly["jobs"]["e2e"]["permissions"] == {"contents": "read"}
    assert nightly["jobs"]["report"]["permissions"] == {"contents": "read", "issues": "write"}


def test_the_specs_are_split_over_a_matrix_of_shards_named_1_to_n(nightly):
    strategy = nightly["jobs"]["e2e"]["strategy"]
    shards = strategy["matrix"]["shard"]
    assert set(strategy["matrix"]) == {"shard"}
    assert len(shards) >= 2 and shards == list(range(1, len(shards) + 1))
    assert strategy["fail-fast"] is False
    # Fewer at once than there are shards: the rest of the account's runners stay free for the pushes of that hour.
    assert isinstance(strategy["max-parallel"], int) and 1 <= strategy["max-parallel"] < len(shards)


def test_each_shard_runs_its_share_on_the_commit_of_the_run_without_publishing(nightly):
    step = the_shards_step(nightly)
    assert step["run"].split() == ["python3", "scripts/nightly_e2e.py", "--shard", '"$SHARD"']
    assert step["env"]["SHARD"] == "${{ matrix.shard }}/${{ strategy.job-total }}"
    assert step["env"]["NIGHTLY_HUB_REF"] == "${{ github.sha }}"
    assert step["env"]["NIGHTLY_DIR"] == "${{ runner.temp }}/hub-nightly-e2e"


def test_playwright_stops_a_shard_before_github_cuts_its_job(nightly):
    job = nightly["jobs"]["e2e"]
    cap = int(the_shards_step(nightly)["env"]["NIGHTLY_MAX_MINUTES"])
    assert isinstance(job["timeout-minutes"], int) and job["timeout-minutes"] <= HOSTED_JOB_MINUTES
    # The stack is set up before the specs and cleaned up after them.
    assert 0 < cap <= job["timeout-minutes"] - 15


def test_each_shard_sets_the_stack_up_before_its_specs_on_the_whole_history(nightly):
    job = nightly["jobs"]["e2e"]
    checkout = step_using(job, "actions/checkout@")
    assert checkout["with"] == {"persist-credentials": False, "fetch-depth": 0}
    assert index_of(job, "actions/checkout@") < index_of(job, STACK) < index_of(job, "scripts/nightly_e2e.py")
    assert step_using(job, STACK)["uses"] == STACK


def test_each_shard_keeps_its_report_and_a_red_one_its_log_and_traces(nightly):
    job = nightly["jobs"]["e2e"]
    folder = the_shards_step(nightly)["env"]["NIGHTLY_DIR"]
    uploads = [step for step in steps(job) if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
    report = next(step for step in uploads if step["with"]["name"] == "e2e-report-${{ matrix.shard }}")
    assert report["if"] == "${{ !cancelled() }}"
    assert report["with"]["path"] == f"{folder}/runs/*/test-results/results.json"
    runs = next(step for step in uploads if step["with"]["name"] == "e2e-runs-${{ matrix.shard }}")
    assert runs["if"] == "failure()"
    assert runs["with"]["path"] == f"{folder}/runs/"


def test_the_report_reads_every_shard_whatever_their_result_and_keeps_the_issue_only_from_main(nightly):
    job = nightly["jobs"]["report"]
    assert job["needs"] == "e2e"
    assert job["if"] == "${{ !cancelled() }}"
    download = step_using(job, "actions/download-artifact@")
    assert download["with"]["pattern"] == "e2e-report-*"
    assert download["continue-on-error"] is True
    step = step_using(job, "scripts/e2e_report.py")
    assert step["env"]["REPORTS"] == download["with"]["path"]
    assert step["run"].splitlines()[-2:] == ['find "$REPORTS" -name results.json -exec cat {} + > "$REPORT"',
                                             "python3 scripts/e2e_report.py"]
    assert step["env"]["RESULT"] == "${{ needs.e2e.result }}"
    assert step["env"]["SHA"] == "${{ github.sha }}"
    assert step["env"]["PUBLISH"] == "${{ github.ref == 'refs/heads/main' }}"
    assert step["env"]["RUN_URL"] == "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert step["env"]["GH_REPO"] == "${{ github.repository }}"
    assert step_using(job, "actions/checkout@")["with"] == {"persist-credentials": False}


def test_the_smoke_and_the_nightly_set_the_stack_up_with_the_same_action(nightly):
    smoke = load(WORKFLOWS / "test.yml")["jobs"]["smoke"]
    for job in (smoke, nightly["jobs"]["e2e"]):
        assert step_using(job, STACK)["uses"] == STACK
        assert job["permissions"] == {"contents": "read"}
        assert not any(needle in str(step.get("run", "")) + str(step.get("uses", ""))
                       for step in steps(job) for needle in ("clone-repo.sh", "docker compose", "setup-uv"))


def test_the_stack_has_the_saas_the_images_and_postgres_beside_the_hub(action):
    assert action["runs"]["using"] == "composite"
    setup = action["runs"]["steps"][-1]
    lines = setup["run"].splitlines()
    assert lines[:2] == ["bash .github/scripts/clone-repo.sh ERPlora/saas ../saas",
                         "bash .github/scripts/clone-repo.sh ERPlora/blueprints ../blueprints img"]
    assert {"cp .env.example .env", "cp ../saas/.env.example ../saas/.env"} <= set(lines)
    assert lines[-1] == "docker compose -f ../compose.yaml up -d --wait"
    assert setup["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert setup["shell"] == "bash"


def test_the_stack_has_the_tools_of_the_hub_pinned_to_a_commit(action):
    uses = {step["uses"].split("@")[0]: step for step in action["runs"]["steps"] if "uses" in step}
    assert set(uses) == {"astral-sh/setup-uv", "pnpm/action-setup", "actions/setup-node"}
    assert all(PINNED.match(step["uses"]) for step in uses.values())
    assert uses["astral-sh/setup-uv"]["with"] == {"enable-cache": True, "cache-dependency-glob": "uv.lock"}
    package = json.loads((REPO / "package.json").read_text())
    assert f"pnpm@{uses['pnpm/action-setup']['with']['version']}" == package["packageManager"]
    assert uses["actions/setup-node"]["with"] == {"node-version": 24, "cache": "pnpm"}


def test_every_action_of_the_nightly_is_pinned_to_a_commit(nightly):
    uses = [step["uses"] for job in nightly["jobs"].values() for step in steps(job) if "uses" in step]
    assert [use for use in uses if use != STACK and not PINNED.match(use)] == []
