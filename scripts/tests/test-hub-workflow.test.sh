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

# ── 3. EVERY job skips DRAFT PRs ─────────────────────────────────────────────────
# Since hub#1522 the suite is nine jobs (scope, clippy, six partitions, the aggregator) and every one
# of them takes a runner, so the filter is asserted on ALL of them — the old «only jobs that run
# cargo/pnpm» test would have let the scope or the aggregator job spin up on a draft.
# Here-strings, never `printf … | grep -q`: under `pipefail`, grep -q closes the pipe at the first
# match and printf dies with "Broken pipe" → a MATCH becomes a failure (red only on Linux; the Mac's
# printf finishes first). Bit us on the first CI run of hub#1471.
draft_if="github.event_name != 'pull_request' || !github.event.pull_request.draft"
jobs="$(awk '/^jobs:/{f=1;next} f&&/^  [a-z_-]+:$/{sub(/:$/,"",$1); print $1}' "$WF")"
[ -n "$jobs" ] || bad "the workflow declares jobs" "no \`jobs:\` entries parsed"
checked=0
for job in $jobs; do
    body="$(awk -v J="  $job:" '$0==J{f=1;next} f&&/^  [a-z_-]+:$/{exit} f' "$WF")"
    checked=$((checked+1))
    if grep -qF "$draft_if" <<<"$body"; then
        ok "job \`$job\` skips draft PRs"
    else
        bad "job \`$job\` skips draft PRs" "no \`if: $draft_if\`: a draft PR would burn runner minutes and get cancelled on the reviewer's re-push (measured 29/08)"
    fi
done
# Positive control (hub#1519): a loop over a job list the awk no longer parses checks NOTHING and
# says nothing about it. The four jobs of hub#1522 are the floor, so the count is an assertion.
if [ "$checked" -ge 4 ]; then
    ok "the draft-filter check inspected every job ($checked)"
else
    bad "the draft-filter check inspected every job" "only $checked job(s) parsed, expected at least 4 (scope, clippy, partitions, aggregator): the job parser no longer matches the file"
fi

# ── 4. this contract is RUN by the workflow it guards (hub#1381: an unexecuted battery is worth 0) ──
if grep -q 'scripts/tests/test-hub-workflow.test.sh' "$WF"; then
    ok "test-hub.yml runs this contract"
else
    bad "test-hub.yml runs this contract" "add a step \`bash scripts/tests/test-hub-workflow.test.sh\` — otherwise this file guards nothing"
fi

# ── 5-9. the shape of the jobs, parsed as YAML ────────────────────────────────────────────────
# Parsed as YAML, not as text: these are assertions about which step belongs to which job, which
# number is whose budget and which job waits for which — what indentation-guessing gets wrong.
# `scripts/tests/test-scope.test.sh` already imports PyYAML from this same workflow, so the
# dependency is proven on the runner.
#
# hub#1522 (pm#655 J1, 08/10): the suite no longer fits ONE job. Measured on `ubuntu-latest` the
# step took ~39 min (build ~6 + run ~33) and run 37769065800 died at the 48-min budget of hub#1519
# with no red test. Since the repo went public the CI runs on GitHub's free machines (20 jobs at a
# time across the org), so the old reason against splitting the suite — ONE saturated self-hosted
# runner — is gone. The shape this file pins now:
#
#   scope       → asks scripts/ci/touches-rust.sh, exposes `outputs.rust`
#   clippy      → the lint gate + the contract batteries, once per run
#   partitions  → a 6-way matrix, `cargo nextest run … --partition slice:k/6`, one Postgres each.
#                 `slice`, not `count`: measured on 5,598 tests (08/10), `count` restarts its
#                 round-robin in every test binary and gave 1094/1030/970/901/828/775 tests per
#                 leg — leg 1 (which also runs the doc-tests) 41 % heavier than leg 6 — while
#                 `slice` deals the whole list and gave 933 each. Same union, no duplicates.
#   workspace   → named EXACTLY `cargo test --workspace`, `if: always()`: green only when every
#                 partition is green (or when a PR touches no Rust). `pm/merge-pr.sh`
#                 (`require_workspace_suite`) authorises a Rust merge by that exact check name.
shape_out="$(WF="$WF" python3 - <<'PY'
import os
import re
import subprocess
import tempfile

