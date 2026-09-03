#!/usr/bin/env bash
# Contract test for ERPlora/hub#1392: every scripts/tests/*.test.sh|mjs contract test must be
# invoked FOR REAL by something under .github/ or .githooks/pre-push.
#
# Why this exists: a test in scripts/tests/ is worth exactly what its invocation is worth. Add
# the file, wire it into a workflow's `paths:` filter, forget the actual step that RUNS it, and
# the file stays green forever because nobody ever executes it — the same defect hub#1381
# closed one level up for the modules' `*.hub.test.py|sh` batteries. Nothing short of scanning
# every real caller can see a wire silently missing: a missing wire leaves no red anywhere.
#
# "Real invocation" is deliberately narrow: `bash ./path`, `bash path`, a bare `./path`, or
# `node [--test] path` — the shapes actually used by this repo's workflows and pre-push hook.
# A file merely NAMED in a `paths:` filter or a comment does not count, because that is exactly
# the false green ERPlora/hub#1365 found in `test-web-workflow.test.sh`'s own self-check: a
# whole-file `grep -q` on the bare name matched a `paths:` entry after the `run:` step that did
# the actual work had been deleted. This guard is discovery-based (glob + scan), not a fixed
# list, so a new test file cannot opt out of the check by not being named here.
#
# `paths:` entries live under `on:`, never inside a step's `run:` — so parsing the workflow as
# YAML and only looking at `steps[].run` values excludes them structurally, no extra filtering
# needed. A comment ABOVE a step is likewise outside any `run:` string and PyYAML never surfaces
# it; a comment INSIDE a `run: |` block is still part of that string, so its lines are stripped
# before matching (same care `alert-issue-workflows.test.sh` takes with `strip_comments`).
# `.githooks/pre-push` is plain bash, not YAML: read as raw text with the same comment-stripping.
#
# Run:  bash scripts/tests/scripts-tests-wiring.test.sh
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check this contract (apt: python3-yaml)\n' >&2
    exit 1
fi

REPO_ROOT="$repo_root" python3 - <<'PY'
import glob
import os
import re
import sys

import yaml

repo_root = os.environ["REPO_ROOT"]

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def strip_comments(text):
    """Shell code with its `#` comment lines removed — a comment that merely NAMES a test file
    must never itself satisfy the invocation check (hub#1365 is exactly that failure mode)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


test_files = sorted(
    os.path.relpath(p, repo_root)
    for p in glob.glob(os.path.join(repo_root, "scripts/tests/*.test.sh"))
    + glob.glob(os.path.join(repo_root, "scripts/tests/*.test.mjs"))
)
check(
    "scripts/tests/ holds contract tests to check",
    bool(test_files),
    "no *.test.sh / *.test.mjs matched — this guard would pass while checking nothing",
)

workflow_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yml")))
    | set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yaml")))
)
check(
    ".github/workflows/ holds workflows to scan",
    bool(workflow_paths),
    "no workflow file matched — the scan would pass without checking anything",
)

# The other place a `run:` step can live in this repo (hub#1327 made the same point for the
# alert-issue guard): a step moved into a composite action would otherwise walk straight out
# of this guard one level down.
action_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/actions/**/action.yml"), recursive=True))
    | set(glob.glob(os.path.join(repo_root, ".github/actions/**/action.yaml"), recursive=True))
)

run_codes = []  # every step's `run:` body across workflows and composite actions, comments stripped

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

    step_lists = []
    for job in (doc.get("jobs") or {}).values():
        if isinstance(job, dict):
            step_lists.append(job.get("steps") or [])
    runs = doc.get("runs")
    if isinstance(runs, dict) and isinstance(runs.get("steps"), list):
        step_lists.append(runs["steps"])

    for steps in step_lists:
        for step in steps:
            if isinstance(step, dict) and step.get("run"):
                run_codes.append(strip_comments(str(step["run"])))

pre_push = os.path.join(repo_root, ".githooks/pre-push")
if os.path.isfile(pre_push):
    with open(pre_push, encoding="utf-8") as fh:
        run_codes.append(strip_comments(fh.read()))
else:
    check(".githooks/pre-push exists to scan", False, "not found — the hook may have moved")


def invocation_pattern(rel_path):
    escaped = re.escape(rel_path)
    # `./path` not glued to a longer path segment, or `bash [./]path`, or `node [--test] path`.
    prefix = r"(?:(?<![\w./-])\./|\bbash\s+(?:\./)?|\bnode(?:\s+--test)?\s+)"
    return re.compile(prefix + escaped + r"(?![\w./-])", re.MULTILINE)


for rel_path in test_files:
    invoked = any(invocation_pattern(rel_path).search(code) for code in run_codes)
    check(
        f"{rel_path} is invoked for real somewhere under .github/ or .githooks/pre-push",
        invoked,
        "only a `paths:` filter or a comment names it, if anything — a contract test with zero "
        "real callers is documentation nobody runs, and nothing turns red when it drifts "
        "(hub#1392)",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on scripts/tests/ wiring")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"PASS: {passed} scripts/tests/ wiring contract case(s)")
PY
