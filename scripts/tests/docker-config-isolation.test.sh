#!/usr/bin/env bash
# Contract test: every job that logs in to a registry does it on a Docker config of its OWN.
#
# Regression test for ERPlora/hub#2449 (ported from ERPlora/saas#2433, where the same incident
# was fixed first).
#
# The slots of `ci-runner-1` (`/home/runner/actions-runner-N`) run as ONE user and therefore read
# and write ONE `~/.docker/config.json`. The post step of `docker/login-action` (`logout: true` by
# default) runs `docker logout ghcr.io` on that shared file, so a job that finishes between another
# job's login and its push/pull leaves that other job with `unauthorized`. Measured on 2026-10-01:
# `N-1 binary against N's schema` logged out at 13:12:37 and saas's migration hit `unauthorized`
# at 13:13:23; `Build & Push erplora/hub` did the same at 05:56:21 against 05:57:24. With saas
# isolated, the remaining pair is `build-hub.yml` × `n-minus-one.yml` — a release that does not
# publish, or a red N-1 check for no reason, and a manual re-run either way.
#
# The fix: before any `docker/*` step, export `DOCKER_CONFIG=$RUNNER_TEMP/docker-config` through
# `$GITHUB_ENV` (the `runner` context is not available in a job-level `env:`), with the shared
# `~/.docker/cli-plugins` linked in — the runner installs buildx THERE, and a bare DOCKER_CONFIG
# hides it. `$RUNNER_TEMP` is per slot and wiped when the job ends.
#
# The scan is DISCOVERY-BASED: every job of every workflow that uses `docker/login-action` must
# obey, so a workflow added tomorrow cannot opt out by not being listed. `KNOWN_LOGINS` is not the
# scan — it is the proof that the scan still SEES the jobs that exist today (hub#1327). The
# isolation step is not grepped but EXECUTED, in every job that carries it, against a scratch
# HOME and RUNNER_TEMP: a copy that drifted is caught where it drifted.
#
# Run:  bash scripts/tests/docker-config-isolation.test.sh
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check the workflow contract (apt: python3-yaml)\n' >&2
    exit 1
fi

REPO_ROOT="$repo_root" python3 - <<'PY'
import glob
import os
import subprocess
import sys
import tempfile

import yaml

repo_root = os.environ["REPO_ROOT"]

# The jobs that log in to a registry TODAY. Not the scan — the proof that the scan still finds
# them. If one deliberately stops logging in, delete its line here too.
KNOWN_LOGINS = {
    (".github/workflows/build-hub.yml", "build-and-push"),
    (".github/workflows/n-minus-one.yml", "n-minus-one"),
}

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def uses(step):
    return str(step.get("uses") or "") if isinstance(step, dict) else ""


def logs_in(job):
    return any(uses(s).startswith("docker/login-action") for s in job.get("steps") or [])


def isolation_steps(job):
    """The steps that point the rest of the job at a private Docker config."""
    return [
        (index, step)
        for index, step in enumerate(job.get("steps") or [])
        if isinstance(step, dict)
        and "DOCKER_CONFIG=" in str(step.get("run") or "")
        and "GITHUB_ENV" in str(step.get("run") or "")
    ]


def structural_problems(job):
    """What makes a logging-in job share the runner's credential file, as a list of reasons."""
    steps = job.get("steps") or []
    found = isolation_steps(job)
    if len(found) != 1:
        return [f"{len(found)} steps export DOCKER_CONFIG through $GITHUB_ENV (expected exactly 1)"]
    index, step = found[0]
    problems = []
    first_docker = next((i for i, s in enumerate(steps) if uses(s).startswith("docker/")), None)
    if first_docker is not None and index > first_docker:
        problems.append(
            "the private config is exported AFTER the first `docker/*` step — setup-buildx keeps "
            "its builder under the config dir and login writes the credential there"
        )
    if "if" in step:
        problems.append(f"the isolation step is conditional (`if: {step['if']}`)")
    if step.get("continue-on-error"):
        problems.append("the isolation step is `continue-on-error`")
    if "DOCKER_CONFIG" in (job.get("env") or {}):
        problems.append("the job `env:` sets DOCKER_CONFIG back")
    for s in steps:
        if isinstance(s, dict) and "DOCKER_CONFIG" in (s.get("env") or {}):
            problems.append(f"step «{s.get('name', uses(s))}» sets DOCKER_CONFIG in its `env:`")
    return problems


