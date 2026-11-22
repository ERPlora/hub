#!/usr/bin/env python3
"""Puts the hub's services of one environment back on the ACTIVE revision right before the one their PRIMARY deployment
runs, and records that revision's settings and image tag in /erplora/<environment>/hub/app_env and image_tag
(ERPlora/aws README, "Ajustes de la app" and "Imagen"). Each environment has its own ECS cluster:
  prod: cluster erplora-prod, services hub and worker, families erplora-prod-*, image erplora/hub;
  pre:  cluster erplora-pre, services hub-pre and worker-pre, families erplora-pre-*, image erplora/hub-pre.
  1. finds each service's previous revision; nothing changes unless every service has one of this environment (tag
     Environment=<environment>, task and execution roles erplora-<environment>-*, the deploy's guard) on this
     environment's image, they all run the same tag and the settings they run pass deploy/app_env_rollback.py, under
     the deploy's rules (in prod, changing VERIFACTU_PRODUCTION_ENABLED takes CONFIRM_PROTECTED), whatever
     deploy/app-env.json says;
  2. moves the services to those revisions and waits until they are stable and each one's PRIMARY deployment is the
     previous revision, COMPLETED (ECS marks it so once the old tasks drain from the ALB); a FAILED rollout, another
     revision as PRIMARY (the circuit breaker put back the one the service ran) or a rollout that outlasts
     ROLLOUT_TIMEOUT_SECONDS fails;
  3. records the settings and the tag only then, so a failed rollback leaves the parameters as they were.
Migrations are NOT undone: the previous code must work on the current schema (expand/contract).
Scheduled hub tasks run the latest ACTIVE worker revision (ERPlora/aws stacks/prod/scheduler.tf), so they keep the
newer image and its settings until the next deploy; to go back everywhere, deploy the previous release.

  python3 scripts/ecs_rollback.py   (in the checkout of the repository)

Env: CONFIRM (exactly ROLLBACK), AWS_REGION, ENVIRONMENT (prod | pre); optional CLUSTER (erplora-<environment>),
     POLL_SECONDS (15), ROLLOUT_TIMEOUT_SECONDS (600), CONFIRM_PROTECTED (NAME=value).
What it shares with the deploy, and how it stops, is ecs_common.py's: an aws call or app_env_rollback.py that fails
ends the rollback with its own exit code, and an answer of aws that cannot be read with jq's, 5. Only the standard
library: the workflow runs it with the runner's python3.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ecs_common import (
    PROJECT,
    Release,
    aws,
    each,
    environment_given,
    key,
    main,
    otherwise,
    primary,
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

APP_ENV_ROLLBACK = Path(__file__).resolve().parents[1] / "deploy" / "app_env_rollback.py"
# The families of the services; each one's service is <family><suffix>, and its app container is named after the
# family (ERPlora/aws modules/ecs-service).
SERVICES = ("hub", "worker")
SECONDS = {"POLL_SECONDS": "15", "ROLLOUT_TIMEOUT_SECONDS": "600"}
UNCHANGED = "; nothing was changed"


@dataclass
class Rollback(Release):
    confirm: str
    workdir: Path = Path()

    @property
    def repository(self) -> str:
        return f"erplora/{PROJECT}{self.suffix}"


def configured(env: Mapping[str, str]) -> Rollback:
    """The rollback the environment asks for: without the confirmation, the region, a known environment or numbers of
    seconds it is refused before any aws call."""
    confirm = env.get("CONFIRM", "")
    if confirm != "ROLLBACK":
        raise refusal(f"CONFIRM must be exactly ROLLBACK, not '{confirm}'{UNCHANGED}")
    if not env.get("AWS_REGION"):
        raise refusal("AWS_REGION is required")
    environment = environment_given(env, UNCHANGED)
    seconds = seconds_given(env, SECONDS, UNCHANGED)
    return Rollback(region=env["AWS_REGION"], environment=environment,
                    cluster=env.get("CLUSTER") or f"erplora-{environment}", seconds=seconds,
                    confirm=env.get("CONFIRM_PROTECTED", ""))


def current_revision(rollback: Rollback, service: str, family: str) -> str:
    current, _ = primary(rollback, service)
    if not re.search(rf":task-definition/{re.escape(family)}:[0-9]+$", current):
        raise refusal(f"{service} has no PRIMARY deployment of {family} (got '{current}'){UNCHANGED}")
    return current


def previous_revision(rollback: Rollback, family: str, current: str) -> str:
    """Of its own family only (its prefix also lists erplora-<environment>-hub-migrate), the highest ACTIVE revision
    below the current one; "" when there is none. The ARNs are the words of the answer's first line."""
    listed = aws("ecs", "list-task-definitions", "--family-prefix", family, "--status", "ACTIVE", "--sort", "DESC",
                 "--region", rollback.region, "--query", "taskDefinitionArns", "--output", "text")
    own, below = current.rsplit(":", 1)
    previous, best = "", 0
    for arn in re.split("[ \t]+", listed.split("\n", 1)[0]):
        revision = arn.rsplit(":", 1)[-1]
        if arn.rsplit(":", 1)[0] == own and re.fullmatch("[0-9]+", revision) and best < int(revision) < int(below):
            previous, best = arn, int(revision)
    return previous


