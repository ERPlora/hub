#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Builds the tree a merge WOULD produce: `head_sha` merged onto `base_sha`, in the
# checkout of `base_sha` that `test-web.yml` leaves on a merge-check (ERPlora/pm#331).
#
# Why: the per-PR run proves the merge with the base AS IT WAS when it started, and
# nothing re-runs it when the base moves. On 2026-09-11 hub#1815 went green 36 min
# before hub#1813 landed the very file its new guard forbids; both merged green and
# `develop` stayed red for 2 h 58 min. `merge-pr.sh` (ERPlora/pm) now dispatches
# `test-web.yml` with the three inputs when the base moved, and this script turns
# them into exactly the tree it asked about — built here from the two shas rather
# than taken from `refs/pull/<pr>/merge`, which GitHub recomputes lazily and could
# still be the OLD merge.
#
# Env: PR, HEAD_SHA, BASE_SHA (all required; the shas in full). Refuses by CODE,
# one per line on stderr, exit 1 (2 for bad inputs):
#   merge_check_inputs_missing       an input is empty or not a full sha
#   merge_check_base_not_checked_out the checkout is not on BASE_SHA
#   merge_check_head_moved           refs/pull/<pr>/head is no longer HEAD_SHA
#   merge_check_conflict             the two do not merge
#
# Contract test: scripts/tests/merge-check-tree.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

refuse() { # $1 = code, $2 = detail, $3 = exit status
    echo "$1: $2" >&2
    exit "${3:-1}"
}

pr=${PR:-}
head_sha=${HEAD_SHA:-}
base_sha=${BASE_SHA:-}

[[ "$pr" =~ ^[0-9]+$ ]] \
    || refuse merge_check_inputs_missing "PR='$pr' is not a pull request number" 2
[[ "$head_sha" =~ ^[0-9a-f]{40}$ ]] \
    || refuse merge_check_inputs_missing "HEAD_SHA='$head_sha' is not a full sha" 2
[[ "$base_sha" =~ ^[0-9a-f]{40}$ ]] \
    || refuse merge_check_inputs_missing "BASE_SHA='$base_sha' is not a full sha" 2

checked_out=$(git rev-parse HEAD)
[ "$checked_out" = "$base_sha" ] \
    || refuse merge_check_base_not_checked_out "the checkout is $checked_out, not $base_sha"

# The PR's CURRENT head: a push since the door read it means this is no longer the
# tree the door is about to merge — say so instead of proving a stale one.
git fetch --quiet --no-tags origin "+refs/pull/$pr/head:refs/remotes/merge-check/pr-$pr"
current_head=$(git rev-parse "refs/remotes/merge-check/pr-$pr")
[ "$current_head" = "$head_sha" ] \
    || refuse merge_check_head_moved "refs/pull/$pr/head is $current_head, not $head_sha — the PR moved; run merge-pr.sh again"

# A conflict leaves the checkout mid-merge; the refusal fails the step, so nothing
# ever builds or tests that tree.
if ! git -c user.name=merge-check -c user.email=merge-check@erplora.invalid \
    merge --no-edit --quiet "$head_sha"; then
    refuse merge_check_conflict "$head_sha does not merge onto $base_sha"
fi

echo "merged tree of #$pr: $head_sha onto $base_sha → $(git rev-parse HEAD)"
