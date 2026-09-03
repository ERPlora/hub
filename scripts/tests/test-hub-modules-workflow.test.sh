#!/usr/bin/env bash
# Contract test for `.github/workflows/test-hub-modules.yml` — the "crater/runbot" gate that
# proves the 27 PUBLISHED modules still work against the runtime (ERPlora/hub#1239).
#
# Regression test for ERPlora/hub#1239. What each case protects, and why it is here:
#
#   · The gate only ran on a nightly `schedule` and on two `paths`, so a PR that changed the
#     runtime, the HTTP surface or the manifest schema merged WITHOUT any published module ever
#     being run against it. That is the exact hole the ADR «El Hub se CIERRA como KERNEL»
#     (2026-08-27) closes: a kernel PR is only mergeable with this workflow green against the
#     published catalogue.
#
#   · When it did run, a failure was MUTE. hub#1215 sat red for a whole day with Actions green
#     because nobody watches a cron. `test-hub.yml` already solved this for `develop` with an
#     idempotent alert issue; the same step belongs here.
#
#   · A module release is the OTHER way this breaks (hub#1215 was caused by `invoice` v1.2.27,
#     with no hub commit at all). A `repository_dispatch` from the module's `release.yml` puts
#     the red where it belongs, and the payload has to be VISIBLE — a run titled like every
#     other nightly does not say which module published.
#
# The file is parsed as YAML (not grepped) so a case fails NAMING the missing element, and the
# workflow under test is a parameter (`--workflow`) so the guard can be proven to catch the
# positive: mutate a copy, run this against it, watch it fail on that element.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
workflow="$script_dir/../../.github/workflows/test-hub-modules.yml"

while [ $# -gt 0 ]; do
    case "$1" in
        --workflow) workflow="$2"; shift 2 ;;
        *) printf 'usage: %s [--workflow <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

if [ ! -f "$workflow" ]; then
    printf 'FAIL: no such workflow: %s\n' "$workflow" >&2
    exit 1
fi

# A YAML parser is REQUIRED, never optional: a guard that silently degrades to "skipped" when a
# tool is missing is the same mute green this workflow exists to abolish.
if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check the workflow contract (apt: python3-yaml)\n' >&2
    exit 1
fi

WORKFLOW="$workflow" REPO_ROOT="$script_dir/../.." python3 - <<'PY'
import os
import re
import sys

import yaml

