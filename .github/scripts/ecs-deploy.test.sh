#!/usr/bin/env bash
# Tests for ecs-deploy.sh with a fake aws CLI that records every call and answers from fixtures,
# and a fake sleep that records the pauses (no test waits for real).
#   bash .github/scripts/ecs-deploy.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0

# A task definition as `describe-task-definition --include TAGS` returns it.
# task_definition <family> <containers JSON>
task_definition() {
  jq -n --arg family "$1" --argjson containers "$2" '{
    taskDefinition: {
      family: $family, taskDefinitionArn: "arn:td/\($family):1", revision: 1, status: "ACTIVE",
      requiresAttributes: [], compatibilities: ["FARGATE"], registeredAt: "t", registeredBy: "u",
      taskRoleArn: "arn:role/\($family)", containerDefinitions: $containers
    },
    tags: [{key: "Project", value: "erplora"}, {key: "ManagedBy", value: "terraform"}]
  }'
}

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin" "$work/fixtures"
  export CALLS_LOG="$work/calls.log" REGISTERED_LOG="$work/registered.log" SLEEP_LOG="$work/sleep.log"
  export FIXTURES="$work/fixtures" POLLS="$work/polls"
  : > "$CALLS_LOG"
  : > "$REGISTERED_LOG"
  : > "$SLEEP_LOG"

  # The hub and the worker run the app plus its pgbouncer sidecar, both on the hub image;
  # the hub fixture also carries containers of other images, which must stay as they are.
  task_definition erplora-prod-hub '[
    {"name": "hub", "image": "reg.example/erplora/hub:bootstrap"},
    {"name": "pgbouncer", "image": "reg.example/erplora/hub:bootstrap"},
    {"name": "log-router", "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
    {"name": "look-alike", "image": "reg.example/erplora/hubx:bootstrap"}]' > "$FIXTURES/erplora-prod-hub.json"
  task_definition erplora-prod-worker '[
    {"name": "worker", "image": "reg.example/erplora/hub:bootstrap"},
    {"name": "pgbouncer", "image": "reg.example/erplora/hub:bootstrap"}]' > "$FIXTURES/erplora-prod-worker.json"
  task_definition erplora-prod-hub-migrate '[
    {"name": "hub-migrate", "image": "reg.example/erplora/hub:bootstrap"}]' > "$FIXTURES/erplora-prod-hub-migrate.json"
  task_definition erplora-prod-db-bootstrap '[
    {"name": "db-bootstrap", "image": "reg.example/erplora/hub:bootstrap"}]' > "$FIXTURES/erplora-prod-db-bootstrap.json"

  # Fails after 500 pauses: a migration loop that never times out fails its test instead of hanging.
  cat > "$work/bin/sleep" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$SLEEP_LOG"
if [ "$(wc -l < "$SLEEP_LOG")" -gt 500 ]; then
  echo "fake sleep: more than 500 pauses" >&2
  exit 1
fi
FAKE

  cat > "$work/bin/aws" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$CALLS_LOG"
