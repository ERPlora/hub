#!/usr/bin/env bash
# Contract tests for scripts/ci/pending-publication-lock.sh — the guard that turns a PR red when
# it deletes a kernel e2e AND, in the same diff, declares a battery "pending publication".
#
# Regression test for ERPlora/hub#1995 (born from hub#1994). What it protects:
#
#   · hub#1264 moves the e2e that assert MODULE behaviour out of the hub and into each module's
#     `erplora test` battery. The move is only safe if the battery that inherits the coverage is
#     ALREADY published and running: `module-hub-batteries.sh` proves it is in the catalogue and
#     `run-module-hub-batteries.sh` runs it.
#   · kitchen#84 added `# pending-publication: <repo>#<n> until <date>` so a NEW battery can land
#     before its module publishes it. The marker excuses the battery from the catalogue check —
#     and nothing stopped the SAME PR that deletes the e2e from using it on the heir. The PR is
#     green, the e2e is gone and its replacement is run by nobody for up to 30 days (hub#1994's
#     expiry): the hub#1381 hole, just with a deadline.
#   · So the rule: the marker is for NEW batteries only. A diff that removes an entry from
#     `scripts/ci/kernel-e2e-targets.txt` and adds a `# pending-publication:` marker to
#     `scripts/ci/module-hub-batteries.txt` exits 1.
#
# Everything here is hermetic: a scratch git repo with two commits, no network.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/pending-publication-lock.sh"
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-pending-publication-lock-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

# The workflow that RUNS the lock on a pull request. `--caller` lets the last section be pointed
# at a MUTATED copy to prove it catches the positive (same knob as `kernel-e2e-targets.test.sh`).
caller="$repo_root/.github/workflows/actionlint.yml"

while [ $# -gt 0 ]; do
    case "$1" in
        --caller) caller="$2"; shift 2 ;;
        *) printf 'usage: %s [--caller <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

passed=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

ok() {
    passed=$((passed + 1))
}

[ -f "$script" ] || fail "no such script: $script"

# ── Fixtures ────────────────────────────────────────────────────────────────────────────
# A scratch repo with the two lists at their real paths. `pr-base` is the commit the PR is measured
# against; each case rewrites the lists and commits them as `pr-head`.
KERNEL='scripts/ci/kernel-e2e-targets.txt'
BATTERIES='scripts/ci/module-hub-batteries.txt'

BASE_KERNEL='# Reviewed list of kernel e2e. Comments and blank lines are not entries.

dashboard_widgets_e2e
services_package_redeem_e2e
kitchen_close_check_e2e'

BASE_BATTERIES='# Reviewed list of module batteries.

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py'

git_q() { git -C "$repo" -c user.name=test -c user.email=test@example.invalid "$@" >/dev/null 2>&1; }

new_repo() { # → $repo with one commit (tag `pr-base`) holding the base lists
    repo="$tmp_dir/repo-$passed"
    rm -rf "$repo"
    mkdir -p "$repo/scripts/ci"
    git_q init -q
    printf '%s\n' "$BASE_KERNEL" > "$repo/$KERNEL"
    printf '%s\n' "$BASE_BATTERIES" > "$repo/$BATTERIES"
    git_q add -A
    git_q commit -q -m base
    git_q tag pr-base
}

commit_head() { # $1=kernel list content, $2=batteries list content → commit tagged `pr-head`
    printf '%s\n' "$1" > "$repo/$KERNEL"
    printf '%s\n' "$2" > "$repo/$BATTERIES"
    git_q add -A
    git_q commit -q --allow-empty -m head
    git_q tag pr-head
}

run_lock() { # extra args → stdout in $out, stderr in $err, status in $status
    out=$(cd "$repo" && bash "$script" "$@" 2>"$tmp_dir/err")
    status=$?
    err=$(cat "$tmp_dir/err")
}

kernel_without_redeem='# Reviewed list of kernel e2e. Comments and blank lines are not entries.

dashboard_widgets_e2e
kitchen_close_check_e2e'

batteries_with_pending_heir='# Reviewed list of module batteries.

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py
# pending-publication: services#90 until 2026-10-20
services/tests/package_redeem.hub.test.py'

batteries_with_published_heir='# Reviewed list of module batteries.

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py
services/tests/package_redeem.hub.test.py'

# ── 1 · The hub#1995 case: delete a kernel e2e + add a pending marker → red ────────────────
new_repo
commit_head "$kernel_without_redeem" "$batteries_with_pending_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 1 ] || fail "deleting a kernel e2e and adding a pending-publication marker must exit 1, got $status (stderr: $err)"
[ -z "$out" ] || fail "the verdict must go to stderr, stdout was: $out"
grep -Fq 'pending-publication-lock: removed-kernel-e2e: services_package_redeem_e2e' <<<"$err" \
    || fail "the red must name the deleted kernel e2e, stderr: $err"
