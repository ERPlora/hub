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

# Hermetic against the git environment it inherits: `.githooks/pre-push` runs this
# battery and git exports GIT_DIR (and `git -c` adds GIT_CONFIG_PARAMETERS) into
# its hooks, which beat every `-C` below and point the fixtures at the pushing
# repository (case 6). git names the set itself, as in
# scripts/materialize-published-modules.sh (hub#1387/#1388).
unset $(git rev-parse --local-env-vars 2>/dev/null)

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

# ── 6. Run from a git hook, the fixtures never touch the repository that pushes ──
#    `.githooks/pre-push` runs this battery, and git exports GIT_DIR into its hooks.
#    An inherited GIT_DIR beats `-C`, so every `g -C "$TMP/seed" …` above landed on
#    the pushing worktree: on 28/09 the push of hub#2304 got commits «base/pr/later»
#    on its branch, a local branch `pr`, and a `git push origin` aimed at GitHub.
#    Same class as hub#1387/#1388. The nested run is this very file under a canary
#    GIT_DIR; the canary must come out exactly as it went in.
if [ -z "${MERGE_CHECK_TREE_NESTED:-}" ]; then
    canary="$TMP/canary"
    g init -q "$canary"
    echo keep > "$canary/keep.txt"
    g -C "$canary" add keep.txt && g -C "$canary" commit -qm keep
    snapshot() { g -C "$canary" for-each-ref --format='%(refname) %(objectname)'; g -C "$canary" symbolic-ref -q HEAD; g -C "$canary" status --porcelain; }
    before=$(snapshot)
    # GIT_WORK_TREE and GIT_INDEX_FILE too: git can export them into a hook as well, and
    # `unset GIT_DIR` alone would leave the fixtures committing the canary's files.
    ( cd "$canary" && GIT_DIR="$canary/.git" GIT_WORK_TREE="$canary" GIT_INDEX_FILE="$canary/.git/index" \
        MERGE_CHECK_TREE_NESTED=1 \
        bash "$repo_root/scripts/tests/merge-check-tree.test.sh" ) > "$TMP/nested.out" 2>&1
    nested_rc=$?
    after=$(snapshot)
    if [ "$before" != "$after" ]; then
        bad "an inherited GIT_DIR (the pre-push hook) leaves the pushing repo untouched" \
            "the fixtures wrote into it: $(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | tr '\n' ' ')"
    elif [ "$nested_rc" -ne 0 ]; then
        bad "the battery passes under an inherited GIT_DIR (the pre-push hook)" "exit $nested_rc — $(tail -c 600 "$TMP/nested.out")"
    else
        ok "an inherited GIT_DIR (the pre-push hook) leaves the pushing repo untouched"
    fi
fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
