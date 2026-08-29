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
verdict="$repo_root/scripts/canonical-mirrors-verdict.sh"

while [ $# -gt 0 ]; do
    case "$1" in
        --workflow) workflow="$2"; shift 2 ;;
        --caller) caller="$2"; shift 2 ;;
        --verdict) verdict="$2"; shift 2 ;;
        *) printf 'usage: %s [--workflow <path>] [--caller <path>] [--verdict <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

for f in "$workflow" "$caller" "$verdict"; do
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

# The hand-ported list sources the verdict refuses to classify (hub#1296): asked of the script
# itself, so the contract below compares the REAL list, not a copy of it.
parsed_sources=$(bash "$verdict" --print-parsed-sources) || {
    printf 'FAIL: %s --print-parsed-sources failed\n' "$verdict" >&2
    exit 1
}

WORKFLOW="$workflow" CALLER="$caller" VERDICT="$verdict" PARSED_SOURCES="$parsed_sources" python3 - <<'PY'
import os
import sys

import yaml

path = os.environ["WORKFLOW"]
caller_path = os.environ["CALLER"]
verdict_path = os.environ["VERDICT"]
parsed_sources = [s for s in os.environ["PARSED_SOURCES"].splitlines() if s.strip()]

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


# ── 3b · The copy FOLLOWS the hub; it does not block it (hub#1296) ───────────────────
#
# The toolkit's action compares byte for byte, which is red BY CONSTRUCTION on any hub PR that
# adds contract. So its outcome is not the verdict: the hub-side `canonical-mirrors-verdict.sh`
# re-reads it — behind an additive change is a warning, a retirement or a hand-edited copy is a
# failure. Three things make that work, and each one missing puts the canonical back behind the
# copy (or opens the door): the action must not end the job (`continue-on-error`), the verdict
# must run AFTER it with its outcome, and the checkout must carry history (the verdict tells a
# lagging copy from a tampered one by looking for the copy's content in the hub's own past).
checkouts = [s for s in steps if "actions/checkout" in str(s.get("uses", ""))]
check(
    "the checkout carries the hub's history (`fetch-depth: 0`)",
    any(str((s.get("with") or {}).get("fetch-depth")) == "0" for s in checkouts),
    "without history every lagging copy reads as DIVERGENT and the PR is red by construction again",
)
mirror = mirror_steps[0] if mirror_steps else {}
check(
    "the toolkit's action step does not end the job by itself (`continue-on-error: true`)",
    mirror.get("continue-on-error") is True,
    "its byte-for-byte failure has to reach the verdict, which is what decides",
)
mirror_id = str(mirror.get("id") or "")
check("the toolkit's action step has an `id` the verdict can read", bool(mirror_id))

VERDICT = "scripts/canonical-mirrors-verdict.sh"
verdict_steps = [s for s in steps if VERDICT in str(s.get("run", ""))]
check(
    f"a step runs `{VERDICT}`",
    len(verdict_steps) == 1,
    f"{len(verdict_steps)} steps run it — the toolkit's outcome is thrown away without it",
)
if verdict_steps and mirror_steps:
    check(
        "the verdict runs AFTER the toolkit's action",
        steps.index(verdict_steps[0]) > steps.index(mirror_steps[0]),
        "it re-reads the action's outcome, so it cannot come first",
    )
    verdict_step = verdict_steps[0]
    whole = str(verdict_step.get("run", "")) + " " + str(verdict_step.get("env") or {})
    check(
        f"the verdict receives the action's outcome (`steps.{mirror_id or '<id>'}.outcome`)",
        bool(mirror_id) and f"steps.{mirror_id}.outcome" in whole,
        "without it a failure of a hand-ported list would be downgraded along with a lagging copy",
    )
    check(
        "the verdict is NOT gated on the action's success (`if:` would skip it on the very failure it exists for)",
        "if" not in verdict_step or "success()" not in str(verdict_step.get("if", "")),
        f"if: {verdict_step.get('if')!r}",
    )

# The list sources the verdict cannot classify are the ones the toolkit parses, and those are
# in the `paths` filter already. Keep the two in step: a source in the filter that the verdict
# does not know is a toolkit failure the verdict would downgrade; a source the verdict knows
# that is not in the filter is a change the mirrors never run for.
VENDORED_OR_NOT_A_LIST = {
    "schemas/module.schema.json",
    "contracts/kernel/**",
    "apps/web/src/**/*.vue",
    ".github/workflows/canonical-mirrors.yml",
}
listed_sources = sorted(set(blocks["pull_request"].get("paths") or []) - VENDORED_OR_NOT_A_LIST)
check(
    f"`{os.path.basename(verdict_path)} --print-parsed-sources` names exactly the hand-ported sources of the filter",
    listed_sources == sorted(parsed_sources),
    f"filter has {listed_sources}, the verdict knows {sorted(parsed_sources)}",
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

# The verdict's own tests (hub#1296), by the same rule: a test nobody runs is a shopping list.
VERDICT_TEST = "scripts/tests/canonical-mirrors-verdict.test.sh"
check(
    f"`{os.path.basename(caller_path)}` runs the verdict's tests (`{VERDICT_TEST}`)",
    any(VERDICT_TEST in str(s.get("run", "")) for s in caller_steps),
    "the classifier decides what merges; its cases have to run on every PR that can change it",
)
for wanted in (VERDICT_TEST, VERDICT):
    check(
        f"`{os.path.basename(caller_path)}` fires when `{wanted}` changes",
        wanted in caller_paths,
        f"paths are {caller_paths} — a PR touching only it would not run its tests",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on {path}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: {passed} canonical-mirrors workflow contract cases")
PY
