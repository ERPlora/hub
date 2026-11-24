#!/usr/bin/env bash
# Tests of the workflows' shape (deploy.yml, test.yml, ci.yml, rollback.yml): one push run of a branch
# at a time, its tests and image build side by side, and a rollback waits only for a deploy.
#   bash .github/scripts/workflows.test.sh
# Needs python3 with PyYAML (preinstalled on GitHub's ubuntu runners and on macOS).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"

python3 - "$here/../workflows" <<'PYEOF'
import pathlib
import sys

import yaml

folder = pathlib.Path(sys.argv[1])
deploy, test, ci, rollback = (
    yaml.safe_load((folder / f"{name}.yml").read_text()) for name in ("deploy", "test", "ci", "rollback")
)
failures = 0


def check(name, ok):
    global failures
    print(("ok   - " if ok else "FAIL - ") + name)
    failures += not ok


def needs(job):
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


def steps(job):
    return job.get("steps", [])


def runs(job):
    return "\n".join(str(step.get("run", "")) for step in steps(job))


def index_of(job, needle):
    """The index of the first step whose `run` or `uses` contains needle, or None."""
    for index, step in enumerate(steps(job)):
        if needle in str(step.get("run", "")) or needle in str(step.get("uses", "")):
            return index
    return None


def before(job, first, second):
    a, b = index_of(job, first), index_of(job, second)
    return a is not None and b is not None and a < b


GROUP = "deploy-${{ github.repository }}-${{ github.ref_name }}"
# The push runs of a branch; a manual run (a release redeploy) is a group of its own.
PUSHES = "${{ github.event_name == 'push' && format('deploy-push-{0}-{1}', github.repository, github.ref_name) || github.run_id }}"
jobs = deploy.get("jobs", {})
build, deploy_job = jobs.get("build", {}), jobs.get("deploy", {})
deploy_if, build_if = str(deploy_job.get("if", "")), str(build.get("if", ""))

# --- deploy.yml: one push run of a branch at a time; a rollback waits only for a deploy ---------
# Compared whole: `queue: max` would keep every push waiting, and cancelling would cut a deploy halfway.
check("a push run waits for the one before it of its branch, and a newer push replaces the one waiting",
      deploy.get("concurrency") == {"group": PUSHES, "cancel-in-progress": False})
check("only the deploy job holds a lock", [name for name, job in jobs.items() if "concurrency" in job] == ["deploy"])
check("the deploy job holds the deploy lock of its branch and never cancels a deploy in progress",
      deploy_job.get("concurrency") == {"group": GROUP, "cancel-in-progress": False})
check("rollback.yml shares the deploy lock", (rollback.get("concurrency") or {}).get("group") == GROUP)

# --- deploy.yml: tests and image build side by side ----------------------------------------------
check("deploy.yml has the jobs test, build and deploy", {"test", "build", "deploy"} <= set(jobs))
check("test runs test.yml", jobs.get("test", {}).get("uses") == "./.github/workflows/test.yml")
check("build does not wait for test", "test" not in needs(build))
check("deploy needs test and build", {"test", "build"} <= set(needs(deploy_job)))
check("deploy requires test to succeed", "needs.test.result == 'success'" in deploy_if)
check("deploy requires build to succeed", "needs.build.result == 'success'" in deploy_if)
check("a release redeploy goes on with test and build skipped",
      "inputs.release != ''" in deploy_if and "needs.build.result == 'skipped'" in deploy_if)
check("a release redeploy builds nothing", "inputs.release == ''" in build_if)
check("the deploy job builds nothing",
      "buildx" not in runs(deploy_job) and index_of(deploy_job, "build-push-action") is None)
check("build caches its layers in GitHub's cache",
      any("type=gha" in str((step.get("with") or {}).get("cache-from", ""))
          and "type=gha,mode=max" in str((step.get("with") or {}).get("cache-to", ""))
          for step in steps(build) if "build-push-action" in str(step.get("uses", ""))))
check("build tests the image before it pushes it", before(build, "docker/image.test.sh", "docker push"))
check("the deploy never moves the environment back to an older commit",
      before(deploy_job, "deploy-order.sh", "scripts/ecs_deploy.py"))
check("the workflow only reads", deploy.get("permissions") == {"contents": "read"})

# --- deploy.yml: the settings of deploy/app-env.json and the confirmation of a protected one ------
# PyYAML reads the key `on` as true (YAML 1.1).
dispatch = (deploy.get("on") or deploy.get(True) or {}).get("workflow_dispatch") or {}
confirm_input = (dispatch.get("inputs") or {}).get("confirm_protected") or {}
check("a manual deploy takes the confirmation of a protected setting, empty by default",
      confirm_input.get("type") == "string" and confirm_input.get("default") == ""
      and confirm_input.get("required") is False)
