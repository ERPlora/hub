#!/usr/bin/env bash
# Puts the hub's services of one environment back on the ACTIVE revision right before the one their PRIMARY
# deployment runs, and records that revision's settings and image tag in /erplora/<environment>/hub/app_env and
# image_tag (ERPlora/aws README, "Ajustes de la app" and "Imagen"). Each environment has its own ECS cluster:
# prod: cluster erplora-prod, services hub and worker, families erplora-prod-*, image erplora/hub;
# pre: cluster erplora-pre, services hub-pre and worker-pre, families erplora-pre-*, image erplora/hub-pre.
#   1. finds each service's previous revision; nothing changes unless every service has one of this environment
#      (tag Environment=<environment>, task and execution roles erplora-<environment>-*, the guard of ecs-deploy.sh),
#      they all run the same tag and the settings they run pass deploy/app_env_rollback.py, under the deploy's rules
#      (in prod, changing VERIFACTU_PRODUCTION_ENABLED takes CONFIRM_PROTECTED), whatever deploy/app-env.json says;
#   2. moves the services to those revisions and waits until they are stable and each one's PRIMARY deployment is
#      the previous revision, COMPLETED (ECS marks it so once the old tasks drain from the ALB); a FAILED rollout,
#      another revision as PRIMARY (the circuit breaker put back the one the service ran) or a rollout that outlasts
#      ROLLOUT_TIMEOUT_SECONDS fails;
#   3. records the settings and the tag only then, so a failed rollback leaves the parameters as they were.
# Migrations are NOT undone: the previous code must work on the current schema (expand/contract).
# Scheduled hub tasks run the latest ACTIVE worker revision (ERPlora/aws stacks/prod/scheduler.tf), so they keep
# the newer image and its settings until the next deploy; to go back everywhere, deploy the previous release.
#
# Env: CONFIRM (exactly ROLLBACK), AWS_REGION, ENVIRONMENT (prod | pre); optional CLUSTER (erplora-<environment>),
#      POLL_SECONDS (15), ROLLOUT_TIMEOUT_SECONDS (600), CONFIRM_PROTECTED (NAME=value).
set -euo pipefail

if [ "${CONFIRM:-}" != ROLLBACK ]; then
  echo "::error::CONFIRM must be exactly ROLLBACK, not '${CONFIRM:-}'; nothing was changed" >&2
  exit 1
fi
if [ -z "${AWS_REGION:-}" ]; then
  echo "::error::AWS_REGION is required" >&2
  exit 1
fi
# A service of pre is the family's short name with -pre (hub-pre); its containers keep the short name.
case "${ENVIRONMENT:-}" in
  prod) suffix="" ;;
  pre) suffix="-pre" ;;
  *)
    echo "::error::ENVIRONMENT must be prod or pre, not '${ENVIRONMENT:-}'; nothing was changed" >&2
    exit 1
    ;;
esac
CLUSTER="${CLUSTER:-erplora-$ENVIRONMENT}"
POLL_SECONDS="${POLL_SECONDS:-15}"
ROLLOUT_TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-600}"
for var in POLL_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  if ! [[ "${!var}" =~ ^[0-9]+$ ]]; then
    echo "::error::$var must be a number of seconds, not '${!var}'; nothing was changed" >&2
    exit 1
  fi
done

# This repo deploys the hub; the saas repo keeps its own copy of this script.
PROJECT=hub
# The families of the services; each one's service is <family><suffix>.
names=(hub worker)
services=("${names[@]/%/$suffix}")
prefix="erplora-$ENVIRONMENT"
repository="erplora/$PROJECT$suffix"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

echo "::warning::rolling back ${services[*]} to their previous revisions; migrations are not undone"

# primary <service>: "<task definition ARN> <rollout state>" of its PRIMARY deployment.
primary() {
  aws ecs describe-services --cluster "$CLUSTER" --services "$1" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text
}

