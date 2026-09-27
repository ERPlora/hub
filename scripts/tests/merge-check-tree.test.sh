#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Contract test for `scripts/ci/merge-check-tree.sh` — the step that builds the
# tree a merge WOULD produce, so `test-web.yml` can prove it green at merge time
# (ERPlora/pm#331).
#
# Why: the per-PR run proves the merge with the base AS IT WAS when it started,
# and nothing re-runs it when the base moves. On 2026-09-11 hub#1815 went green
# 36 min before hub#1813 landed the very file its new guard forbids; both merged
# green and `develop` stayed red for 2 h 58 min. `merge-pr.sh` now dispatches
# `test-web.yml` with `pr` + `head_sha` + `base_sha`, and this script is what
# turns those three inputs into exactly that tree — or refuses, by CODE:
#
#   merge_check_inputs_missing       an input is empty or not a full sha
#   merge_check_base_not_checked_out the checkout is not on `base_sha`
#   merge_check_head_moved           `refs/pull/<pr>/head` is no longer `head_sha`
#   merge_check_conflict             the two do not merge
#
# Hermetic: a bare repo stands in for `origin`, with the `refs/pull/<n>/head`
# GitHub publishes for every PR. No network, no gh.
#
# Run:  bash scripts/tests/merge-check-tree.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
script="$repo_root/scripts/ci/merge-check-tree.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

g() { git -c user.name=t -c user.email=t@t.invalid -c init.defaultBranch=develop "$@"; }

# origin: develop with a base commit, then a PR branch and a later develop commit
# that do not touch the same file — the shape of the 11/09 cross.
g init -q --bare "$TMP/origin.git"
g clone -q "$TMP/origin.git" "$TMP/seed" 2>/dev/null
echo base > "$TMP/seed/a.txt"
g -C "$TMP/seed" add a.txt && g -C "$TMP/seed" commit -qm base
g -C "$TMP/seed" push -q origin HEAD:develop
g -C "$TMP/seed" checkout -q -b pr
echo pr > "$TMP/seed/pr.txt"
g -C "$TMP/seed" add pr.txt && g -C "$TMP/seed" commit -qm pr
head_sha=$(g -C "$TMP/seed" rev-parse HEAD)
g -C "$TMP/seed" push -q origin HEAD:refs/pull/7/head
g -C "$TMP/seed" checkout -q develop
echo later > "$TMP/seed/later.txt"
g -C "$TMP/seed" add later.txt && g -C "$TMP/seed" commit -qm later
base_sha=$(g -C "$TMP/seed" rev-parse HEAD)
g -C "$TMP/seed" push -q origin HEAD:develop

# A runner checkout of `base_sha`, as actions/checkout leaves it (detached).
checkout() { # $1 = dir, $2 = sha
    g clone -q "$TMP/origin.git" "$1" 2>/dev/null
    g -C "$1" checkout -q --detach "$2"
}

# Runs the script in $1 with the three inputs; stdout+stderr in $TMP/out.
run_in() { # $1 = dir, $2 = pr, $3 = head, $4 = base
    ( cd "$1" && PR="$2" HEAD_SHA="$3" BASE_SHA="$4" bash "$script" ) > "$TMP/out" 2>&1
}

echo "merge-check-tree.sh — the merged tree of pm#331"

if [ ! -f "$script" ]; then
    bad "scripts/ci/merge-check-tree.sh exists" "no such file: $script"
    printf '\n%d passed, %d failed\n' "$pass" "$fail"
    exit 1
fi

# ── 1. The happy path: HEAD becomes the merge of head_sha onto base_sha ──────
checkout "$TMP/ok" "$base_sha"
if ! run_in "$TMP/ok" 7 "$head_sha" "$base_sha"; then
    bad "builds the merged tree of a clean PR" "exit $? — $(cat "$TMP/out")"
