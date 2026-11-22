#!/usr/bin/env python3
"""Deploys an image tag of the hub to one environment, in that environment's ECS cluster (erplora-<environment>),
touching only its hub task families and services:
  prod: cluster erplora-prod, families erplora-prod-{hub,worker,hub-migrate}, services hub and worker, image
        erplora/hub;
  pre:  cluster erplora-pre, families erplora-pre-{hub,worker,hub-migrate}, services hub-pre and worker-pre (the
        team's pre-production), image erplora/hub-pre; the containers keep the short names.
  0. reads the latest ACTIVE revision of each family and refuses, before registering anything, one that is not of this
     environment: tag Environment=<environment> and task and execution roles erplora-<environment>-* (the deploy roles
     can register any family: ECS takes no resource there, so this guard keeps pre's role from turning a prod revision
     into its own and back);
  1. registers a new revision of each family from that one, with its tags, changing only the image of the containers
     that run the hub image (the app and its pgbouncer sidecar) and the app's settings, exactly those of
     deploy/app-env.json in that commit, which deploy/app_env.py checks first, refusing any that break a rule (in prod,
     changing VERIFACTU_PRODUCTION_ENABLED takes CONFIRM_PROTECTED); Terraform owns the rest;
  2. runs the migration (hub-migrate) on the new revision and polls it until it is STOPPED; if it fails, never ran or
     outlasts MIGRATE_TIMEOUT_SECONDS (the task is left running), the deploy stops before any service changes;
  3. moves the services to the new revisions (in pre also to one task: a push wakes pre up when its evening stop has
     put it to sleep), waits until they are stable and then polls each one's PRIMARY deployment until it is the new
     revision, COMPLETED: ECS marks it COMPLETED seconds to a minute after services-stable returns, once the old tasks
     drain from the ALB. A FAILED rollout or another revision as PRIMARY (with rollback = true the circuit breaker puts
     the old one back and the wait still succeeds) fails at once; a rollout that outlasts ROLLOUT_TIMEOUT_SECONDS fails
     too;
  4. records the settings in /erplora/<environment>/hub/app_env and the tag in .../image_tag, so the revisions
     Terraform registers, and with them the scheduled tasks, keep them (ERPlora/aws README, "Ajustes de la app").
Never db-bootstrap: the deploy role cannot pass its roles (ERPlora/aws stacks/prod/deploy_role.tf).
Rollback: the circuit breaker reverts a broken deploy; back to the previous revisions, the rollback workflow
  (ecs-rollback.sh); back to a release, the deploy workflow with that release.

  python3 scripts/ecs_deploy.py   (in the checkout of the repository)

Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA), ENVIRONMENT (prod | pre); optional
     CLUSTER (erplora-<environment>), POLL_SECONDS (15), MIGRATE_TIMEOUT_SECONDS (3600), ROLLOUT_TIMEOUT_SECONDS (600),
     CONFIRM_PROTECTED (NAME=value).
A refusal exits 1 after its ::error:: line; an aws call or app_env.py that fails ends the deploy with its own exit code
(128 + N when signal N killed it). The answers of aws are read with jq's rules, and one that cannot be read ends the
deploy with jq's exit code for it, 5. Only the standard library: the workflow runs it with the runner's python3.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# This repo deploys the hub; the saas repo keeps its own copy of this script.
PROJECT = "hub"
NAME = Path(__file__).name
APP_ENV = Path(__file__).resolve().parents[1] / "deploy" / "app_env.py"
FAMILIES = ("hub", "worker", "hub-migrate")
MIGRATION = "hub-migrate"
# The families of the services; each one's service is <family><suffix>.
SERVICES = ("hub", "worker")
# One-off tasks run like the worker: same subnets, its security group, public IP.
NETWORK_SERVICE = "worker"
REQUIRED = ("AWS_REGION", "REGISTRY", "IMAGE_TAG", "ENVIRONMENT")
ENVIRONMENTS = ("prod", "pre")
SECONDS = {"POLL_SECONDS": "15", "MIGRATE_TIMEOUT_SECONDS": "3600", "ROLLOUT_TIMEOUT_SECONDS": "600"}
READ_ONLY = ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt",
             "registeredBy", "deregisteredAt")
PRIMARY_QUERY = "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]"
# jq's exit code for an answer it cannot read.
UNREADABLE = 5
JSON_BLANK = " \t\n\r"


class Stop(Exception):
    """Ends the deploy with an exit code; what it had to say is already said."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def error(line: str) -> None:
    print(f"::error::{line}", file=sys.stderr)


