#!/usr/bin/env python3
"""The Hub's browser run on a stack of its own: every spec of tests/e2e on the newest origin/main, or a share of them.
The nightly workflow (.github/workflows/nightly.yml) runs one share per job and keeps the one issue of a red night;
the smoke of test.yml runs its @smoke tests. A night writes nothing to GitHub: what came out red is in its output.

  python3 scripts/nightly_e2e.py [--shard <i>/<n>] [--spec tests/e2e/<name>.spec.ts]...   every spec, or a share of
                                                                                            them, or the ones named

A night builds the stack of tests/e2e/README.md («Varias ejecuciones a la vez») by itself: detached worktrees of
the Hub and the SaaS in NIGHTLY_DIR (the shared checkouts only get a fetch), their e2e databases,
the SaaS seeded (the ids of `a` and `b`, the fake assistant provider, its taxonomy), both runservers and `pnpm e2e`.
Whatever happens, it then stops what listens on the stack's ports, drops both databases and removes the worktrees.
A step before the specs that fails is a red night too, and the issue names it. Each night's log and Playwright's
output (results.json, traces, failure screenshots) stay in NIGHTLY_DIR/runs/<night>/, the newest NIGHTLY_KEEP_RUNS.
INT and TERM stop it as soon as the command it runs ends; while the specs run, at once.

Environment (default): NIGHTLY_DIR (~/.erplora/hub-nightly-e2e) · HUB_REPO (the clone this script is in) ·
ERPLORA_ROOT (the folder above it: compose.yaml, blueprints/) · SAAS_REPO ($ERPLORA_ROOT/saas) · NIGHTLY_HUB_REF
(origin/main; the Hub's commit, any of HUB_REPO, pushed or not) · NIGHTLY_GREP (none; Playwright's --grep) ·
NIGHTLY_HUB_PORT (9770, under the fleet workers' ports; SaaS +1, fake assistant provider +2, Vites +5 and +6, Meta's
proxy +9) · NIGHTLY_MAX_MINUTES (360, Playwright's global timeout) · NIGHTLY_START_SECONDS (300, for the servers to
answer) · NIGHTLY_KEEP_RUNS (7).
Exit: 0 green · 1 red · 2 usage · 3 another night is running · 130 or 143 stopped by INT or TERM. Only the standard
library: a runner or a Mac runs it with its own python3.
"""

from __future__ import annotations

import contextlib
import fnmatch
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from nightly_stack import HERE, SIGNALS, Interrupted, Night, Settings, remove, say

USAGE = "usage: nightly_e2e.py [--shard <i>/<n>] [--spec tests/e2e/<name>.spec.ts]..."
NUMBERS = (("NIGHTLY_HUB_PORT", "9770"), ("NIGHTLY_MAX_MINUTES", "360"), ("NIGHTLY_START_SECONDS", "300"),
           ("NIGHTLY_KEEP_RUNS", "7"))
NOT_PLAIN = re.compile(r"\.\.|[^A-Za-z0-9._/-]")
SHARD = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")
# Each command gets its stack's variables explicitly, none from the shell that started the night (a worker's DB_NAME
# would point the SaaS at a Hub database), and the specs that spend real tokens or open a visible browser stay off.
UNSET = ("DB_NAME", "SAAS_URL", "E2E_HUB_PORT", "VITE_DEV_PORT", "E2E_SAAS_DB", "E2E_SAAS_DIR", "E2E_MAIL_DIR",
         "E2E_SAAS_PORT", "HUB_INTERNAL_URL", "EMAIL_FILE_PATH", "E2E_OUTPUT_DIR", "CATALOG_DIR", "QA_REAL_PROVIDER",
         "E2E_HEADED")


class Usage(Exception):
    """A wrong argument or setting: said with the usage, exit 2."""


def whole_number(env, name: str, default: str) -> int:
    value = env.get(name) or default
    if not re.fullmatch(r"[0-9]+", value):
        raise Usage(f"{name} must be a whole number, not «{value}»")
    return int(value)