def run_isolation(script, *, shared_plugins):
    """Execute the step for real; return (exported DOCKER_CONFIG, RUNNER_TEMP, shared ~/.docker)."""
    tmp = tempfile.mkdtemp(prefix="docker-config-isolation-")
    home = os.path.join(tmp, "home")
    shared = os.path.join(home, ".docker")
    os.makedirs(shared)
    with open(os.path.join(shared, "config.json"), "w") as fh:
        fh.write('{"auths": {"ghcr.io": {"auth": "c2hhcmVk"}}}')
    if shared_plugins:
        os.makedirs(os.path.join(shared, "cli-plugins"))
        with open(os.path.join(shared, "cli-plugins", "docker-buildx"), "w") as fh:
            fh.write("#!/bin/sh\n")
    runner_temp = os.path.join(tmp, "actions-runner-3", "_work", "_temp")
    os.makedirs(runner_temp)
    github_env = os.path.join(tmp, "github_env")
    open(github_env, "w").close()
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env={
            "PATH": os.environ["PATH"],
            "HOME": home,
            "RUNNER_TEMP": runner_temp,
            "GITHUB_ENV": github_env,
        },
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, f"exit {result.returncode}: {result.stderr.strip()[:200]}", runner_temp, shared
    with open(github_env) as fh:
        exported = dict(line.split("=", 1) for line in fh.read().splitlines() if "=" in line)
    return exported.get("DOCKER_CONFIG"), "", runner_temp, shared


def runtime_problems(script):
    """What the step does wrong when it actually runs, on a self-hosted slot and on GitHub's."""
    problems = []
    config, err, runner_temp, shared = run_isolation(script, shared_plugins=True)
    if config is None:
        return [f"the step fails to run: {err or 'DOCKER_CONFIG not exported'}"]
    if not os.path.isdir(config):
        problems.append(f"DOCKER_CONFIG={config} is not a directory after the step")
    elif not os.path.realpath(config).startswith(os.path.realpath(runner_temp) + os.sep):
        problems.append(f"DOCKER_CONFIG={config} is not under $RUNNER_TEMP (per slot, wiped per job)")
    elif os.path.realpath(os.path.join(config, "config.json")) == os.path.realpath(
        os.path.join(shared, "config.json")
    ):
        problems.append("the private config.json IS the shared credential file")
    elif not os.path.isfile(os.path.join(config, "cli-plugins", "docker-buildx")):
        problems.append(
            "buildx (in ~/.docker/cli-plugins on ci-runner-1) is unreachable from the private config"
        )
    config, err, _, _ = run_isolation(script, shared_plugins=False)
    if config is None:
        problems.append(f"the step fails where buildx is a system plugin (GitHub-hosted): {err}")
    else:
        link = os.path.join(config, "cli-plugins")
        if os.path.islink(link) and not os.path.exists(link):
            problems.append("a dangling cli-plugins link where ~/.docker/cli-plugins does not exist")
    return problems


# ── The detector, before it is trusted with the real files ────────────────────────────────────
GOOD_STEP = (
    'set -euo pipefail\nconfig="${RUNNER_TEMP}/docker-config"\nmkdir -p "${config}"\n'
    'if [ -d "${HOME}/.docker/cli-plugins" ]; then\n'
    '  ln -sfn "${HOME}/.docker/cli-plugins" "${config}/cli-plugins"\nfi\n'
    'echo "DOCKER_CONFIG=${config}" >> "${GITHUB_ENV}"\n'
)