args=("$@")
# value <flag>: the argument that follows <flag> in this call.
value() {
  local i
  for ((i = 0; i < ${#args[@]} - 1; i++)); do
    if [ "${args[i]}" = "$1" ]; then
      printf '%s\n' "${args[i + 1]}"
      return
    fi
  done
}
case "$1 $2" in
  "ecs describe-task-definition")
    family="$(value --task-definition)"
    if [ ! -f "$FIXTURES/$family.json" ]; then
      echo "An error occurred (ClientException): Unable to describe task definition." >&2
      exit 254
    fi
    # Tags only come back when asked for.
    if [ "$(value --include)" = TAGS ]; then cat "$FIXTURES/$family.json"; else jq 'del(.tags)' "$FIXTURES/$family.json"; fi
    ;;
  "ecs register-task-definition")
    file="$(value --cli-input-json)"
    file="${file#file://}"
    jq -c . "$file" >> "$REGISTERED_LOG"
    echo "arn:td/$(jq -r .family "$file"):2"
    ;;
  "ecs describe-services")
    if [[ "$(value --query)" == *deployments* ]]; then
      # PRIMARY deployment after the wait: the new revision, COMPLETED, unless faked.
      service="$(value --services)"
      printf '%s\t%s\n' "${FAKE_PRIMARY_TASK_DEFINITION:-arn:td/erplora-prod-$service:2}" "${FAKE_ROLLOUT_STATE:-COMPLETED}"
    else
      echo '{"awsvpcConfiguration":{"subnets":["s"],"securityGroups":["g"],"assignPublicIp":"ENABLED"}}'
    fi
    ;;
  "ecs run-task")
    if [ -n "${FAKE_RUN_TASK_FAILURE:-}" ]; then
      jq -n --arg reason "$FAKE_RUN_TASK_FAILURE" '{tasks: [], failures: [{arn: "arn:capacity", reason: $reason}]}'
    else
      echo '{"tasks": [{"taskArn": "arn:task/erplora-prod/migrate1"}], "failures": []}'
    fi
    ;;
  "ecs describe-tasks")
    case "$(value --query)" in
      *lastStatus*)
        # FAKE_TASK_STATUSES: what successive polls answer; the last one repeats.
        read -ra statuses <<< "${FAKE_TASK_STATUSES:-RUNNING STOPPED}"
        n="$(cat "$POLLS" 2> /dev/null || echo 0)"
        echo "$((n + 1))" > "$POLLS"
        if [ "$n" -ge "${#statuses[@]}" ]; then n=$((${#statuses[@]} - 1)); fi
        echo "${statuses[n]}"
        ;;
      *exitCode*) echo "${FAKE_MIGRATE_EXIT:-0}" ;;
      *stoppedReason*) echo "${FAKE_STOPPED_REASON:-Essential container in task exited}" ;;
    esac
    ;;
  *) ;;
esac
FAKE
  chmod +x "$work/bin/aws" "$work/bin/sleep"
}

# run_deploy [VAR=value...]: deploys abc123 with the fakes; the arguments override the environment.
run_deploy() {
  env -u CLUSTER -u PROJECT -u POLL_SECONDS -u MIGRATE_TIMEOUT_SECONDS \
    PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 "$@" \
    bash "$here/ecs-deploy.sh" > "$work/out.log" 2>&1
}

# run_deploy_without <VAR>: the same with <VAR> unset.
run_deploy_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 \
    env -u "$1" bash "$here/ecs-deploy.sh" > "$work/out.log" 2>&1
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    failures=$((failures + 1))
  fi
}

line_of() { grep -n -- "$1" "$CALLS_LOG" | head -1 | cut -d: -f1; }
last_line_of() { grep -n -- "$1" "$CALLS_LOG" | tail -1 | cut -d: -f1; }
count_of() { grep -c -- "$1" "$CALLS_LOG" || true; }
# registered <family> <jq filter>: evaluates the filter on the revision registered for <family>.
registered() { jq -e --arg family "$1" "select(.family == \$family) | $2" "$REGISTERED_LOG" > /dev/null; }

# --- a deploy that succeeds ---------------------------------------------------
setup
run_deploy && status=0 || status=$?
check "deploy succeeds" '[ "$status" -eq 0 ]'
check "registers a new revision of hub, worker and hub-migrate, and nothing else" \
  '[ "$(jq -r .family "$REGISTERED_LOG" | sort | paste -sd " " -)" = "erplora-prod-hub erplora-prod-hub-migrate erplora-prod-worker" ]'
check "db-bootstrap is never read nor registered" '! grep -q db-bootstrap "$CALLS_LOG" "$REGISTERED_LOG"'
check "every container of the hub image gets the new image: the app and its pgbouncer" \
  'registered erplora-prod-hub "[.containerDefinitions[] | select(.name == \"hub\" or .name == \"pgbouncer\") | .image] == [\"reg.example/erplora/hub:abc123\", \"reg.example/erplora/hub:abc123\"]" &&
   registered erplora-prod-worker "[.containerDefinitions[].image] == [\"reg.example/erplora/hub:abc123\", \"reg.example/erplora/hub:abc123\"]" &&
   registered erplora-prod-hub-migrate ".containerDefinitions[0].image == \"reg.example/erplora/hub:abc123\""'