path = os.environ["WORKFLOW"]
with open(path, encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def dump(value):
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()


# YAML 1.1 turns the bare key `on` into the boolean True — the classic Actions gotcha.
triggers = doc.get("on", doc.get(True))
check("the workflow declares triggers", isinstance(triggers, dict), f"got {triggers!r}")
triggers = triggers if isinstance(triggers, dict) else {}

jobs = doc.get("jobs") or {}
job = jobs.get("module-e2e") or {}
check("the `module-e2e` job exists", bool(job), f"jobs found: {sorted(jobs)}")
steps = job.get("steps") or []


# ── 1 · The gate runs on every PR that touches a KERNEL SURFACE ──────────────────────
# The six surfaces the ADR freezes: the declarative engine and the row contract
# (`crates/runtime`), the HTTP/WS surface (`crates/server`), the manifest schema
# (`schemas`), the SQL dialects and migrations (`crates/db`), the guest ABI
# (`crates/guest-sdk`) and its host (`crates/wasm-host`). Changing any of them without
# running the published catalogue is how a kernel PR breaks a module in production.
REQUIRED_PATHS = [
    "crates/runtime/**",
    "crates/server/**",
    "schemas/**",
    "crates/db/**",
    "crates/guest-sdk/**",
    "crates/wasm-host/**",
    ".github/workflows/test-hub-modules.yml",
]
# Desde el 29/08 (Ioan) estos e2e NO corren en las PRs: los corre el gate pre-push, que
# materializa el catálogo publicado y los ejecuta por defecto (hub#1353 — medido: 30 binarios,
# 1 365 tests, 0 fallos, 5m07s). Si están rojos, el push se aborta y no llega a haber PR. El
# `push` a develop/main se queda: es la red post-merge de hub#572, que el gate no puede dar.
check(
    "el workflow NO corre en `pull_request` (lo corre el gate local)",
    triggers.get("pull_request") is None,
    f"got {triggers.get('pull_request')!r}",
)
push_paths = (triggers.get("push") or {}).get("paths")
check(
    "sigue corriendo en `push` a develop/main sobre TODO el repo",
    push_paths is None,
    f"push.paths = {push_paths!r} — un filtro aquí dejaría el post-merge ciego",
)


# ── 2 · A failure is LOUD: an idempotent alert issue, like `test-hub.yml` ────────────
perms = job.get("permissions") or doc.get("permissions") or {}
check(
    "the job may write issues (`permissions.issues: write`)",
    perms.get("issues") == "write",
    f"permissions are {perms}",
)

ALERT_TITLE = "Los módulos publicados ROMPEN contra develop"
alert = [s for s in steps if ALERT_TITLE in str(s.get("run", ""))]
check(
    f"a step opens the alert issue titled «{ALERT_TITLE}»",
    len(alert) == 1,
    f"{len(alert)} steps mention it",
)
if len(alert) == 1:
    run = str(alert[0].get("run", ""))
    cond = str(alert[0].get("if", ""))
    check(
        "the alert search phrase carries no colon (colons are GitHub search syntax)",
        ":" not in ALERT_TITLE,
        ALERT_TITLE,
    )
    # Review of hub#1246: the idempotent lookup (list the open issues, match the title
    # LOCALLY, comment or create) used to be inlined here with `gh issue list --search`,
    # which reads GitHub's SEARCH index — it lags behind reality (it returned zero with open
    # issues on 2026-08-16). It is now `scripts/ci/alert-issue.sh`, the ONE implementation
    # shared with `test-hub.yml` and `image-freshness.yml` (hub#1246) — its own idempotency
    # and its own ban on `--search` are covered by scripts/tests/alert-issue.test.sh, not
    # duplicated here. This step's job is only to delegate to it with the right title/body.
    code = "\n".join(l for l in run.splitlines() if not l.lstrip().startswith("#"))
    check(
        "the alert never inlines `--search` (delegates to scripts/ci/alert-issue.sh instead)",
        "--search" not in code,
        "GitHub's search index lags: two failures minutes apart would open two issues",
    )
    check(
        "the alert delegates the lookup to the shared scripts/ci/alert-issue.sh",
        "./scripts/ci/alert-issue.sh" in code,
        "every alert step (test-hub, image-freshness, test-hub-modules) must share ONE"
        " implementation instead of copies that can drift apart (hub#1246)",
    )
    check(
        "the alert passes the exact title through TITLE=",
        f'title="{ALERT_TITLE}"' in code and ("TITLE=\"$title\"" in code or "TITLE=$title" in code),
        code,
    )
    # Review of hub#1245: the tests step can die BEFORE `tee` creates the log (the target-list
    # guard, the resolver pipeline). awk on an absent file exits 2, `set -euo pipefail`
    # kills the alert step, and the issue never opens — the mute red this step abolishes.
    check(
        "the alert survives a missing cargo log (the tests step can die before `tee`)",
        '[ -s "$RUNNER_TEMP/module-e2e.log" ]' in run,
        "guard the log with `[ -s ... ]` so the fallback text is used instead of dying",
    )
    check(
        "the alert names the FAILING TARGETS, not just the run",
        "FAILING_TARGETS" in run,
        "an alert that does not say what broke sends the reader back to the log",
    )
    check(
        "the alert is gated on the TEST step's own outcome",
        "steps.tests.outcome == 'failure'" in cond,
        f"if: {cond!r} — an environmental failure (disk, service container) must not fake"
        " a 'the modules are broken' verdict",
    )
    check(
        "the alert never fires on a `pull_request` (the PR check is already visible)",
        "pull_request" not in cond,
        f"if: {cond!r}",
    )
    for event in ("schedule", "repository_dispatch", "push"):
        check(
            f"the alert fires for `{event}` (nobody watches it otherwise)",
            event in cond,
            f"if: {cond!r}",
        )
    check(
        "the alert step carries a token",
        "GH_TOKEN" in (alert[0].get("env") or {}),
        f"env is {alert[0].get('env')}",
    )

tests_step = [s for s in steps if s.get("id") == "tests"]
check(
    "the `cargo test` step has `id: tests` (the alert's gate reads its outcome)",
    len(tests_step) == 1,
    f"{len(tests_step)} steps carry that id",
)


# ── 2b · The target set is guarded by a reviewed LIST, never by a magic number ───────
# hub#1359 (the red: hub#1354): the floor used to be `[ "$count" -ge 30 ]`. That is a snapshot, not a contract —
# hub#1264 moves module-owned e2e out of the hub into each module's `erplora test` battery, the
# seventh slice took the count to 29, and `develop` went red for the whole fleet blaming a grep
# that was working. The only repair a number offers is to lower it, which teaches the wrong
# reflex about a coverage guard; and it can never catch the other direction, because a count
# only grows there.
RESOLVER = "scripts/ci/kernel-e2e-targets.sh"
MANIFEST = "scripts/ci/kernel-e2e-targets.txt"
if len(tests_step) == 1:
    tests_code = "\n".join(
        l
        for l in str(tests_step[0].get("run", "")).splitlines()
        if not l.lstrip().startswith("#")
    )
    check(
        f"the tests step resolves its targets through `{RESOLVER}`",
        RESOLVER in tests_code,
        "inlining the resolution again is how the local gate and this job drifted apart"
        " over the module catalogue (hub#1153)",
    )
    # `-ge <n>` / `-lt <n>` over the target count in any form: the exact shape that broke, and
    # any near-miss rewrite of it.
    numeric_floor = re.search(r"\$\{?count\}?\"?\s*-(?:ge|gt|lt|le|eq|ne)\s*\"?\d+", tests_code)
    check(
        "the tests step carries NO hardcoded numeric floor on the target count",
        numeric_floor is None,
        f"found {numeric_floor.group(0) if numeric_floor else ''!r} — the floor is the reviewed"
        f" list in {MANIFEST}, so removing a target takes an edit a reviewer can see (hub#1359)",
    )

for shipped in (RESOLVER, MANIFEST):
    check(
        f"`{shipped}` really exists in this checkout",
        os.path.isfile(os.path.join(os.environ["REPO_ROOT"], shipped)),
        "a workflow that calls a file nobody shipped fails at 3am, not at review time",
    )


# ── 3 · A module release notifies the hub, and the run SAYS which module ─────────────
dispatch = triggers.get("repository_dispatch")
check("the workflow accepts `repository_dispatch`", isinstance(dispatch, dict), f"got {dispatch!r}")
types = (dispatch or {}).get("types") or []
check(
    "`repository_dispatch.types` contains `module-published`",
    "module-published" in types,
    f"types are {types}",
)

run_name = str(doc.get("run-name", ""))
for field in ("module", "version"):
    check(
        f"`run-name` echoes `client_payload.{field}`",
        f"client_payload.{field}" in run_name,
        f"run-name is {run_name!r} — a run that does not name the module reads like"
        " every other nightly",
    )

summary = [
    s
    for s in steps
    if "GITHUB_STEP_SUMMARY" in str(s.get("run", ""))
    and "client_payload" in (str(s.get("run", "")) + dump(s.get("env") or {}))
]
check(
    "a step writes the dispatch payload into the job summary",
    len(summary) >= 1,
    "the payload has to survive into the run, not only into its title",
)

guard = [
    s
    for s in steps
    if "repository_dispatch" in str(s.get("if", "")) and "::error::" in str(s.get("run", ""))
]
check(
    "a dispatch with no `module` in the payload fails LOUDLY",
    len(guard) >= 1,
    "an empty payload would otherwise run as an anonymous nightly",
)


# ── 4 · The hard-won guards of hub#1216 stay put ─────────────────────────────────────
# These are not new: they are the regressions this file must never let back in.
cleanup = [s for s in steps if "RUNNER_TEMP/modules-workspace" in str(s.get("run", "")) and "rm -rf" in str(s.get("run", ""))]
check(
    "the runner cleanup step exists",
    len(cleanup) >= 1,
    "a job that leaves modules behind breaks its NEIGHBOUR on the shared runner (hub#1216)",
)
check(
    "the runner cleanup runs with `if: always()`",
    any(str(s.get("if", "")).strip() == "always()" for s in cleanup),
    "a cancelled run (cancel-in-progress fires daily) must still clean up",
)

# hub#1153: the clone loop, the floor and the loud per-module failure moved into
# `scripts/materialize-published-modules.sh`, which `.githooks/pre-push` runs too. Two copies of
# this logic is how the local gate ended up measuring against the PARKED `modules-workspace`
# checkout while this job measured the published catalogue — and copies of the same config drifting
# apart already cost `main` once (the Postgres image, hub#647). So the guard now asserts the SHARE,
# not the inline code.
MATERIALIZER = "scripts/materialize-published-modules.sh"


def code_of(step):
    """The step's shell, with the comments stripped.

    A `--floor 25` written in a COMMENT would keep these cases green while the real flag was
    gone — the same trap the alert lookup above dodges.
    """
    return "\n".join(
        l for l in str(step.get("run", "")).splitlines() if not l.lstrip().startswith("#")
    )


clone = [s for s in steps if MATERIALIZER in code_of(s)]
check(
    f"the catalogue is materialised by the shared `{MATERIALIZER}`",
    len(clone) >= 1,
    "a second copy of the clone logic is how the local gate and this job drifted apart (hub#1153)",
)
check(
    "the >=25 published manifests floor stays (`--floor 25`)",
    any("--floor 25" in code_of(s) for s in clone),
    "without it, a partial clone silently shrinks coverage instead of failing (hub#1216)",
)
check(
    "the materialiser is asked for the deploy-key bundle (`--keys`)",
    any("--keys" in code_of(s) for s in clone),
    "each module needs its own read-only key; the bundle is also the id source (hub#1216)",
)
# Resolved against the REPO, never against `--workflow`: the whole point of that flag is to run
# this guard over a mutated COPY living somewhere else.
check(
    f"`{MATERIALIZER}` really exists in this checkout",
    os.path.isfile(os.path.join(os.environ["REPO_ROOT"], MATERIALIZER)),
    "a workflow that calls a script nobody shipped fails at 3am, not at review time",
)

require = (job.get("env") or {}).get("ERPLORA_E2E_REQUIRE_MODULES")
check(
    "`ERPLORA_E2E_REQUIRE_MODULES` is set (missing modules are FATAL here)",
    str(require) == "1",
    f"got {require!r} — without it the e2e skip themselves and the job goes green empty",
)

# ── 5 · The module batteries are PAIRED with the e2e they inherit (hub#1381) ─────────
# hub#1264 moves module-owned e2e into each module's `erplora test` battery. On 2026-08-30 the
# coverage did not change place, it fell into a hole: hub#1372 deleted
# `services_package_redeem_e2e.rs` (391 lines this very job ran) and its replacement battery was
# run by NOBODY — `git grep against-hub` over `origin/develop` returned nothing, with both CIs
# green. This job already materialises the published catalogue, so it is the one place that can
# check, for free, that every retired e2e points at a battery that is really there.
BATTERY_GUARD = "scripts/ci/module-hub-batteries.sh"
BATTERY_LIST = "scripts/ci/module-hub-batteries.txt"

battery_step = [s_ for s_ in steps if s_.get("id") == "batteries"]
check(
    "a step with `id: batteries` guards the module battery list",
    len(battery_step) == 1,
    f"{len(battery_step)} steps carry that id",
)
if len(battery_step) == 1:
    battery_code = code_of(battery_step[0])
    check(
        f"the battery step runs `{BATTERY_GUARD}`",
        BATTERY_GUARD in battery_code,
        "the pairing has to be checked by the shipped guard, not re-inlined here",
    )
    check(
        "the battery step is not allowed to fail softly",
        battery_step[0].get("continue-on-error") in (None, False),
        "a guard that cannot fail the job is a comment",
    )
    # It reads the catalogue, so it can only run once the catalogue is on disk. Ordered by index
    # rather than by name: a rename of either step must not silently reorder the check.
    clone_idx = min(i for i, s_ in enumerate(steps) if MATERIALIZER in code_of(s_))
    battery_idx = steps.index(battery_step[0])
    check(
        "the battery step runs AFTER the catalogue is materialised",
        battery_idx > clone_idx,
        f"battery step at {battery_idx}, materialiser at {clone_idx}",
    )

for shipped in (BATTERY_GUARD, BATTERY_LIST):
    check(
        f"`{shipped}` really exists in this checkout",
        os.path.isfile(os.path.join(os.environ["REPO_ROOT"], shipped)),
        "a workflow that calls a file nobody shipped fails at 3am, not at review time",
    )

# A module publishing or withdrawing a battery breaks this guard on the CRON and on the
# `module-published` dispatch — where nobody is watching. That is the exact mute red hub#1215 sat
# in for a whole day, so it gets the same idempotent alert as the suite next to it.
BATTERY_ALERT_TITLE = "La lista de baterías de módulo no cuadra con el catálogo publicado"
battery_alert = [s_ for s_ in steps if BATTERY_ALERT_TITLE in str(s_.get("run", ""))]
check(
    f"a step opens the battery alert issue titled «{BATTERY_ALERT_TITLE}»",
    len(battery_alert) == 1,
    f"{len(battery_alert)} steps mention it",
)
check(
    "the battery alert title carries no colon (colons are GitHub search syntax)",
    ":" not in BATTERY_ALERT_TITLE,
    BATTERY_ALERT_TITLE,
)
if len(battery_alert) == 1:
    b_run = str(battery_alert[0].get("run", ""))
    b_cond = str(battery_alert[0].get("if", ""))
    b_code = "\n".join(l for l in b_run.splitlines() if not l.lstrip().startswith("#"))
    check(
        "the battery alert delegates to the shared scripts/ci/alert-issue.sh",
        "./scripts/ci/alert-issue.sh" in b_code,
        "a fourth copy of the list-and-filter logic is how they drift apart (hub#1246)",
    )
    check(
        "the battery alert never inlines `--search`",
        "--search" not in b_code,
        "GitHub's search index lags behind reality (hub#1246)",
    )
    check(
        "the battery alert is gated on the GUARD step's own outcome",
        "steps.batteries.outcome == 'failure'" in b_cond,
        f"if: {b_cond!r} — an environmental failure must not fake a pairing verdict",
    )
    check(
        "the battery alert never fires on a `pull_request`",
        "pull_request" not in b_cond,
        f"if: {b_cond!r}",
    )
    for event in ("schedule", "repository_dispatch", "push"):
        check(
            f"the battery alert fires for `{event}` (nobody watches it otherwise)",
            event in b_cond,
            f"if: {b_cond!r}",
        )
    check(
        "the battery alert carries a token",
        "GH_TOKEN" in (battery_alert[0].get("env") or {}),
        f"env is {battery_alert[0].get('env')}",
    )
    check(
        "the battery alert quotes the guard's own verdict, not just the run URL",
        "VERDICT" in b_run,
        "an alert that does not say WHICH battery broke sends the reader back to the log",
    )


# ── 6 · The batteries are RUN, not just counted (hub#1381) ───────────────────────────
# Section 5 proves a battery EXISTS where the slice promised. That is half a guard: a battery
# nobody executes is documentation. `services/tests/package_redeem.hub.test.py` inherited 391
# lines of coverage on 2026-08-30 and was run by nobody for four days, both CIs green — the
# module gate reports a hub battery as `⚠ … no se ha corrido` and passes anyway.
#
# The runner boots the server built FROM THIS REF (not a published image) with the published
# catalogue in `HUB_MODULES_DIR`, one hub per module, and runs each battery against it. That is
# also what makes the run mean what this workflow claims: the kernel under test against the
# modules as published.
RUNNER = "scripts/ci/run-module-hub-batteries.sh"

runner_step = [s_ for s_ in steps if s_.get("id") == "run-batteries"]
check(
    "a step with `id: run-batteries` RUNS the module batteries",
    len(runner_step) == 1,
    f"{len(runner_step)} steps carry that id — a list that is never executed is a comment",
)
if len(runner_step) == 1:
    runner_code = code_of(runner_step[0])
    check(
        f"the runner step runs `{RUNNER}`",
        RUNNER in runner_code,
        "the batteries have to be run by the shipped runner, not re-inlined here",
    )
    check(
        "the runner step is not allowed to fail softly",
        runner_step[0].get("continue-on-error") in (None, False),
        "a runner that cannot fail the job is exactly the `⚠ … no se ha corrido` it replaces",
    )
    # It needs the catalogue on disk, the pairing verdict, and a server binary — in that order.
    clone_idx = min(i for i, s_ in enumerate(steps) if MATERIALIZER in code_of(s_))
    runner_idx = steps.index(runner_step[0])
    check(
        "the runner step runs AFTER the catalogue is materialised",
        runner_idx > clone_idx,
        f"runner step at {runner_idx}, materialiser at {clone_idx}",
    )
    if len(battery_step) == 1:
        check(
            "the runner step runs AFTER the pairing guard",
            runner_idx > steps.index(battery_step[0]),
            "running a list that already lost a battery buries the verdict that says so",
        )
    build_idx = [
        i for i, s_ in enumerate(steps) if "cargo build -p erplora-server" in code_of(s_)
    ]
    check(
        "some step builds `erplora-server` for the runner",
        bool(build_idx),
        "the batteries talk HTTP to a live kernel; without the binary there is nothing to talk to",
    )
    if build_idx:
        check(
            "the server is built BEFORE the batteries are run",
            runner_idx > min(build_idx),
            f"runner step at {runner_idx}, build at {min(build_idx)}",
        )
    check(
        "the runner is handed the published catalogue, not a checkout of modules-workspace",
        "ERPLORA_MODULES_DIR" in runner_code or "--catalogue" in runner_code,
        "a runner pointed at the working tree measures something nobody ships",
    )

check(
    f"`{RUNNER}` really exists in this checkout",
    os.path.isfile(os.path.join(os.environ["REPO_ROOT"], RUNNER)),
    "a workflow that calls a file nobody shipped fails at 3am, not at review time",
)

# Same mute-red problem as its two neighbours: a battery breaking on the cron or on a module's
# `module-published` dispatch has nobody watching.
RUNNER_ALERT_TITLE = "Las baterías de módulo del catálogo publicado NO pasan contra el kernel"
runner_alert = [s_ for s_ in steps if RUNNER_ALERT_TITLE in str(s_.get("run", ""))]
check(
    f"a step opens the runner alert issue titled «{RUNNER_ALERT_TITLE}»",
    len(runner_alert) == 1,
    f"{len(runner_alert)} steps mention it",
)
check(
    "the runner alert title carries no colon (colons are GitHub search syntax)",
    ":" not in RUNNER_ALERT_TITLE,
    RUNNER_ALERT_TITLE,
)
if len(runner_alert) == 1:
    r_run = str(runner_alert[0].get("run", ""))
    r_cond = str(runner_alert[0].get("if", ""))
    r_code = "\n".join(l for l in r_run.splitlines() if not l.lstrip().startswith("#"))
    check(
        "the runner alert delegates to the shared scripts/ci/alert-issue.sh",
        "./scripts/ci/alert-issue.sh" in r_code,
        "a fifth copy of the list-and-filter logic is how they drift apart (hub#1246)",
    )
    check(
        "the runner alert never inlines `--search`",
        "--search" not in r_code,
        "GitHub's search index lags behind reality (hub#1246)",
    )
    check(
        "the runner alert is gated on the RUNNER step's own outcome",
        "steps.run-batteries.outcome == 'failure'" in r_cond,
        f"if: {r_cond!r} — a failure elsewhere must not fake a battery verdict",
    )
    check(
        "the runner alert never fires on a `pull_request`",
        "pull_request" not in r_cond,
        f"if: {r_cond!r}",
    )
    for event in ("schedule", "repository_dispatch", "push"):
        check(
            f"the runner alert fires for `{event}` (nobody watches it otherwise)",
            event in r_cond,
            f"if: {r_cond!r}",
        )
    check(
        "the runner alert carries a token",
        "GH_TOKEN" in (runner_alert[0].get("env") or {}),
        f"env is {runner_alert[0].get('env')}",
    )
    check(
        "the runner alert quotes the runner's own verdict, not just the run URL",
        "VERDICT" in r_run,
        "an alert that does not say WHICH battery broke sends the reader back to the log",
    )


if failures:
    print(f"FAIL: {len(failures)} contract case(s) on {path}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: {passed} test-hub-modules workflow contract cases")
PY
