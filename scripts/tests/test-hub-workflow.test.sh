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
checked=0
for job in $jobs; do
    body="$(awk -v J="  $job:" '$0==J{f=1;next} f&&/^  [a-z_-]+:$/{exit} f' "$WF")"
    # Only jobs that run cargo/pnpm cost minutes; alert-style jobs are gated on push already.
    # Here-strings, never `printf … | grep -q`: under `pipefail`, grep -q closes the pipe at the
    # first match and printf dies with "Broken pipe" → a MATCH becomes a failure (red only on
    # Linux; the Mac's printf finishes first). Bit us on the first CI run of hub#1471.
    #
    # The command is looked for ANYWHERE in the job, not right after `run:` (hub#1519): the cargo
    # steps now carry a shell block (`run: |` + `set -uo pipefail` + `timeout 48m cargo …`), and
    # the old `run: *(cargo|pnpm)` matched none of them — the draft filter stopped being checked
    # and nothing said so. Same rule as section 5: the name NOT followed by a path character, which
    # is what keeps the `$HOME/.cargo/bin` of the toolchain step out. Erring loose is the safe
    # direction here: a job wrongly counted as costly only demands an `if:` it
    # already has, while one wrongly skipped asserts nothing at all. `\b` is avoided on purpose
    # (BSD and GNU ERE differ, and this file must parse under the bash 3.2 floor of hub#1468).
    grep -qE '(cargo|pnpm)([^[:alnum:]_./-]|$)' <<<"$body" || continue
    checked=$((checked+1))
    if grep -qF "$draft_if" <<<"$body"; then
        ok "job \`$job\` skips draft PRs"
    else
        bad "job \`$job\` skips draft PRs" "no \`if: $draft_if\`: a draft PR would burn runner minutes and get cancelled on the reviewer's re-push (measured 29/08)"
    fi
done
# Positive control (hub#1519): the loop above is a `continue` away from checking NOTHING and
# saying nothing about it — which is how the draft filter stopped being verified the day the
# cargo steps moved from `run: cargo …` to a `run: |` block. A battery that passes vacuously is
# the defect this repo keeps paying for, so the count is an assertion, not a debug line.
if [ "$checked" -gt 0 ]; then
    ok "the draft-filter check actually inspected a job that costs minutes ($checked)"
else
    bad "the draft-filter check actually inspected a job that costs minutes" "every job was skipped by the cargo/pnpm filter, so \`skips draft PRs\` was never asserted: the filter no longer matches how the steps are written"
fi

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
import re

import yaml

doc = yaml.safe_load(open(os.environ["WF"], encoding="utf-8"))
job = (doc.get("jobs") or {}).get("test") or {}
steps = job.get("steps") or []
job_budget = job.get("timeout-minutes")


def emit(ok, name, detail=""):
    print(("PASS" if ok else "FAIL") + "\t" + name + "\t" + detail)


# `cargo` NOT followed by a path character, instead of the bare substring: the `Toolchain` step
# mentions it only inside `$HOME/.cargo/bin`, where what follows is a `/`, so this drops that path
# (a `curl | sh` of seconds, whose right net is the job-level backstop) while still matching every
# way the command is actually spelled — `cargo test`, `"$CARGO_HOME/bin/cargo" bench`, a wrapper
# behind a variable. Deliberately NOT anchored to the start of a line: a step that reaches the
# toolchain through a path costs the same minutes, and a filter that stopped seeing it would leave
# this budget guard MUTE — the exact failure mode hub#1519 is about. Erring loose is the safe
# direction: at worst a step that merely prints the word is asked for a budget it can afford.
CARGO = re.compile(r"cargo(?![\w./-])")

costly = [s for s in steps if CARGO.search(s.get("run") or "")]
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

# The overrun message only exists if the shell gets far enough to print it. Actions runs a `run:`
# block as `bash -e {0}` — this workflow overrides no `shell:`, so `-e` is ON — and `set -uo
# pipefail` does NOT clear it. A bare `timeout ... cargo ...` that returns 124 therefore aborts the
# block ON THAT LINE: the `rc=$?` below it, the `overrun=true` output and the `::error
# title=Presupuesto...::` annotation never run. The step still goes red, so this does not show up as
# a broken build — it shows up as the budget guard going MUTE, which is the exact failure hub#1519
# exists to remove. Worse, `steps.<id>.outputs.overrun` then stays empty and the develop-broken
# alert fires on a merely slow runner: the false verdict its `if:` is there to prevent.
#
# The repo already spells the two idioms that survive `-e`: `cmd || rc=$?` (a checked command, so
# `-e` stays quiet) and an explicit `set +e` (test-hub-modules.yml). Only a STANDALONE capture is
# unreachable, so that is what is matched here — `|| rc=$?` is exempt by construction, not by a
# special case. `set +e` must come BEFORE the capture: after it, it changes nothing.
CAPTURE = re.compile(r"^[ \t]*[A-Za-z_][A-Za-z0-9_]*=(?:\$\?|\$\{PIPESTATUS\[)", re.M)
# The clear has to be a COMMAND, so this is anchored to the start of a line and reads a real `set`
# with a `+…e` flag (`set +e`, `set +ex`, `set -u +e`) — a `#` comment can never satisfy it. The
# substring search that stood here first could: every budgeted step explains its `set +e` in a
# comment right above the command, so deleting the command left the guard green. `set +u`/`set +x`
# stay unmatched on purpose: they do not clear errexit.
CLEARS_ERREXIT = re.compile(r"^[ \t]*set[ \t]+(?:[-+][A-Za-z]+[ \t]+)*\+[A-Za-z]*e", re.M)


