"""What the hub's deploy (ecs_deploy.py) and its rollback (ecs_rollback.py) share: how they run aws and stop, how they
read what they are given and what aws answers, how they tell a revision of their environment from another's, and how
they finish: watching the services' rollout and recording the settings and the image tag.

A refusal exits 1 after its ::error:: line; an aws call or a settings' script that fails ends the run with its own exit
code (128 + N when signal N killed it). The answers of aws are read with jq's rules, and one that cannot be read ends the
run with jq's exit code for it, 5. Only the standard library: the workflows run them with the runner's python3.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# This repo deploys the hub; the saas repo keeps its own copy of these scripts.
PROJECT = "hub"
ENVIRONMENTS = ("prod", "pre")
PRIMARY_QUERY = "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]"
# jq's exit code for an answer it cannot read.
UNREADABLE = 5
JSON_BLANK = " \t\n\r"


class Stop(Exception):
    """Ends the run with an exit code; what it had to say is already said."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def program() -> str:
    return Path(sys.argv[0]).name


def error(line: str) -> None:
    print(f"::error::{line}", file=sys.stderr)


def refusal(line: str) -> Stop:
    error(line)
    return Stop(1)


def unreadable(what: str, reason: Exception) -> Stop:
    print(f"{program()}: {what} cannot be read: {reason}", file=sys.stderr)
    return Stop(UNREADABLE)


def run(command: list[str], stdout=subprocess.PIPE) -> str:
    """Runs a command with its stderr passing through; a failure ends the run with its exit code. Returns what it
    wrote without its trailing newlines, when it is read."""
    try:
        done = subprocess.run(command, stdout=stdout, check=False)
    except FileNotFoundError:
        print(f"{program()}: {command[0]}: command not found", file=sys.stderr)
        raise Stop(127) from None
    if done.returncode != 0:
        raise Stop(done.returncode if done.returncode > 0 else 128 - done.returncode)
    return "" if done.stdout is None else done.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def aws(*arguments: str, stdout=subprocess.PIPE) -> str:
    return run(["aws", *arguments], stdout=stdout)


@dataclass
class Release:
    """Where a deploy or a rollback works: its region, environment and cluster, and the seconds of its waits as given
    (the messages say them so)."""

    region: str
    environment: str
    cluster: str
    seconds: dict[str, str]

    @property
    def suffix(self) -> str:
        return "" if self.environment == "prod" else "-pre"

    @property
    def prefix(self) -> str:
        return f"erplora-{self.environment}"

    def seconds_of(self, name: str) -> int:
        return int(self.seconds[name])


def environment_given(env: Mapping[str, str], consequence: str) -> str:
    environment = env.get("ENVIRONMENT", "")
    if environment not in ENVIRONMENTS:
        raise refusal(f"ENVIRONMENT must be prod or pre, not '{environment}'{consequence}")
    return environment


def seconds_given(env: Mapping[str, str], defaults: Mapping[str, str], consequence: str) -> dict[str, str]:
    """Each setting of <defaults> as given, or its default when it is missing or empty; one that is not a number of
    seconds is refused."""
    seconds = {name: env.get(name) or default for name, default in defaults.items()}
    for name, value in seconds.items():
        if not re.fullmatch("[0-9]+", value):
            raise refusal(f"{name} must be a number of seconds, not '{value}'{consequence}")
    return seconds


def values(text: str) -> list:
    """What jq reads from an answer: nothing from a blank one, else its one JSON value."""
    return [json.loads(text)] if text.strip(JSON_BLANK) else []


def key(value: object, name: str) -> object:
    """jq's `.name`: null on null; anything but an object or null cannot be read through."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    raise TypeError(f"cannot index {type(value).__name__} with {name!r}")


def each(value: object) -> list:
    """jq's `.[]`: the items of a list or the values of an object; nothing else can be iterated."""
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    raise TypeError(f"cannot iterate over {type(value).__name__}")


def tags(found: object) -> list:
    """jq's `.tags[]?`: tags that cannot be iterated are none (a revision that is no object fails where its definition
    is read)."""
    try:
        return each(key(found, "tags"))
    except TypeError:
        return []


def otherwise(value: object, default: object) -> object:
    """jq's `value // default`: only null and false give way."""
    return default if value is None or value is False else value


def compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def text(value: object) -> str:
    """A value as jq writes it inside a string: text as it is, anything else as compact JSON."""
    return value if isinstance(value, str) else compact(value)


def written(value: object) -> str:
    """A value as `jq -r` writes it and $(…) keeps it: text as it is, anything else as indented JSON, without its
    trailing newlines."""
    return (value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)).rstrip("\n")


def role_is(found: dict, name: str, prefix: str) -> bool:
    arn = key(key(found, "taskDefinition"), name)
    return isinstance(arn, str) and re.search(rf"^arn:aws[a-z-]*:iam::[0-9]+:role/{prefix}-", arn) is not None


