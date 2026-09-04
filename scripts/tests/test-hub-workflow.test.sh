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
if grep -qE '^  pull_request:' <<<"$on_txt"; then
    ok "runs on \`pull_request\` (hub#1466: the heavy suite lives in Actions again)"
else
    bad "runs on \`pull_request\`" "\`on.pull_request\` is missing — the local gate no longer attests (fast mode), so without this check nothing ever authorises a Rust PR to merge"
fi
pr_block="$(awk '/^  pull_request:/{f=1;next} f&&/^  [a-z_]+:/{f=0} f' <<<"$on_txt")"
if grep -qE 'ready_for_review' <<<"$pr_block"; then
    ok "\`pull_request.types\` includes \`ready_for_review\`"
else
    bad "\`pull_request.types\` includes \`ready_for_review\`" "a draft that becomes ready would never get a run: the draft filter skipped opened/synchronize"
fi

# ── 2. the post-merge net on develop/main stays (hub#572) ─────────────────────
push_blk="$(awk '/^  push:/{f=1;next} f&&/^  [a-z_]+:/{f=0} f' <<<"$on_txt")"
if grep -qE 'develop' <<<"$push_blk"; then
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
    # Here-strings, never `printf … | grep -q`: under `pipefail`, grep -q closes the pipe at the
    # first match and printf dies with "Broken pipe" → a MATCH becomes a failure (red only on
    # Linux; the Mac's printf finishes first). Bit us on the first CI run of hub#1471.
    grep -qE 'run: *(cargo|pnpm)' <<<"$body" || continue
    if grep -qF "$draft_if" <<<"$body"; then
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

# ── 5. a time-budget overrun is a NAMED red, never a mute `cancelled` (hub#1519) ──
# GitHub marks a job that hits the JOB-level `timeout-minutes` as `cancelled` — indistinguishable
# from a cancel by concurrency or by a newer push. It names no test, and `merge-pr.sh` reads it as
# not-green and refuses to merge without saying why: the queue blocks and the block does not
# explain itself. A STEP that hits its OWN `timeout-minutes` FAILS instead, and a failed step is a
# red that points at itself. So: every step that costs minutes carries its own budget, and the
# job's budget stays strictly ABOVE their sum, which leaves the job-level cancel as what it should
# be — the backstop for a hang OUTSIDE a budgeted step (container init, cache), never the normal
# way the suite ends.
#
# Run 33787341170 died exactly this way: 40m20s, step `cargo test --workspace` cancelled with the
# whole suite already green and the doc-tests as the last thing on the log. Hence the split: the
# doc-tests get their own step so an overrun there is legible as an overrun THERE.
#
# Parsed as YAML, not as text: these are numeric assertions about a step's own budget, and
# associating a number with the step it belongs to is what indentation-guessing gets wrong.
# `scripts/tests/test-scope.test.sh` already imports PyYAML from this same workflow, so the
# dependency is proven on the runner.
budget_out="$(WF="$WF" python3 - <<'PY'
import os

import yaml

doc = yaml.safe_load(open(os.environ["WF"], encoding="utf-8"))
job = (doc.get("jobs") or {}).get("test") or {}
steps = job.get("steps") or []
job_budget = job.get("timeout-minutes")


def emit(ok, name, detail=""):
    print(("PASS" if ok else "FAIL") + "\t" + name + "\t" + detail)


costly = [s for s in steps if "cargo" in (s.get("run") or "")]
emit(bool(costly), "the `test` job runs cargo at all",
     "no step runs cargo: the rest of this contract would pass vacuously")

unbudgeted = [s.get("name") or s.get("id") or "<unnamed>"
              for s in costly if s.get("timeout-minutes") is None]
emit(not unbudgeted, "every cargo step carries its own `timeout-minutes` (hub#1519)",
     "these can only be stopped by the job-level cancel, which is mute: " + ", ".join(unbudgeted))

step_total = sum(s.get("timeout-minutes") or 0 for s in steps)
emit(isinstance(job_budget, int) and job_budget > step_total,
     "job budget (%s) > sum of the step budgets (%s) (hub#1519)" % (job_budget, step_total),
     "the job-level cancel would fire first and turn a named red back into a mute `cancelled`")

doc_steps = [s for s in costly if "cargo test" in s["run"] and "--doc" in s["run"]]
emit(len(doc_steps) == 1, "the doc-tests run in their OWN step (hub#1519)",
     "they were the last thing running when run 33787341170 was axed and nothing said so; "
     "found %d step(s) running `cargo test --doc`" % len(doc_steps))

suite = [s for s in costly if "cargo test" in s["run"] and "--doc" not in s["run"]]
emit(bool(suite) and all(all(f in s["run"] for f in ("--lib", "--bins", "--tests")) for s in suite),
     "the non-doc suite step selects its targets explicitly (hub#1519)",
     "a bare `cargo test` runs the doc-tests too, so the doc step would be decorative and the "
     "doc-tests would run twice")
PY
)" || bad "the budget contract could be evaluated" "python3/PyYAML failed on $WF"
while IFS=$'\t' read -r verdict name detail; do
    [ -n "${verdict:-}" ] || continue
    if [ "$verdict" = PASS ]; then ok "$name"; else bad "$name" "$detail"; fi
done <<<"$budget_out"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