def _job(steps, env=None):
    job = {"steps": steps}
    if env:
        job["env"] = env
    return job


LOGIN = {"uses": "docker/login-action@v3"}
BUILDX = {"uses": "docker/setup-buildx-action@v3"}
ISOLATE = {"name": "Isolate", "run": GOOD_STEP}

check("the detector flags a login with no private config", bool(structural_problems(_job([LOGIN]))))
check(
    "the detector flags a private config exported after setup-buildx",
    bool(structural_problems(_job([BUILDX, ISOLATE, LOGIN]))),
)
check(
    "the detector flags a conditional isolation step",
    bool(structural_problems(_job([{**ISOLATE, "if": "github.ref == 'refs/heads/main'"}, LOGIN]))),
)
check(
    "the detector flags DOCKER_CONFIG set back in the job env",
    bool(structural_problems(_job([ISOLATE, LOGIN], env={"DOCKER_CONFIG": "/home/runner/.docker"}))),
)
check(
    "the detector accepts the fix",
    structural_problems(_job([ISOLATE, BUILDX, LOGIN])) == [],
    str(structural_problems(_job([ISOLATE, BUILDX, LOGIN]))),
)
check("the runtime check accepts the fix", runtime_problems(GOOD_STEP) == [], str(runtime_problems(GOOD_STEP)))
check(
    "the runtime check flags a config left in the shared HOME",
    bool(runtime_problems('echo "DOCKER_CONFIG=${HOME}/.docker" >> "${GITHUB_ENV}"')),
)
check(
    "the runtime check flags a private config that hides buildx",
    bool(
        runtime_problems(
            'config="${RUNNER_TEMP}/docker-config"; mkdir -p "$config"; '
            'echo "DOCKER_CONFIG=$config" >> "$GITHUB_ENV"'
        )
    ),
)
check(
    "the runtime check flags a dangling cli-plugins link",
    bool(
        runtime_problems(
            'config="${RUNNER_TEMP}/docker-config"; mkdir -p "$config"; '
            'ln -sfn "$HOME/.docker/cli-plugins" "$config/cli-plugins"; '
            'echo "DOCKER_CONFIG=$config" >> "$GITHUB_ENV"'
        )
    ),
)

# ── The real workflows ────────────────────────────────────────────────────────────────────────
workflow_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yml")))
    | set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yaml")))
)
check(
    ".github/workflows/ holds workflows to scan",
    bool(workflow_paths),
    "no workflow file matched — the scan would pass without checking anything",
)

discovered = set()
for path in workflow_paths:
    rel_path = os.path.relpath(path, repo_root)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        check(f"{rel_path} parses as YAML", False, str(exc).replace("\n", " ")[:200])
        continue
    if not isinstance(doc, dict):
        continue
    for job_name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict) or not logs_in(job):
            continue
        discovered.add((rel_path, job_name))
        where = f"{rel_path} · job `{job_name}`"
        problems = structural_problems(job)
        if not problems:
            problems = runtime_problems(isolation_steps(job)[0][1]["run"])
        check(
            f"{where}: logs in on a Docker config of its own",
            not problems,
            "; ".join(problems)
            + " — the slots of ci-runner-1 share ~/.docker/config.json and any other job's "
            "`docker logout` takes this job's credential with it (hub#2449)",
        )

for rel_path, job_name in sorted(KNOWN_LOGINS):
    check(
        f"{rel_path}: the scan still finds the login of job `{job_name}`",
        (rel_path, job_name) in discovered,
        "no login matched — either it was removed without updating KNOWN_LOGINS, or the "
        "discovery itself is broken and this guard is protecting nothing (hub#1327)",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on the jobs' Docker config")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"OK: {passed} contract case(s) on the jobs' Docker config")
PY