def of_its_environment(found: list, release: Release) -> bool:
    """`any(.tags[]?; .key == "Environment" and .value == $environment)` and both roles of the environment's prefix, as
    `jq -e` answers it: a revision it cannot read through is not of the environment either."""
    try:
        tagged = bool(found) and any(
            key(tag, "key") == "Environment" and key(tag, "value") == release.environment for tag in tags(found[0]))
        return tagged and all(role_is(found[0], name, release.prefix) for name in ("taskRoleArn", "executionRoleArn"))
    except TypeError:
        return False


def carried(found: list) -> str:
    """What a refused revision carries: its first Environment tag and its roles, "none" for what it lacks."""
    if not found:
        return ""
    environment = next((key(tag, "value") for tag in tags(found[0]) if key(tag, "key") == "Environment"), None)
    definition = key(found[0], "taskDefinition")
    said = (text(otherwise(value, "none")) for value in (
        environment, key(definition, "taskRoleArn"), key(definition, "executionRoleArn")))
    return "Environment={}, task role {}, execution role {}".format(*said).rstrip("\n")


def refuse_another_environment(found: list, subject: str, release: Release, consequence: str) -> None:
    """Refuses <subject>, the revision found, unless it is of the release's environment: the deploy roles can register
    any family (ECS takes no resource there), so another environment's role could have left it."""
    if not of_its_environment(found, release):
        raise refusal(f"{subject} is no revision of {release.environment} ({carried(found)}){consequence}")


def primary(release: Release, service: str) -> tuple[str, str]:
    """The task definition and the rollout state of the service's PRIMARY deployment, split from aws's first line as
    bash's `read` split it: the first word, and the rest of the line."""
    line = aws("ecs", "describe-services", "--cluster", release.cluster, "--services", service,
               "--region", release.region, "--query", PRIMARY_QUERY, "--output", "text").split("\n", 1)[0]
    words = re.split("[ \t]+", line.strip(" \t"), maxsplit=1)
    return words[0], words[1] if len(words) > 1 else ""


def wait_until_stable(release: Release, services: list[str]) -> None:
    aws("ecs", "wait", "services-stable", "--cluster", release.cluster, "--region", release.region,
        "--services", *services, stdout=None)


def still_rolling_out(release: Release, pending: list[str], targets: dict[str, str]) -> list[str]:
    """The services of <pending> whose rollout is still in progress; one that runs another revision, or whose rollout
    FAILED, ends the run once every service was read."""
    in_progress, failed = [], False
    for service in pending:
        task_definition, state = primary(release, service)
        if task_definition != targets[service] or state == "FAILED":
            error(f"{service} runs {task_definition} ({state}), not {targets[service]}; rolled back by the circuit "
                  "breaker? See the service events")
            failed = True
        elif state != "COMPLETED":
            in_progress.append(service)
    if failed:
        raise Stop(1)
    return in_progress


def watch_rollout(release: Release, targets: dict[str, str]) -> None:
    """services-stable can return while a PRIMARY deployment is still IN_PROGRESS: polls the services whose rollout
    has not completed yet (<targets>: service -> the revision it must run), all of them on the same clock."""
    pending = list(targets)
    waited = 0
    while True:
        pending = still_rolling_out(release, pending, targets)
        if not pending:
            return
        if waited >= release.seconds_of("ROLLOUT_TIMEOUT_SECONDS"):
            for service in pending:
                error(f"rollout of {service} did not complete in {release.seconds['ROLLOUT_TIMEOUT_SECONDS']} s; "
                      "see the service events")
            raise Stop(1)
        time.sleep(release.seconds_of("POLL_SECONDS"))
        waited += release.seconds_of("POLL_SECONDS")


def record(release: Release, workdir: Path, image_tag: str) -> None:
    """Records the settings the settings' script wrote in <workdir>/app_env.json and the tag, once the services run
    their revisions, so the revisions Terraform registers, and with them the scheduled tasks, keep them (ERPlora/aws
    README, "Ajustes de la app")."""
    settings = (workdir / "app_env.json").read_text(encoding="utf-8", errors="surrogateescape").rstrip("\n")
    parameter = f"/erplora/{release.environment}/{PROJECT}"
    for name, value in (("app_env", settings), ("image_tag", image_tag)):
        aws("ssm", "put-parameter", "--name", f"{parameter}/{name}", "--value", value, "--type", "String",
            "--overwrite", "--region", release.region, stdout=subprocess.DEVNULL)
    print(f"recorded its settings and {image_tag} in {parameter}/app_env and image_tag")


def main(work: Callable[[], None]) -> int:
    """Runs <work> and returns its exit code. Each line goes out as it is written, among what aws and the settings'
    scripts write, and as the bytes it was given."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape", line_buffering=True)
    try:
        work()
    except Stop as stop:
        return stop.code
    return 0