grep -Fq 'pending-publication-lock: added-marker: # pending-publication: services#90 until 2026-10-20' <<<"$err" \
    || fail "the red must name the marker the PR added, stderr: $err"
ok

# ── 2 · Moving coverage to an ALREADY published battery is the normal slice → green ────────
new_repo
commit_head "$kernel_without_redeem" "$batteries_with_published_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "deleting a kernel e2e with a published heir must exit 0, got $status (stderr: $err)"
ok

# ── 3 · A pending marker for a NEW battery, no kernel e2e deleted → green (kitchen#84) ──────
new_repo
commit_head "$BASE_KERNEL" "$batteries_with_pending_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "a pending marker without a kernel deletion must exit 0, got $status (stderr: $err)"
ok

# ── 4 · Reordering the kernel list is not a deletion → green ────────────────────────────────
new_repo
commit_head '# Reviewed list of kernel e2e. Comments and blank lines are not entries.

kitchen_close_check_e2e
dashboard_widgets_e2e
services_package_redeem_e2e' "$batteries_with_pending_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "a reordered kernel list removes no entry and must exit 0, got $status (stderr: $err)"
ok

# ── 5 · Deleting a COMMENT or blank line of the kernel list is not a deletion → green ──────
new_repo
commit_head 'dashboard_widgets_e2e
services_package_redeem_e2e
kitchen_close_check_e2e' "$batteries_with_pending_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "removing only comments/blank lines of the kernel list must exit 0, got $status (stderr: $err)"
ok

# ── 6 · A marker that was already in base and is merely MOVED is not added by this PR → green ──
new_repo
batteries_base_with_marker='# Reviewed list of module batteries.

# pending-publication: kitchen#84 until 2026-10-01
kitchen/tests/closed_check.hub.test.py
inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py'
printf '%s\n' "$batteries_base_with_marker" > "$repo/$BATTERIES"
git_q commit -q -am base2
git_q tag -f pr-base
commit_head "$kernel_without_redeem" '# Reviewed list of module batteries.

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py
services/tests/package_redeem.hub.test.py
# pending-publication: kitchen#84 until 2026-10-01
kitchen/tests/closed_check.hub.test.py'
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "a pre-existing marker that only moves must not count as added, got $status (stderr: $err)"
ok

# ── 7 · An INDENTED marker is still a marker (module-hub-batteries.sh trims lines) → red ───
new_repo
commit_head "$kernel_without_redeem" '# Reviewed list of module batteries.

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py
    # pending-publication: services#90 until 2026-10-20
services/tests/package_redeem.hub.test.py'
run_lock --base pr-base --head pr-head
[ "$status" -eq 1 ] || fail "an indented pending-publication marker must still trip the lock, got $status (stderr: $err)"
ok

# ── 8 · An INDENTED kernel entry is still an entry (kernel-e2e-targets.sh trims lines) → red ─
new_repo
printf '%s\n' '# Reviewed list of kernel e2e.
  dashboard_widgets_e2e
  services_package_redeem_e2e' > "$repo/$KERNEL"
git_q commit -q -am base2
git_q tag -f pr-base
commit_head '# Reviewed list of kernel e2e.
  dashboard_widgets_e2e' "$batteries_with_pending_heir"
run_lock --base pr-base --head pr-head
[ "$status" -eq 1 ] || fail "deleting an indented kernel entry plus a marker must exit 1, got $status (stderr: $err)"
ok

# ── 9 · `--head` defaults to HEAD (the checked-out PR merge commit in CI) ───────────────────
new_repo
commit_head "$kernel_without_redeem" "$batteries_with_pending_heir"
run_lock --base pr-base
[ "$status" -eq 1 ] || fail "without --head the lock must compare against HEAD, got $status (stderr: $err)"
# …and an explicit `--head` is honoured when it is NOT the checkout: a later commit that restores
# the base lists makes HEAD clean while `pr-head` still carries the offence.
printf '%s\n' "$BASE_KERNEL" > "$repo/$KERNEL"
printf '%s\n' "$BASE_BATTERIES" > "$repo/$BATTERIES"
git_q commit -q -am restore
run_lock --base pr-base --head pr-head
[ "$status" -eq 1 ] || fail "an explicit --head must be compared, not HEAD, got $status (stderr: $err)"
run_lock --base pr-base
[ "$status" -eq 0 ] || fail "HEAD restores the base lists, so without --head the lock must exit 0, got $status (stderr: $err)"
ok