import yaml

doc = yaml.safe_load(open(os.environ["WF"], encoding="utf-8"))
jobs = doc.get("jobs") or {}
AGGREGATOR = "cargo test --workspace"
SAFE_RUST_GATE = "needs.scope.outputs.rust != 'false'"


def emit(ok, name, detail=""):
    print(("PASS" if ok else "FAIL") + "\t" + name + "\t" + " ".join(str(detail).split()))


def steps_of(job):
    return (job or {}).get("steps") or []


def needs_of(job):
    n = (job or {}).get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def step_name(s):
    return s.get("name") or s.get("id") or "<unnamed>"


# `cargo` NOT followed by a path character, instead of the bare substring: the `Toolchain` step
# mentions it only inside `$HOME/.cargo/bin`, where what follows is a `/`, so this drops that path
# (a `curl | sh` of seconds, whose right net is the job-level backstop) while still matching every
# way the command is actually spelled — `cargo test`, `"$CARGO_HOME/bin/cargo" bench`, a wrapper
# behind a variable. Erring loose is the safe direction: at worst a step that merely prints the
# word is asked for a budget it can afford.
CARGO = re.compile(r"cargo(?![\w./-])")


def costly(job):
    return [s for s in steps_of(job) if CARGO.search(s.get("run") or "")]


