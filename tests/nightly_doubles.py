"""What the tests of scripts/nightly_e2e.py and scripts/nightly_stack.py share: the scripts and their doubles.

Each night runs as GitHub Actions or a person runs it, on throwaway clones of a hub and a saas repository (real git),
with fake uv, pnpm, node, docker, curl, lsof and gh first on the PATH that record every call. Nothing real runs:
no server, database or browser. The scripts are loaded from their path, as the Mac runs them outside Django.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "nightly_e2e.py"


def load(name):
    """scripts/<name>.py as a module, registered under its name so the other script imports this one."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nightly_stack = load("nightly_stack")
nightly_e2e = load("nightly_e2e")
ISSUE = "Pruebas de navegador del Hub en rojo en la pasada nocturna"
OPEN_ISSUE = json.dumps([{"number": 9, "title": ISSUE}])
NOTHING_RUNS = r"^(uv|pnpm|node|e2e|runserver|database|drop) "

# uv: `sync` (FAKE_SYNC_SECONDS makes it slow, FAKE_SYNC_EXIT makes it fail); `run python manage.py runserver <addr>`
# logs its environment and sleeps like a server (its pid in $FAKE_PIDS; FAKE_SERVER_EXITS makes it exit at once,
# FAKE_SERVER_KEEPS_TERM makes it ignore TERM); `run python tests/e2e/panel/<seed>.py` exits with FAKE_SEED_EXIT; any
# other `run python manage.py <command>` exits with FAKE_MANAGE_EXIT.
FAKE_UV = r"""#!/usr/bin/env bash
where="$(basename "$PWD")"
case "$*" in
  sync | "sync "*)
    echo "uv $where $*" >> "$FAKE_CALLS"
    if [ -n "${FAKE_SYNC_SECONDS:-}" ]; then sleep "$FAKE_SYNC_SECONDS"; echo "uv $where sync done" >> "$FAKE_CALLS"; fi
    exit "${FAKE_SYNC_EXIT:-0}" ;;
  "run python manage.py runserver "*)
    echo "runserver $where $5 DB_NAME=${DB_NAME:-} VITE_DEV_PORT=${VITE_DEV_PORT:-} SAAS_URL=${SAAS_URL:-}" \
      "HUB_INTERNAL_URL=${HUB_INTERNAL_URL:-} EMAIL_FILE_PATH=${EMAIL_FILE_PATH:-}" \
      "ASSISTANT_SERVICE_PROVIDER=${ASSISTANT_SERVICE_PROVIDER:-} E2E_RELAX_LOGIN_RATE_LIMIT=${E2E_RELAX_LOGIN_RATE_LIMIT:-}" \
      "DEMO_SPAWN_RATELIMIT=${DEMO_SPAWN_RATELIMIT:-} HUB_CALLBACK_TEMPLATE=${HUB_CALLBACK_TEMPLATE:-}" \
      "HUB_ADMIN_CALLBACK_URL=${HUB_ADMIN_CALLBACK_URL:-} HTTPS_PROXY=${HTTPS_PROXY:-} OPENAI_API_KEY=${OPENAI_API_KEY:-} CATALOG_DIR=${CATALOG_DIR:-}" \
      >> "$FAKE_CALLS"
    [ -z "${FAKE_SERVER_EXITS:-}" ] || exit 1
    [ -z "${FAKE_SERVER_KEEPS_TERM:-}" ] || trap '' TERM
    echo "$$" >> "$FAKE_PIDS"
    exec sleep 120 ;;
  "run python tests/e2e/panel/"*)
    shift 2
    echo "seed $where $* DB_NAME=${DB_NAME:-} HUB_INTERNAL_URL=${HUB_INTERNAL_URL:-}" >> "$FAKE_CALLS"
    exit "${FAKE_SEED_EXIT:-0}" ;;
  "run python manage.py "*)
    shift 3
    echo "manage $where $* DB_NAME=${DB_NAME:-}" >> "$FAKE_CALLS"
    exit "${FAKE_MANAGE_EXIT:-0}" ;;
esac
echo "uv unexpected $where $*" >> "$FAKE_CALLS"
exit 2
"""
# pnpm: `install`; `e2e <args>` logs its arguments, the commit it runs on, its environment and the fake servers alive,
# leaves FAKE_RESULTS as its JSON report and exits with FAKE_E2E_EXIT. FAKE_MAIN_MOVES=<remote> moves main and fetches
# it meanwhile; with FAKE_E2E_NEVER_ENDS it then sleeps like specs that hang (its pid in $FAKE_PIDS).
# FAKE_GONE_LISTENER=<file>: when the specs end, lsof reports once the pid in <file>.pid, a server already gone.
FAKE_PNPM = r"""#!/usr/bin/env bash
where="$(basename "$PWD")"
case "${1:-}" in
  install) echo "pnpm $where $*" >> "$FAKE_CALLS"; exit 0 ;;
  e2e)
    shift
    echo "e2e $where args=$* HEAD=$(git rev-parse HEAD) E2E_HUB_PORT=${E2E_HUB_PORT:-} VITE_DEV_PORT=${VITE_DEV_PORT:-}" \
      "SAAS_URL=${SAAS_URL:-} DB_NAME=${DB_NAME:-} E2E_SAAS_DB=${E2E_SAAS_DB:-} E2E_SAAS_DIR=${E2E_SAAS_DIR:-}" \
      "E2E_MAIL_DIR=${E2E_MAIL_DIR:-} CI=${CI:-} COMPOSE_FILE=${COMPOSE_FILE:-} CATALOG_DIR=${CATALOG_DIR:-}" \
      "QA_REAL_PROVIDER=${QA_REAL_PROVIDER:-} E2E_OUTPUT_DIR=${E2E_OUTPUT_DIR:-}" >> "$FAKE_CALLS"
    [ -f .env ] && echo "e2e sees .env $(cat .env)" >> "$FAKE_CALLS"
    while read -r pid; do
      kill -0 "$pid" 2> /dev/null && echo "e2e sees a server alive" >> "$FAKE_CALLS"
    done < "$FAKE_PIDS"
    mkdir -p "$E2E_OUTPUT_DIR"
    [ -z "${FAKE_RESULTS:-}" ] || cp "$FAKE_RESULTS" "$E2E_OUTPUT_DIR/results.json"
    if [ -n "${FAKE_MAIN_MOVES:-}" ]; then
      git -C "$FAKE_MAIN_MOVES" -c user.name=nightly -c user.email=nightly@example.com commit -q --allow-empty -m later
      git -C "$HUB_REPO" fetch --quiet origin
    fi
    [ -z "${FAKE_GONE_LISTENER:-}" ] || cp "$FAKE_GONE_LISTENER.pid" "$FAKE_GONE_LISTENER"
    if [ -n "${FAKE_E2E_NEVER_ENDS:-}" ]; then
      echo "$$" >> "$FAKE_PIDS"
      exec sleep 120
    fi
    exit "${FAKE_E2E_EXIT:-0}" ;;
esac
echo "pnpm unexpected $where $*" >> "$FAKE_CALLS"
exit 2
"""
# node: tests/e2e/database.ts [--drop] (FAKE_DB_FAILS=hub|saas fails that checkout's creation, FAKE_DB_SECONDS makes
# it slow, FAKE_DROP_FAILS fails its drop) and tests/e2e/whatsapp-graph.ts <hub port> <saas url>, which prints the SaaS's proxy variables (FAKE_GRAPH_EXIT
# makes it fail).
FAKE_NODE = r"""#!/usr/bin/env bash
where="$(basename "$PWD")"
case "$*" in
  "tests/e2e/database.ts --drop")
    echo "drop $where DB_NAME=${DB_NAME:-} E2E_SAAS_PORT=${E2E_SAAS_PORT:-}" >> "$FAKE_CALLS"
    if [ "${FAKE_DROP_FAILS:-}" = "$where" ]; then exit 1; fi
    exit 0 ;;
  "tests/e2e/database.ts")
    echo "database $where DB_NAME=${DB_NAME:-} E2E_SAAS_PORT=${E2E_SAAS_PORT:-}" >> "$FAKE_CALLS"
    [ -z "${FAKE_DB_SECONDS:-}" ] || sleep "$FAKE_DB_SECONDS"
    if [ "${FAKE_DB_FAILS:-}" = "$where" ]; then echo "database.ts: could not migrate" >&2; exit 1; fi
    exit 0 ;;
  "tests/e2e/whatsapp-graph.ts "*)
    echo "graph $where $2 $3" >> "$FAKE_CALLS"
    [ -z "${FAKE_GRAPH_EXIT:-}" ] || exit "$FAKE_GRAPH_EXIT"
    echo "HTTPS_PROXY=http://127.0.0.1:$(($2 + 9))"
    exit 0 ;;
esac
echo "node unexpected $where $*" >> "$FAKE_CALLS"
exit 2
"""
# docker: the ids of a and b (FAKE_IDS names others) from the Hub's database; FAKE_DOCKER_EXIT makes it fail.
FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "docker $(basename "$PWD") $*" >> "$FAKE_CALLS"
[ -z "${FAKE_DOCKER_EXIT:-}" ] || exit "$FAKE_DOCKER_EXIT"
case "$*" in *"select id from base_hub"*) printf '%s\n' ${FAKE_IDS-0190-a 0190-b} ;; esac
"""
FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_CALLS"
exit "${FAKE_CURL_EXIT:-0}"
"""
# lsof: what listens on the stack's ports, none by default; the pids of FAKE_LISTENERS that are alive, and once the
# gone pid of FAKE_GONE_LISTENER.
FAKE_LSOF = r"""#!/usr/bin/env bash
echo "lsof $*" >> "$FAKE_CALLS"
if [ -n "${FAKE_LISTENERS:-}" ]; then
  while read -r pid; do kill -0 "$pid" 2> /dev/null && echo "$pid"; done < "$FAKE_LISTENERS"
  exit 0
fi
if [ -n "${FAKE_GONE_LISTENER:-}" ] && [ -f "$FAKE_GONE_LISTENER" ]; then
  cat "$FAKE_GONE_LISTENER"
  rm -f "$FAKE_GONE_LISTENER"
  exit 0
fi
exit 1
"""
# gh: records its calls, the repository it writes to and the bodies it is given, answers OPEN_ISSUES to
# `issue list` and exits with FAKE_GH_EXIT.
FAKE_GH = r"""#!/usr/bin/env bash
echo "gh $*" >> "$CALLS_LOG"
echo "gh repo ${GH_REPO:-unset}" >> "$FAKE_CALLS"
call="$*"
while [ $# -gt 0 ]; do
  case "$1" in
    --body-file) cat "$2" >> "$BODIES_LOG"; shift ;;
    --comment | --body) printf '%s\n' "$2" >> "$BODIES_LOG"; shift ;;
  esac
  shift
done
case "$call" in *"issue list"*) printf '%s\n' "${OPEN_ISSUES:-[]}" ;; esac
exit "${FAKE_GH_EXIT:-0}"
"""
# git: the real one, each call recorded; FAKE_PRUNE_EXIT makes `worktree prune` fail.
FAKE_GIT = r"""#!/usr/bin/env bash
echo "git $*" >> "$FAKE_CALLS"
if [ -n "${FAKE_PRUNE_EXIT:-}" ] && [ "${*: -2}" = "worktree prune" ]; then exit "$FAKE_PRUNE_EXIT"; fi
exec "$REAL_GIT" "$@"
"""
# tee: the real one, half a second late, as a log on a busy disk.
FAKE_TEE = r"""#!/usr/bin/env bash
sleep 0.5
exec "$REAL_TEE" "$@"
"""
FAKES = {"git": FAKE_GIT, "tee": FAKE_TEE, "uv": FAKE_UV, "pnpm": FAKE_PNPM, "node": FAKE_NODE, "docker": FAKE_DOCKER, "curl": FAKE_CURL,
         "lsof": FAKE_LSOF, "gh": FAKE_GH}