def app_image(described: str, name: str, previous: str, rollback: Rollback) -> str:
    """Refuses <previous> unless it is of the rollback's environment, and reads the image of its app container as
    `jq -r '[.taskDefinition.containerDefinitions[] | select(.name == $name) | .image][0] // "none"'` writes it. An
    answer that cannot be read through ends the rollback, as jq did."""
    try:
        found = values(described)
        refuse_another_environment(found, previous, rollback, UNCHANGED)
        containers = each(key(key(found[0], "taskDefinition"), "containerDefinitions"))
        images = [key(container, "image") for container in containers if key(container, "name") == name]
    except (ValueError, TypeError) as reason:
        raise unreadable(previous, reason) from None
    return written(otherwise(images[0] if images else None, "none"))


def previous_of(rollback: Rollback, name: str) -> tuple[str, str]:
    """The revision the service of <name> goes back to and its image tag. What describe-task-definition answers for it
    stays in <workdir>/<name>.json, where app_env_rollback.py reads it."""
    service, family = f"{name}{rollback.suffix}", f"{rollback.prefix}-{name}"
    current = current_revision(rollback, service, family)
    previous = previous_revision(rollback, family, current)
    if not previous:
        raise refusal(f"{service} runs {current} and {family} has no earlier ACTIVE revision{UNCHANGED}")
    path = rollback.workdir / f"{name}.json"
    with path.open("wb") as described:
        aws("ecs", "describe-task-definition", "--task-definition", previous, "--include", "TAGS",
            "--region", rollback.region, "--output", "json", stdout=described)
    image = app_image(path.read_text(encoding="utf-8", errors="surrogateescape"), name, previous, rollback)
    if f"/{rollback.repository}:" not in image:
        raise refusal(f"{previous} does not run an {rollback.repository} image ({image}){UNCHANGED}")
    return previous, image.rsplit(":", 1)[-1]


def roll_back(rollback: Rollback) -> None:
    services = [f"{name}{rollback.suffix}" for name in SERVICES]
    print(f"::warning::rolling back {' '.join(services)} to their previous revisions; migrations are not undone")
    previous = [previous_of(rollback, name) for name in SERVICES]
    tags = [tag for _, tag in previous]
    if len(set(tags)) != 1:
        raise refusal(f"the previous revisions run different tags ({' '.join(tags)}){UNCHANGED}")
    run([sys.executable, str(APP_ENV_ROLLBACK), str(rollback.workdir), rollback.environment, rollback.region,
         f"--confirm={rollback.confirm}"], stdout=None)
    targets = {}
    for service, (revision, _) in zip(services, previous, strict=True):
        aws("ecs", "update-service", "--cluster", rollback.cluster, "--service", service, "--task-definition", revision,
            "--region", rollback.region, stdout=subprocess.DEVNULL)
        print(f"rolling back {service} to {revision}")
        targets[service] = revision
    wait_until_stable(rollback, services)
    watch_rollout(rollback, targets)
    print("services stable on the previous revisions")
    record(rollback, rollback.workdir, tags[0])


def roll_back_from(env: Mapping[str, str]) -> None:
    rollback = configured(env)
    with tempfile.TemporaryDirectory() as workdir:
        rollback.workdir = Path(workdir)
        roll_back(rollback)


if __name__ == "__main__":
    sys.exit(main(lambda: roll_back_from(os.environ)))
