#!/usr/bin/env bash
# Contract test for `.github/workflows/canonical-mirrors.yml` — the trigger that makes the
# toolkit's vendored copies actually get COMPARED (ERPlora/hub#1261).
#
# Regression test for ERPlora/hub#1261. What it protects, and why it is a test and not a review:
#
#   · `module-toolkit` vendors, by hand, several files whose authority lives in this repository,
#     and its `test/canonical-mirrors.test.mjs` compares them byte for byte. That test cannot run
#     from the toolkit (no hub checkout, no credential for one — the org is on the free plan), so
#     it runs FROM HERE, through the toolkit's composite action.
#
#   · The whole thing hangs off a `paths:` filter. A mirrored surface that is missing from that
#     list is a guard that never RUNS, and a guard that never runs is not a weak guard: it is an
#     OPEN door that reads as green. It already happened with the frozen kernel surface: hub#1235
#     created `contracts/kernel/`, module-toolkit#115 vendored the six files, and the filter was
#     never widened — hub#1260 moved `contracts/kernel/routes.snapshot` and the mirrors workflow
#     was not among its checks.
#
#   · The filter is duplicated in `pull_request` and in `push`. A path added to one block only is
#     the same hole in slow motion, so symmetry is asserted, not assumed.
#
# The workflow is parsed as YAML (not grepped) so a case fails NAMING the missing path, and both
# the workflow under test and its caller are parameters (`--workflow`, `--caller`) so the guard can
# be proven to catch the positive: mutate a copy, run this against it, watch it fail on that path.
#
# Run:  bash scripts/tests/canonical-mirrors-workflow.test.sh

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
workflow="$repo_root/.github/workflows/canonical-mirrors.yml"
caller="$repo_root/.github/workflows/actionlint.yml"

while [ $# -gt 0 ]; do
    case "$1" in
        --workflow) workflow="$2"; shift 2 ;;
        --caller) caller="$2"; shift 2 ;;
        *) printf 'usage: %s [--workflow <path>] [--caller <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

for f in "$workflow" "$caller"; do
    if [ ! -f "$f" ]; then
        printf 'FAIL: no such workflow: %s\n' "$f" >&2
        exit 1
    fi
done

# A YAML parser is REQUIRED, never optional: a guard that degrades to "skipped" when a tool is
# missing is the very mute green this file exists to abolish.
if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check the workflow contract (pip: pyyaml)\n' >&2
    exit 1
fi

WORKFLOW="$workflow" CALLER="$caller" python3 - <<'PY'
import os
import sys

import yaml

path = os.environ["WORKFLOW"]
caller_path = os.environ["CALLER"]

with open(path, encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)
with open(caller_path, encoding="utf-8") as fh:
    caller = yaml.safe_load(fh)

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def triggers_of(document):
    # YAML 1.1 turns the bare key `on` into the boolean True — the classic Actions gotcha.
    value = document.get("on", document.get(True))
    return value if isinstance(value, dict) else {}


triggers = triggers_of(doc)
check("the workflow declares triggers", bool(triggers), f"got {doc.get('on', doc.get(True))!r}")


# ── 1 · Every mirrored surface is in the filter, in BOTH blocks ──────────────────────
#
# The list is the one `module-toolkit/test/canonical-mirrors.test.mjs` compares. `contracts/kernel/`
# is the frozen kernel surface of the ADR «El Hub se CIERRA como KERNEL» (2026-08-27): six files
# vendored by module-toolkit#115, and the reason this test exists (hub#1261).
REQUIRED_PATHS = [
    "schemas/module.schema.json",
    "crates/db/src/lib.rs",
    "crates/runtime/src/manifest.rs",
    "crates/runtime/src/hub_users.rs",
    "crates/runtime/src/migration_guard.rs",
    "apps/web/src/main.ts",
    "apps/web/src/**/*.vue",
    "contracts/kernel/**",
    ".github/workflows/canonical-mirrors.yml",
]

