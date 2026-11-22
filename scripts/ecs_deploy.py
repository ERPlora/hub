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
  (ecs_rollback.py); back to a release, the deploy workflow with that release.

  python3 scripts/ecs_deploy.py   (in the checkout of the repository)

Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA), ENVIRONMENT (prod | pre); optional
     CLUSTER (erplora-<environment>), POLL_SECONDS (15), MIGRATE_TIMEOUT_SECONDS (3600), ROLLOUT_TIMEOUT_SECONDS (600),
     CONFIRM_PROTECTED (NAME=value).
What it shares with the rollback, and how it stops, is ecs_common.py's: an aws call or app_env.py that fails ends the
deploy with its own exit code, and an answer of aws that cannot be read with jq's, 5. Only the standard library: the
workflow runs it with the runner's python3.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ecs_common import (
    PROJECT,
    Release,
    aws,
    compact,
    each,
    environment_given,
    key,
    main,
    otherwise,
    record,
    refusal,
    refuse_another_environment,
    run,
    seconds_given,
    unreadable,
    values,
    wait_until_stable,
    watch_rollout,
    written,
)

APP_ENV = Path(__file__).resolve().parents[1] / "deploy" / "app_env.py"
FAMILIES = ("hub", "worker", "hub-migrate")
MIGRATION = "hub-migrate"
# The families of the services; each one's service is <family><suffix>.
SERVICES = ("hub", "worker")
# One-off tasks run like the worker: same subnets, its security group, public IP.
NETWORK_SERVICE = "worker"
REQUIRED = ("AWS_REGION", "REGISTRY", "IMAGE_TAG", "ENVIRONMENT")
SECONDS = {"POLL_SECONDS": "15", "MIGRATE_TIMEOUT_SECONDS": "3600", "ROLLOUT_TIMEOUT_SECONDS": "600"}
READ_ONLY = ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities", "registeredAt",
             "registeredBy", "deregisteredAt")


@dataclass
class Deploy(Release):
    registry: str
    image_tag: str
    confirm: str
    workdir: Path = Path()
    arns: dict[str, str] = field(default_factory=dict)

    @property
    def project_image(self) -> str:
        return f"{self.registry}/erplora/{PROJECT}{self.suffix}:"

    @property
    def image(self) -> str:
        return f"{self.project_image}{self.image_tag}"


def configured(env: Mapping[str, str]) -> Deploy:
    """The deploy the environment asks for: a missing setting, an unknown environment or a number of seconds that is
    none is refused before any aws call."""
    for name in REQUIRED:
        if not env.get(name):
            raise refusal(f"{name} is required")
    environment = environment_given(env, "")
    seconds = seconds_given(env, SECONDS, "")
    return Deploy(region=env["AWS_REGION"], registry=env["REGISTRY"], image_tag=env["IMAGE_TAG"],
                  environment=environment, cluster=env.get("CLUSTER") or f"erplora-{environment}",
                  confirm=env.get("CONFIRM_PROTECTED", ""), seconds=seconds)


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
    refuse_another_environment(found, family, deploy, "; nothing was registered")
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
    return written(arn), failures


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
    wait_until_stable(deploy, list(targets))
    return targets


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
    record(deploy, deploy.workdir, deploy.image_tag)


def deploy_from(env: Mapping[str, str]) -> None:
    deploy = configured(env)
    with tempfile.TemporaryDirectory() as workdir:
        deploy.workdir = Path(workdir)
        deploy_all(deploy)


if __name__ == "__main__":
    sys.exit(main(lambda: deploy_from(os.environ)))