check "containers of another image keep theirs" \
  'registered erplora-prod-hub "[.containerDefinitions[] | select(.name == \"log-router\" or .name == \"look-alike\") | .image] == [\"public.ecr.aws/aws-observability/aws-for-fluent-bit:stable\", \"reg.example/erplora/hubx:bootstrap\"]"'
check "the rest of the definition is kept" 'registered erplora-prod-hub ".taskRoleArn == \"arn:role/erplora-prod-hub\""'
check "read-only fields are stripped before registering" \
  '! jq -e "has(\"taskDefinitionArn\") or has(\"revision\") or has(\"status\") or has(\"requiresAttributes\") or has(\"compatibilities\") or has(\"registeredAt\") or has(\"registeredBy\")" "$REGISTERED_LOG" > /dev/null'
check "the new revision keeps the tags of the one it copies" \
  'registered erplora-prod-worker ".tags == [{\"key\": \"Project\", \"value\": \"erplora\"}, {\"key\": \"ManagedBy\", \"value\": \"terraform\"}]"'
check "the migration runs the new hub-migrate revision with the worker network configuration" \
  'grep -q "run-task .*--task-definition arn:td/erplora-prod-hub-migrate:2 .*--network-configuration {\"awsvpcConfiguration\"" "$CALLS_LOG"'
check "aws ecs wait tasks-stopped is not used" '! grep -q "wait tasks-stopped" "$CALLS_LOG"'
check "the exit code is read from the migration container, by name" \
  'grep -q "describe-tasks .*containers\[?name==.hub-migrate.\]\.exitCode" "$CALLS_LOG" && ! grep -q "containers\[0\]" "$CALLS_LOG"'
check "the migration finishes before any service changes" \
  '[ "$(last_line_of "describe-tasks")" -lt "$(line_of "update-service")" ]'
check "the services move to the new revisions" \
  'for s in hub worker; do grep -q "update-service .*--service $s --task-definition arn:td/erplora-prod-$s:2" "$CALLS_LOG" || exit 1; done'
check "the deploy waits for both services to be stable" \
  'grep -Eq "wait services-stable .*--services hub worker( |$)" "$CALLS_LOG"'
check "after the wait, each service's PRIMARY deployment is checked" \
  'for s in hub worker; do n="$(last_line_of "describe-services .*--services $s .*deployments")"; [ -n "$n" ] && [ "$n" -gt "$(line_of "wait services-stable")" ] || exit 1; done'
check "the deployed tag is recorded in SSM" \
  'grep -q "^ssm put-parameter --name /erplora/prod/hub/image_tag --value abc123 --type String --overwrite" "$CALLS_LOG"'
check "the tag is recorded only after the services are checked" \
  '[ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services .*deployments")" ]'
check "every aws call names the region" '[ -s "$CALLS_LOG" ] && ! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'
check "nothing of the saas is touched" '! grep -q saas "$CALLS_LOG"'

# --- polling the migration ----------------------------------------------------
setup
run_deploy FAKE_TASK_STATUSES="PROVISIONING PENDING RUNNING STOPPED" && status=0 || status=$?
check "polling: a slow migration still succeeds" '[ "$status" -eq 0 ]'
check "polling: the task is polled until it is STOPPED" '[ "$(count_of "describe-tasks .*lastStatus")" -eq 4 ]'
check "polling: every 15 seconds by default" '[ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15 15" ]'
setup
run_deploy POLL_SECONDS=5 FAKE_TASK_STATUSES="RUNNING STOPPED" && status=0 || status=$?
check "polling: POLL_SECONDS sets the pause" '[ "$status" -eq 0 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "5" ]'

