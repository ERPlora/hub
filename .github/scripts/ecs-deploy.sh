#!/usr/bin/env bash
# Deploys an image tag of the hub to one environment, in that environment's ECS cluster
# (erplora-<environment>; PLAN-AWS §6), touching only its hub task families and services:
#   prod: cluster erplora-prod, families erplora-prod-{hub,worker,hub-migrate}, services hub and
#         worker, image erplora/hub;
#   pre:  cluster erplora-pre, families erplora-pre-{hub,worker,hub-migrate}, services hub-pre and
#         worker-pre (the team's pre-production), image erplora/hub-pre.
#   0. reads the latest ACTIVE revision of each family and refuses, before registering anything, one
#      that is not of this environment: tag Environment=<environment> and task and execution roles
#      erplora-<environment>-* (the deploy roles can register any family: ECS takes no resource
#      there, so this guard keeps pre's role from turning a prod revision into its own and back);
#   1. registers a new revision of each family from that one, with its tags, changing only the image
#      of the containers that run the hub image (the app and its pgbouncer sidecar); Terraform owns
#      the rest of the definition;
#   2. runs the migration (hub-migrate) on the new revision and polls it until it is STOPPED; if it
#      fails, never ran or outlasts MIGRATE_TIMEOUT_SECONDS (the task is left running), the deploy
#      stops before any service changes;
#   3. moves the services to the new revisions (in pre also to one task: a push wakes pre up when
#      its evening stop has put it to sleep), waits until they are stable and then polls each
#      one's PRIMARY deployment until it is the new revision, COMPLETED: ECS marks it COMPLETED
#      seconds to a minute after services-stable returns, once the old tasks drain from the ALB.
#      A FAILED rollout or another revision as PRIMARY (with rollback = true the circuit breaker
#      puts the old one back and the wait still succeeds) fails at once; a rollout that outlasts
#      ROLLOUT_TIMEOUT_SECONDS fails too;
#   4. records the tag in /erplora/<environment>/hub/image_tag, so the revisions Terraform registers,
#      and with them the scheduled tasks, keep running it (aws-next README, "Imagen").
# Never db-bootstrap: the deploy role cannot pass its roles (aws-next deploy_role.tf).
# Rollback: the circuit breaker reverts a broken deploy; back to the previous revisions, the
#   rollback workflow (ecs-rollback.sh); back to a release, the deploy workflow with that release.
#
# Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA), ENVIRONMENT
#      (prod | pre); optional CLUSTER (erplora-<environment>), POLL_SECONDS (15),
#      MIGRATE_TIMEOUT_SECONDS (3600), ROLLOUT_TIMEOUT_SECONDS (600).
set -euo pipefail

for var in AWS_REGION REGISTRY IMAGE_TAG ENVIRONMENT; do
  if [ -z "${!var:-}" ]; then
    echo "::error::$var is required" >&2
    exit 1
  fi
done
# A service of pre is the family's short name with -pre (hub-pre); its containers keep the short name.
case "$ENVIRONMENT" in
  prod) suffix="" ;;
  pre) suffix="-pre" ;;
  *)
    echo "::error::ENVIRONMENT must be prod or pre, not '$ENVIRONMENT'" >&2
    exit 1
    ;;
esac
CLUSTER="${CLUSTER:-erplora-$ENVIRONMENT}"
POLL_SECONDS="${POLL_SECONDS:-15}"
MIGRATE_TIMEOUT_SECONDS="${MIGRATE_TIMEOUT_SECONDS:-3600}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-600}"
for var in POLL_SECONDS MIGRATE_TIMEOUT_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
    echo "::error::$var must be a number of seconds, not '${!var}'" >&2
    exit 1
  fi
done

# This repo deploys the hub; the saas repo keeps its own copy of this script.
PROJECT=hub
families=(hub worker hub-migrate)
migration=hub-migrate
# The families of the services; each one's service is <family><suffix>.
services=(hub worker)

