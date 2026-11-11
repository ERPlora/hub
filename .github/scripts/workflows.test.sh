#!/usr/bin/env bash
# Tests of the workflows' shape (deploy.yml, test.yml, ci.yml, rollback.yml): the tests and the
# image build run side by side, and only the deploy itself waits for the one before.
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
jobs = deploy.get("jobs", {})
build, deploy_job = jobs.get("build", {}), jobs.get("deploy", {})
deploy_if, build_if = str(deploy_job.get("if", "")), str(build.get("if", ""))

# --- deploy.yml: only the deploy waits for the one before ---------------------------------------
check("deploy.yml has no workflow-level concurrency", "concurrency" not in deploy)
check("only the deploy job holds a lock", [name for name, job in jobs.items() if "concurrency" in job] == ["deploy"])
lock = deploy_job.get("concurrency") or {}
check("the deploy job holds the deploy lock of its branch", lock.get("group") == GROUP)
check("a deploy in progress is never cancelled", lock.get("cancel-in-progress") is False)
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
      before(deploy_job, "deploy-order.sh", "ecs-deploy.sh"))
check("the workflow only reads", deploy.get("permissions") == {"contents": "read"})
check("only build and deploy get an OIDC token",
      sorted(name for name, job in jobs.items() if (job.get("permissions") or {}).get("id-token") == "write")
      == ["build", "deploy"])

# --- test.yml: three independent jobs behind the required check "test / test" ------------------
tjobs = test.get("jobs", {})
check("test.yml has the jobs python, frontend, scripts and test",
      {"python", "frontend", "scripts", "test"} <= set(tjobs))
check("python, frontend and scripts wait for nothing",
      all(not needs(tjobs.get(name, {})) for name in ("python", "frontend", "scripts")))
check("test (the required check) needs the three jobs",
      set(needs(tjobs.get("test", {}))) == {"python", "frontend", "scripts"})
check("test reports even when a job fails or is cancelled", str(tjobs.get("test", {}).get("if", "")) == "always()")
python_runs, frontend_runs, scripts_runs = (runs(tjobs.get(name, {})) for name in ("python", "frontend", "scripts"))
check("python runs pytest over a Postgres service",
      "pytest" in python_runs and "postgres" in (tjobs.get("python", {}).get("services") or {}))
check("pytest runs in parallel (pytest-xdist)", "pytest" in python_runs and " -n " in python_runs)
# The seeds' images are checked against the shared library's manifest (base/tests/test_seed_images.py): ERPlora/blueprints
# is public and fetched beside the Hub, where config/settings.py looks for it (CATALOG_DIR), before pytest runs.
check("python fetches ERPlora/blueprints into ../blueprints before pytest",
      "ERPlora/blueprints.git ../blueprints" in python_runs
      and python_runs.index("ERPlora/blueprints.git") < python_runs.index("pytest"))
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
check("frontend runs lint, typecheck, Vitest and the build",
      all(f"pnpm {task}" in frontend_runs for task in ("lint", "typecheck", "test", "build")))
check("scripts runs actionlint, shellcheck and the script tests",
      all(needle in scripts_runs for needle in ("actionlint", "shellcheck", ".test.sh")))
# A passing error of GitHub (a 5xx, a cut connection) while the CI fetches a tool is retried instead of turning a PR
# red (hub#830): actionlint comes through download-tool.sh, which retries and checks the pin, and no workflow calls a
# curl that gives up at the first error.
actionlint_step = next((step for step in steps(tjobs.get("scripts", {})) if "actionlint" in str(step.get("run", ""))), {})
check("actionlint is downloaded with download-tool.sh",
      "bash .github/scripts/download-tool.sh" in str(actionlint_step.get("run", "")))
bare_curls = [
    f"{path.name}: {step.get('name') or str(step.get('run'))[:40]!r}"
    for path in sorted(folder.glob("*.yml"))
    for job in (yaml.safe_load(path.read_text()).get("jobs") or {}).values()
    for step in steps(job)
    if "curl " in str(step.get("run", "")) and "--retry-all-errors" not in str(step.get("run", ""))
]
check(f"every curl of the workflows retries a passing error (--retry-all-errors){': ' if bare_curls else ''}"
      + ", ".join(bare_curls), not bare_curls)
setup_uv = [step for job in tjobs.values() for step in steps(job) if "astral-sh/setup-uv" in str(step.get("uses", ""))]
check("setup-uv is used", bool(setup_uv))
check("setup-uv caches by uv.lock",
      bool(setup_uv) and all(str((step.get("with") or {}).get("enable-cache")).lower() == "true"
                             and (step.get("with") or {}).get("cache-dependency-glob") == "uv.lock"
                             for step in setup_uv))

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
