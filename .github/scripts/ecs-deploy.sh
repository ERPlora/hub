#!/usr/bin/env bash
# Deploys an image tag of the hub to the prod ECS cluster (PLAN-AWS §6), touching only the hub's
# task families (hub, worker, hub-migrate) and services (hub, worker):
#   1. registers a new revision of each family from its latest ACTIVE one, with its tags, changing
#      only the image of the containers that run the hub image (the app and its pgbouncer sidecar);
#      Terraform owns the rest of the definition;
#   2. runs the migration (hub-migrate) on the new revision and polls it until it is STOPPED; if it
#      fails, never ran or outlasts MIGRATE_TIMEOUT_SECONDS (the task is left running), the deploy
#      stops before any service changes;
#   3. moves the services to the new revisions, waits until they are stable and checks that each
#      one's PRIMARY deployment is the new revision, COMPLETED (with rollback = true the circuit
#      breaker puts the old one back and the wait still succeeds);
#   4. records the tag in /erplora/prod/hub/image_tag, so the revisions Terraform registers, and
#      with them the scheduled tasks, keep running it (aws-next README, "Imagen").
# Never db-bootstrap: the deploy role cannot pass its roles (aws-next deploy_role.tf).
# Rollback: the circuit breaker reverts a broken deploy; back to the previous revisions, the
#   rollback workflow (ecs-rollback.sh); back to a release, the deploy workflow with that release.
#
# Env: AWS_REGION, REGISTRY (ECR registry host), IMAGE_TAG (image tag = commit SHA);
#      optional CLUSTER (erplora-prod), POLL_SECONDS (15), MIGRATE_TIMEOUT_SECONDS (3600).
set -euo pipefail

for var in AWS_REGION REGISTRY IMAGE_TAG; do
  if [ -z "${!var:-}" ]; then
    echo "::error::$var is required" >&2
    exit 1
  fi
done
CLUSTER="${CLUSTER:-erplora-prod}"
POLL_SECONDS="${POLL_SECONDS:-15}"
MIGRATE_TIMEOUT_SECONDS="${MIGRATE_TIMEOUT_SECONDS:-3600}"
for var in POLL_SECONDS MIGRATE_TIMEOUT_SECONDS; do
  if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
    echo "::error::$var must be a number of seconds, not '${!var}'" >&2
    exit 1
  fi
done

# This repo deploys the hub; the saas repo keeps its own copy of this script.
PROJECT=hub
families=(hub worker hub-migrate)
migration=hub-migrate
services=(hub worker)

project_image="$REGISTRY/erplora/$PROJECT:"
image="$project_image$IMAGE_TAG"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

register() {
  local name="$1"
  aws ecs describe-task-definition --task-definition "erplora-prod-$name" --include TAGS \
    --region "$AWS_REGION" --output json |
    jq --arg project_image "$project_image" --arg image "$image" '
      (.tags // []) as $tags
      | .taskDefinition
      | .containerDefinitions |= map(if ((.image // "") | startswith($project_image)) then .image = $image else . end)
      | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
            .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)
      | if ($tags | length) > 0 then .tags = $tags else . end' \
      > "$workdir/$name.json"
  if ! jq -e --arg image "$image" 'any(.containerDefinitions[]; .image == $image)' "$workdir/$name.json" > /dev/null; then
    echo "::error::erplora-prod-$name has no container of the image $project_image<tag>; nothing was deployed" >&2
    exit 1
  fi
  aws ecs register-task-definition --cli-input-json "file://$workdir/$name.json" \
    --region "$AWS_REGION" --query taskDefinition.taskDefinitionArn --output text > "$workdir/$name.arn"
  echo "registered $(cat "$workdir/$name.arn")"
}

arn_of() { cat "$workdir/$1.arn"; }

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
      echo "::error::$name is still $status after ${MIGRATE_TIMEOUT_SECONDS}s; it was left running ($task) and no service changed; logs in /ecs/erplora-prod-$name" >&2
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
    echo "::error::$name exited with code $code; logs in /ecs/erplora-prod-$name" >&2
    exit 1
  fi
}

for name in "${families[@]}"; do
  register "$name"
done

# One-off tasks run like the worker: same subnets, sg-worker, public IP.
network="$(aws ecs describe-services --cluster "$CLUSTER" --services worker --region "$AWS_REGION" \
  --query 'services[0].networkConfiguration' --output json)"

migrate "$migration"

for service in "${services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "$service" \
    --task-definition "$(arn_of "$service")" --region "$AWS_REGION" > /dev/null
  echo "updated $service"
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${services[@]}"

failed=0
for service in "${services[@]}"; do
  primary="$(aws ecs describe-services --cluster "$CLUSTER" --services "$service" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text)"
  read -r task_definition state <<< "$primary"
  if [ "$task_definition" != "$(arn_of "$service")" ] || [ "$state" != COMPLETED ]; then
    echo "::error::$service runs $task_definition ($state), not $(arn_of "$service"); rolled back by the circuit breaker? See the service events" >&2
    failed=1
  fi
done
if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "services stable on the new revisions"

aws ssm put-parameter --name "/erplora/prod/$PROJECT/image_tag" --value "$IMAGE_TAG" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded $IMAGE_TAG in /erplora/prod/$PROJECT/image_tag"