ecs_step = next((step for step in steps(deploy_job) if "scripts/ecs_deploy.py" in str(step.get("run", ""))), {})
check("the deploy runs python3 scripts/ecs_deploy.py with the confirmation in its environment, never inline",
      (ecs_step.get("env") or {}).get("CONFIRM_PROTECTED") == "${{ inputs.confirm_protected }}"
      and str(ecs_step.get("run", "")).split() == ["python3", "scripts/ecs_deploy.py"])
checkout = next((step for step in steps(deploy_job) if "actions/checkout" in str(step.get("uses", ""))), {})
check("the deploy checks out the whole history: it reads deploy/app-env.json of the commit it deploys",
      (checkout.get("with") or {}).get("fetch-depth") == 0)

# --- rollback.yml: the same confirmation as a deploy -------------------------------------------
rollback_dispatch = (rollback.get("on") or rollback.get(True) or {}).get("workflow_dispatch") or {}
rollback_confirm = (rollback_dispatch.get("inputs") or {}).get("confirm_protected") or {}
check("a rollback takes the confirmation of a protected setting, empty by default",
      rollback_confirm.get("type") == "string" and rollback_confirm.get("default") == ""
      and rollback_confirm.get("required") is False)
rollback_job = (rollback.get("jobs") or {}).get("rollback", {})
rollback_step = next((step for step in steps(rollback_job) if "ecs_rollback.py" in str(step.get("run", ""))), {})
check("the rollback runs python3 scripts/ecs_rollback.py with the confirmation in its environment, never inline",
      (rollback_step.get("env") or {}).get("CONFIRM_PROTECTED") == "${{ inputs.confirm_protected }}"
      and str(rollback_step.get("run", "")).split() == ["python3", "scripts/ecs_rollback.py"])
check("only build and deploy get an OIDC token",
      sorted(name for name, job in jobs.items() if (job.get("permissions") or {}).get("id-token") == "write")
      == ["build", "deploy"])

# --- test.yml: four independent jobs behind the required check "test / test" -------------------
tjobs = test.get("jobs", {})
TEST_JOBS = ("python", "frontend", "scripts", "smoke")
check("test.yml has the jobs python, frontend, scripts, smoke and test", {*TEST_JOBS, "test"} <= set(tjobs))
check("python, frontend, scripts and smoke wait for nothing", all(not needs(tjobs.get(name, {})) for name in TEST_JOBS))
check("test (the required check) needs python, frontend, scripts and smoke",
      set(needs(tjobs.get("test", {}))) == set(TEST_JOBS))
check("test reports even when a job fails or is cancelled", str(tjobs.get("test", {}).get("if", "")) == "always()")
# A red shard of python's matrix (or a red job) only turns "test / test" red if test reads every job's result and
# nothing turns a failure into a pass on the way: no continue-on-error, on a job or on a step (hub#1185).
test_results = "\n".join(str((step.get("env") or {}).get("RESULTS", "")) for step in steps(tjobs.get("test", {})))
check("test reads the result of python (every shard), frontend, scripts and smoke",
      all(f"{name}=${{{{ needs.{name}.result }}}}" in test_results for name in TEST_JOBS))
check("no job or step of test.yml continues on error, so no red shard is hidden",
      not any("continue-on-error" in job or any("continue-on-error" in step for step in steps(job))
              for job in tjobs.values()))
python_runs, frontend_runs, scripts_runs = (runs(tjobs.get(name, {})) for name in ("python", "frontend", "scripts"))
check("python runs pytest over a Postgres service",
      "pytest" in python_runs and "postgres" in (tjobs.get("python", {}).get("services") or {}))
check("pytest runs in parallel (pytest-xdist)", "pytest" in python_runs and " -n " in python_runs)
# Before pytest, beside the Hub: the SaaS's signed declaration (apps/verifactu/tests/test_producer.py) and the shared
# image library, where config/settings/web.py looks for it (CATALOG_DIR; base/tests/test_seed_images.py).
for clone in ("ERPlora/saas ../saas public/declaracion", "ERPlora/blueprints ../blueprints img"):
    check(f"python clones {clone} before pytest", before(tjobs.get("python", {}), f"clone-repo.sh {clone}", "pytest"))
