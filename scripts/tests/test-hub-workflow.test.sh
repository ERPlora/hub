#!/usr/bin/env bash
# Contract of .github/workflows/test-hub.yml — run with:  bash scripts/tests/test-hub-workflow.test.sh
#
# What this fixes in place (hub#1466, 2026-09-03): the heavy Rust suite runs in Actions on EVERY
# pull request again, in parallel across the runner's slots, and the local pre-push gate keeps
# only the fast stage (check + fmt + clippy, no attestation). Measured on tanda R2 (02/09): the
# local gate is one lock for the whole machine, ~20 min per pass, and each reviewer fix pays it
# again — 6 serial passes = the 2 h of the tanda. `merge-pr.sh` authorises with this workflow's
# check when the local attestation is absent.
#
# What must NOT come back with the trigger: the 29/08 waste — half the runner minutes went to runs
# cancelled by the reviewer's re-push on DRAFT PRs. So the trigger returns WITH the draft filter.
#
# The workflow is read as text on purpose: these are shape assertions (a trigger, a type, an
# `if:`), and the YAML-level truth of the prose is `scripts/tests/ci-prose-matches-triggers.test.sh`.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WF="${TEST_HUB_WORKFLOW:-$ROOT/.github/workflows/test-hub.yml}"
pass=0; fail=0
ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad(){ printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

[ -f "$WF" ] || { echo "no such workflow: $WF" >&2; exit 2; }
echo "test-hub.yml"

on_block(){ awk '/^on:/{f=1;next} f&&/^[a-z]/{f=0} f' "$WF"; }
on_txt="$(on_block)"

# ── 1. the trigger is back, with the type that lets a draft become a run ───────
if printf '%s' "$on_txt" | grep -qE '^  pull_request:'; then
    ok "runs on \`pull_request\` (hub#1466: the heavy suite lives in Actions again)"
else
    bad "runs on \`pull_request\`" "\`on.pull_request\` is missing — the local gate no longer attests (fast mode), so without this check nothing ever authorises a Rust PR to merge"
fi
if printf '%s' "$on_txt" | awk '/^  pull_request:/{f=1;next} f&&/^  [a-z_]+:/{f=0} f' | grep -qE 'ready_for_review'; then
    ok "\`pull_request.types\` includes \`ready_for_review\`"
else
    bad "\`pull_request.types\` includes \`ready_for_review\`" "a draft that becomes ready would never get a run: the draft filter skipped opened/synchronize"
fi

# ── 2. the post-merge net on develop/main stays (hub#572) ─────────────────────
if printf '%s' "$on_txt" | awk '/^  push:/{f=1;next} f&&/^  [a-z_]+:/{f=0} f' | grep -qE 'develop' ; then
    ok "still runs on \`push\` to develop (two green PRs can still break develop together)"
else
    bad "still runs on \`push\` to develop" "the post-merge net of hub#572 is gone"
fi

# ── 3. every job that costs minutes skips DRAFT PRs ────────────────────────────
draft_if="github.event_name != 'pull_request' || !github.event.pull_request.draft"
jobs="$(awk '/^jobs:/{f=1;next} f&&/^  [a-z_-]+:$/{sub(/:$/,"",$1); print $1}' "$WF")"
[ -n "$jobs" ] || bad "the workflow declares jobs" "no \`jobs:\` entries parsed"
for job in $jobs; do
    body="$(awk -v J="  $job:" '$0==J{f=1;next} f&&/^  [a-z_-]+:$/{exit} f' "$WF")"
    # Only jobs that run cargo/pnpm cost minutes; alert-style jobs are gated on push already.
    printf '%s' "$body" | grep -qE 'run: *(cargo|pnpm)' || continue
    if printf '%s' "$body" | grep -qF "$draft_if"; then
        ok "job \`$job\` skips draft PRs"
    else
        bad "job \`$job\` skips draft PRs" "no \`if: $draft_if\`: a draft PR would burn runner minutes and get cancelled on the reviewer's re-push (measured 29/08)"
    fi
done

# ── 4. this contract is RUN by the workflow it guards (hub#1381: an unexecuted battery is worth 0) ──
if grep -q 'scripts/tests/test-hub-workflow.test.sh' "$WF"; then
    ok "test-hub.yml runs this contract"
else
    bad "test-hub.yml runs this contract" "add a step \`bash scripts/tests/test-hub-workflow.test.sh\` — otherwise this file guards nothing"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