targets=()
tags=()
for i in "${!services[@]}"; do
  service="${services[i]}" name="${names[i]}"
  family="$prefix-$name"
  out="$(primary "$service")"
  read -r current _ <<< "$out"
  if ! [[ "$current" =~ :task-definition/$family:[0-9]+$ ]]; then
    echo "::error::$service has no PRIMARY deployment of $family (got '$current'); nothing was changed" >&2
    exit 1
  fi

  # Same family only (its prefix also lists erplora-<env>-hub-migrate), the highest revision below the current one.
  arns="$(aws ecs list-task-definitions --family-prefix "$family" --status ACTIVE --sort DESC \
    --region "$AWS_REGION" --query taskDefinitionArns --output text)"
  read -ra listed <<< "$arns"
  previous="" best=0
  for arn in "${listed[@]}"; do
    revision="${arn##*:}"
    if [ "${arn%:*}" = "${current%:*}" ] && [ "$revision" -lt "${current##*:}" ] && [ "$revision" -gt "$best" ]; then
      previous="$arn" best="$revision"
    fi
  done
  if [ -z "$previous" ]; then
    echo "::error::$service runs $current and $family has no earlier ACTIVE revision; nothing was changed" >&2
    exit 1
  fi

  aws ecs describe-task-definition --task-definition "$previous" --include TAGS \
    --region "$AWS_REGION" --output json > "$workdir/$name.json"
  if ! jq -e --arg environment "$ENVIRONMENT" --arg roles "^arn:aws[a-z-]*:iam::[0-9]+:role/$prefix-" '
      any(.tags[]?; .key == "Environment" and .value == $environment)
      and ((.taskDefinition.taskRoleArn // "") | test($roles))
      and ((.taskDefinition.executionRoleArn // "") | test($roles))' "$workdir/$name.json" > /dev/null; then
    carries="$(jq -r '"Environment=\(first(.tags[]? | select(.key == "Environment") | .value) // "none"), task role \(.taskDefinition.taskRoleArn // "none"), execution role \(.taskDefinition.executionRoleArn // "none")"' \
      "$workdir/$name.json")"
    echo "::error::$previous is no revision of $ENVIRONMENT ($carries); nothing was changed" >&2
    exit 1
  fi
  # The app's container is named after the family's short name (ERPlora/aws modules/ecs-service).
  image="$(jq -r --arg name "$name" '[.taskDefinition.containerDefinitions[] | select(.name == $name) | .image][0] // "none"' \
    "$workdir/$name.json")"
  if [[ "$image" != */$repository:* ]]; then
    echo "::error::$previous does not run an $repository image ($image); nothing was changed" >&2
    exit 1
  fi
  targets+=("$previous")
  tags+=("${image##*:}")
done

if [ "$(printf '%s\n' "${tags[@]}" | sort -u | wc -l)" -ne 1 ]; then
  echo "::error::the previous revisions run different tags (${tags[*]}); nothing was changed" >&2
  exit 1
fi
python3 "$(dirname "$0")/../../deploy/app_env_rollback.py" "$workdir" "$ENVIRONMENT" "$AWS_REGION" --confirm="${CONFIRM_PROTECTED:-}"

for i in "${!services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "${services[i]}" \
    --task-definition "${targets[i]}" --region "$AWS_REGION" > /dev/null
  echo "rolling back ${services[i]} to ${targets[i]}"
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${services[@]}"

# services-stable can return while a PRIMARY deployment is still IN_PROGRESS: poll the services
# (by index) whose rollout has not completed yet, all of them on the same clock.
pending=("${!services[@]}")
waited=0
while :; do
  failed=0
  in_progress=()
  for i in "${pending[@]}"; do
    out="$(primary "${services[i]}")"
    read -r task_definition state <<< "$out"
    if [ "$task_definition" != "${targets[i]}" ] || [ "$state" = FAILED ]; then
      echo "::error::${services[i]} runs $task_definition ($state), not ${targets[i]}; rolled back by the circuit breaker? See the service events" >&2
      failed=1
    elif [ "$state" != COMPLETED ]; then
      in_progress+=("$i")
    fi
  done
  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
  if [ "${#in_progress[@]}" -eq 0 ]; then
    break
  fi
  if [ "$waited" -ge "$ROLLOUT_TIMEOUT_SECONDS" ]; then
    for i in "${in_progress[@]}"; do
      echo "::error::rollout of ${services[i]} did not complete in $ROLLOUT_TIMEOUT_SECONDS s; see the service events" >&2
    done
    exit 1
  fi
  sleep "$POLL_SECONDS"
  waited=$((waited + POLL_SECONDS))
  pending=("${in_progress[@]}")
done
echo "services stable on the previous revisions"

aws ssm put-parameter --name "/erplora/$ENVIRONMENT/$PROJECT/app_env" --value "$(< "$workdir/app_env.json")" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
aws ssm put-parameter --name "/erplora/$ENVIRONMENT/$PROJECT/image_tag" --value "${tags[0]}" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded its settings and ${tags[0]} in /erplora/$ENVIRONMENT/$PROJECT/app_env and image_tag"