setup
run_deploy MIGRATE_TIMEOUT_SECONDS=0 && status=0 || status=$?
check "timeout 0: a migration that is not STOPPED fails the deploy" '[ "$status" -ne 0 ]'
check "timeout 0: no service changes and no tag is recorded" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "timeout 0: the task is left running" '! grep -q "stop-task" "$CALLS_LOG"'
check "timeout 0: the error names the timeout and the task" \
  'grep -q "::error::.*hub-migrate.*0s.*arn:task/erplora-prod/migrate1" "$work/out.log"'
setup
run_deploy MIGRATE_TIMEOUT_SECONDS=30 FAKE_TASK_STATUSES=RUNNING && status=0 || status=$?
check "timeout 30 s: polls at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(count_of "describe-tasks .*lastStatus")" -eq 3 ] && ! grep -q "update-service" "$CALLS_LOG"'
setup
run_deploy MIGRATE_TIMEOUT_SECONDS=soon && status=0 || status=$?
check "a MIGRATE_TIMEOUT_SECONDS that is not a number fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q MIGRATE_TIMEOUT_SECONDS "$work/out.log"'

# --- a migration that fails ---------------------------------------------------
setup
run_deploy FAKE_MIGRATE_EXIT=1 && status=0 || status=$?
check "a failed migration fails the deploy" '[ "$status" -ne 0 ]'
check "a failed migration changes no service and records no tag" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "the error names the exit code and the log group" \
  'grep -q "::error::hub-migrate .*code 1.*/ecs/erplora-prod-hub-migrate" "$work/out.log"'

setup
run_deploy FAKE_MIGRATE_EXIT=None FAKE_STOPPED_REASON="CannotPullContainerError: pull image manifest has been retried 1 time(s)" &&
  status=0 || status=$?
check "a migration that never ran fails the deploy" '[ "$status" -ne 0 ] && ! grep -q "update-service" "$CALLS_LOG"'
check "its error shows the stoppedReason" \
  'grep -q "::error::hub-migrate .*CannotPullContainerError: pull image manifest has been retried 1 time(s)" "$work/out.log"'

setup
run_deploy FAKE_RUN_TASK_FAILURE="RESOURCE:ENI" && status=0 || status=$?
check "a migration task that cannot start fails the deploy" \
  '[ "$status" -ne 0 ] && ! grep -Eq "describe-tasks|update-service|put-parameter" "$CALLS_LOG"'
check "its error shows the failure reason" 'grep -q "::error::hub-migrate .*RESOURCE:ENI" "$work/out.log"'

# --- a family without the hub image -------------------------------------------
setup
task_definition erplora-prod-worker '[{"name": "worker", "image": "other.example/erplora/hub:bootstrap"}]' \
  > "$FIXTURES/erplora-prod-worker.json"
run_deploy && status=0 || status=$?
check "a family with no container of the hub image fails before the migration" \
  '[ "$status" -ne 0 ] && ! grep -Eq "run-task|update-service|put-parameter" "$CALLS_LOG"'
check "its error names the family" 'grep -q "::error::erplora-prod-worker " "$work/out.log"'

# --- circuit breaker ----------------------------------------------------------
# rollback = true: ECS puts the old revision back and services-stable still succeeds.
setup
run_deploy FAKE_PRIMARY_TASK_DEFINITION=arn:td/erplora-prod-hub:1 && status=0 || status=$?
check "a service rolled back to the old revision fails the deploy" '[ "$status" -ne 0 ]'
check "the rollback error names the service" 'grep -q "::error::hub " "$work/out.log"'
check "a rolled back deploy records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_deploy FAKE_ROLLOUT_STATE=FAILED && status=0 || status=$?
check "a FAILED rollout fails the deploy" '[ "$status" -ne 0 ] && ! grep -q "put-parameter" "$CALLS_LOG"'
check "the rollout error names the service and the state" 'grep -q "::error::hub .*FAILED" "$work/out.log"'

# --- required environment -----------------------------------------------------
for var in AWS_REGION REGISTRY IMAGE_TAG; do
  setup
  run_deploy_without "$var" && status=0 || status=$?
  check "without $var it fails before any aws call" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'
  check "the error names $var" 'grep -q "$var" "$work/out.log"'
done

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