blocks = {}
for event in ("pull_request", "push"):
    block = triggers.get(event)
    check(f"the workflow runs on `{event}`", isinstance(block, dict), f"got {block!r}")
    blocks[event] = block if isinstance(block, dict) else {}

for event, block in blocks.items():
    paths = block.get("paths") or []
    check(
        f"`on.{event}` filters by `paths`",
        bool(paths),
        "no filter at all is not the fix either: it would run the mirrors on every PR",
    )
    for wanted in REQUIRED_PATHS:
        check(
            f"`on.{event}.paths` covers `{wanted}`",
            wanted in paths,
            f"a PR touching it would NOT run the mirrors — the vendored copy drifts in silence"
            f" (paths are {paths})",
        )


# ── 2 · The two filters stay in step ─────────────────────────────────────────────────
#
# `pull_request` catches the drift before merge; `push` catches what reaches an integration branch
# by another road (a batch merge, a direct push). A path in one list only is half a guard.
pr_paths = set(blocks["pull_request"].get("paths") or [])
push_paths = set(blocks["push"].get("paths") or [])
missing_in_push = sorted(pr_paths - push_paths)
missing_in_pr = sorted(push_paths - pr_paths)
check(
    "the `push` filter covers everything the `pull_request` filter covers",
    not missing_in_push,
    f"only in `pull_request`: {missing_in_push}",
)
check(
    "the `pull_request` filter covers everything the `push` filter covers",
    not missing_in_pr,
    f"only in `push`: {missing_in_pr}",
)

branches = blocks["push"].get("branches") or []
for branch in ("main", "develop"):
    check(
        f"`on.push.branches` includes `{branch}`",
        branch in branches,
        f"branches are {branches}",
    )


# ── 3 · The job still runs the toolkit's own comparison ──────────────────────────────
#
# The filter is worthless if the step it gates stops being the mirrors. No `with: token`: the
# action resolves through module-toolkit's organization Actions-sharing, and if that ever goes away
# the step fails RED instead of degrading to green.
ACTION = "ERPlora/module-toolkit/.github/actions/check-canonical-mirrors"
steps = [step for job in (doc.get("jobs") or {}).values() for step in (job.get("steps") or [])]
mirror_steps = [s for s in steps if ACTION in str(s.get("uses", ""))]
check(
    f"a step runs `{ACTION}`",
    len(mirror_steps) == 1,
    f"{len(mirror_steps)} steps use it — the paths filter gates nothing without it",
)
check(
    "the workflow checks the hub out before comparing",
    any("actions/checkout" in str(s.get("uses", "")) for s in steps),
    "the action compares against a hub checkout; without one it has nothing to read",
)


# ── 4 · This contract test RUNS somewhere ────────────────────────────────────────────
#
# The sin it exists to punish, applied to itself. It lives in `actionlint.yml` and not inside
# `canonical-mirrors.yml` on purpose: that workflow fires by its own `paths` filter, so a pull
# request that deleted an entry from the filter would not run the guard that protects the filter.
# `actionlint.yml` fires on ANY change under `.github/workflows/**`, which breaks the circle.
SELF = "scripts/tests/canonical-mirrors-workflow.test.sh"
caller_steps = [s for job in (caller.get("jobs") or {}).values() for s in (job.get("steps") or [])]
check(
    f"`{os.path.basename(caller_path)}` runs this contract test",
    any(SELF in str(s.get("run", "")) for s in caller_steps),
    "a test nobody runs is a shopping list, not a guard",
)
caller_pr = triggers_of(caller).get("pull_request") or {}
caller_paths = caller_pr.get("paths") or []
check(
    f"`{os.path.basename(caller_path)}` fires on any change under `.github/workflows/**`",
    ".github/workflows/**" in caller_paths,
    f"paths are {caller_paths} — the caller must not depend on the filter it is protecting",
)
check(
    f"`{os.path.basename(caller_path)}` also fires when only this test changes",
    SELF in caller_paths,
    f"paths are {caller_paths} — a PR touching only the test would not execute it",
)

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on {path}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: {passed} canonical-mirrors workflow contract cases")
PY
