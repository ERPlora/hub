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
pr = triggers.get("pull_request")
check("the workflow runs on `pull_request`", isinstance(pr, dict), f"got {pr!r}")
pr_paths = (pr or {}).get("paths") or []
for wanted in REQUIRED_PATHS:
    check(
        f"`on.pull_request.paths` covers `{wanted}`",
        wanted in pr_paths,
        f"paths are {pr_paths}",
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
        "the alert is idempotent (searches for the open issue before creating one)",
        "gh issue list" in run and "gh issue comment" in run and "gh issue create" in run,
        "it must reuse the open issue, never open one per run",
    )
    check(
        "the alert search phrase carries no colon (colons are GitHub search syntax)",
        ":" not in ALERT_TITLE,
        ALERT_TITLE,
    )
    # Review of hub#1245: `gh issue list --search` reads GitHub's SEARCH index, which lags
    # behind reality (it returned zero with open issues on 2026-08-16). Two failures minutes
    # apart — push develop then push main, two module releases — would open two issues, which
    # is the opposite of idempotent. The lookup must list the open issues and match the title
    # locally.
    code = "\n".join(l for l in run.splitlines() if not l.lstrip().startswith("#"))
    check(
        "the alert looks the open issue up by LISTING and filtering locally, never `--search`",
        "--search" not in code and "--json number,title" in code and "select(.title ==" in code,
        "GitHub's search index lags: two failures minutes apart would open two issues",
    )
    # Review of hub#1245: the tests step can die BEFORE `tee` creates the log (the `>= 30
    # targets` guard, the grep pipeline). awk on an absent file exits 2, `set -euo pipefail`
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

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on {path}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: {passed} test-hub-modules workflow contract cases")
PY
