#!/usr/bin/env bash
# Contract test: every "open or refresh the alert issue" step across the CI workflows
# delegates its lookup to the ONE shared `scripts/ci/alert-issue.sh` instead of inlining
# `gh issue list --search` again.
#
# Regression test for ERPlora/hub#1246: `test-hub.yml` and `image-freshness.yml` matched the
# open issue with `gh issue list --search '"..." in:title'` — `--search` reads GitHub's search
# INDEX, which lags behind reality (it returned ZERO with open issues on 2026-08-16, and hit
# intermittently later, which is worse). `test-hub-modules.yml` had already fixed this for
# itself (hub#1239) by listing and filtering locally; this test makes sure that fix — now
# `scripts/ci/alert-issue.sh`, shared by every alert step — cannot silently regress back to
# `--search` in any of them.
#
# Regression test for ERPlora/hub#1327: the first version of this test carried a HARDCODED list
# of three workflows, so the two alert steps it did not name (`test-web.yml`, `n-minus-one.yml`)
# kept their inline `--search` while the guard stayed green — and any workflow added tomorrow
# would inherit the same blind spot. The scan is now DISCOVERY-BASED: every step of every
# workflow that touches an issue (`gh issue …`) or calls the shared script IS an alert step and
# must obey the contract, so a new workflow cannot opt out of the guard by not being listed.
# The composite actions under `.github/actions/**` are scanned the same way: a step moved into one
# of them would otherwise walk straight back out of the guard one level down.
#
# It parses each workflow as YAML (not grep) so a failure NAMES the workflow, the job, the step
# and the missing element, and it checks the step's `run:` CODE with comments stripped out — a
# comment merely explaining "we used to use --search here" must never itself satisfy (or break)
# this check.
#
# Run:  bash scripts/tests/alert-issue-workflows.test.sh
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
import sys

import yaml

repo_root = os.environ["REPO_ROOT"]

SHARED_SCRIPT = "./scripts/ci/alert-issue.sh"

# The alert steps that exist TODAY, mapped to the stable title text their `run:` code must still
# contain literally. This map is NOT the scan (the scan below walks every workflow): it is the
# self-check that proves the scan still SEES things. A discovery-based guard that silently stops
# discovering passes green while protecting nothing — the exact failure mode hub#1327 was, one
# level up. If an alert step is deliberately retired, delete its line here too.
KNOWN_ALERT_STEPS = {
    ".github/workflows/test-hub.yml": "develop is broken after a merge",
    ".github/workflows/image-freshness.yml": "main HEAD has no image in GHCR",
    ".github/workflows/test-hub-modules.yml": "Los módulos publicados ROMPEN contra develop",
    ".github/workflows/test-web.yml": "el web de develop esta roto tras un merge",
    ".github/workflows/n-minus-one.yml": "N-1 no sirve contra el esquema de la rama actual",
}

# What makes a step an "alert step": it either already delegates, or it still talks to the issue
# API by hand. Both shapes must be caught — matching only the delegating shape would make the
# guard blind to precisely the regression it exists to stop.
ALERT_MARKERS = (SHARED_SCRIPT, "gh issue create", "gh issue comment", "gh issue list")

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def strip_comments(run):
    """The `run:` code without its `#` comment lines."""
    return "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))


workflow_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yml")))
    | set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yaml")))
)
check(
    ".github/workflows/ holds workflows to scan",
    bool(workflow_paths),
    "no workflow file matched — the scan would pass without checking anything",
)

# A composite action is the OTHER place a `run:` step can live in this repo, and a step moved into
# one would leave the guard exactly the way `test-web.yml` left the hardcoded list (hub#1327).
# There is no alert step in one today; this is the door, closed before somebody walks through it.
action_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/actions/**/action.yml"), recursive=True))
    | set(glob.glob(os.path.join(repo_root, ".github/actions/**/action.yaml"), recursive=True))
)

# rel_path -> list of the `run:` code of its alert steps, comments stripped
discovered = {}


def step_groups(doc):
    """(label, steps, enforce_checkout) for every step list the file defines.

    A workflow job owns its own checkout, so the guard can demand one. A composite action cannot:
    the CALLER's job checks the repo out, and the action has no way to see (or add) that step —
    demanding it there would be a false red. The `--search` and delegation rules still apply.
    """
    for job_name, job in (doc.get("jobs") or {}).items():
        if isinstance(job, dict):
            yield f"job `{job_name}`", job.get("steps") or [], True
    runs = doc.get("runs")
    if isinstance(runs, dict) and isinstance(runs.get("steps"), list):
        yield "composite action", runs["steps"], False


for path in workflow_paths + action_paths:
    rel_path = os.path.relpath(path, repo_root)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        check(f"{rel_path} parses as YAML", False, str(exc).replace("\n", " ")[:200])
        continue
    if not isinstance(doc, dict):
        continue

    for label, steps, enforce_checkout in step_groups(doc):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            code = strip_comments(str(step.get("run") or ""))
            if not any(marker in code for marker in ALERT_MARKERS):
                continue

            where = f"{rel_path} · {label} · step «{step.get('name', index)}»"
            discovered.setdefault(rel_path, []).append(code)

            check(
                f"{where}: never inlines `--search`",
                "--search" not in code,
                "GitHub's search index lags behind reality, so the alert stops being "
                "idempotent exactly when there is most noise (hub#1246)",
            )
            check(
                f"{where}: delegates to the shared {SHARED_SCRIPT}",
                SHARED_SCRIPT in code,
                "every alert step must share ONE lookup implementation, not a copy that can "
                "drift apart again (hub#1246)",
            )
            # A step that calls a script from the repo needs the repo ON DISK. `alert-develop`
            # in `test-web.yml` was a job of its own with no checkout at all (hub#1327): the
            # delegation would have died with `No such file or directory` at 3am, and a mute
            # alert is worse than the duplicate it replaced.
            if enforce_checkout and SHARED_SCRIPT in code:
                checked_out = any(
                    str((earlier or {}).get("uses") or "").startswith("actions/checkout")
                    for earlier in steps[:index]
                    if isinstance(earlier, dict)
                )
                check(
                    f"{where}: its job checks the repo out before calling the script",
                    checked_out,
                    f"no `actions/checkout` step precedes it in {label}, so "
                    f"{SHARED_SCRIPT} would not exist on the runner",
                )

for rel_path, title_marker in sorted(KNOWN_ALERT_STEPS.items()):
    codes = discovered.get(rel_path, [])
    check(
        f"{rel_path}: the scan still finds its alert step",
        bool(codes),
        "no step matched the alert markers — either the step was removed without updating "
        "KNOWN_ALERT_STEPS, or the discovery itself is broken and this guard is protecting "
        "nothing (hub#1327)",
    )
    if not codes:
        continue
    matching = [code for code in codes if title_marker in code]
    check(
        f"{rel_path}: exactly one step opens/refreshes the «{title_marker}» alert",
        len(matching) == 1,
        f"{len(matching)} step(s) carry that title — two would open two issues for one failure",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on the alert-issue workflow steps")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"PASS: {passed} alert-issue workflow contract case(s)")
PY