# ── 10 · A base that does not resolve is an ENVIRONMENT error (2), never a verdict ──────────
new_repo
commit_head "$kernel_without_redeem" "$batteries_with_pending_heir"
run_lock --base no-such-ref --head pr-head
[ "$status" -eq 2 ] || fail "an unresolvable --base must exit 2 (not a verdict), got $status (stderr: $err)"
run_lock --head pr-head
[ "$status" -eq 2 ] || fail "a missing --base must exit 2, got $status (stderr: $err)"
ok

# ── 12 · A comment that merely MENTIONS the marker is not a marker → green ─────────────────
# The real list documents the marker in its own header (`#     # pending-publication: kitchen#84
# until …`). `module-hub-batteries.sh` only honours it at the start of the trimmed line, so a PR
# that deletes a kernel e2e and adds a line of prose about the marker must stay green.
new_repo
commit_head "$kernel_without_redeem" '# Reviewed list of module batteries.
# A NEW battery enters with `# pending-publication: <repo>#<n> until <date>` above its entry:
#     # pending-publication: kitchen#84 until 2026-10-23
#     kitchen/tests/closed_check.hub.test.py

inventory/tests/combo_stock.hub.test.py
kitchen/tests/tickets.hub.test.py
services/tests/package_redeem.hub.test.py'
run_lock --base pr-base --head pr-head
[ "$status" -eq 0 ] || fail "prose that only mentions the marker is not a marker and must exit 0, got $status (stderr: $err)"
ok

# ── 11 · The caller really runs the lock on every pull request ─────────────────────────────
# The lock only protects anything if a workflow that runs ON PULL REQUESTS executes it against
# the PR's base. `test-hub-modules.yml` runs on kernel PRs again (pm#655) but skips drafts and
# watches other paths, so the caller is `actionlint.yml`, whose `paths:` already carries both lists. Checked on the parsed
# YAML (comments inside `run:` stripped), because a comment naming the script runs nothing:
#   a) a step runs `bash ./scripts/ci/pending-publication-lock.sh --base HEAD^1`, with no
#      `continue-on-error` (a red that cannot fail the job is decoration);
#   b) the checkout keeps the merge commit's first parent (`fetch-depth` >= 2) — at depth 1
#      `HEAD^1` does not exist and the step would die with 2 on every PR;
#   c) the lock, this test, and BOTH lists are in the `pull_request` `paths:` filter.
if ! python3 -c 'import yaml' 2>/dev/null; then
    fail "python3 with PyYAML is required to check the caller (apt: python3-yaml)"
fi
[ -f "$caller" ] || fail "hub#1995: the caller was not found at $caller"
if ! verdict=$(CALLER="$caller" python3 - <<'PY' 2>&1
import os
import sys

import yaml

with open(os.environ["CALLER"], encoding="utf-8") as fh:
    wf = yaml.safe_load(fh)

# PyYAML reads the bare key `on` as the boolean True.
on = wf.get("on", wf.get(True)) or {}
pr = on.get("pull_request") or {}
paths = pr.get("paths") or []
problems = []
for needed in (
    "scripts/ci/pending-publication-lock.sh",
    "scripts/tests/pending-publication-lock.test.sh",
    "scripts/ci/kernel-e2e-targets.txt",
    "scripts/ci/module-hub-batteries.txt",
):
    if needed not in paths:
        problems.append(f"{needed} is missing from the pull_request paths: filter")


def code(run):
    return "\n".join(l for l in (run or "").splitlines() if not l.lstrip().startswith("#"))


lock_steps, test_steps, depth_ok = [], [], False
for job in (wf.get("jobs") or {}).values():
    for step in job.get("steps") or []:
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            depth = (step.get("with") or {}).get("fetch-depth")
            if depth is not None and (int(depth) == 0 or int(depth) >= 2):
                depth_ok = True
        run = code(step.get("run"))
        if "bash ./scripts/ci/pending-publication-lock.sh --base HEAD^1" in run:
            lock_steps.append(step)
        if "bash ./scripts/tests/pending-publication-lock.test.sh" in run:
            test_steps.append(step)

if not lock_steps:
    problems.append("no step runs `bash ./scripts/ci/pending-publication-lock.sh --base HEAD^1`")
if any(s.get("continue-on-error") for s in lock_steps):
    problems.append("the lock step carries continue-on-error: its red could never fail the job")
if not test_steps:
    problems.append("no step runs `bash ./scripts/tests/pending-publication-lock.test.sh`")
if not depth_ok:
    problems.append("actions/checkout has no fetch-depth >= 2: HEAD^1 (the PR base) is not there")

if problems:
    print("\n".join(problems))
    sys.exit(1)
PY
); then
    fail "hub#1995: $caller does not run the lock on pull requests:
$verdict"
fi
ok

printf 'PASS: %s pending-publication-lock cases\n' "$passed"
