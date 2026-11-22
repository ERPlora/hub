"""What one night of the Hub's nightly browser run does (scripts/nightly_e2e.py starts it): fetch main, make the
worktrees of the Hub and the SaaS, their dependencies, databases and seeding, start both servers, run the specs, and
then, whatever happened, stop what listens on the stack's ports, drop both databases and remove the worktrees.

Every command gets the stack's own variables, and INT and TERM stop the night once the command running ends, as a
shell's trap does; while the specs run, at once. Only the standard library: the Mac runs it with its own python3.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Interrupted(Exception):
    """INT or TERM: the night ends with 128 + the signal's number, as a shell would."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class Signals:
    """A signal waits for the command running to end, as a shell's trap does; while the specs run it acts at once."""

    def __init__(self) -> None:
        self.pending: int | None = None
        self.at_once = False
        self.holding = False

    def install(self) -> None:
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, self.received)

    def received(self, number: int, _frame) -> None:
        if self.pending is None:
            self.pending = 128 + number
        if self.at_once:
            self.checkpoint()

    def checkpoint(self) -> None:
        if self.holding:
            return
        code, self.pending = self.pending, None
        if code is not None:
            raise Interrupted(code)

    @contextlib.contextmanager
    def together(self):
        """Commands a signal stops only once all of them have ended, as the commands of one subshell."""
        self.holding = True
        try:
            yield
        finally:
            self.holding = False
        self.checkpoint()

    def wait_at_once(self, process: subprocess.Popen) -> int:
        self.at_once = True
        try:
            self.checkpoint()
            return process.wait()
        finally:
            self.at_once = False


SIGNALS = Signals()


def say(text: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} nightly-e2e: {text}", flush=True)


def environment(extra: dict | None = None) -> dict:
    return {**os.environ, **(extra or {})}


def run(command: list[str], cwd: str | None = None, extra: dict | None = None, **options):
    sys.stdout.flush()
    try:
        done = subprocess.run(command, cwd=cwd, env=environment(extra), check=False, **options)
    except OSError as error:
        print(f"nightly-e2e: {error}", file=sys.stderr, flush=True)
        done = subprocess.CompletedProcess(command, 127, stdout="")
    SIGNALS.checkpoint()
    return done


def ok(command: list[str], cwd: str | None = None, extra: dict | None = None, **options) -> bool:
    return run(command, cwd, extra, **options).returncode == 0


def pause(seconds: int) -> None:
    time.sleep(seconds)
    SIGNALS.checkpoint()