def refusal(line: str) -> Stop:
    error(line)
    return Stop(1)


def unreadable(what: str, reason: Exception) -> Stop:
    print(f"{NAME}: {what} cannot be read: {reason}", file=sys.stderr)
    return Stop(UNREADABLE)


def run(command: list[str], stdout=subprocess.PIPE) -> str:
    """Runs a command with its stderr passing through; a failure ends the deploy with its exit code. Returns what it
    wrote without its trailing newlines, when it is read."""
    try:
        done = subprocess.run(command, stdout=stdout, check=False)
    except FileNotFoundError:
        print(f"{NAME}: {command[0]}: command not found", file=sys.stderr)
        raise Stop(127) from None
    if done.returncode != 0:
        raise Stop(done.returncode if done.returncode > 0 else 128 - done.returncode)
    return "" if done.stdout is None else done.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def aws(*arguments: str, stdout=subprocess.PIPE) -> str:
    return run(["aws", *arguments], stdout=stdout)


@dataclass
class Deploy:
    region: str
    registry: str
    image_tag: str
    environment: str
    cluster: str
    confirm: str
    # As given: the messages say them so.
    seconds: dict[str, str]
    workdir: Path = Path()
    arns: dict[str, str] = field(default_factory=dict)

    @property
    def suffix(self) -> str:
        return "" if self.environment == "prod" else "-pre"

    @property
    def prefix(self) -> str:
        return f"erplora-{self.environment}"

    @property
    def project_image(self) -> str:
        return f"{self.registry}/erplora/{PROJECT}{self.suffix}:"

    @property
    def image(self) -> str:
        return f"{self.project_image}{self.image_tag}"

    def seconds_of(self, name: str) -> int:
        return int(self.seconds[name])


def configured(env: Mapping[str, str]) -> Deploy:
    """The deploy the environment asks for: a missing setting, an unknown environment or a number of seconds that is
    none is refused before any aws call."""
    for name in REQUIRED:
        if not env.get(name):
            raise refusal(f"{name} is required")
    environment = env["ENVIRONMENT"]
    if environment not in ENVIRONMENTS:
        raise refusal(f"ENVIRONMENT must be prod or pre, not '{environment}'")
    seconds = {name: env.get(name) or default for name, default in SECONDS.items()}
    for name, value in seconds.items():
        if not re.fullmatch("[0-9]+", value):
            raise refusal(f"{name} must be a number of seconds, not '{value}'")
    return Deploy(region=env["AWS_REGION"], registry=env["REGISTRY"], image_tag=env["IMAGE_TAG"],
                  environment=environment, cluster=env.get("CLUSTER") or f"erplora-{environment}",
                  confirm=env.get("CONFIRM_PROTECTED", ""), seconds=seconds)


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


def role_is(found: dict, name: str, prefix: str) -> bool:
    arn = key(key(found, "taskDefinition"), name)
    return isinstance(arn, str) and re.search(rf"^arn:aws[a-z-]*:iam::[0-9]+:role/{prefix}-", arn) is not None


def of_its_environment(found: list, deploy: Deploy) -> bool:
    """`any(.tags[]?; .key == "Environment" and .value == $environment)` and both roles of the environment's prefix, as
    `jq -e` answers it: a revision it cannot read through is not of the environment either."""
    try:
        tagged = bool(found) and any(
            key(tag, "key") == "Environment" and key(tag, "value") == deploy.environment for tag in tags(found[0]))
        return tagged and all(role_is(found[0], name, deploy.prefix) for name in ("taskRoleArn", "executionRoleArn"))
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


def with_new_image(container: object, deploy: Deploy) -> object:
    image = otherwise(key(container, "image"), "")
    if not isinstance(image, str):
        raise TypeError("startswith() requires string inputs")
    if image.startswith(deploy.project_image):
        container["image"] = deploy.image
    return container


def revision_of(found: dict, deploy: Deploy) -> dict:
    """The revision to register from the one found: the new image, without the fields ECS sets, with its tags."""
    definition = found["taskDefinition"]
    containers = each(definition.get("containerDefinitions"))
    definition["containerDefinitions"] = [with_new_image(container, deploy) for container in containers]
    for name in READ_ONLY:
        definition.pop(name, None)
    definition["tags"] = found["tags"]
    return definition


def checked(answer: str, family: str, deploy: Deploy) -> dict:
    found = values(answer)
    if not of_its_environment(found, deploy):
        raise refusal(f"{family} is no revision of {deploy.environment} ({carried(found)}); nothing was registered")
    return revision_of(found[0], deploy)