else
    parents=$(git -C "$TMP/ok" rev-list --parents -n 1 HEAD | cut -d' ' -f2-)
    if [ "$parents" != "$base_sha $head_sha" ]; then
        bad "HEAD is the merge of head_sha onto base_sha" "parents of HEAD: '$parents'"
    elif [ ! -f "$TMP/ok/pr.txt" ] || [ ! -f "$TMP/ok/later.txt" ]; then
        bad "the working tree carries BOTH sides" "pr.txt or later.txt missing after the merge"
    else
        ok "HEAD is the merge of head_sha onto base_sha, with both sides in the tree"
    fi
fi

# ── 2. Inputs: all three, full shas ─────────────────────────────────────────
checkout "$TMP/in" "$base_sha"
for case_ in "|$head_sha|$base_sha" "7||$base_sha" "7|$head_sha|" "7|abc123|$base_sha" "x7|$head_sha|$base_sha"; do
    IFS='|' read -r p h b <<<"$case_"
    if run_in "$TMP/in" "$p" "$h" "$b"; then
        bad "refuses incomplete inputs (pr='$p' head='${h:0:7}' base='${b:0:7}')" "exit 0"
    elif ! grep -q 'merge_check_inputs_missing' "$TMP/out"; then
        bad "incomplete inputs refuse with merge_check_inputs_missing" "$(cat "$TMP/out")"
    else
        ok "refuses pr='$p' head='${h:0:7}' base='${b:0:7}' with merge_check_inputs_missing"
    fi
done

# ── 3. The checkout must BE the base it is asked to prove ───────────────────
checkout "$TMP/wrongbase" "$head_sha"
if run_in "$TMP/wrongbase" 7 "$head_sha" "$base_sha"; then
    bad "refuses when the checkout is not base_sha" "exit 0"
elif ! grep -q 'merge_check_base_not_checked_out' "$TMP/out"; then
    bad "a wrong checkout refuses with merge_check_base_not_checked_out" "$(cat "$TMP/out")"
else
    ok "a checkout that is not base_sha refuses with merge_check_base_not_checked_out"
fi

# ── 4. The PR moved since the door read its head → not the tree it asked for ─
checkout "$TMP/moved" "$base_sha"
g -C "$TMP/seed" checkout -q pr
echo more > "$TMP/seed/pr2.txt"
g -C "$TMP/seed" add pr2.txt && g -C "$TMP/seed" commit -qm pr2
g -C "$TMP/seed" push -q -f origin HEAD:refs/pull/7/head
if run_in "$TMP/moved" 7 "$head_sha" "$base_sha"; then
    bad "refuses when refs/pull/<pr>/head moved" "exit 0"
elif ! grep -q 'merge_check_head_moved' "$TMP/out"; then
    bad "a moved PR head refuses with merge_check_head_moved" "$(cat "$TMP/out")"
else
    ok "a PR whose head moved refuses with merge_check_head_moved"
fi
g -C "$TMP/seed" push -q -f origin "$head_sha:refs/pull/7/head"

# ── 5. A conflict is a refusal, never a half-merged tree that goes green ────
g -C "$TMP/seed" checkout -q -b clash "$base_sha"
echo theirs > "$TMP/seed/a.txt"
g -C "$TMP/seed" commit -qam theirs
clash_sha=$(g -C "$TMP/seed" rev-parse HEAD)
g -C "$TMP/seed" push -q origin HEAD:refs/pull/8/head
g -C "$TMP/seed" checkout -q develop
echo ours > "$TMP/seed/a.txt"
g -C "$TMP/seed" commit -qam ours
clash_base=$(g -C "$TMP/seed" rev-parse HEAD)
g -C "$TMP/seed" push -q origin HEAD:develop
checkout "$TMP/clash" "$clash_base"
if run_in "$TMP/clash" 8 "$clash_sha" "$clash_base"; then
    bad "refuses a PR that conflicts with the base" "exit 0"
elif ! grep -q 'merge_check_conflict' "$TMP/out"; then
    bad "a conflict refuses with merge_check_conflict" "$(cat "$TMP/out")"
else
    ok "a PR that conflicts with the base refuses with merge_check_conflict"
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
