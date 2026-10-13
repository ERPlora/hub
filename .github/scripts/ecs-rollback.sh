#!/usr/bin/env bash
# Puts the hub's services (hub, worker) back on the ACTIVE revision right before the one their
# PRIMARY deployment runs, waits until they are stable, checks it and records that revision's
# image tag in /erplora/prod/hub/image_tag (aws-next README, "Imagen").
# Migrations are NOT undone: the previous code must work on the current schema (expand/contract).
# Nothing changes unless every service has a previous revision and they all run the same tag.
# Scheduled hub tasks run the latest ACTIVE worker revision (aws-next scheduler.tf), so they keep
# the newer image until the next deploy; to go back everywhere, deploy the previous release.
#
# Env: CONFIRM (exactly ROLLBACK), AWS_REGION; optional CLUSTER (erplora-prod).
set -euo pipefail

if [ "${CONFIRM:-}" != ROLLBACK ]; then
  echo "::error::CONFIRM must be exactly ROLLBACK, not '${CONFIRM:-}'; nothing was changed" >&2
  exit 1
fi
if [ -z "${AWS_REGION:-}" ]; then
  echo "::error::AWS_REGION is required" >&2
  exit 1
fi
CLUSTER="${CLUSTER:-erplora-prod}"

# This repo deploys the hub; the saas repo keeps its own copy of this script.
PROJECT=hub
services=(hub worker)

echo "::warning::rolling back ${services[*]} to their previous revisions; migrations are not undone"

# primary <service>: "<task definition ARN> <rollout state>" of its PRIMARY deployment.
primary() {
  aws ecs describe-services --cluster "$CLUSTER" --services "$1" --region "$AWS_REGION" \
    --query "services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState]" --output text
}

targets=()
tags=()
for service in "${services[@]}"; do
  family="erplora-prod-$service"
  out="$(primary "$service")"
  read -r current _ <<< "$out"
  if ! [[ "$current" =~ :task-definition/$family:[0-9]+$ ]]; then
    echo "::error::$service has no PRIMARY deployment of $family (got '$current'); nothing was changed" >&2
    exit 1
  fi

  # The family prefix also lists longer families (erplora-prod-hub-migrate): same family only,
  # and the highest revision below the current one.
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

  image="$(aws ecs describe-task-definition --task-definition "$previous" --region "$AWS_REGION" \
    --query "taskDefinition.containerDefinitions[?name=='$service'].image | [0]" --output text)"
  if [[ "$image" != */erplora/$PROJECT:* ]]; then
    echo "::error::$previous does not run an erplora/$PROJECT image ($image); nothing was changed" >&2
    exit 1
  fi
  targets+=("$previous")
  tags+=("${image##*:}")
done

for tag in "${tags[@]}"; do
  if [ "$tag" != "${tags[0]}" ]; then
    echo "::error::the previous revisions run different tags (${tags[*]}); nothing was changed" >&2
    exit 1
  fi
done

for i in "${!services[@]}"; do
  aws ecs update-service --cluster "$CLUSTER" --service "${services[i]}" \
    --task-definition "${targets[i]}" --region "$AWS_REGION" > /dev/null
  echo "rolling back ${services[i]} to ${targets[i]}"
done

aws ecs wait services-stable --cluster "$CLUSTER" --region "$AWS_REGION" --services "${services[@]}"

failed=0
for i in "${!services[@]}"; do
  out="$(primary "${services[i]}")"
  read -r task_definition state <<< "$out"
  if [ "$task_definition" != "${targets[i]}" ] || [ "$state" != COMPLETED ]; then
    echo "::error::${services[i]} runs $task_definition ($state), not ${targets[i]}; see the service events" >&2
    failed=1
  fi
done
if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "services stable on the previous revisions"

aws ssm put-parameter --name "/erplora/prod/$PROJECT/image_tag" --value "${tags[0]}" \
  --type String --overwrite --region "$AWS_REGION" > /dev/null
echo "recorded ${tags[0]} in /erplora/prod/$PROJECT/image_tag"
