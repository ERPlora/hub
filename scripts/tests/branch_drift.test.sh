#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/branch_drift.py` — the signal that catches a
# `develop` → `main` release batch landing FLATTENED (ERPlora/hub#1878).
#
# WHY THIS EXISTS. A batch squashed past `merge-pr.sh` breaks nothing anybody can
# see: CI passes, the content really does reach production, and the board marks
# the work done. The only casualty is the SHAPE of the history — `main` stops
# descending from `develop` — and nothing in this repo looked at the shape. It
# went unnoticed for two weeks: all 15 promotions between 2026-08-30 and
# 2026-09-13 landed with one parent, and the bill arrived as hub#1876, a release
# PR reported CONFLICTING in 12 files that were not real conflicts. A conflict
# resolved in a hurry "in favour of develop" is how one worker's change silently
# overwrites another's.
#
# GitHub cannot be asked to refuse the squash — rulesets and branch protection
# are paywalled on private repos with the org on Free — so the guard is one of
# DETECTION, the same choice `saas` made on 2026-09-06.
#
# WHAT IT PINS. The discrimination, in both directions, against REAL repositories
# built here commit by commit (no stubs: the whole question is what git answers):
#
#   · a batch merged keeping the parent  → exit 0, silence;
#   · a batch SQUASHED onto `main`       → exit 4 and the word said out loud;
#   · ordinary drift with no batch at all → exit 0 (this is the false positive
#     that would teach everyone to ignore the signal);
#   · a hotfix sitting on `main`          → NOT reported as a flattening: it is a
#     different fault with its own signal;
#   · a ref that is not in the checkout   → exit 3, never 0. A run that could not
#     measure must never read as a run that found nothing;
#   · the workflow that carries it fetches BOTH refs before measuring and does
#     not swallow the failure — a guard whose red is ignored is a decoration.
#
# The exit codes matter as much as the verdict: 4 is the flattening's own code,
# distinct from 0, from a generic 1 and from the 3 of "I could not measure", so
# whoever reads the job can tell them apart without opening the log.
#
# Run:  bash scripts/tests/branch_drift.test.sh
#
# bash 3.2 compatible (hub#1468) and it pipes into nothing that short-circuits
# (hub#1534). PyYAML is required for the workflow cases, same as the other
# workflow-contract batteries in `actionlint.yml`.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

signal="$repo_root/scripts/branch_drift.py"
workflow="$repo_root/.github/workflows/develop-main-drift.yml"

# `git -C <path>` does NOT override `GIT_DIR`/`GIT_WORK_TREE`: the environment wins. Run from a
# git hook (the pre-push gate is one) these would point every command below at the REAL repo
# instead of the throwaway one, and the cases would measure the wrong history.
for leaked in $(env | sed -n 's/^\(GIT_[A-Z_]*\)=.*/\1/p'); do
    unset "$leaked"
done

passed=0
failures=0
tmp_root=$(mktemp -d)
trap 'rm -rf "$tmp_root"' EXIT

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    failures=$((failures + 1))
}

ok() {
    passed=$((passed + 1))
}

git_q() { # $1 = repo, rest = git args
    local repo="$1"
    shift
    git -C "$repo" "$@" >/dev/null 2>&1
}

# A repository with the two branches this signal compares, seeded with one shared commit so
# `main` and `develop` start from a common ancestor — the shape every scenario below forks from.
new_repo() { # $1 = name  → prints the path
    local repo="$tmp_root/$1"
    mkdir -p "$repo"
    git -C "$repo" init -q
    git_q "$repo" symbolic-ref HEAD refs/heads/main
    git_q "$repo" config user.email "ci@erplora.test"
    git_q "$repo" config user.name "ERPlora CI"
    git_q "$repo" config commit.gpgsign false
    git_q "$repo" config core.hooksPath /dev/null
    printf 'base\n' >"$repo/README.md"
    git_q "$repo" add -A
    git_q "$repo" commit -m "base"
    git_q "$repo" branch develop
    printf '%s' "$repo"
}