def remove(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        with contextlib.suppress(OSError):
            os.remove(path)


def git_folder(repo: str, which: str) -> str:
    """--git-dir or --git-common-dir of a checkout, as an absolute path."""
    found = run(["git", "rev-parse", which], cwd=repo, stdout=subprocess.PIPE, text=True)
    return os.path.abspath(os.path.join(repo, found.stdout.strip()))


def main_checkout(repo: str) -> str:
    """The .env lives only in the repo's main checkout, the one that holds .git, also from a linked worktree."""
    return os.path.dirname(git_folder(repo, "--git-common-dir"))


@dataclass(frozen=True)
class Settings:
    hub_repo: str
    erplora_root: str
    saas_repo: str
    nightly_dir: str
    port: int
    max_minutes: int
    start_seconds: int
    keep_runs: int
    gh_repo: str


def answers(url: str) -> bool:
    return ok(["curl", "-fsS", "-o", "/dev/null", "--max-time", "5", url], stderr=subprocess.DEVNULL)


def assignments(words: str) -> dict:
    """The VAR=value words a command prints for env."""
    return dict(word.partition("=")[::2] for word in words.split())


def dependencies(folder: str) -> bool:
    with SIGNALS.together():
        return ok(["uv", "sync"], folder) and ok(["pnpm", "install", "--frozen-lockfile"], folder)


def remove_worktree(repo: str, folder: str) -> bool:
    """The night's own, so --force: it has submodules and untracked dependencies."""
    if os.path.exists(folder) and not ok(["git", "-C", repo, "worktree", "remove", "--force", folder],
                                         stderr=subprocess.DEVNULL):
        remove(folder)
    return ok(["git", "-C", repo, "worktree", "prune"])


def make_worktree(repo: str, folder: str, commit: str) -> bool:
    env_file = f"{main_checkout(repo)}/.env"
    if not (remove_worktree(repo, folder) and ok(["git", "-C", repo, "worktree", "add", "--quiet", "--detach", folder,
                                                  commit])
            and ok(["git", "-C", folder, "submodule", "update", "--init", "--quiet"])):
        return False
    try:
        if os.path.isfile(env_file):
            shutil.copy(env_file, f"{folder}/.env")
    except OSError as error:
        print(f"nightly-e2e: {error}", file=sys.stderr, flush=True)
        return False
    return True


class Night:
    """One night's stack: its ports, databases, worktrees and the servers it starts, each in a process group of its
    own, so stopping one stops its Vite too."""

    def __init__(self, settings: Settings, folder: str, specs: list[str]) -> None:
        port = settings.port
        self.settings, self.folder, self.specs = settings, folder, specs
        self.hub_port, self.saas_port, self.provider_port = port, port + 1, port + 2
        self.ports = (port, port + 1, port + 2, port + 5, port + 6, port + 9)
        self.hub_db, self.saas_db = f"hub_e2e_{port}", f"saas_e2e_{port + 1}"
        self.hub_wt, self.saas_wt = f"{settings.nightly_dir}/hub", f"{settings.nightly_dir}/saas"
        mail = f"{self.saas_wt}/.mail-{self.saas_port}"
        self.hub_env = {"E2E_HUB_PORT": str(port), "VITE_DEV_PORT": str(port + 5),
                        "SAAS_URL": f"http://localhost:{self.saas_port}", "DB_NAME": self.hub_db,
                        "E2E_SAAS_DB": self.saas_db, "E2E_SAAS_DIR": self.saas_wt, "E2E_MAIL_DIR": mail,
                        "CATALOG_DIR": f"{settings.erplora_root}/blueprints/img"}
        self.saas_env = {"DB_NAME": self.saas_db, "VITE_DEV_PORT": str(port + 6),
                         "HUB_INTERNAL_URL": f"http://localhost:{port}", "EMAIL_FILE_PATH": mail,
                         "ASSISTANT_SERVICE_PROVIDER": "e2e-local", "E2E_RELAX_LOGIN_RATE_LIMIT": "True",
                         "DEMO_SPAWN_RATELIMIT": "100/h",
                         "HUB_CALLBACK_TEMPLATE": f"http://{{slug}}.localhost:{port}/auth/callback",
                         "HUB_ADMIN_CALLBACK_URL": f"http://hubs.localhost:{port}/auth/callback",
                         "OPENAI_API_KEY": "sk-e2e-0000000000000000000000000000e2e1"}
        self.own_group = os.getpgrp()
        self.started: list[subprocess.Popen] = []
        self.cleaned = False

    def steps(self) -> tuple:
        settings = self.settings
        return (
            ("traer origin/main", lambda: ok(["git", "-C", settings.hub_repo, "fetch", "--quiet", "origin"])
             and ok(["git", "-C", settings.saas_repo, "fetch", "--quiet", "origin"])),
            ("los worktrees", lambda: make_worktree(settings.hub_repo, self.hub_wt,
                                                    os.environ.get("NIGHTLY_HUB_REF") or "origin/main")
             and make_worktree(settings.saas_repo, self.saas_wt, "origin/main")),
            ("las dependencias del Hub", lambda: dependencies(self.hub_wt)),
            ("las dependencias del SaaS", lambda: dependencies(self.saas_wt)),
            # What an earlier night left when it was cut (the Mac switched off): its servers and its databases.
            ("borrar lo que dejó una noche anterior", lambda: self.stop_stack() and self.hub_database("--drop")
             and self.saas_database("--drop")),
            ("la BD del Hub", self.hub_database),
            ("la BD del SaaS", self.saas_database),
            ("la siembra del SaaS", self.seed_saas),
            ("arrancar los servidores", self.start_stack),
        )

    def hub_database(self, *drop: str) -> bool:
        return ok(["node", "tests/e2e/database.ts", *drop], self.hub_wt, self.hub_env)

    def saas_database(self, *drop: str) -> bool:
        return ok(["node", "tests/e2e/database.ts", *drop], self.saas_wt, {"E2E_SAAS_PORT": str(self.saas_port)})

    def in_saas(self, command: list[str], **extra: str) -> bool:
        return ok(["uv", "run", "python", *command], self.saas_wt, {"DB_NAME": self.saas_db, **extra})

    def seed_saas(self) -> bool:
        found = run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hub", "-d", self.hub_db, "-At", "-c",
                     "select id from base_hub where slug in ('a', 'b') order by slug"], self.hub_wt,
                    stdout=subprocess.PIPE, text=True)
        if found.returncode != 0:
            return False
        ids = found.stdout.rstrip("\n")
        if len([line for line in ids.split("\n") if line]) != 2:
            say(f"the Hub's database should hold a and b, and holds «{ids}»")
            return False
        return (self.in_saas(["tests/e2e/panel/whatsapp_hub_seed.py", *ids.split()],
                             HUB_INTERNAL_URL=f"http://127.0.0.1:{self.hub_port}")
                and self.in_saas(["tests/e2e/panel/assistant_seed.py", "gateway",
                                  f"http://127.0.0.1:{self.provider_port}/v1"])
                # The business types, as every deploy seeds them after migrating.
                and self.in_saas(["manage.py", "seed_taxonomy"]))

    def start(self, command: list[str], folder: str, extra: dict, **options) -> subprocess.Popen | None:
        sys.stdout.flush()
        try:
            started = subprocess.Popen(command, cwd=folder, env=environment(extra), start_new_session=True, **options)
        except OSError as error:
            print(f"nightly-e2e: {error}", file=sys.stderr, flush=True)
            return None
        self.started.append(started)
        return started

    def start_server(self, folder: str, log: str, extra: dict) -> bool:
        port = self.hub_port if folder == self.hub_wt else self.saas_port
        runserver = ["uv", "run", "python", "manage.py", "runserver", f"127.0.0.1:{port}"]
        with open(log, "ab") as out:
            return self.start(runserver, folder, extra, stdout=out, stderr=subprocess.STDOUT) is not None

    def start_stack(self) -> bool:
        deadline = time.monotonic() + self.settings.start_seconds
        graph = run(["node", "tests/e2e/whatsapp-graph.ts", str(self.hub_port), f"http://localhost:{self.saas_port}"],
                    self.hub_wt, stdout=subprocess.PIPE, text=True)
        if graph.returncode != 0:
            say("whatsapp-graph.ts failed: the SaaS starts without Meta's proxy and the WhatsApp specs will say what is"
                " missing")
        proxy = assignments(graph.stdout) if graph.returncode == 0 else {}
        if not (self.start_server(self.saas_wt, f"{self.folder}/saas.log", {**self.saas_env, **proxy})
                and self.start_server(self.hub_wt, f"{self.folder}/hub.log", self.hub_env)):
            return False
        urls = (f"http://127.0.0.1:{self.hub_port}/healthz",
                f"http://localhost:{self.ports[3]}/static/spa/@vite/client",
                f"http://127.0.0.1:{self.saas_port}/healthz")
        while not all(answers(url) for url in urls):
            if any(server.poll() is not None for server in self.started):
                say("a server exited before answering: see hub.log and saas.log")
                return False
            if time.monotonic() >= deadline:
                say(f"the servers did not answer within {self.settings.start_seconds} s")
                return False
            pause(2)
        return True

    def listeners(self) -> list[str]:
        """The pids listening on the stack's ports: a spec may restart the Hub's runserver on its own."""
        found = run(["lsof", "-nP", "-t", "-sTCP:LISTEN", *(f"-iTCP:{port}" for port in self.ports)],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return sorted(set(found.stdout.split()))

    def signal_all(self, number: int) -> None:
        for server in self.started:
            with contextlib.suppress(OSError):
                os.killpg(server.pid, number)
        for pid in self.listeners():
            try:
                group = os.getpgid(int(pid))
            except (OSError, ValueError):
                continue  # gone since lsof saw it
            with contextlib.suppress(OSError):
                if group != self.own_group:
                    os.killpg(group, number)
                else:
                    os.kill(int(pid), number)

    def anything_left(self) -> bool:
        return any(server.poll() is None for server in self.started) or bool(self.listeners())

    def stop_stack(self) -> bool:
        self.signal_all(signal.SIGTERM)
        waited = 0
        while self.anything_left() and waited < 20:
            pause(1)
            waited += 1
        if self.anything_left():
            say("still running after 20 s: killing it")
            self.signal_all(signal.SIGKILL)
        self.started = []
        return True

    def run_specs(self) -> bool:
        grep = os.environ.get("NIGHTLY_GREP")
        command = ["pnpm", "e2e", f"--global-timeout={self.settings.max_minutes * 60000}",
                   *(["--grep", grep] if grep else []), *self.specs]
        extra = {**self.hub_env, "CI": "1", "E2E_OUTPUT_DIR": f"{self.folder}/test-results"}
        specs = self.start(command, self.hub_wt, extra, stdin=subprocess.DEVNULL)
        return specs is not None and SIGNALS.wait_at_once(specs) == 0

    def clean_up(self) -> None:
        """Never stops half way: a drop or a removal that fails is said here and tried again by the next night."""
        if self.cleaned:
            return
        self.cleaned = True
        say("clean-up: servers, databases and worktrees")
        self.stop_stack()
        if os.path.isdir(self.hub_wt) and not self.hub_database("--drop"):
            say(f"could not drop {self.hub_db}: the next night tries again")
        if os.path.isdir(self.saas_wt) and not self.saas_database("--drop"):
            say(f"could not drop {self.saas_db}: the next night tries again")
        say("clean-up: removing the worktrees")
        for repo, folder in ((self.settings.hub_repo, self.hub_wt), (self.settings.saas_repo, self.saas_wt)):
            if not remove_worktree(repo, folder):
                say(f"could not remove {folder}")
        say("clean-up done")

    def commit(self) -> str:
        """The commit the night ran on: main may have moved, and been fetched, while the specs ran."""
        with SIGNALS.together():
            for command in (["git", "-C", self.hub_wt, "rev-parse", "HEAD"],
                            ["git", "-C", self.settings.hub_repo, "rev-parse", "origin/main"]):
                found = run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if found.returncode == 0:
                    return found.stdout.rstrip("\n")
            return "unknown"

    def specs_result(self) -> tuple[str, str]:
        """success or failure, and the step before the specs that failed, if one did."""
        for label, done in self.steps():
            say(f"step: {label}")
            if not done():
                say(f"failed: {label}")
                return "failure", label
        say("step: las specs")
        return ("success" if self.run_specs() else "failure"), ""

    def report(self, result: str, failed_step: str, commit: str, publish: bool) -> int:
        settings = {"RESULT": result, "REPORT": f"{self.folder}/test-results/results.json", "STEP": failed_step,
                    "SHA": commit, "RUN_DIR": self.folder, "PUBLISH": "true" if publish else "false"}
        if not ok([sys.executable, str(HERE / "e2e_report.py")], extra=settings):
            say("the report failed: the night's result did not reach GitHub")
            return 1
        return 0 if result == "success" else 1