def settings_from(env) -> Settings:
    hub_repo = env.get("HUB_REPO") or subprocess.run(
        ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.rstrip("\n")
    erplora_root = env.get("ERPLORA_ROOT") or os.path.dirname(hub_repo.rstrip("/"))
    numbers = [whole_number(env, name, default) for name, default in NUMBERS]
    if not 1024 <= numbers[0] <= 65526:
        raise Usage("NIGHTLY_HUB_PORT must be a port from 1024 to 65526")
    if numbers[3] < 1:
        raise Usage("NIGHTLY_KEEP_RUNS must keep at least this night")
    return Settings(hub_repo, erplora_root, env.get("SAAS_REPO") or f"{erplora_root}/saas",
                    env.get("NIGHTLY_DIR") or f"{env['HOME']}/.erplora/hub-nightly-e2e", *numbers)


@dataclass
class Arguments:
    shard: str = ""
    specs: list[str] = field(default_factory=list)


def value_of(words: list[str], missing: str) -> str:
    if not words:
        raise Usage(missing)
    return words.pop(0)


def spec_of(words: list[str]) -> str:
    spec = value_of(words, "--spec needs a spec")
    if not fnmatch.fnmatchcase(spec, "tests/e2e/*.spec.ts"):
        raise Usage(f"--spec takes tests/e2e/<name>.spec.ts, not «{spec}»")
    if NOT_PLAIN.search(spec):
        raise Usage(f"--spec takes a plain path inside tests/e2e, not «{spec}»")
    return spec


def shard_of(words: list[str]) -> str:
    """Playwright's --shard: share i of n, from 1 to n."""
    shard = value_of(words, "--shard needs <i>/<n>")
    found = SHARD.fullmatch(shard)
    if not found or int(found.group(1)) > int(found.group(2)):
        raise Usage(f"--shard takes <i>/<n> with i from 1 to n, not «{shard}»")
    return shard


def parse(argv: list[str]) -> Arguments:
    arguments = Arguments()
    words = list(argv)
    while words:
        word = words.pop(0)
        if word == "--spec":
            arguments.specs.append(spec_of(words))
        elif word == "--shard":
            arguments.shard = shard_of(words)
        else:
            raise Usage(f"unknown argument «{word}»")
    return arguments


def take_lock(lock: str) -> bool:
    try:
        os.mkdir(lock)
    except OSError:
        holder = Path(lock, "pid").read_text().strip() if os.path.isfile(f"{lock}/pid") else ""
        if holder.lstrip("-").isdigit() and alive(int(holder)):
            say(f"another night is running (pid {holder}): nothing to do (exit 3)")
            return False
        say(f"the night of pid {holder or '?'} is gone: taking its lock over")
        remove(lock)
        os.mkdir(lock)
    Path(lock, "pid").write_text(f"{os.getpid()}\n")
    return True


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def send_output_to(log: str) -> subprocess.Popen | None:
    """In a terminal or GitHub Actions the night's output also goes to the log; otherwise only to the log. tee
    runs in a session of its own, so a Ctrl-C reaches the night and its clean-up still writes to the log."""
    sys.stdout.flush()
    tee = None
    if os.isatty(1) or os.environ.get("GITHUB_ACTIONS") == "true":
        tee = subprocess.Popen(["tee", "-a", log], stdin=subprocess.PIPE, start_new_session=True)
        target = tee.stdin.fileno()
    else:
        target = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
    os.dup2(target, 1)
    os.dup2(target, 2)
    if tee:
        tee.stdin.close()
    else:
        os.close(target)
    return tee


def close_output(tee: subprocess.Popen | None) -> None:
    """Waits for tee to write the last lines, so whoever reads the output after the night finds them."""
    if tee is None:
        return
    sys.stdout.flush()
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    os.close(null)
    with contextlib.suppress(subprocess.TimeoutExpired):
        tee.wait(timeout=5)


def prune_runs(runs: str, keep: int) -> None:
    every = sorted(entry.path for entry in os.scandir(runs) if entry.is_dir(follow_symlinks=False))
    for old in every[:-keep]:
        remove(old)


def one_night(night: Night) -> int:
    say(f"night in {night.folder}, Hub on {night.hub_port}, SaaS on {night.saas_port}, databases {night.hub_db} and"
        f" {night.saas_db}")
    result, failed_step = night.specs_result()
    commit = night.commit()
    night.clean_up()
    status = night.report(result, failed_step, commit)
    prune_runs(f"{night.settings.nightly_dir}/runs", night.settings.keep_runs)
    say(f"night over: {result}")
    return status


def run_night(settings: Settings, arguments: Arguments) -> int:
    # The night removes these two folders by force: they are its own worktrees (.git is a file) or nothing, never a
    # checkout somebody works in.
    for folder in (f"{settings.nightly_dir}/hub", f"{settings.nightly_dir}/saas"):
        if os.path.isdir(f"{folder}/.git"):
            raise Usage(f"{folder} is a checkout of its own, not a worktree of the night: choose another NIGHTLY_DIR")
    os.makedirs(f"{settings.nightly_dir}/runs", exist_ok=True)
    lock = f"{settings.nightly_dir}/lock"
    if not take_lock(lock):
        return 3
    folder = f"{settings.nightly_dir}/runs/{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    os.makedirs(folder, exist_ok=True)
    tee = send_output_to(f"{folder}/night.log")
    os.environ["COMPOSE_FILE"] = f"{settings.erplora_root}/compose.yaml"
    for name in UNSET:
        os.environ.pop(name, None)
    stack = Night(settings, folder, arguments.specs, arguments.shard)
    SIGNALS.install()
    try:
        status = one_night(stack)
    except Interrupted as stop:
        status = stop.code
    finally:
        stack.clean_up()
        remove(lock)
    close_output(tee)
    return status


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        settings = settings_from(os.environ)
        arguments = parse(sys.argv[1:] if argv is None else argv)
        return run_night(settings, arguments)
    except Usage as error:
        print(f"nightly-e2e: {error} (exit 2)\n{USAGE}", file=sys.stderr)
        return 2
    except Interrupted as stop:
        return stop.code
    except subprocess.CalledProcessError as error:
        return error.returncode


if __name__ == "__main__":
    sys.exit(main())