commit_on() { # $1 = repo, $2 = branch, $3 = file, $4 = subject, [$5 = ISO date]
    local repo="$1" branch="$2" file="$3" subject="$4" when="${5:-}"
    git_q "$repo" checkout "$branch"
    printf '%s\n' "$subject" >"$repo/$file"
    git_q "$repo" add -A
    if [ -n "$when" ]; then
        GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" git_q "$repo" commit -m "$subject"
    else
        git_q "$repo" commit -m "$subject"
    fi
}

# The shape `merge-pr.sh` produces: `main` keeps `develop` as a parent.
merge_release() { # $1 = repo
    git_q "$1" checkout main
    git_q "$1" merge --no-ff -m "Develop → main — lote" develop
    git_q "$1" checkout develop
}

# The shape that breaks ancestry: `develop`'s content lands as ONE brand-new commit.
squash_release() { # $1 = repo
    git_q "$1" checkout main
    git_q "$1" merge --squash develop
    git_q "$1" commit -m "Develop (#1876) — lote"
    git_q "$1" checkout develop
}

run_signal() { # $1 = repo → sets $status and $output
    output=$(python3 "$signal" --repo-path "$1" --base main --head develop --dry-run 2>&1)
    status=$?
}

if [ ! -f "$signal" ]; then
    fail "scripts/branch_drift.py does not exist — the hub has no guard against a flattened batch (hub#1878)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 1 · The discrimination, on real repositories
# ═══════════════════════════════════════════════════════════════════════════════