def leaks(run):
    """The step captures `$?`/PIPESTATUS on a line `bash -e` aborts before ever reaching."""
    m = CAPTURE.search(run)
    if not m:
        return False
    clear = CLEARS_ERREXIT.search(run)
    return not (clear and clear.start() < m.start())


leaky = [s.get("name") or s.get("id") or "<unnamed>"
         for s in steps if leaks(s.get("run") or "")]

emit(not leaky, "a step that reads `$?` clears errexit first (hub#1519)",
     "Actions runs these under `bash -e`, so the capture line is unreachable and the overrun "
     "stays mute: " + ", ".join(leaky))


# Positive control. A guard no mutant can turn red is decoration, and this one is one line away
# from being exactly that: every budgeted step here EXPLAINS its `set +e` in a comment right above
# the command, so a search for the bare substring is satisfied by the explanation alone. The
# mutant below is the real one (command deleted, comment left) and it MUST be caught.
MUTANT = "set -uo pipefail\n# `set +e` por lo mismo que en `clippy`\nrc=${PIPESTATUS[0]}\n"
SAFE = "set -uo pipefail\nset +e\nrc=${PIPESTATUS[0]}\n"


emit(leaks(MUTANT) and not leaks(SAFE),
     "the errexit guard catches a `set +e` that is only a COMMENT (hub#1519)",
     "a comment that merely NAMES `set +e` exempts the step, so deleting the real command "
     "leaves this contract green: the guard is decorative for every step it protects")
PY
)" || bad "the budget contract could be evaluated" "python3/PyYAML failed on $WF"
while IFS=$'\t' read -r verdict name detail; do
    [ -n "${verdict:-}" ] || continue
    if [ "$verdict" = PASS ]; then ok "$name"; else bad "$name" "$detail"; fi
done <<<"$budget_out"

# ── 6. the suite's target/ fits the runner's disk six times over (infra#294) ──
# The runner has six slots on a 301 GB disk, and every slot builds its own `target/`. With
# `RUSTFLAGS=-C debuginfo=0` alone a mature target was 38 GB (6 × 38 + ~122 GB of base = 350 GB):
# the disk filled up and tests died with «No space left on device», which reads as a broken test.
# 91 % of that target is the ~318 linked test executables, and each one still carried two things
# nothing in CI ever reads:
#   · DWARF (8.2 of 32.4 GB) — the rustflag only reaches rustc; std's precompiled DWARF and the C
#     libraries built by `cc` with `-g` (it follows the PROFILE's `debug`, not RUSTFLAGS) are
#     linked into every binary;
#   · the symbol table (11.3 GB) — only a printed backtrace uses it, and CI never sets
#     `RUST_BACKTRACE`. A panic still names its `file:line:col` (that is `Location`, in `.rodata`).
# So the job builds with the PROFILE saying no debuginfo and strip the symbols, which drops both.
# Configured through the profile env on purpose: `CARGO_PROFILE_DEV_*` is inherited by the `test`
# profile, and it keeps local builds (debuggers, backtraces) untouched.
disk_out="$(WF="$WF" python3 - <<'PY'
import os

import yaml


def emit(ok, name, detail=""):
    print(("PASS" if ok else "FAIL") + "\t" + name + "\t" + detail)


def thin_target(env):
    """Why the target/ of the test job would NOT be thin; empty when it is."""
    env = {k: str(v).strip().lower() for k, v in (env or {}).items()}
    for profile in ("DEV", "TEST"):
        # TEST inherits DEV: a key TEST leaves unset takes the value of DEV.
        debug = env.get(f"CARGO_PROFILE_{profile}_DEBUG", env.get("CARGO_PROFILE_DEV_DEBUG"))
        strip = env.get(f"CARGO_PROFILE_{profile}_STRIP", env.get("CARGO_PROFILE_DEV_STRIP"))
        if debug not in ("0", "false", "none"):
            return f"CARGO_PROFILE_{profile}_DEBUG is {debug!r}: the profile still asks for DWARF"
        if strip not in ("symbols", "true"):
            return f"CARGO_PROFILE_{profile}_STRIP is {strip!r}: every test binary keeps its symbol table"
    return ""