def prepare(deploy: Deploy, name: str) -> None:
    """Reads the latest ACTIVE revision of <name>'s family, refuses it if it is not of this environment, and writes the
    new revision to <workdir>/<name>.json."""
    family = f"{deploy.prefix}-{name}"
    answer = aws("ecs", "describe-task-definition", "--task-definition", family, "--include", "TAGS",
                 "--region", deploy.region, "--output", "json")
    try:
        revision = checked(answer, family, deploy)
    except (ValueError, TypeError) as reason:
        raise unreadable(family, reason) from None
    if not any(key(container, "image") == deploy.image for container in revision["containerDefinitions"]):
        raise refusal(f"{family} has no container of the image {deploy.project_image}<tag>; nothing was registered")
    (deploy.workdir / f"{name}.json").write_text(json.dumps(revision, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8", errors="surrogateescape")


def register(deploy: Deploy, name: str) -> None:
    deploy.arns[name] = aws("ecs", "register-task-definition", "--cli-input-json",
                            f"file://{deploy.workdir}/{name}.json", "--region", deploy.region,
                            "--query", "taskDefinition.taskDefinitionArn", "--output", "text")
    print(f"registered {deploy.arns[name]}")


def started(answer: str) -> tuple[str, str]:
    """The task run-task started and its failures, read as jq's `.tasks[0].taskArn // empty` and `.failures` read
    them: "" for no task, and nothing at all from a blank answer."""
    try:
        found = values(answer)
        arn = key(first(key(found[0], "tasks")), "taskArn") if found else None
    except (ValueError, TypeError) as reason:
        raise unreadable("the answer of run-task", reason) from None
    if not found:
        return "", ""
    failures = compact(key(found[0], "failures"))
    if arn is None or arn is False:
        return "", failures
    return (arn if isinstance(arn, str) else json.dumps(arn, indent=2, ensure_ascii=False)).rstrip("\n"), failures


def first(value: object) -> object:
    """jq's `.[0]`: null on null or an empty list; anything but a list or null cannot be read through."""
    if isinstance(value, list) or value is None:
        return value[0] if value else None
    raise TypeError(f"cannot index {type(value).__name__} with a number")


def describe_task(deploy: Deploy, task: str, query: str) -> str:
    return aws("ecs", "describe-tasks", "--cluster", deploy.cluster, "--tasks", task, "--region", deploy.region,
               "--query", query, "--output", "text")


def wait_until_stopped(deploy: Deploy, task: str) -> None:
    waited = 0
    while True:
        status = describe_task(deploy, task, "tasks[0].lastStatus")
        if status == "STOPPED":
            return
        if waited >= deploy.seconds_of("MIGRATE_TIMEOUT_SECONDS"):
            raise refusal(f"{MIGRATION} is still {status} after {deploy.seconds['MIGRATE_TIMEOUT_SECONDS']}s; it was "
                          f"left running ({task}) and no service changed; logs in /ecs/{deploy.prefix}-{MIGRATION}")
        time.sleep(deploy.seconds_of("POLL_SECONDS"))
        waited += deploy.seconds_of("POLL_SECONDS")


def migrate(deploy: Deploy, network: str) -> None:
    """Runs the migration on its new revision and polls it until it is STOPPED; its container has the family's name
    (ERPlora/aws modules/ecs-service)."""
    answer = aws("ecs", "run-task", "--cluster", deploy.cluster, "--launch-type", "FARGATE",
                 "--task-definition", deploy.arns[MIGRATION], "--network-configuration", network,
                 "--started-by", f"deploy-{deploy.image_tag[:12]}", "--region", deploy.region, "--output", "json")
    task, failures = started(answer)
    if not task:
        raise refusal(f"{MIGRATION} did not start: {failures}")
    print(f"running {MIGRATION}: {task}")
    wait_until_stopped(deploy, task)
    code = describe_task(deploy, task, f"tasks[0].containers[?name=='{MIGRATION}'].exitCode | [0]")
    if code == "None":
        raise refusal(f"{MIGRATION} stopped without running: {describe_task(deploy, task, 'tasks[0].stoppedReason')}")
    if code != "0":
        raise refusal(f"{MIGRATION} exited with code {code}; logs in /ecs/{deploy.prefix}-{MIGRATION}")


def move(deploy: Deploy) -> dict[str, str]:
    """Moves each service to its family's new revision and waits until they are stable; pre sleeps every evening
    (desired count 0), so a deploy wakes it up with one task per service. Returns the revision each service must run."""
    wake = [] if deploy.environment == "prod" else ["--desired-count", "1"]
    targets = {}
    for name in SERVICES:
        service = f"{name}{deploy.suffix}"
        aws("ecs", "update-service", "--cluster", deploy.cluster, "--service", service,
            "--task-definition", deploy.arns[name], *wake, "--region", deploy.region, stdout=subprocess.DEVNULL)
        print(f"updated {service}")
        targets[service] = deploy.arns[name]
    aws("ecs", "wait", "services-stable", "--cluster", deploy.cluster, "--region", deploy.region,
        "--services", *targets, stdout=None)
    return targets


def primary(deploy: Deploy, service: str) -> tuple[str, str]:
    """The task definition and the rollout state of the service's PRIMARY deployment, split from aws's first line as
    bash's `read` split it: the first word, and the rest of the line."""
    line = aws("ecs", "describe-services", "--cluster", deploy.cluster, "--services", service,
               "--region", deploy.region, "--query", PRIMARY_QUERY, "--output", "text").split("\n", 1)[0]
    words = re.split("[ \t]+", line.strip(" \t"), maxsplit=1)
    return words[0], words[1] if len(words) > 1 else ""


def still_rolling_out(deploy: Deploy, pending: list[str], targets: dict[str, str]) -> list[str]:
    """The services of <pending> whose rollout is still in progress; one that runs another revision, or whose rollout
    FAILED, ends the deploy once every service was read."""
    in_progress, failed = [], False
    for service in pending:
        task_definition, state = primary(deploy, service)
        if task_definition != targets[service] or state == "FAILED":
            error(f"{service} runs {task_definition} ({state}), not {targets[service]}; rolled back by the circuit "
                  "breaker? See the service events")
            failed = True
        elif state != "COMPLETED":
            in_progress.append(service)
    if failed:
        raise Stop(1)
    return in_progress


def watch_rollout(deploy: Deploy, targets: dict[str, str]) -> None:
    """services-stable can return while a PRIMARY deployment is still IN_PROGRESS: polls the services whose rollout
    has not completed yet, all of them on the same clock."""
    pending = list(targets)
    waited = 0
    while True:
        pending = still_rolling_out(deploy, pending, targets)
        if not pending:
            return
        if waited >= deploy.seconds_of("ROLLOUT_TIMEOUT_SECONDS"):
            for service in pending:
                error(f"rollout of {service} did not complete in {deploy.seconds['ROLLOUT_TIMEOUT_SECONDS']} s; "
                      "see the service events")
            raise Stop(1)
        time.sleep(deploy.seconds_of("POLL_SECONDS"))
        waited += deploy.seconds_of("POLL_SECONDS")


def record(deploy: Deploy) -> None:
    """Records the settings app_env.py wrote and the tag, once the services run the new revisions."""
    settings = (deploy.workdir / "app_env.json").read_text(encoding="utf-8", errors="surrogateescape").rstrip("\n")
    parameter = f"/erplora/{deploy.environment}/{PROJECT}"
    for name, value in (("app_env", settings), ("image_tag", deploy.image_tag)):
        aws("ssm", "put-parameter", "--name", f"{parameter}/{name}", "--value", value, "--type", "String",
            "--overwrite", "--region", deploy.region, stdout=subprocess.DEVNULL)
    print(f"recorded its settings and {deploy.image_tag} in {parameter}/app_env and image_tag")


def deploy_all(deploy: Deploy) -> None:
    # Every revision is read and checked, and gets its settings, before any is registered.
    for name in FAMILIES:
        prepare(deploy, name)
    run([sys.executable, str(APP_ENV), str(deploy.workdir), deploy.environment, deploy.image_tag, deploy.region,
         f"--confirm={deploy.confirm}"], stdout=None)
    for name in FAMILIES:
        register(deploy, name)
    network = aws("ecs", "describe-services", "--cluster", deploy.cluster, "--services",
                  f"{NETWORK_SERVICE}{deploy.suffix}", "--region", deploy.region,
                  "--query", "services[0].networkConfiguration", "--output", "json")
    migrate(deploy, network)
    watch_rollout(deploy, move(deploy))
    print("services stable on the new revisions")
    record(deploy)


def main() -> int:
    # Each line goes out as it is written, among what aws and app_env.py write, and as the bytes it was given.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape", line_buffering=True)
    try:
        deploy = configured(os.environ)
        with tempfile.TemporaryDirectory() as workdir:
            deploy.workdir = Path(workdir)
            deploy_all(deploy)
    except Stop as stop:
        return stop.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