# WeasyPrint's libraries are installed without Ubuntu's mirror (hub#1222: a DNS outage of the mirror kept every run red
# for hours, and retries alone would spend minutes the python job does not have): their .deb files come from GitHub's
# cache, one entry per runner image and per test.yml, through apt-install.sh, which only goes to the mirror without
# them and retries it then. The cache is saved right after the download, not at the end of the job: the end only saves
# when every test passes, and other runs would miss it for the minutes of pytest.
python_steps = steps(tjobs.get("python", {}))
weasyprint = next((step for step in python_steps if step.get("name") == "WeasyPrint's libraries"), {})
weasyprint_run = str(weasyprint.get("run", "")).split()
check("WeasyPrint's libraries are installed with apt-install.sh",
      weasyprint_run[:2] == ["bash", ".github/scripts/apt-install.sh"] and len(weasyprint_run) > 3
      and "apt-get" not in weasyprint_run)
archives = weasyprint_run[2] if len(weasyprint_run) > 2 else None


def cache_step(action):
    """The step of python that runs actions/cache/<action> over the install's archives, or None."""
    return next((step for step in python_steps if str(step.get("uses", "")).startswith(f"actions/cache/{action}@")
                 and (step.get("with") or {}).get("path") == archives), None)


apt_restore, apt_save = cache_step("restore"), cache_step("save")
check("their archives are restored from GitHub's cache before the install",
      apt_restore is not None and python_steps.index(apt_restore) < python_steps.index(weasyprint))
check("and saved right after it, under the same key, only when the cache missed",
      apt_save is not None and apt_restore is not None and python_steps.index(apt_save) == python_steps.index(weasyprint) + 1
      and (apt_save.get("with") or {}).get("key") == f"${{{{ steps.{apt_restore.get('id')}.outputs.cache-primary-key }}}}"
      and str(apt_save.get("if", "")) == f"steps.{apt_restore.get('id')}.outputs.cache-hit != 'true'")
apt_key = str(((apt_restore or {}).get("with") or {}).get("key", ""))
image = next((step for step in python_steps if step.get("id") and f"steps.{step['id']}.outputs." in apt_key), None)
check("the cache keeps one entry per runner image and per test.yml (where the package list lives)",
      image is not None and apt_restore is not None and python_steps.index(image) < python_steps.index(apt_restore)
      and all(name in str(image.get("run", "")) for name in ("$ImageOS", "$ImageVersion"))
      and "hashFiles('.github/workflows/test.yml')" in apt_key)
# pytest is spread over a matrix of shards (hub#1185): a single job ran the whole suite, which grows every day, and
# GitHub's runners take from 18 to 29 min on the same commit, so a slow one hit the job's 30 minutes and turned PRs and
# main's deploy red without a failing test. Each shard runs its share through pytest-shard.sh with the index and total
# GitHub gives the job (strategy.job-index, strategy.job-total), so the shards cover the whole suite whatever the size
# of the matrix; a failing shard cancels none of the others, so every failure shows; and the job's timeout stays where
# it was, with a warning from the shard before it gets near.
python_job = tjobs.get("python", {})
strategy = python_job.get("strategy") or {}
matrix = strategy.get("matrix") or {}
shards = matrix.get("shard")
check("python runs as a matrix of at least 2 shards, named 1 to N, and nothing else",
      isinstance(shards, list) and len(shards) >= 2 and shards == list(range(1, len(shards) + 1)) and set(matrix) == {"shard"})
check("a failing shard cancels none of the others (fail-fast: false)", strategy.get("fail-fast") is False)
check("the python job keeps its 30-minute timeout", python_job.get("timeout-minutes") == 30)
shard_step = next((step for step in python_steps if "pytest-shard.sh" in str(step.get("run", ""))), {})
shard_env = shard_step.get("env") or {}
shard_run = [shard_env.get(word.strip('"')[1:], word) if word.strip('"').startswith("$") else word
             for word in str(shard_step.get("run", "")).split()]
check("pytest runs through pytest-shard.sh with the job's index and total in the matrix",
      shard_run[:4] == ["bash", ".github/scripts/pytest-shard.sh", "${{ strategy.job-index }}", "${{ strategy.job-total }}"])
