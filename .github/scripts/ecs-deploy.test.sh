#!/usr/bin/env bash
# Tests for ecs-deploy.sh with a fake aws CLI that records every call and answers from fixtures,
# and a fake sleep that records the pauses (no test waits for real).
#   bash .github/scripts/ecs-deploy.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0

# A task definition as `describe-task-definition --include TAGS` returns it, with the roles and the
# Environment tag Terraform gives it (aws-next modules/ecs-service: erplora-<env>-<name>-task and
# -execution); the tag and the roles may be overridden.
# task_definition <family> <containers JSON> [<Environment tag, "" = none> [<task role> [<execution role>]]]
task_definition() {
  local family="$1" environment
  environment="$(cut -d- -f2 <<< "$family")"
  jq -n --arg family "$family" --argjson containers "$2" --arg environment "${3-$environment}" \
    --arg task_role "${4:-arn:aws:iam::123456789012:role/$family-task}" \
    --arg execution_role "${5:-arn:aws:iam::123456789012:role/$family-execution}" '{
    taskDefinition: {
      family: $family, taskDefinitionArn: "arn:td/\($family):1", revision: 1, status: "ACTIVE",
      requiresAttributes: [], compatibilities: ["FARGATE"], registeredAt: "t", registeredBy: "u",
      taskRoleArn: $task_role, executionRoleArn: $execution_role, containerDefinitions: $containers
    },
    tags: ([{key: "Project", value: "erplora"}, {key: "ManagedBy", value: "terraform"}]
      + (if $environment == "" then [] else [{key: "Environment", value: $environment}] end))
  }'
}

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin" "$work/fixtures"
  export CALLS_LOG="$work/calls.log" REGISTERED_LOG="$work/registered.log" SLEEP_LOG="$work/sleep.log"
  export FIXTURES="$work/fixtures" POLLS="$work/polls" ROLLOUT_POLLS="$work/rollout-polls"
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
  # pre: the same families in the same cluster, named erplora-pre-*, on its own ECR repository; its
  # services are hub-pre and worker-pre, their containers keep the short names.
  task_definition erplora-pre-hub '[
    {"name": "hub", "image": "reg.example/erplora/hub-pre:bootstrap"},
    {"name": "pgbouncer", "image": "reg.example/erplora/hub-pre:bootstrap"}]' > "$FIXTURES/erplora-pre-hub.json"
  task_definition erplora-pre-worker '[
    {"name": "worker", "image": "reg.example/erplora/hub-pre:bootstrap"},
    {"name": "pgbouncer", "image": "reg.example/erplora/hub-pre:bootstrap"}]' > "$FIXTURES/erplora-pre-worker.json"
  task_definition erplora-pre-hub-migrate '[
    {"name": "hub-migrate", "image": "reg.example/erplora/hub-pre:bootstrap"}]' > "$FIXTURES/erplora-pre-hub-migrate.json"
  task_definition erplora-pre-db-bootstrap '[
    {"name": "db-bootstrap", "image": "reg.example/erplora/hub:bootstrap"}]' > "$FIXTURES/erplora-pre-db-bootstrap.json"

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
      # PRIMARY deployment after the wait: successive reads of a service answer the next of
      # FAKE_PRIMARY_REVISIONS and FAKE_ROLLOUT_STATES (the last one repeats); by default the new
      # revision (2), COMPLETED.
      service="$(value --services)"
      # The family of a service: hub → erplora-prod-hub, hub-pre → erplora-pre-hub.
      if [[ "$service" == *-pre ]]; then family="erplora-pre-${service%-pre}"; else family="erplora-prod-$service"; fi
      read -ra revisions <<< "${FAKE_PRIMARY_REVISIONS:-2}"
      read -ra states <<< "${FAKE_ROLLOUT_STATES:-COMPLETED}"
      n="$(cat "$ROLLOUT_POLLS.$service" 2> /dev/null || echo 0)"
      echo "$((n + 1))" > "$ROLLOUT_POLLS.$service"
      r="$n" s="$n"
      if [ "$r" -ge "${#revisions[@]}" ]; then r=$((${#revisions[@]} - 1)); fi
      if [ "$s" -ge "${#states[@]}" ]; then s=$((${#states[@]} - 1)); fi
      printf '%s\t%s\n' "arn:td/$family:${revisions[r]}" "${states[s]}"
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

# run_deploy [VAR=value...]: deploys abc123 to prod with the fakes; the arguments override the environment.
run_deploy() {
  env -u CLUSTER -u PROJECT -u POLL_SECONDS -u MIGRATE_TIMEOUT_SECONDS -u ROLLOUT_TIMEOUT_SECONDS \
    PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 ENVIRONMENT=prod "$@" \
    bash "$here/ecs-deploy.sh" > "$work/out.log" 2>&1
}

# run_deploy_without <VAR>: the same with <VAR> unset.
run_deploy_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 REGISTRY=reg.example IMAGE_TAG=abc123 ENVIRONMENT=prod \
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
check "the rest of the definition is kept" \
  'registered erplora-prod-hub ".taskRoleArn == \"arn:aws:iam::123456789012:role/erplora-prod-hub-task\" and .executionRoleArn == \"arn:aws:iam::123456789012:role/erplora-prod-hub-execution\""'
check "read-only fields are stripped before registering" \
  '! jq -e "has(\"taskDefinitionArn\") or has(\"revision\") or has(\"status\") or has(\"requiresAttributes\") or has(\"compatibilities\") or has(\"registeredAt\") or has(\"registeredBy\")" "$REGISTERED_LOG" > /dev/null'
check "the new revision keeps the tags of the one it copies, Environment included" \
  'registered erplora-prod-worker ".tags == [{\"key\": \"Project\", \"value\": \"erplora\"}, {\"key\": \"ManagedBy\", \"value\": \"terraform\"}, {\"key\": \"Environment\", \"value\": \"prod\"}]"'
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
check "nothing of pre is touched" '! grep -Eq "erplora-pre|-pre |/erplora/pre/" "$CALLS_LOG" "$REGISTERED_LOG"'
check "prod's services keep their desired count" '! grep -q "desired-count" "$CALLS_LOG"'
check "every revision is read before any is registered" \
  '[ "$(last_line_of "describe-task-definition")" -lt "$(line_of "register-task-definition")" ]'

# The calls of a prod deploy before pre existed (2026-10-14): the same calls with the same arguments;
# only the reads moved, so the three revisions are read (and checked) before any is registered.
check "prod: the calls are exactly today's" \
  '[ "$(sed -E "s|file://[^ ]*/|file://<workdir>/|" "$CALLS_LOG")" = "$(cat <<'"'"'CALLS'"'"'
ecs describe-task-definition --task-definition erplora-prod-hub --include TAGS --region eu-south-2 --output json
ecs describe-task-definition --task-definition erplora-prod-worker --include TAGS --region eu-south-2 --output json
ecs describe-task-definition --task-definition erplora-prod-hub-migrate --include TAGS --region eu-south-2 --output json
ecs register-task-definition --cli-input-json file://<workdir>/hub.json --region eu-south-2 --query taskDefinition.taskDefinitionArn --output text
ecs register-task-definition --cli-input-json file://<workdir>/worker.json --region eu-south-2 --query taskDefinition.taskDefinitionArn --output text
ecs register-task-definition --cli-input-json file://<workdir>/hub-migrate.json --region eu-south-2 --query taskDefinition.taskDefinitionArn --output text
ecs describe-services --cluster erplora-prod --services worker --region eu-south-2 --query services[0].networkConfiguration --output json
ecs run-task --cluster erplora-prod --launch-type FARGATE --task-definition arn:td/erplora-prod-hub-migrate:2 --network-configuration {"awsvpcConfiguration":{"subnets":["s"],"securityGroups":["g"],"assignPublicIp":"ENABLED"}} --started-by deploy-abc123 --region eu-south-2 --output json
ecs describe-tasks --cluster erplora-prod --tasks arn:task/erplora-prod/migrate1 --region eu-south-2 --query tasks[0].lastStatus --output text
ecs describe-tasks --cluster erplora-prod --tasks arn:task/erplora-prod/migrate1 --region eu-south-2 --query tasks[0].lastStatus --output text
ecs describe-tasks --cluster erplora-prod --tasks arn:task/erplora-prod/migrate1 --region eu-south-2 --query tasks[0].containers[?name=='"'"'hub-migrate'"'"'].exitCode | [0] --output text
ecs update-service --cluster erplora-prod --service hub --task-definition arn:td/erplora-prod-hub:2 --region eu-south-2
ecs update-service --cluster erplora-prod --service worker --task-definition arn:td/erplora-prod-worker:2 --region eu-south-2
ecs wait services-stable --cluster erplora-prod --region eu-south-2 --services hub worker
ecs describe-services --cluster erplora-prod --services hub --region eu-south-2 --query services[0].deployments[?status=='"'"'PRIMARY'"'"'] | [0].[taskDefinition, rolloutState] --output text
ecs describe-services --cluster erplora-prod --services worker --region eu-south-2 --query services[0].deployments[?status=='"'"'PRIMARY'"'"'] | [0].[taskDefinition, rolloutState] --output text
ssm put-parameter --name /erplora/prod/hub/image_tag --value abc123 --type String --overwrite --region eu-south-2
CALLS
)" ]'

# --- pre: same cluster, its own families, services, repository and tag ---------------
setup
run_deploy ENVIRONMENT=pre && status=0 || status=$?
check "pre: the deploy succeeds" '[ "$status" -eq 0 ]'
check "pre: registers only pre's families" \
  '[ "$(jq -r .family "$REGISTERED_LOG" | sort | paste -sd " " -)" = "erplora-pre-hub erplora-pre-hub-migrate erplora-pre-worker" ]'
check "pre: the image is pre's repository, on the app and on its pgbouncer" \
  'registered erplora-pre-hub "[.containerDefinitions[].image] == [\"reg.example/erplora/hub-pre:abc123\", \"reg.example/erplora/hub-pre:abc123\"]" &&
   registered erplora-pre-worker "[.containerDefinitions[].image] == [\"reg.example/erplora/hub-pre:abc123\", \"reg.example/erplora/hub-pre:abc123\"]" &&
   registered erplora-pre-hub-migrate ".containerDefinitions[0].image == \"reg.example/erplora/hub-pre:abc123\""'
check "pre: the new revisions keep Environment=pre" \
  'for f in hub worker hub-migrate; do registered "erplora-pre-$f" "any(.tags[]; .key == \"Environment\" and .value == \"pre\")" || exit 1; done'
check "pre: the migration runs pre's hub-migrate with worker-pre's network, in the shared cluster" \
  'grep -q "^ecs describe-services --cluster erplora-prod --services worker-pre .*networkConfiguration" "$CALLS_LOG" &&
   grep -q "run-task --cluster erplora-prod .*--task-definition arn:td/erplora-pre-hub-migrate:2 " "$CALLS_LOG" &&
   grep -q "describe-tasks .*containers\[?name==.hub-migrate.\]\.exitCode" "$CALLS_LOG"'
check "pre: updates only hub-pre and worker-pre, to pre's revisions" \
  '[ "$(grep -c "update-service" "$CALLS_LOG")" -eq 2 ] &&
   grep -q "update-service --cluster erplora-prod --service hub-pre --task-definition arn:td/erplora-pre-hub:2 " "$CALLS_LOG" &&
   grep -q "update-service --cluster erplora-prod --service worker-pre --task-definition arn:td/erplora-pre-worker:2 " "$CALLS_LOG"'
check "pre: a push wakes its services (desired count 1)" \
  '[ "$(grep -c "update-service .*--desired-count 1 " "$CALLS_LOG")" -eq 2 ]'
check "pre: waits for hub-pre and worker-pre and checks their rollouts" \
  'grep -Eq "wait services-stable .*--services hub-pre worker-pre( |$)" "$CALLS_LOG" &&
   for s in hub-pre worker-pre; do grep -q "describe-services .*--services $s .*deployments" "$CALLS_LOG" || exit 1; done'
check "pre: records its own image tag" \
  'grep -q "^ssm put-parameter --name /erplora/pre/hub/image_tag --value abc123 --type String --overwrite" "$CALLS_LOG"'
check "pre: a pre run never names a prod family, service, parameter or repository" \
  '! grep -Eq "erplora-prod-|/erplora/prod/|erplora/hub:|--services? (hub|worker)( |$)|--services (hub|worker) " "$CALLS_LOG" "$REGISTERED_LOG"'
check "pre: db-bootstrap is never read nor registered" '! grep -q db-bootstrap "$CALLS_LOG" "$REGISTERED_LOG"'
setup
run_deploy ENVIRONMENT=pre FAKE_MIGRATE_EXIT=1 && status=0 || status=$?
check "pre: a failed migration names pre's log group" \
  '[ "$status" -ne 0 ] && grep -q "::error::hub-migrate .*code 1.*/ecs/erplora-pre-hub-migrate" "$work/out.log"'

# --- the environment ----------------------------------------------------------
for environment in "" dev PROD staging; do
  setup
  run_deploy ENVIRONMENT="$environment" && status=0 || status=$?
  check "ENVIRONMENT '$environment' fails before any aws call" \
    '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::ENVIRONMENT" "$work/out.log"'
done

# --- a base revision of another environment is refused, before registering anything --
# refused_base <family>: the deploy failed naming <family>, and registered and ran nothing.
refused_base() {
  [ "$status" -ne 0 ] && [ ! -s "$REGISTERED_LOG" ] &&
    ! grep -Eq "register-task-definition|run-task|update-service|put-parameter" "$CALLS_LOG" &&
    grep -q "::error::$1 .*nothing was registered" "$work/out.log"
}
setup
task_definition erplora-prod-worker '[{"name": "worker", "image": "reg.example/erplora/hub:bootstrap"}]' pre \
  > "$FIXTURES/erplora-prod-worker.json"
run_deploy && status=0 || status=$?
check "prod: a base revision tagged Environment=pre is refused, nothing registered" 'refused_base erplora-prod-worker'
setup
task_definition erplora-prod-hub-migrate '[{"name": "hub-migrate", "image": "reg.example/erplora/hub:bootstrap"}]' "" \
  > "$FIXTURES/erplora-prod-hub-migrate.json"
run_deploy && status=0 || status=$?
check "prod: a base revision without the Environment tag is refused" 'refused_base erplora-prod-hub-migrate'
setup
task_definition erplora-pre-hub '[{"name": "hub", "image": "reg.example/erplora/hub-pre:bootstrap"}]' pre \
  arn:aws:iam::123456789012:role/erplora-prod-hub-task > "$FIXTURES/erplora-pre-hub.json"
run_deploy ENVIRONMENT=pre && status=0 || status=$?
check "pre: a base revision with a prod task role is refused" 'refused_base erplora-pre-hub'
setup
task_definition erplora-pre-worker '[{"name": "worker", "image": "reg.example/erplora/hub-pre:bootstrap"}]' pre "" \
  arn:aws:iam::123456789012:role/erplora-prod-worker-execution > "$FIXTURES/erplora-pre-worker.json"
run_deploy ENVIRONMENT=pre && status=0 || status=$?
check "pre: a base revision with a prod execution role is refused" 'refused_base erplora-pre-worker'
setup
jq 'del(.taskDefinition.taskRoleArn)' "$FIXTURES/erplora-prod-hub.json" > "$work/no-role.json"
mv "$work/no-role.json" "$FIXTURES/erplora-prod-hub.json"
run_deploy && status=0 || status=$?
check "a base revision without a task role is refused" 'refused_base erplora-prod-hub'
check "the error says what the revision carries" \
  'grep -q "::error::erplora-prod-hub .*Environment=prod.*task role none" "$work/out.log"'

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
check "a family with no container of the hub image fails before registering anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "register-task-definition|run-task|update-service|put-parameter" "$CALLS_LOG"'
check "its error names the family" 'grep -q "::error::erplora-prod-worker " "$work/out.log"'

# --- the rollout after services-stable ----------------------------------------
# services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it
# COMPLETED once the old tasks have drained from the ALB, seconds to a minute later.
# FAKE_TASK_STATUSES=STOPPED: the migration needs no pause, so every pause logged is the rollout's.
# reads_of <service>: how many times its PRIMARY deployment was read.
reads_of() { count_of "describe-services .*--services $1 .*deployments"; }
rollback_error() {
  grep -qF "::error::$1 runs arn:td/erplora-prod-$1:1 (COMPLETED), not arn:td/erplora-prod-$1:2; rolled back by the circuit breaker? See the service events" "$work/out.log"
}

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: IN_PROGRESS on the first read and COMPLETED on the second, the deploy succeeds" '[ "$status" -eq 0 ]'
check "rollout: each service's PRIMARY deployment is read again after one pause of POLL_SECONDS" \
  '[ "$(reads_of hub)" -eq 2 ] && [ "$(reads_of worker)" -eq 2 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15" ]'
check "rollout: the tag is recorded once every rollout is COMPLETED" \
  'grep -q "^ssm put-parameter --name /erplora/prod/hub/image_tag --value abc123 " "$CALLS_LOG" &&
   [ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services .*deployments")" ]'

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=FAILED && status=0 || status=$?
check "a FAILED rollout fails the deploy at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "a FAILED rollout records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
check "the rollout error names the service and the state" 'grep -q "::error::hub .*FAILED" "$work/out.log"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED" && status=0 || status=$?
check "a rollout that turns FAILED fails the deploy on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 2 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 1 ] && ! grep -q "put-parameter" "$CALLS_LOG"'

# rollback = true: the circuit breaker puts the old revision back and services-stable still succeeds.
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_PRIMARY_REVISIONS=1 && status=0 || status=$?
check "a service rolled back to the old revision fails the deploy at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "the rollback error names the service and both revisions" 'rollback_error hub'
check "a rolled back deploy records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_PRIMARY_REVISIONS="2 1" FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" &&
  status=0 || status=$?
check "a rollout IN_PROGRESS that the circuit breaker rolls back fails the deploy on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 2 ] && rollback_error hub && ! grep -q "put-parameter" "$CALLS_LOG"'

setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=IN_PROGRESS ROLLOUT_TIMEOUT_SECONDS=30 && status=0 || status=$?
check "rollout timeout 30 s: reads at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 3 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15" ]'
check "rollout timeout: the error names each service and the limit" \
  'grep -q "::error::rollout of hub did not complete in 30 s" "$work/out.log" &&
   grep -q "::error::rollout of worker did not complete in 30 s" "$work/out.log"'
check "rollout timeout: no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_deploy FAKE_TASK_STATUSES=STOPPED FAKE_ROLLOUT_STATES=IN_PROGRESS && status=0 || status=$?
check "rollout timeout: 600 seconds by default (41 reads, 40 pauses)" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 41 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 40 ] &&
   grep -q "::error::rollout of hub did not complete in 600 s" "$work/out.log"'
setup
run_deploy ROLLOUT_TIMEOUT_SECONDS=soon && status=0 || status=$?
check "a ROLLOUT_TIMEOUT_SECONDS that is not a number fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q ROLLOUT_TIMEOUT_SECONDS "$work/out.log"'

# --- required environment -----------------------------------------------------
for var in AWS_REGION REGISTRY IMAGE_TAG ENVIRONMENT; do
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