RED_REPORT = {
    "suites": [{"title": "sale-sales.spec.ts", "file": "sale-sales.spec.ts", "line": 0, "specs": [
        {"title": "charges in cash", "file": "sale-sales.spec.ts", "line": 4, "tests": [
            {"projectName": "", "status": "unexpected",
             "results": [{"status": "failed", "error": {"message": "Error: expect(locator).toBeVisible()"}}]}]}]}],
    "errors": [], "stats": {"expected": 360, "skipped": 0, "unexpected": 1, "flaky": 0}}
GREEN_REPORT = {"suites": [], "errors": [], "stats": {"expected": 361, "skipped": 0, "unexpected": 0, "flaky": 0}}


def git(*arguments: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=nightly", "-c", "user.email=nightly@example.com", "-c",
                           "init.defaultBranch=main", *arguments], check=True, stdout=subprocess.PIPE, text=True)
    return done.stdout.strip()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class World:
    """Two "GitHub" repositories, their clones beside compose.yaml and blueprints/ as in erplora-next's root, the
    fakes, and the logs of one night at a time."""

    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.nightly = self.home / ".erplora" / "hub-nightly-e2e"
        self.erplora = root / "erplora"
        self.hub = self.erplora / "hub"
        self.saas = self.erplora / "saas"
        self.logs = {name: root / f"{name}.log" for name in ("calls", "pids", "gh", "bodies")}
        self.every_pid: list[int] = []
        self.status = None
        self.home.mkdir()
        for repo in ("hub", "saas"):
            remote = root / "remote" / repo
            (remote / "scripts").mkdir(parents=True)
            for name in ("nightly_e2e.py", "nightly_stack.py"):
                (remote / "scripts" / name).write_text((SCRIPTS / name).read_text())
            (remote / "scripts" / "nightly_e2e.py").chmod(0o755)
            git("init", "-q", str(remote))
            git("-C", str(remote), "add", "-A")
            git("-C", str(remote), "commit", "-q", "-m", "first")
            git("clone", "-q", str(remote), str(self.erplora / repo))
            (self.erplora / repo / ".env").write_text(f"LOCAL_SETTING={repo}\n")
        (self.erplora / "compose.yaml").touch()
        (self.erplora / "blueprints" / "img").mkdir(parents=True)
        self.clone_head = git("-C", str(self.hub), "rev-parse", "HEAD")
        # main moves after the clone fetched: the night must test the newest main, not the clone's.
        (root / "remote" / "hub" / "moved.txt").write_text("moved\n")
        git("-C", str(root / "remote" / "hub"), "add", "-A")
        git("-C", str(root / "remote" / "hub"), "commit", "-q", "-m", "moved")
        self.newest_main = git("-C", str(root / "remote" / "hub"), "rev-parse", "HEAD")
        self.write_fakes()

    def write_fakes(self) -> None:
        (self.root / "bin").mkdir()
        for name, body in FAKES.items():
            (self.root / "bin" / name).write_text(body)
            (self.root / "bin" / name).chmod(0o755)
        (self.root / "red.json").write_text(json.dumps(RED_REPORT))
        (self.root / "green.json").write_text(json.dumps(GREEN_REPORT))

    def environment(self, settings: dict) -> dict:
        """Red by default (the e2e exits 1 with one red spec), no issue open, nothing of the caller's night."""
        env = {name: value for name, value in os.environ.items()
               if name != "GITHUB_ACTIONS" and not name.startswith(("NIGHTLY_", "FAKE_"))}
        env.update(PATH=f"{self.root / 'bin'}:{os.environ['PATH']}", HOME=str(self.home), HUB_REPO=str(self.hub),
                   ERPLORA_ROOT=str(self.erplora), NIGHTLY_START_SECONDS="5",
                   FAKE_E2E_EXIT="1", FAKE_RESULTS=str(self.root / "red.json"), FAKE_CALLS=str(self.logs["calls"]),
                   FAKE_PIDS=str(self.logs["pids"]), CALLS_LOG=str(self.logs["gh"]),
                   BODIES_LOG=str(self.logs["bodies"]), REAL_GIT=shutil.which("git"),
                   REAL_TEE=shutil.which("tee"))
        env.update(settings)
        return env

    def start(self, *arguments: str, **settings: str) -> subprocess.Popen:
        for log in self.logs.values():
            log.write_text("")
        with open(self.root / "out", "wb") as out:
            return subprocess.Popen([sys.executable, str(SCRIPT), *arguments], env=self.environment(settings),
                                    stdout=out, stderr=subprocess.STDOUT)

    def night(self, *arguments: str, **settings: str) -> int:
        night = self.start(*arguments, **settings)
        self.status = night.wait(timeout=120)
        self.every_pid += self.pids()
        return self.status

    def green(self, *arguments: str, **settings: str) -> int:
        return self.night(*arguments, FAKE_E2E_EXIT="0", FAKE_RESULTS=str(self.root / "green.json"), **settings)

    def read(self, name: str) -> str:
        return self.logs[name].read_text()

    def lines(self) -> list[str]:
        return self.read("calls").splitlines()

    def calls(self, text: str) -> int:
        return sum(text in line for line in self.lines())

    def calls_re(self, pattern: str) -> int:
        return sum(bool(re.search(pattern, line)) for line in self.lines())

    def first(self, text: str) -> int:
        return next(number for number, line in enumerate(self.lines()) if text in line)

    def last(self, text: str) -> int:
        return max(number for number, line in enumerate(self.lines()) if text in line)

    def gh(self, pattern: str) -> int:
        return sum(bool(re.search(pattern, line)) for line in self.read("gh").splitlines())

    def out(self) -> str:
        return (self.root / "out").read_text()

    def pids(self) -> list[int]:
        return [int(pid) for pid in self.read("pids").split()]

    def alive_servers(self) -> int:
        return sum(alive(pid) for pid in self.pids())

    def worktrees(self) -> tuple[int, int]:
        return tuple(len(git("-C", str(repo), "worktree", "list").splitlines()) for repo in (self.hub, self.saas))

    def night_logs(self) -> list[Path]:
        return sorted(self.nightly.glob("runs/*/night.log"))

    def log(self) -> str:
        """The log of the night just run, with the report of what came out red."""
        return self.night_logs()[-1].read_text()

    def stop(self) -> None:
        for pid in self.every_pid + self.pids():
            if alive(pid):
                os.kill(pid, signal.SIGKILL)



def wait_for(condition, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.1)



def fresh_world(root: Path):
    made = World(root)
    yield made
    made.stop()