doc = yaml.safe_load(open(os.environ["WF"], encoding="utf-8"))
job = (doc.get("jobs") or {}).get("test") or {}
why = thin_target(job.get("env"))
emit(not why, "the test job builds a thin target/ — no DWARF, no symbol table (infra#294)", why)

# Positive control: the state that filled the disk (rustflag only) and a half fix (DWARF gone,
# symbols kept: ~29 GB per slot, still 298 GB for six) must both be caught; a TEST override that
# undoes DEV too.
old = {"RUSTFLAGS": "-C debuginfo=0"}
half = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "debuginfo"}
undone = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "symbols",
          "CARGO_PROFILE_TEST_STRIP": "none"}
good = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "symbols"}
emit(all(thin_target(e) for e in (old, half, undone)) and not thin_target(good),
     "the thin-target guard catches the rustflag-only env and a half strip (infra#294)",
     "the guard accepts an env that leaves DWARF or the symbol table in every test binary")
PY
)" || bad "the disk contract could be evaluated" "python3/PyYAML failed on $WF"
while IFS=$'\t' read -r verdict name detail; do
    [ -n "${verdict:-}" ] || continue
    if [ "$verdict" = PASS ]; then ok "$name"; else bad "$name" "$detail"; fi
done <<<"$disk_out"

# ── 7. a PR that touches no Rust does not hold a runner for the Rust suite (26/09) ──────────
# 43 of 60 hub PRs since 24/09 touched no Rust and still held a self-hosted runner ~47 min
# (clippy + `cargo test --workspace`), queueing every module PR behind them. The `scope` step asks
# scripts/ci/touches-rust.sh; clippy and both cargo test steps run only when it says Rust. `push`
# to develop/main always runs everything (the post-merge net of hub#572 is untouched).
scope_out="$(WF="$WF" python3 - <<'PY'
import os
import yaml

doc = yaml.safe_load(open(os.environ["WF"], encoding="utf-8"))
steps = doc["jobs"]["test"]["steps"]

def emit(ok, name, detail):
    print(("PASS" if ok else "FAIL") + "\t" + name + "\t" + detail)

scope = [s for s in steps if s.get("id") == "scope"]
emit(len(scope) == 1, "the job has ONE `scope` step", "found %d steps with id: scope" % len(scope))
if scope:
    run = scope[0].get("run", "")
    idx = steps.index(scope[0])
    emit("scripts/ci/touches-rust.sh" in run, "the scope step asks scripts/ci/touches-rust.sh",
         "the classifier is not called: the skip would be decided by a look-alike")
    emit("rc=$?" in run and '"$rc" -eq 1' in run,
         "only the classifier's explicit «no» (exit 1) skips; any other failure runs the suite",
         "a missing or crashing classifier must never read as «no Rust»")
    emit("pull_request" in run and "rust=true" in run,
         "the scope step answers rust=true outside a pull request",
         "a push to develop/main must always run the suite (hub#572)")
    emit("HEAD^1" in run, "the scope step diffs the merge commit against its first parent",
         "without HEAD^1 the diff is not the PR's own change set")
    costly = [s for s in steps if any(k in str(s.get("run", "")) for k in ("cargo clippy", "cargo test"))]
    emit(len(costly) >= 3, "the costly steps are found (clippy + cargo test + doc-tests)",
         "found %d: the step names changed and this check no longer sees them" % len(costly))
    for s in costly:
        cond = str(s.get("if", ""))
        emit(cond.strip() == "steps.scope.outputs.rust != 'false'",
             "step «%s» is skipped ONLY on an explicit rust=false (fail-safe)" % s.get("name", "?"),
             "the condition must be exactly `steps.scope.outputs.rust != 'false'`: `== 'true'` skips the suite in silence when the output is missing (hub#1463), and no condition makes a web-only PR pay it")
        emit(steps.index(s) > idx, "step «%s» comes after the scope step" % s.get("name", "?"),
             "a step before `scope` cannot read its output")
co = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout")]
emit(bool(co) and (co[0].get("with") or {}).get("fetch-depth") == 2,
     "checkout fetches 2 commits (the merge commit and its first parent)",
     "with the default depth 1, HEAD^1 does not exist and every PR would fall back to the full suite")
PY
)" || bad "the scope contract could be evaluated" "python3/PyYAML failed on $WF"
while IFS=$'\t' read -r verdict name detail; do
    [ -n "${verdict:-}" ] || continue
    if [ "$verdict" = PASS ]; then ok "$name"; else bad "$name" "$detail"; fi
done <<<"$scope_out"
if grep -q 'scripts/tests/touches-rust.test.sh' "$WF"; then
    ok "test-hub.yml runs the classifier's contract"
else
    bad "test-hub.yml runs the classifier's contract" "add a step \`bash scripts/tests/touches-rust.test.sh\`"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