if [ -f "$signal" ]; then
    # ── A healthy batch stays silent ──────────────────────────────────────────
    repo=$(new_repo healthy)
    commit_on "$repo" develop feature.txt "newest"
    merge_release "$repo"
    run_signal "$repo"
    if [ "$status" -eq 0 ]; then
        ok
    else
        fail "a batch merged keeping the parent must exit 0, got $status — a guard that fires on the healthy shape is noise nobody reads: $output"
    fi

    # ── 🔴 THE POSITIVE: a squashed batch is caught and SAID ──────────────────
    repo=$(new_repo flattened)
    commit_on "$repo" develop feature.txt "newest"
    squash_release "$repo"
    run_signal "$repo"
    if [ "$status" -eq 4 ]; then
        ok
    else
        fail "a SQUASHED batch must exit 4 (its own code, not 0/1/3), got $status: $output"
    fi
    # Case-folded rather than matched literally: the contract is that the word is SAID, not the
    # capitalisation it happens to be said in today.
    said=$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')
    case "$said" in
        (*flattened*) ok ;;
        (*) fail "the finding has to be SAID, not only returned — 'flattened' missing from the output: $output" ;;
    esac

    # ── …and it is still found after `develop` moves on ───────────────────────
    # Matching only `develop`'s tip would go blind the minute the next PR merges, which on this
    # repo is minutes: the signal would almost never see anything.
    repo=$(new_repo flattened_then_more_work)
    commit_on "$repo" develop feature.txt "newest"
    squash_release "$repo"
    commit_on "$repo" develop later.txt "work after the batch"
    run_signal "$repo"
    if [ "$status" -eq 4 ]; then
        ok
    else
        fail "the flattened batch must still be found after develop advances, got $status: $output"
    fi

    # ── Ordinary drift with no batch at all is NOT a flattening ───────────────
    # `main` simply has not received anything yet. Firing here would make the guard cry wolf on
    # the most common state of this repo, which is the fastest way to get it ignored.
    repo=$(new_repo plain_drift)
    commit_on "$repo" develop feature.txt "unreleased work" "2026-08-01T10:00:00+00:00"
    run_signal "$repo"
    if [ "$status" -eq 0 ]; then
        ok
    else
        fail "drift with no batch landed is not a flattening: expected 0, got $status: $output"
    fi
    case "$output" in
        (*"days waiting"*) ok ;;
        (*) fail "plain drift must still be MEASURED and printed: $output" ;;
    esac

    # ── Two commits of `develop` with the SAME tree: the batch is still healthy ───
    #
    # `develop` does not carry one commit per tree. A retro-merge done with `-s ours` has the
    # exact tree of its first parent, and so does an empty commit — so the tree `main` serves can
    # match SEVERAL commits of `develop`, and the newest of them is by definition not an ancestor
    # of a `main` that was merged before it existed. Deciding on the first match found therefore
    # calls a perfectly healthy release flattened, and it is not a remote shape: hub#1877 is
    # precisely a `-s ours` merge into `develop`.
    repo=$(new_repo healthy_then_identical_tree)
    commit_on "$repo" develop feature.txt "newest"
    merge_release "$repo"
    git_q "$repo" checkout develop
    git_q "$repo" commit --allow-empty -m "same tree as the batch (retro-merge / empty commit)"
    run_signal "$repo"
    if [ "$status" -eq 0 ]; then
        ok
    else
        fail "a healthy batch must stay healthy when develop grows a second commit with the SAME tree: expected 0, got $status: $output"
    fi

    # ── …and the other way round: several matches, NONE an ancestor, is still a squash ──
    # The symmetric case of the one above, and the one that proves widening the search did not
    # blunt the detector: a flattened batch plus an empty commit on top is two commits carrying
    # `main`'s tree, neither of which `main` descends from. That is still the disease.
    repo=$(new_repo flattened_with_identical_trees)
    commit_on "$repo" develop feature.txt "newest"
    squash_release "$repo"
    git_q "$repo" checkout develop
    git_q "$repo" commit --allow-empty -m "same tree, still not an ancestor of main"
    run_signal "$repo"
    if [ "$status" -eq 4 ]; then
        ok
    else
        fail "several commits with main's tree and NONE an ancestor is still a flattened batch: expected 4, got $status: $output"
    fi

    # ── A hotfix on `main` is a different fault, with its own signal ──────────
    repo=$(new_repo hotfix)
    commit_on "$repo" main hotfix.txt "urgent"
    run_signal "$repo"
    if [ "$status" -eq 0 ]; then
        ok
    else
        fail "a hotfix on main is not a flattened batch (it is the unreturned-hotfix signal): got $status: $output"
    fi

    # ── A ref that is not here means "I could not measure", never "nothing" ───
    repo=$(new_repo missing_ref)
    git_q "$repo" branch -D develop
    output=$(python3 "$signal" --repo-path "$repo" --base main --head develop --dry-run 2>&1)
    status=$?
    if [ "$status" -eq 3 ]; then
        ok
    else
        fail "a missing ref must exit 3 (not 0: an unmeasured run must never read as a clean one), got $status: $output"
    fi

    # ── Both signals open their issue in the CI area's queue (pm#663) ─────────
    # hub issues are split by handbook area and each area's queue is `gh issue list --label
    # module:<key>`: a signal issue without `module:ci` reaches nobody.
    labels_report=$(SIGNAL="$signal" python3 - <<'PY'
import importlib.util, os, sys, types

spec = importlib.util.spec_from_file_location("branch_drift", os.environ["SIGNAL"])
mod = importlib.util.module_from_spec(spec)
sys.modules["branch_drift"] = mod  # @dataclass looks its module up there
spec.loader.exec_module(mod)

class Issues:
    def __init__(self):
        self.created = []
    def find_open(self, marker):
        return None
    def create(self, title, body, labels):
        self.created.append(labels)

issues = Issues()
mod.sync_issue(types.SimpleNamespace(drifting=True), title="t", body="b", issues=issues)
mod.sync_issue(types.SimpleNamespace(drifting=True), title="t", body="b", issues=issues,
               marker=mod.RETURN_MARKER, close_comment=mod.RETURN_CLOSE_COMMENT)
for labels in issues.created:
    print(",".join(sorted(labels)))
# The lookup must NOT move to module:ci: the signal issues already open were created without it,
# and a lookup that misses them opens a twin every run.
queries = []
mod.GhIssues("ERPlora/hub", run=lambda args: queries.append(args) or "[]").find_open(mod.MARKER)
print("lookup:" + queries[0][queries[0].index("--label") + 1])
PY
)
    if [ "$labels_report" = "$(printf 'area:ci-cd,module:ci,prio:P1\narea:ci-cd,module:ci,prio:P1\nlookup:area:ci-cd')" ]; then
        ok
    else
        fail "both signal issues must be created with prio:P1, area:ci-cd and module:ci, and still be looked up by area:ci-cd (pm#663); got: $labels_report"
    fi

    # ── Stdlib only: the signal must not depend on resolving any environment ──
    stdlib_report=$(SIGNAL="$signal" python3 - <<'PY'
import ast, os, sys

tree = ast.parse(open(os.environ["SIGNAL"], encoding="utf-8").read())
roots = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        roots.update(alias.name.split(".")[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        roots.add(node.module.split(".")[0])
foreign = sorted(r for r in roots if r not in sys.stdlib_module_names)
print(" ".join(foreign))
PY
)
    if [ -z "$stdlib_report" ]; then
        ok
    else
        fail "the signal must be stdlib-pure (it runs with no project environment); third-party imports: $stdlib_report"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# 2 · The workflow that carries it
# ═══════════════════════════════════════════════════════════════════════════════
#
# Measuring is half the job; the other half is that the measurement RUNS and that its red is
# not swallowed. `fetch-depth: 0` was believed to be enough in `saas` and was not: the
# self-hosted runner reuses its `_work` between jobs, and a workspace without
# `refs/remotes/origin/develop` left the signal mute behind a traceback.

if [ ! -f "$workflow" ]; then
    fail ".github/workflows/develop-main-drift.yml does not exist — nothing ever runs the guard (hub#1878)"
else
    if ! python3 -c 'import yaml' 2>/dev/null; then
        fail "python3 with PyYAML is required to read the workflow as Actions reads it"
    else
        workflow_report=$(WORKFLOW="$workflow" python3 - <<'PY'
import os
import sys

import yaml

problems = []
doc = yaml.safe_load(open(os.environ["WORKFLOW"], encoding="utf-8").read())

# PyYAML resolves the bare key `on` to the boolean True (YAML 1.1). Actions reads it as the
# string; a test that only looked up "on" would silently check nothing.
triggers = doc.get("on", doc.get(True)) or {}
if "schedule" not in triggers:
    problems.append("no `schedule`: without the daily run the guard only ever sees the batch it rides in on")
if "main" not in ((triggers.get("push") or {}).get("branches") or []):
    problems.append("no `push` on `main`: the signal would not close itself the moment the batch lands")
if "workflow_dispatch" not in triggers:
    problems.append("no `workflow_dispatch`: the guard could not be run on demand while diagnosing")

if (doc.get("permissions") or {}).get("issues") != "write":
    problems.append("`permissions.issues` is not `write`: the signal could not keep its own issue")

steps = []
for job in (doc.get("jobs") or {}).values():
    if isinstance(job, dict):
        steps.extend(job.get("steps") or [])
runs = [str(step.get("run") or "") for step in steps]

fetching = [i for i, run in enumerate(runs) if "develop:refs/remotes/origin/develop" in run]
fetching_main = [i for i, run in enumerate(runs) if "main:refs/remotes/origin/main" in run]
measuring = [i for i, run in enumerate(runs) if "branch_drift.py" in run]

if not measuring:
    problems.append("no step runs `scripts/branch_drift.py`")
if not fetching:
    problems.append("no step fetches `origin/develop` explicitly (`fetch-depth: 0` is not enough)")
if not fetching_main:
    problems.append("no step fetches `origin/main` explicitly — it is the other side of the range")
if fetching and measuring and min(fetching) >= min(measuring):
    problems.append("the explicit fetch must come BEFORE the measurement")

for step in steps:
    if "branch_drift.py" in str(step.get("run") or "") and step.get("continue-on-error"):
        problems.append("`continue-on-error` on the measuring step: a guard whose red is ignored is a decoration")

print("\n".join(problems))
sys.exit(0)
PY
)
        if [ -z "$workflow_report" ]; then
            ok
        else
            while IFS= read -r problem; do
                [ -n "$problem" ] && fail "develop-main-drift.yml: $problem"
            done <<<"$workflow_report"
        fi
    fi
fi

if [ "$failures" -gt 0 ]; then
    printf 'FAIL: %d case(s) on the develop → main flattening guard (hub#1878)\n' "$failures" >&2
    exit 1
fi

printf 'PASS: %d case(s) on the develop → main flattening guard (hub#1878)\n' "$passed"
