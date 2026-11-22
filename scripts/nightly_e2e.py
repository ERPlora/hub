#!/usr/bin/env python3
"""The Hub's nightly browser run: every spec of tests/e2e, once a night, on the newest origin/main, on the Mac.
Never a check: a red night stops no PR and no deploy. It keeps ONE open issue instead (scripts/e2e_report.py): a red
night opens it or comments on it, and the first green night closes it.

  python3 scripts/nightly_e2e.py [--no-publish] [--spec tests/e2e/<name>.spec.ts]...   every spec, or the ones named
  python3 scripts/nightly_e2e.py install-launchd [--at HH:MM]                           every night by launchd (02:17)
  python3 scripts/nightly_e2e.py uninstall-launchd

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
answer) · NIGHTLY_KEEP_RUNS (7) · GH_REPO (ERPlora/hub).
Exit: 0 green · 1 red · 2 usage · 3 another night is running · 4 install-launchd without the script in HUB_REPO ·
130 or 143 stopped by INT or TERM. Only the standard library: the Mac runs it with its own python3.
"""

from __future__ import annotations

import contextlib
import fnmatch
import os
import plistlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from nightly_stack import HERE, SIGNALS, Interrupted, Night, Settings, git_folder, ok, remove, run, say

LABEL = "com.erplora.hub.nightly-e2e"
USAGE = ("usage: nightly_e2e.py [--no-publish] [--spec tests/e2e/<name>.spec.ts]... | install-launchd [--at HH:MM]"
         " | uninstall-launchd")
NUMBERS = (("NIGHTLY_HUB_PORT", "9770"), ("NIGHTLY_MAX_MINUTES", "360"), ("NIGHTLY_START_SECONDS", "300"),
           ("NIGHTLY_KEEP_RUNS", "7"))
NOT_PLAIN = re.compile(r"\.\.|[^A-Za-z0-9._/-]")
CLOCK = re.compile(r"[01][0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]")
# Each command gets its stack's variables explicitly, none from the shell that started the night (a worker's DB_NAME
# would point the SaaS at a Hub database), and the specs that spend real tokens or open a visible browser stay off.
UNSET = ("DB_NAME", "SAAS_URL", "E2E_HUB_PORT", "VITE_DEV_PORT", "E2E_SAAS_DB", "E2E_SAAS_DIR", "E2E_MAIL_DIR",
         "E2E_SAAS_PORT", "HUB_INTERNAL_URL", "EMAIL_FILE_PATH", "E2E_OUTPUT_DIR", "CATALOG_DIR", "QA_REAL_PROVIDER",
         "E2E_HEADED")
WRITTEN_BY = b"<!-- Written by nightly_e2e.py install-launchd: run it again instead of editing this file. -->\n"


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
                    env.get("NIGHTLY_DIR") or f"{env['HOME']}/.erplora/hub-nightly-e2e", *numbers,
                    env.get("GH_REPO") or "ERPlora/hub")


@dataclass
class Arguments:
    command: str = "night"
    publish: bool = True
    at: str = "02:17"
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


def parse(argv: list[str]) -> Arguments:
    arguments = Arguments()
    words = list(argv)
    if words and words[0] in ("install-launchd", "uninstall-launchd"):
        arguments.command = words.pop(0)
    while words:
        word = words.pop(0)
        given = f"{arguments.command}:{word}"
        if given == "night:--no-publish":
            arguments.publish = False
        elif given == "night:--spec":
            arguments.specs.append(spec_of(words))
        elif given == "install-launchd:--at":
            arguments.at = value_of(words, "--at needs HH:MM")
        else:
            raise Usage(f"unknown argument «{word}»")
    return arguments


# ── install-launchd / uninstall-launchd: the Mac's timer ──────────────────────────────────────────────────────────
def launch_agent() -> str:
    return f"{os.environ['HOME']}/Library/LaunchAgents/{LABEL}.plist"


def agent(settings: Settings, script: str, at: str) -> bytes:
    hour, minute = (int(part) for part in at.split(":"))
    log = f"{settings.nightly_dir}/launchd.log"
    names = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ["HOME"], "HUB_REPO": settings.hub_repo,
             "ERPLORA_ROOT": settings.erplora_root, "SAAS_REPO": settings.saas_repo,
             "NIGHTLY_DIR": settings.nightly_dir, "NIGHTLY_HUB_PORT": str(settings.port), "GH_REPO": settings.gh_repo}
    content = {"Label": LABEL, "ProgramArguments": [script], "EnvironmentVariables": names,
               "StartCalendarInterval": {"Hour": hour, "Minute": minute}, "RunAtLoad": False,
               "StandardOutPath": log, "StandardErrorPath": log}
    return plistlib.dumps(content, sort_keys=False).replace(b"<plist ", WRITTEN_BY + b"<plist ", 1)


def write_at_once(path: str, content: bytes) -> bool:
    temporary = f"{path}.tmp.{os.getpid()}"
    try:
        Path(temporary).write_bytes(content)
        os.replace(temporary, path)
    except OSError:
        remove(temporary)
        return False
    return True


def install(settings: Settings, at: str) -> int:
    plist = launch_agent()
    uid = os.getuid()
    if not CLOCK.fullmatch(at):
        raise Usage(f"--at takes HH:MM from 00:00 to 23:59, not «{at}»")
    # A linked worktree goes away with its branch, and the agent would then run nothing, every night, unseen.
    if git_folder(settings.hub_repo, "--git-dir") != git_folder(settings.hub_repo, "--git-common-dir"):
        raise Usage(f"{settings.hub_repo} is a linked worktree: run install-launchd from the main checkout of the Hub")
    script = f"{settings.hub_repo}/scripts/nightly_e2e.py"
    if not os.access(script, os.X_OK):
        print(f"nightly-e2e: {script} is missing or not executable (exit 4)", file=sys.stderr)
        return 4
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    os.makedirs(settings.nightly_dir, exist_ok=True)
    if not write_at_once(plist, agent(settings, script, at)):
        print(f"nightly-e2e: cannot write {plist} (exit 1)", file=sys.stderr)
        return 1
    run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not ok(["launchctl", "bootstrap", f"gui/{uid}", plist]):
        print(f"nightly-e2e: launchctl bootstrap gui/{uid} {plist} failed (exit 1)", file=sys.stderr)
        return 1
    say(f"{LABEL} loaded: every night at {at} ({plist}; what launchd sees, in {settings.nightly_dir}/launchd.log)")
    return 0


def uninstall() -> int:
    plist = launch_agent()
    run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    remove(plist)
    say(f"{LABEL} unloaded, {plist} removed")
    return 0


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
    """In a terminal or GitHub Actions the night's output also goes to the log; under launchd only to the log. tee
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


def one_night(night: Night, publish: bool) -> int:
    say(f"night in {night.folder}, Hub on {night.hub_port}, SaaS on {night.saas_port}, databases {night.hub_db} and"
        f" {night.saas_db}")
    result, failed_step = night.specs_result()
    commit = night.commit()
    night.clean_up()
    status = night.report(result, failed_step, commit, publish)
    prune_runs(f"{night.settings.nightly_dir}/runs", night.settings.keep_runs)
    say(f"night over: {result}")
    SIGNALS.checkpoint()
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
    stack = Night(settings, folder, arguments.specs)
    SIGNALS.install()
    try:
        status = one_night(stack, arguments.publish)
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
        os.environ["GH_REPO"] = settings.gh_repo
        arguments = parse(sys.argv[1:] if argv is None else argv)
        if arguments.command == "uninstall-launchd":
            return uninstall()
        if arguments.command == "install-launchd":
            return install(settings, arguments.at)
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