prefix="erplora-$ENVIRONMENT"
project_image="$REGISTRY/erplora/$PROJECT$suffix:"
image="$project_image$IMAGE_TAG"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# prepare <family>: reads the latest ACTIVE revision of $prefix-<family>, refuses it if it is not of
# this environment, and writes the new revision to $workdir/<family>.json.
prepare() {
  local name="$1" carries
  aws ecs describe-task-definition --task-definition "$prefix-$name" --include TAGS \
    --region "$AWS_REGION" --output json > "$workdir/$name.base.json"
  if ! jq -e --arg environment "$ENVIRONMENT" --arg roles "^arn:aws[a-z-]*:iam::[0-9]+:role/$prefix-" '
      any(.tags[]?; .key == "Environment" and .value == $environment)
      and ((.taskDefinition.taskRoleArn // "") | test($roles))
      and ((.taskDefinition.executionRoleArn // "") | test($roles))' "$workdir/$name.base.json" > /dev/null; then
    carries="$(jq -r '"Environment=\(first(.tags[]? | select(.key == "Environment") | .value) // "none"), task role \(.taskDefinition.taskRoleArn // "none"), execution role \(.taskDefinition.executionRoleArn // "none")"' \
      "$workdir/$name.base.json")"
    echo "::error::$prefix-$name is no revision of $ENVIRONMENT ($carries); nothing was registered" >&2
    exit 1
  fi
  jq --arg project_image "$project_image" --arg image "$image" '
    (.tags // []) as $tags
    | .taskDefinition
    | .containerDefinitions |= map(if ((.image // "") | startswith($project_image)) then .image = $image else . end)
    | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
          .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)
    | if ($tags | length) > 0 then .tags = $tags else . end' \
    "$workdir/$name.base.json" > "$workdir/$name.json"
  if ! jq -e --arg image "$image" 'any(.containerDefinitions[]; .image == $image)' "$workdir/$name.json" > /dev/null; then
    echo "::error::$prefix-$name has no container of the image $project_image<tag>; nothing was registered" >&2
    exit 1
  fi
}

register() {
  local name="$1"
  aws ecs register-task-definition --cli-input-json "file://$workdir/$name.json" \
    --region "$AWS_REGION" --query taskDefinition.taskDefinitionArn --output text > "$workdir/$name.arn"
  echo "registered $(cat "$workdir/$name.arn")"
}

arn_of() { cat "$workdir/$1.arn"; }

# primary <service>: "<task definition ARN> <rollout state>" of its PRIMARY deployment.
primary() {
  aws ecs describe-services --cluster "$CLUSTER" --services "$1" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text
}

# migrate <family>: its container has the family's name (aws-next modules/ecs-service).
migrate() {
  local name="$1" run task status code reason waited=0
  run="$(aws ecs run-task --cluster "$CLUSTER" --launch-type FARGATE \
    --task-definition "$(arn_of "$name")" \
    --network-configuration "$network" \
    --started-by "deploy-${IMAGE_TAG:0:12}" \
    --region "$AWS_REGION" --output json)"
  task="$(jq -r '.tasks[0].taskArn // empty' <<< "$run")"
  if [ -z "$task" ]; then
    echo "::error::$name did not start: $(jq -c '.failures' <<< "$run")" >&2
    exit 1
  fi
  echo "running $name: $task"

  while :; do
    status="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
      --query 'tasks[0].lastStatus' --output text)"
    if [ "$status" = STOPPED ]; then
      break
    fi
    if [ "$waited" -ge "$MIGRATE_TIMEOUT_SECONDS" ]; then
      echo "::error::$name is still $status after ${MIGRATE_TIMEOUT_SECONDS}s; it was left running ($task) and no service changed; logs in /ecs/$prefix-$name" >&2
      exit 1
    fi
    sleep "$POLL_SECONDS"
    waited=$((waited + POLL_SECONDS))
  done

  code="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
    --query "tasks[0].containers[?name=='$name'].exitCode | [0]" --output text)"
  if [ "$code" = None ]; then
    reason="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$AWS_REGION" \
      --query 'tasks[0].stoppedReason' --output text)"
    echo "::error::$name stopped without running: $reason" >&2
    exit 1
  fi
  if [ "$code" != 0 ]; then
    echo "::error::$name exited with code $code; logs in /ecs/$prefix-$name" >&2
    exit 1
  fi
}

# Every revision is read and checked before any is registered.
for name in "${families[@]}"; do
  prepare "$name"
done
for name in "${families[@]}"; do
  register "$name"
done

# One-off tasks run like the worker: same subnets, its security group, public IP.
network="$(aws ecs describe-services --cluster "$CLUSTER" --services "worker$suffix" --region "$AWS_REGION" \
  --query 'services[0].networkConfiguration' --output json)"

migrate "$migration"

# pre sleeps every evening (desired count 0): a deploy wakes it up with one task per service.
wake=()
if [ "$ENVIRONMENT" = pre ]; then
  wake=(--desired-count 1)
fi
for name in "${services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "$name$suffix" \
    --task-definition "$(arn_of "$name")" "${wake[@]}" --region "$AWS_REGION" > /dev/null
  echo "updated $name$suffix"
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${services[@]/%/$suffix}"

# services-stable can return while a PRIMARY deployment is still IN_PROGRESS: poll the services
# (by family) whose rollout has not completed yet, all of them on the same clock.
pending=("${services[@]}")
waited=0
while :; do
  failed=0
  in_progress=()
  for name in "${pending[@]}"; do
    out="$(primary "$name$suffix")"
    read -r task_definition state <<< "$out"
    if [ "$task_definition" != "$(arn_of "$name")" ] || [ "$state" = FAILED ]; then
      echo "::error::$name$suffix runs $task_definition ($state), not $(arn_of "$name"); rolled back by the circuit breaker? See the service events" >&2
      failed=1
    elif [ "$state" != COMPLETED ]; then
      in_progress+=("$name")
    fi
  done
  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
  if [ "${#in_progress[@]}" -eq 0 ]; then
    break
  fi
  if [ "$waited" -ge "$ROLLOUT_TIMEOUT_SECONDS" ]; then
    for name in "${in_progress[@]}"; do
      echo "::error::rollout of $name$suffix did not complete in $ROLLOUT_TIMEOUT_SECONDS s; see the service events" >&2
    done
    exit 1
  fi
  sleep "$POLL_SECONDS"
  waited=$((waited + POLL_SECONDS))
  pending=("${in_progress[@]}")
done
echo "services stable on the new revisions"

aws ssm put-parameter --name "/erplora/$ENVIRONMENT/$PROJECT/image_tag" --value "$IMAGE_TAG" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded $IMAGE_TAG in /erplora/$ENVIRONMENT/$PROJECT/image_tag"