def run_step(script, env):
    """Execute the `run:` block of a step the way Actions does (`bash -e`), with a fake GITHUB_OUTPUT.

    Returns (exit code, the GITHUB_OUTPUT contents). Only for steps whose inputs arrive through
    `env:` — an inline `${{ }}` would be left unexpanded and the result would mean nothing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out")
        open(out, "w").close()
        full = dict(os.environ, GITHUB_OUTPUT=out, RUNNER_TEMP=tmp, **env)
        rc = subprocess.run(["bash", "-e", "-c", script], env=full,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        return rc, open(out).read()


cargo_jobs = {jid: j for jid, j in jobs.items() if costly(j)}
emit(bool(cargo_jobs), "some job runs cargo at all",
     "no step runs cargo: the rest of this contract would pass vacuously")

# ── 5. a time-budget overrun is a NAMED red, never a mute `cancelled` (hub#1519) ──────────────
# GitHub marks a job that hits the JOB-level `timeout-minutes` as `cancelled` — indistinguishable
# from a cancel by concurrency or by a newer push. It names no test, and `merge-pr.sh` reads it as
# not-green and refuses to merge without saying why. A STEP that hits its OWN `timeout-minutes`
# FAILS instead, and a failed step is a red that points at itself. So every step that costs
# minutes carries its own budget, each job's budget stays strictly ABOVE the sum of its steps',
# and the shell `timeout` inside a step fires BEFORE the own limit of the step, so the step can still
# say out loud that it was the clock (exit 124/137) and not a test.
for jid, job in cargo_jobs.items():
    unbudgeted = [step_name(s) for s in costly(job) if s.get("timeout-minutes") is None]
    emit(not unbudgeted, "job `%s`: every cargo step carries its own `timeout-minutes` (hub#1519)" % jid,
         "these can only be stopped by the job-level cancel, which is mute: " + ", ".join(unbudgeted))
    budget = job.get("timeout-minutes")
    total = sum(s.get("timeout-minutes") or 0 for s in steps_of(job))
    emit(isinstance(budget, int) and budget > total,
         "job `%s`: budget (%s) > sum of its step budgets (%s) (hub#1519)" % (jid, budget, total),
         "the job-level cancel would fire first and turn a named red back into a mute `cancelled`")

SHELL_TIMEOUT = re.compile(r"(?:^|[\s;|&(])timeout\s+(\d+)m\b")
late = []
for jid, job in jobs.items():
    for s in steps_of(job):
        for minutes in SHELL_TIMEOUT.findall(s.get("run") or ""):
            step_budget = s.get("timeout-minutes")
            if not isinstance(step_budget, int) or int(minutes) >= step_budget:
                late.append("%s/%s (timeout %sm vs step %s)" % (jid, step_name(s), minutes, step_budget))
emit(not late, "every shell `timeout` fires before the `timeout-minutes` of its step (hub#1519)",
     "the step limit would cut first and the overrun message would never print: " + ", ".join(late))

raw = open(os.environ["WF"], encoding="utf-8").read()
emit("timeout 48m" not in raw, "no `timeout 48m` is left (hub#1522)",
     "the 48-min monolithic budget is what killed run 37769065800 with no red test")

# The overrun message only exists if the shell gets far enough to print it. Actions runs a `run:`
# block as `bash -e {0}` — this workflow overrides no `shell:`, so `-e` is ON — and `set -uo
# pipefail` does NOT clear it. A bare `timeout ... cargo ...` that returns 124 therefore aborts the
# block ON THAT LINE: the `rc=$?` below it, the `overrun=true` output and the `::error
# title=Presupuesto...::` annotation never run. The step still goes red, so this does not show up as
# a broken build — it shows up as the budget guard going MUTE, which is the exact failure hub#1519
# exists to remove.
#
# The repo already spells the two idioms that survive `-e`: `cmd || rc=$?` (a checked command, so
# `-e` stays quiet) and an explicit `set +e`. Only a STANDALONE capture is unreachable, so that is
# what is matched here — `|| rc=$?` is exempt by construction. `set +e` must come BEFORE the
# capture: after it, it changes nothing.
CAPTURE = re.compile(r"^[ \t]*[A-Za-z_][A-Za-z0-9_]*=(?:\$\?|\$\{PIPESTATUS\[)", re.M)
# The clear has to be a COMMAND, so this is anchored to the start of a line and reads a real `set`
# with a `+…e` flag (`set +e`, `set +ex`, `set -u +e`) — a `#` comment can never satisfy it.
CLEARS_ERREXIT = re.compile(r"^[ \t]*set[ \t]+(?:[-+][A-Za-z]+[ \t]+)*\+[A-Za-z]*e", re.M)


def leaks(run):
    """The step captures `$?`/PIPESTATUS on a line `bash -e` aborts before ever reaching."""
    m = CAPTURE.search(run)
    if not m:
        return False
    clear = CLEARS_ERREXIT.search(run)
    return not (clear and clear.start() < m.start())


leaky = ["%s/%s" % (jid, step_name(s)) for jid, job in jobs.items() for s in steps_of(job)
         if leaks(s.get("run") or "")]
emit(not leaky, "a step that reads `$?` clears errexit first (hub#1519)",
     "Actions runs these under `bash -e`, so the capture line is unreachable and the overrun "
     "stays mute: " + ", ".join(leaky))
# Positive control: the real mutant (command deleted, explanatory comment left) MUST be caught.
MUTANT = "set -uo pipefail\n# `set +e` por lo mismo que en `clippy`\nrc=${PIPESTATUS[0]}\n"
SAFE = "set -uo pipefail\nset +e\nrc=${PIPESTATUS[0]}\n"
emit(leaks(MUTANT) and not leaks(SAFE),
     "the errexit guard catches a `set +e` that is only a COMMENT (hub#1519)",
     "a comment that merely NAMES `set +e` exempts the step, so deleting the real command "
     "leaves this contract green")

# ── 6. every job that compiles builds a thin, non-incremental target/ (infra#294, hub#1522) ────
# 91 % of a target is the ~318 linked test executables, and each one carried DWARF (from std and from
# the C libraries built by `cc`, which follow the PROFILE, not RUSTFLAGS) and a symbol table nothing in CI
# reads. Profile env, not rustflags: the `test` profile inherits `dev`, and local builds keep their
# debuginfo. `CARGO_INCREMENTAL=0`: incremental state is pure disk on a one-shot CI build (pm#655 J1).


def thin_target(env):
    """Why the target/ of a job would NOT be thin; empty when it is."""
    env = {k: str(v).strip().lower() for k, v in (env or {}).items()}
    for profile in ("DEV", "TEST"):
        # TEST inherits DEV: a key TEST leaves unset takes the value of DEV.
        debug = env.get(f"CARGO_PROFILE_{profile}_DEBUG", env.get("CARGO_PROFILE_DEV_DEBUG"))
        strip = env.get(f"CARGO_PROFILE_{profile}_STRIP", env.get("CARGO_PROFILE_DEV_STRIP"))
        if debug not in ("0", "false", "none"):
            return f"CARGO_PROFILE_{profile}_DEBUG is {debug!r}: the profile still asks for DWARF"
        if strip not in ("symbols", "true"):
            return f"CARGO_PROFILE_{profile}_STRIP is {strip!r}: every test binary keeps its symbol table"
    if env.get("CARGO_INCREMENTAL") not in ("0", "false"):
        return f"CARGO_INCREMENTAL is {env.get('CARGO_INCREMENTAL')!r}: incremental state is wasted disk in CI"
    return ""


wf_env = doc.get("env") or {}
for jid, job in cargo_jobs.items():
    why = thin_target(dict(wf_env, **(job.get("env") or {})))
    emit(not why, "job `%s` builds a thin target/ — no DWARF, no symbol table, no incremental (infra#294)" % jid, why)
old = {"RUSTFLAGS": "-C debuginfo=0", "CARGO_INCREMENTAL": 0}
half = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "debuginfo", "CARGO_INCREMENTAL": 0}
undone = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "symbols",
          "CARGO_PROFILE_TEST_STRIP": "none", "CARGO_INCREMENTAL": 0}
incremental = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "symbols"}
good = {"CARGO_PROFILE_DEV_DEBUG": 0, "CARGO_PROFILE_DEV_STRIP": "symbols", "CARGO_INCREMENTAL": 0}
emit(all(thin_target(e) for e in (old, half, undone, incremental)) and not thin_target(good),
     "the thin-target guard catches the rustflag-only env, a half strip and an incremental build",
     "the guard accepts an env that leaves DWARF, the symbol table or incremental state behind")

# ── 7. a PR that touches no Rust does not hold runners for the Rust suite (26/09) ─────────────
# 43 of 60 hub PRs since 24/09 touched no Rust and still held a runner ~47 min. The `scope` job asks
# scripts/ci/touches-rust.sh; clippy and the partitions run only when it says Rust. `push` to
# develop/main always runs everything (the post-merge net of hub#572 is untouched).
scope_job = jobs.get("scope") or {}
scope = [s for s in steps_of(scope_job) if s.get("id") == "scope"]
emit(len(scope) == 1, "the `scope` job has ONE `scope` step", "found %d steps with id: scope" % len(scope))
if scope:
    run = scope[0].get("run", "")
    emit("scripts/ci/touches-rust.sh" in run, "the scope step asks scripts/ci/touches-rust.sh",
         "the classifier is not called: the skip would be decided by a look-alike")
    emit("rc=$?" in run and '"$rc" -eq 1' in run,
         "only an explicit «no» of the classifier (exit 1) skips; any other failure runs the suite",
         "a missing or crashing classifier must never read as «no Rust»")
    emit("pull_request" in run and "rust=true" in run,
         "the scope step answers rust=true outside a pull request",
         "a push to develop/main must always run the suite (hub#572)")
    emit("HEAD^1" in run, "the scope step diffs the merge commit against its first parent",
         "without HEAD^1 the diff is not the own change set of the PR")
emit(str((scope_job.get("outputs") or {}).get("rust", "")).replace(" ", "") == "${{steps.scope.outputs.rust}}",
     "the `scope` job exposes `outputs.rust` from its scope step",
     "the other jobs read `needs.scope.outputs.rust`: without this output it is always empty")
co = [s for s in steps_of(scope_job) if str(s.get("uses", "")).startswith("actions/checkout")]
emit(bool(co) and (co[0].get("with") or {}).get("fetch-depth") == 2,
     "the checkout of the scope job fetches 2 commits (the merge commit and its first parent)",
     "with the default depth 1, HEAD^1 does not exist and every PR would fall back to the full suite")

clippy_steps = [(jid, s) for jid, j in jobs.items() for s in steps_of(j) if "cargo clippy" in (s.get("run") or "")]
emit(len(clippy_steps) == 1, "clippy runs ONCE per run, not once per partition",
     "found %d steps running `cargo clippy`" % len(clippy_steps))
gated = list(clippy_steps)
part_jobs = [jid for jid, j in jobs.items() if "cargo nextest run" in "".join(s.get("run") or "" for s in steps_of(j))]
for jid, s in clippy_steps:
    job = jobs[jid]
    cond = str(s.get("if", "")).strip() + " " + str(job.get("if", ""))
    emit(SAFE_RUST_GATE in cond and "== 'true'" not in cond and "scope" in needs_of(job),
         "clippy is skipped ONLY on an explicit rust=false (fail-safe)",
         "its job must `needs: scope` and its condition read `%s`: `== 'true'` skips in silence when "
         "the output is missing (hub#1463), and no condition makes a web-only PR pay it" % SAFE_RUST_GATE)
for jid in part_jobs:
    job = jobs[jid]
    cond = str(job.get("if", ""))
    emit(SAFE_RUST_GATE in cond and "== 'true'" not in cond and "scope" in needs_of(job),
         "job `%s` is skipped ONLY on an explicit rust=false (fail-safe)" % jid,
         "it must `needs: scope` and its job-level `if:` contain `%s`" % SAFE_RUST_GATE)

# ── 8. the suite runs as a 6-way nextest matrix, each leg with its own Postgres (hub#1522) ────
emit(len(part_jobs) == 1, "ONE job runs `cargo nextest run`", "found %d: %s" % (len(part_jobs), part_jobs))
parts = []
if part_jobs:
    pid = part_jobs[0]
    pj = jobs[pid]
    strategy = pj.get("strategy") or {}
    parts = (strategy.get("matrix") or {}).get("part") or []
    emit(parts == [1, 2, 3, 4, 5, 6], "job `%s` is a matrix over part: [1..6]" % pid,
         "matrix.part is %r" % (parts,))
    emit(strategy.get("fail-fast") is False, "the matrix has `fail-fast: false`",
         "with fail-fast one red partition cancels the other five: the aggregator would see "
         "`cancelled` legs and the PR would lose the rest of its failures")
    nx = [s for s in steps_of(pj) if "cargo nextest run" in (s.get("run") or "") and "--no-run" not in s["run"]]
    emit(len(nx) == 1, "the partition runs ONE `cargo nextest run` step", "found %d" % len(nx))
    if nx:
        run = " ".join(nx[0]["run"].replace("\\\n", " ").split())
        for flag in ("--workspace", "--lib --bins --tests", "--exclude erplora-tauri",
                     "--exclude tauri-plugin-erplora-android", "--no-fail-fast",
                     "--partition slice:${{ matrix.part }}/%d" % len(parts)):
            emit(flag in run, "the nextest step passes `%s`" % flag,
                 "the partitions would not add up to the old `cargo test --workspace --lib --bins --tests`")
        m = SHELL_TIMEOUT.search(nx[0]["run"])
        emit(bool(m) and int(m.group(1)) <= 30,
             "the run budget of a partition is a shell `timeout` of at most 30 min (hub#1522)",
             "found %s: a partition that needs more must become more partitions, not a bigger clock"
             % (m.group(0) if m else "no `timeout Nm`"))
        emit("124" in nx[0]["run"] and "137" in nx[0]["run"] and "::error" in nx[0]["run"]
             and "hub#1519" in nx[0]["run"],
             "the partition names a clock overrun (exit 124/137) as the clock, not as a test (hub#1519)",
             "an overrun would read as a broken test")
    installs = [s for s in steps_of(pj)
                if str(s.get("uses", "")).startswith("taiki-e/install-action")
                or "cargo binstall" in (s.get("run") or "")]
    emit(bool(installs), "nextest is installed as a prebuilt binary (taiki-e/install-action or cargo-binstall)",
         "no install step: the matrix would fail with `no such command: nextest`")
    emit("cargo install cargo-nextest" not in raw, "nextest is never compiled from source",
         "`cargo install cargo-nextest` costs minutes on every one of the six legs")
    pg = ((pj.get("services") or {}).get("postgres") or {})
    emit(pg.get("image") == "pgvector/pgvector:pg18",
         "every partition gets its own Postgres (`pgvector/pgvector:pg18`)",
         "image is %r: `crates/vector/tests/pg_store.rs` needs pgvector (ADR-0282)" % pg.get("image"))
    emit(any(step_name(s) == "Free disk space" for s in steps_of(pj)),
         "every partition frees disk before building", "each leg links the whole test target/")
    # Doc-tests: once, in partition 1 only, and still COUNTED (hub#1519: a doc step that runs none is
    # as green as one that passes them).
    doc_steps = [(jid, s) for jid, j in jobs.items() for s in steps_of(j)
                 if "cargo test" in (s.get("run") or "") and "--doc" in s["run"]]
    emit(len(doc_steps) == 1 and doc_steps[0][0] == pid,
         "the doc-tests run in ONE step, inside the partition job",
         "found %d step(s) running `cargo test --doc`" % len(doc_steps))
    if doc_steps:
        ds = doc_steps[0][1]
        emit(str(ds.get("if", "")).replace(" ", "") == "matrix.part==1",
             "the doc-tests run only in partition 1",
             "if: %r — six legs would each pay a doc-test build for 4 tests" % ds.get("if"))
        emit("test result: ok" in ds["run"] and '"$total" -eq 0' in ds["run"],
             "the doc-tests are still COUNTED (an empty doc run is red, hub#1519)",
             "a doc step that runs no doc-test would go green")
    bare = ["%s/%s" % (jid, step_name(s)) for jid, j in jobs.items() for s in steps_of(j)
            if re.search(r"cargo test(?![^\n]*--doc)", s.get("run") or "")]
    emit(not bare, "no step runs `cargo test` outside the doc-tests (the suite belongs to nextest now)",
         "the suite would run twice: " + ", ".join(bare))
    # The per-leg verdict feeds the develop-broken alert (hub#572) in the aggregator.
    outs = pj.get("outputs") or {}
    emit(all(("verdict_%d" % k) in outs for k in parts),
         "the partition job declares one `verdict_<k>` output per leg",
         "matrix legs overwrite a shared output name: each leg needs its own key")
    vs = [s for s in steps_of(pj) if s.get("id") == "verdict"]
    emit(len(vs) == 1 and "always()" in str(vs[0].get("if", "")) if vs else False,
         "a `verdict` step runs `if: always()` at the end of each leg",
         "without it a red leg reports nothing to the alert")
    if vs:
        def verdict(**env):
            rc, out = run_step(vs[0]["run"], dict({"PART": "3", "TESTS_OVERRUN": "", "DOC_OVERRUN": "",
                                                   "DOC_OUTCOME": "skipped"}, **env))
            return rc, out.strip()
        cases = [
            ({"TESTS_OUTCOME": "success"}, "verdict_3=pass"),
            ({"TESTS_OUTCOME": "failure"}, "verdict_3=test-failure"),
            ({"TESTS_OUTCOME": "failure", "TESTS_OVERRUN": "true"}, "verdict_3=overrun"),
            ({"TESTS_OUTCOME": "success", "DOC_OUTCOME": "failure"}, "verdict_3=test-failure"),
            ({"TESTS_OUTCOME": "success", "DOC_OUTCOME": "failure", "DOC_OVERRUN": "true"}, "verdict_3=overrun"),
            ({"BUILD_OUTCOME": "failure", "TESTS_OUTCOME": "skipped"}, "verdict_3=test-failure"),
            ({"BUILD_OUTCOME": "failure", "BUILD_OVERRUN": "true", "TESTS_OUTCOME": "skipped"}, "verdict_3=overrun"),
            ({"TESTS_OUTCOME": "skipped"}, "verdict_3=environment"),
            ({"TESTS_OUTCOME": "cancelled"}, "verdict_3=environment"),
        ]
        for env, want in cases:
            rc, got = verdict(**env)
            emit(rc == 0 and got == want, "verdict step: %s → %s" % (env, want),
                 "got rc=%s output=%r" % (rc, got))

# ── 9. ONE aggregator named exactly `cargo test --workspace` decides (hub#1522) ──────────────
named = [jid for jid, j in jobs.items() if j.get("name") == AGGREGATOR]
emit(len(named) == 1, "exactly ONE job is named `%s`" % AGGREGATOR,
     "found %d: merge-pr.sh matches the check name exactly (== and SUCCESS)" % len(named))
if named:
    aid = named[0]
    aj = jobs[aid]
    emit("always()" in str(aj.get("if", "")), "the aggregator runs `if: always()`",
         "without it a red partition SKIPS the aggregator, and a skipped check is not a red one")
    emit(set(needs_of(aj)) >= {"scope", "clippy"} | set(part_jobs),
         "the aggregator needs scope, clippy and the partitions", "needs: %r" % needs_of(aj))
    decide = [s for s in steps_of(aj) if s.get("id") == "decide"]
    emit(len(decide) == 1, "the aggregator has ONE `decide` step", "found %d" % len(decide))
    if decide:
        env_keys = set((decide[0].get("env") or {}).keys())
        emit({"SCOPE_RESULT", "RUST", "CLIPPY_RESULT", "PARTITIONS_RESULT"} <= env_keys
             and ("$" + "{{") not in decide[0]["run"],
             "the decision reads its inputs from `env:` only (so it can be executed here)",
             "env keys: %r" % sorted(env_keys))
        ok = {"SCOPE_RESULT": "success", "RUST": "true", "CLIPPY_RESULT": "success",
              "PARTITIONS_RESULT": "success"}
        cases = [
            ("every partition green", {}, 0),
            ("one partition red", {"PARTITIONS_RESULT": "failure"}, 1),
            ("a partition cancelled", {"PARTITIONS_RESULT": "cancelled"}, 1),
            ("partitions skipped although the PR touches Rust", {"PARTITIONS_RESULT": "skipped"}, 1),
            ("clippy red", {"CLIPPY_RESULT": "failure"}, 1),
            ("scope failed (output missing)", {"SCOPE_RESULT": "failure", "RUST": "",
                                               "CLIPPY_RESULT": "skipped", "PARTITIONS_RESULT": "skipped"}, 1),
            ("PR without Rust: partitions skipped", {"RUST": "false", "PARTITIONS_RESULT": "skipped"}, 0),
            ("PR without Rust but the contracts job red", {"RUST": "false", "CLIPPY_RESULT": "failure",
                                                           "PARTITIONS_RESULT": "skipped"}, 1),
        ]
        for label, delta, want in cases:
            rc, _ = run_step(decide[0]["run"], dict(ok, **delta))
            emit((rc == 0) == (want == 0), "aggregator: %s → %s" % (label, "green" if want == 0 else "red"),
                 "decide exited %s" % rc)
    alert = [s for s in steps_of(aj) if "alert-issue.sh" in (s.get("run") or "")]
    emit(len(alert) == 1, "the develop-broken alert (hub#572) lives in the aggregator, once per run",
         "found %d alert steps there: one per leg would post six comments per detection" % len(alert))
    if alert:
        cond = " ".join(str(alert[0].get("if", "")).split())
        emit("refs/heads/develop" in cond and "'push'" in cond and '"test-failure"' in cond,
             "the alert fires only on a push to develop with a REAL test failure",
             "if: %r — an overrun or a broken runner must not cry «develop is broken»" % cond)
    emit(not any("alert-issue.sh" in (s.get("run") or "") for jid, j in jobs.items() if jid != aid
                 for s in steps_of(j)),
         "no other job opens the develop-broken alert", "the partitions must leave it to the aggregator")
    leg_names = [str(jobs[j].get("name", "")) for j in part_jobs]
    emit(all(n != AGGREGATOR and not n.startswith(AGGREGATOR + " (") for n in leg_names),
         "the partition legs do not reuse the name of the aggregator", "names: %r" % leg_names)
PY
)" || bad "the shape contract could be evaluated" "python3/PyYAML failed on $WF"
while IFS=$'\t' read -r verdict name detail; do
    [ -n "${verdict:-}" ] || continue
    if [ "$verdict" = PASS ]; then ok "$name"; else bad "$name" "$detail"; fi
done <<<"$shape_out"
if grep -q 'scripts/tests/touches-rust.test.sh' "$WF"; then
    ok "test-hub.yml runs the classifier's contract"
else
    bad "test-hub.yml runs the classifier's contract" "add a step \`bash scripts/tests/touches-rust.test.sh\`"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
