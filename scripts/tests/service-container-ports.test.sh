#!/usr/bin/env bash
# Contract test: no service container in this repo's workflows pins a HOST port.
#
# Regression test for ERPlora/hub#1433 — the guard hub#898 fixed the workflows without leaving.
# Ported from ERPlora/saas#1790, where the same incident came back for lack of it.
#
# `ci-runner-1` is ONE machine with several slots and a SINGLE Docker daemon, shared by the whole
# organization. A fixed host port in a `services:` block (`ports: - 5432:5432`) is grabbed by
# whichever job starts first; the next one dies ~2 s into "Initialize containers" with
#
#     Bind for 0.0.0.0:5432 failed: port is already allocated
#     ##[error]Docker start fail with exit code 1
#
# — BEFORE running a single step, so there is no `FAILED` line to search for and the run looks
# like an infrastructure hiccup. Publishing only the CONTAINER port lets Docker pick a free host
# port per job, and `job.services.<id>.ports['<container port>']` reports the one it picked.
#
# Why a guard and not just the fix: hub#898 fixed the five workflows here file by file and left
# nothing behind to hold the rule. The saas then re-staged the identical failure — three deploys
# to PRE blocked in 21 h (runs 33496481985, 33599084755, 33600703937), because its migrations job
# still pinned 5432 and blocks `build-and-push`. A fix without a guard is memory, and memory is
# what ran out here.
#
# The scan is DISCOVERY-BASED: every service of every workflow must obey, so a workflow added
# tomorrow cannot opt out by not being listed. `KNOWN_SERVICES` is not the scan — it is the
# self-check that proves the scan still SEES things, the failure mode hub#1327 already hit one
# level up: a discovery guard that silently stops discovering passes green while protecting
# nothing. The synthetic cases prove the detector still catches the positive.
#
# Run:  bash scripts/tests/service-container-ports.test.sh
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

if ! python3 -c 'import yaml' 2>/dev/null; then
    printf 'FAIL: python3 with PyYAML is required to check the workflow contract (apt: python3-yaml)\n' >&2
    exit 1
fi

REPO_ROOT="$repo_root" python3 - <<'PY'
import glob
import os
import sys

import yaml

repo_root = os.environ["REPO_ROOT"]

# The service containers that exist TODAY. Not the scan — the proof that the scan still finds
# something. If a service is deliberately retired, delete its line here too.
KNOWN_SERVICES = {
    ".github/workflows/n-minus-one.yml": "postgres",
    ".github/workflows/test-hub-modules.yml": "postgres",
    ".github/workflows/test-hub.yml": "postgres",
    ".github/workflows/test-web.yml": "postgres",
    ".github/workflows/visual-baselines.yml": "postgres",
}

failures = []
passed = 0


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")


def pinned_ports(service):
    """The `ports:` entries that bind a fixed HOST port.

    YAML reads `- 5432` as an int (container port only — Docker picks the host side) and
    `- 5432:5432` / `- 127.0.0.1:5432:5432` as a string carrying a colon (a fixed host binding).
    The colon is therefore the whole rule.
    """
    ports = service.get("ports") or []
    if not isinstance(ports, list):
        ports = [ports]
    return [port for port in ports if ":" in str(port)]


def container_ports(service):
    """The container-side port of every entry, whichever form it was written in."""
    ports = service.get("ports") or []
    if not isinstance(ports, list):
        ports = [ports]
    return [str(port).split(":")[-1].split("/")[0] for port in ports]


# ── The detector, before it is trusted with the real files ────────────────────────────────
# A guard is only worth what its positive control proves. These three cases are the failure this
# test exists to stop, written down: if a refactor ever makes `pinned_ports` blind, they go red
# here instead of going green in a run that no longer protects anything.
def _service(literal):
    return yaml.safe_load(literal)["services"]["svc"]


check(
    "the detector catches `5432:5432`",
    pinned_ports(_service("services:\n  svc:\n    ports:\n      - 5432:5432\n")) == ["5432:5432"],
    "a pinned host port must be reported, that is the whole point of this test",
)
check(
    "the detector catches an address-qualified binding",
    pinned_ports(_service("services:\n  svc:\n    ports:\n      - '127.0.0.1:5432:5432'\n"))
    == ["127.0.0.1:5432:5432"],
    "`127.0.0.1:5432:5432` binds the same single host port as `5432:5432`",
)
check(
    "the detector accepts a container-only port",
    pinned_ports(_service("services:\n  svc:\n    ports:\n      - 5432\n")) == [],
    "publishing only the container port is the fix, so it must not be flagged",
)

workflow_paths = sorted(
    set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yml")))
    | set(glob.glob(os.path.join(repo_root, ".github/workflows/*.yaml")))
)
check(
    ".github/workflows/ holds workflows to scan",
    bool(workflow_paths),
    "no workflow file matched — the scan would pass without checking anything",
)

# rel_path -> the service ids found there
discovered = {}

for path in workflow_paths:
    rel_path = os.path.relpath(path, repo_root)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        check(f"{rel_path} parses as YAML", False, str(exc).replace("\n", " ")[:200])
        continue
    if not isinstance(doc, dict):
        continue

    for job_name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for service_id, service in (job.get("services") or {}).items():
            if not isinstance(service, dict):
                continue
            discovered.setdefault(rel_path, []).append(service_id)
            where = f"{rel_path} · job `{job_name}` · service `{service_id}`"

            check(
                f"{where}: publishes the container port only",
                not pinned_ports(service),
                f"{pinned_ports(service)} pins a host port, and the slots of ci-runner-1 share "
                "one Docker daemon — the second concurrent job dies in «Initialize containers» "
                f"(hub#898). Publish `- {container_ports(service)[0] if container_ports(service) else '5432'}` "
                f"and read the assigned one from `job.services.{service_id}.ports`",
            )

            # The other half of the same fix: a dynamic host port that a step then ignores by
            # writing the container port by hand connects to whatever else happens to be on that
            # port on the runner — or to nothing at all. Both halves have to hold, or the service
            # is dynamic and the client is not.
            hardcoded = []
            for index, step in enumerate(job.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                text = str(step.get("run") or "") + "\n".join(
                    f"{k}={v}" for k, v in (step.get("env") or {}).items()
                )
                for port in container_ports(service):
                    for host in ("localhost", "127.0.0.1"):
                        if f"{host}:{port}" in text:
                            hardcoded.append(f"step «{step.get('name', index)}» → {host}:{port}")
            check(
                f"{where}: no step writes its port by hand",
                not hardcoded,
                f"{hardcoded} — the host port is assigned by Docker at start, so it has to be "
                f"read from `job.services.{service_id}.ports` (or `docker port` after a restart), "
                "never assumed",
            )

for rel_path, service_id in sorted(KNOWN_SERVICES.items()):
    check(
        f"{rel_path}: the scan still finds its `{service_id}` service",
        service_id in discovered.get(rel_path, []),
        "no service matched — either it was removed without updating KNOWN_SERVICES, or the "
        "discovery itself is broken and this guard is protecting nothing (hub#1327)",
    )

if failures:
    print(f"FAIL: {len(failures)} contract case(s) on the workflow service containers")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"OK: {passed} contract case(s) on the workflow service containers")
PY
