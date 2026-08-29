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
# `scripts/ci/alert-issue.sh`, shared by all three steps — cannot silently regress back to
# `--search` in any of them, and that a future alert step (`test-web.yml`, ERPlora/hub#1246)
# is expected to follow the same contract.
#
# It parses each workflow as YAML (not grep) so a failure NAMES the workflow and the missing
# element, and it checks the step's `run:` CODE with comments stripped out — a comment merely
# explaining "we used to use --search here" must never itself satisfy (or break) this check.
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check the workflow contract (apt: python3-yaml)\n' >&2
    exit 1
fi

REPO_ROOT="$repo_root" python3 - <<'PY'
import os
import sys

import yaml

repo_root = os.environ["REPO_ROOT"]

# (workflow path, the stable title text that step's `run:` code must contain literally)
TARGETS = [
    (".github/workflows/test-hub.yml", "develop is broken after a merge"),
    (".github/workflows/image-freshness.yml", "main HEAD has no image in GHCR"),
    (".github/workflows/test-hub-modules.yml", "Los módulos publicados ROMPEN contra develop"),
]

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


for rel_path, title_marker in TARGETS:
    path = os.path.join(repo_root, rel_path)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except FileNotFoundError:
        check(f"{rel_path} exists", False, "file not found")
        continue

    steps = []
    for job in (doc.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])

    alert_steps = [s for s in steps if title_marker in str(s.get("run") or "")]
    check(
        f"{rel_path}: exactly one step opens/refreshes the «{title_marker}» alert",
        len(alert_steps) == 1,
        f"{len(alert_steps)} step(s) mention it",
    )
    if len(alert_steps) != 1:
        continue

    run = str(alert_steps[0].get("run") or "")
    code = "\n".join(line for line in run.splitlines() if not line.lstrip().startswith("#"))

    check(
        f"{rel_path}: the alert step never inlines `--search`",
        "--search" not in code,
        "GitHub's search index lags behind reality (hub#1246)",
    )
    check(
        f"{rel_path}: the alert step delegates to the shared scripts/ci/alert-issue.sh",
        "./scripts/ci/alert-issue.sh" in code,
        "every alert step must share ONE lookup implementation, not a copy that can drift (hub#1246)",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on the alert-issue workflow steps")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"PASS: {passed} alert-issue workflow contract case(s)")
PY