warn_minutes = shard_run[4] if len(shard_run) > 4 else ""
check("the shard warns before the job's timeout, with room to add a shard",
      warn_minutes.isdigit() and 0 < int(warn_minutes) <= python_job.get("timeout-minutes", 0) * 2 // 3)
check("each shard runs pytest in parallel (pytest-xdist)", " -n " in " ".join(shard_run[5:]) + " ")
check("pytest runs only through pytest-shard.sh", "pytest " not in python_runs.replace(str(shard_step.get("run")), ""))
lock = (folder.resolve().parent.parent / "uv.lock").read_text()
check("pytest-split, which pytest-shard.sh runs, is locked in uv.lock", '\nname = "pytest-split"\n' in lock)
# tests/test_guardrails_size.py compares the size allow list with the one where the branch left origin/main, and fails
# when origin/main is not there: a shallow checkout has neither that branch nor the history to find the point.
python_checkout = next((step for step in python_steps if "actions/checkout" in str(step.get("uses", ""))), {})
check("the python job checks out the whole history, origin/main included (fetch-depth: 0)",
      (python_checkout.get("with") or {}).get("fetch-depth") == 0)
check("frontend runs lint, typecheck, Vitest and the build",
      all(f"pnpm {task}" in frontend_runs for task in ("lint", "typecheck", "test", "build")))
# Vitest checks the scripts the e2e runs inside the SaaS against the SaaS of main (tests/e2e/saas-names.ts), so the SaaS
# is beside the Hub, with its live submodule and its dependencies, before Vitest.
frontend_job = tjobs.get("frontend", {})
for setup in ("clone-repo.sh ERPlora/saas ../saas", "submodule update --init", "uv sync --locked --directory ../saas"):
    check(f"frontend runs {setup} before Vitest", before(frontend_job, setup, "pnpm test"))
check("scripts runs actionlint, shellcheck and the script tests",
      all(needle in scripts_runs for needle in ("actionlint", "shellcheck", ".test.sh")))
# A passing error of GitHub (a 5xx, a cut connection) while the CI fetches a tool is retried instead of turning a PR
# red (hub#830): actionlint comes through download-tool.sh, which retries and checks the pin, and no workflow calls a
# curl that gives up at the first error.
actionlint_step = next((step for step in steps(tjobs.get("scripts", {})) if "actionlint" in str(step.get("run", ""))), {})
check("actionlint is downloaded with download-tool.sh",
      "bash .github/scripts/download-tool.sh" in str(actionlint_step.get("run", "")))
all_steps = [(path.name, job, step) for path in sorted(folder.glob("*.yml"))
             for job in (yaml.safe_load(path.read_text()).get("jobs") or {}).values() for step in steps(job)]


def listed(found):
    """The steps found, as "<workflow>: <step>", after a colon, or nothing."""
    return (": " if found else "") + ", ".join(f"{name}: {step.get('name') or str(step.get('run'))[:40]!r}"
                                               for name, _, step in found)


bare_curls = [(name, job, step) for name, job, step in all_steps
              if "curl " in str(step.get("run", "")) and "--retry-all-errors" not in str(step.get("run", ""))]
check("every curl of the workflows retries a passing error (--retry-all-errors)" + listed(bare_curls), not bare_curls)
# GitHub limits anonymous clones from its shared runners and refuses them with a 403, which turned PRs red: every
# clone goes through clone-repo.sh, which sends the job's token and retries a failed attempt; that token only reads.
bare_clones = [found for found in all_steps if "git clone" in str(found[2].get("run", ""))]
check("no workflow runs git clone itself: clones go through clone-repo.sh" + listed(bare_clones), not bare_clones)
clones = [found for found in all_steps if "clone-repo.sh" in str(found[2].get("run", ""))]
anonymous = [found for found in clones if (found[2].get("env") or {}).get("GH_TOKEN") != "${{ github.token }}"]
check("every clone goes as the job's token (GH_TOKEN: ${{ github.token }})" + listed(anonymous), bool(clones) and not anonymous)
writers = [found for found in clones if found[1].get("permissions") != {"contents": "read"}]
check("and that token only reads (the job's permissions: contents: read)" + listed(writers), not writers)
setup_uv = [step for job in tjobs.values() for step in steps(job) if "astral-sh/setup-uv" in str(step.get("uses", ""))]
check("setup-uv is used", bool(setup_uv))
check("setup-uv caches by uv.lock",
      bool(setup_uv) and all(str((step.get("with") or {}).get("enable-cache")).lower() == "true"
                             and (step.get("with") or {}).get("cache-dependency-glob") == "uv.lock"
                             for step in setup_uv))

# --- test.yml: the browser smoke stops the merge ----------------------------------------------------
# A change that breaks a critical walk in the browser turns "test / test" red: the job smoke runs smoke-e2e.sh (the
# tests tagged @smoke, narrowed with --spec while the groups enter one at a time) on the stack nightly_e2e.py builds,
# with the SaaS beside the Hub because every login goes through erplora.com.
smoke_job = tjobs.get("smoke", {})
smoke_runs = runs(smoke_job)
smoke_step = next((step for step in steps(smoke_job) if "smoke-e2e.sh" in str(step.get("run", ""))), {})
smoke_words = str(smoke_step.get("run", "")).split()
check("smoke runs the browser smoke with smoke-e2e.sh", smoke_words[:2] == ["bash", ".github/scripts/smoke-e2e.sh"])
check("smoke runs Playwright only through smoke-e2e.sh",
      not any(needle in smoke_runs for needle in ("pnpm e2e", "playwright", "nightly_e2e.py")))
smoke_specs = [smoke_words[index + 1] for index, word in enumerate(smoke_words[:-1]) if word == "--spec"]
check("smoke's step is that command and its --spec, with nothing after them that could hide a red (as `|| true`)",
      smoke_words[2:] == [word for spec in smoke_specs for word in ("--spec", spec)])
# The groups that already stop the merge, with their specs: a spec dropped from the job, or one named outside them,
# turns this red. A group that enters adds its specs here and to the job in the same change.
SMOKE_GROUPS = {
    "signing in, sessions, permissions, isolation and suspension": ("login-and-shell", "base-access", "base-sign-out",
        "base-session-revoke", "employee-permissions", "two-orgs-isolated", "hub-suspended"),
    "charging and the cash register": ("sale-pos", "sale-cash-gate", "cash-register-shift", "printing-sale"),
    "the ticket's QR, the invoice and VeriFactu": ("sale-fiscal-qr", "sale-invoice-chain", "invoice-sale",
                                                    "invoice-manual", "verifactu-records"),
    "the kitchen and the tables": ("kitchen-pos", "sale-table", "table-floor"),
    "appointments, services and vouchers": ("appointment-agenda", "appointment-charge", "service-catalog",
                                            "service-vouchers", "sale-voucher"),
    "sign-up, apps, the demo and live updates": ("base-sign-up-taxes-on", "base-app-activation", "demo", "two-tabs-live"),
}
grouped = []
for group, names in SMOKE_GROUPS.items():
    specs = [f"tests/e2e/{name}.spec.ts" for name in names]
    grouped += specs
    missing = ", ".join(spec for spec in specs if spec not in smoke_specs)
    check(f"smoke runs every spec of the group «{group}»{': missing ' if missing else ''}{missing}", not missing)
ungrouped = [spec for spec in smoke_specs if spec not in grouped]
check(f"smoke names no spec outside those groups{': ' if ungrouped else ''}" + ", ".join(ungrouped), not ungrouped)
repo = folder.resolve().parent.parent
unsmoked = [spec for spec in smoke_specs if not (repo / spec).is_file() or "@smoke" not in (repo / spec).read_text()]
check(f"every spec the smoke names exists and has a test tagged @smoke{': ' if unsmoked else ''}" + ", ".join(unsmoked),
      not unsmoked)
check("smoke has a timeout of its own, in whole minutes",
      isinstance(smoke_job.get("timeout-minutes"), int) and smoke_job.get("timeout-minutes") > 0)
# The specs reach the stack's Postgres with `docker compose exec` (tests/e2e/global-setup.ts), and nightly_e2e.py takes
# the SaaS from ../saas, as in the erplora-next tree.
check("smoke starts Postgres with docker compose before the smoke", before(smoke_job, "docker compose", "smoke-e2e.sh"))
check("smoke clones ERPlora/saas into ../saas before the smoke",
      before(smoke_job, "clone-repo.sh ERPlora/saas ../saas", "smoke-e2e.sh"))
uploads = [step for step in steps(smoke_job) if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
smoke_dir = str((smoke_step.get("env") or {}).get("NIGHTLY_DIR", ""))
check("a red smoke keeps the run's log and Playwright's traces (NIGHTLY_DIR/runs/)",
      bool(smoke_dir) and any(str(step.get("if", "")) == "failure()"
                              and (step.get("with") or {}).get("path") == f"{smoke_dir}/runs/" for step in uploads))

# --- ci.yml: a newer push supersedes the run of the older one -----------------------------------
check("ci.yml runs test.yml", (ci.get("jobs", {}).get("test") or {}).get("uses") == "./.github/workflows/test.yml")
ci_lock = ci.get("concurrency") or {}
check("ci.yml cancels the run of an older push to the same branch",
      ci_lock.get("group") == "ci-${{ github.repository }}-${{ github.ref_name }}"
      and ci_lock.get("cancel-in-progress") is True)

print()
if failures:
    print(f"{failures} test(s) failed")
    sys.exit(1)
print("all tests passed")
PYEOF
