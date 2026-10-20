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
check("frontend runs lint, typecheck, Vitest and the build",
      all(f"pnpm {task}" in frontend_runs for task in ("lint", "typecheck", "test", "build")))
check("scripts runs actionlint, shellcheck and the script tests",
      all(needle in scripts_runs for needle in ("actionlint", "shellcheck", ".test.sh")))
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
