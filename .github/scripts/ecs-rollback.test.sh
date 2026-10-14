#!/usr/bin/env bash
# Tests for ecs-rollback.sh with a fake aws CLI that records every call, answers from fixtures and
# keeps each service's PRIMARY revision as state (update-service moves it), and a fake sleep that
# records the pauses (no test waits for real).
#   bash .github/scripts/ecs-rollback.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
td="arn:aws:ecs:eu-south-2:123456789012:task-definition"

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin" "$work/fixtures" "$work/state"
  export CALLS_LOG="$work/calls.log" SLEEP_LOG="$work/sleep.log" FIXTURES="$work/fixtures" STATE="$work/state"
  : > "$CALLS_LOG"
  : > "$SLEEP_LOG"

  # Both services run revision 12. The family prefix of hub also lists hub-migrate, and hub has a
  # newer revision (13) than the one it runs: the previous one is hub:10, not hub-migrate:11.
  echo "$td/erplora-prod-hub:12" > "$STATE/primary-hub"
  echo "$td/erplora-prod-worker:12" > "$STATE/primary-worker"
  printf '%s\t' "$td/erplora-prod-hub-migrate:14" "$td/erplora-prod-hub-migrate:11" "$td/erplora-prod-hub:13" \
    "$td/erplora-prod-hub:12" "$td/erplora-prod-hub:10" "$td/erplora-prod-hub:9" > "$FIXTURES/list-erplora-prod-hub"
  printf '%s\t' "$td/erplora-prod-worker:12" "$td/erplora-prod-worker:10" > "$FIXTURES/list-erplora-prod-worker"
  # The app image of a revision: reg.example/erplora/hub:tag-<revision>, unless listed here.
  : > "$FIXTURES/images"

  # Fails after 500 pauses: a rollout loop that never times out fails its test instead of hanging.
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
  "ecs describe-services")
    service="$(value --services)"
    primary="$(cat "$STATE/primary-$service")"
    state=COMPLETED
    if [ -f "$STATE/moved-$service" ]; then
      # After update-service, successive reads of a service answer the next of FAKE_ROLLOUT_STATES
      # and, if set, FAKE_PRIMARY_REVISIONS (revision numbers of its family); the last one repeats.
      n="$(cat "$STATE/reads-$service" 2> /dev/null || echo 0)"
      echo "$((n + 1))" > "$STATE/reads-$service"
      read -ra states <<< "${FAKE_ROLLOUT_STATES:-COMPLETED}"
      s="$n"
      if [ "$s" -ge "${#states[@]}" ]; then s=$((${#states[@]} - 1)); fi
      state="${states[s]}"
      if [ -n "${FAKE_PRIMARY_REVISIONS:-}" ]; then
        read -ra revisions <<< "$FAKE_PRIMARY_REVISIONS"
        r="$n"
        if [ "$r" -ge "${#revisions[@]}" ]; then r=$((${#revisions[@]} - 1)); fi
        primary="${primary%:*}:${revisions[r]}"
      fi
    fi
    printf '%s\t%s\n' "$primary" "$state"
    ;;
  "ecs list-task-definitions")
    cat "$FIXTURES/list-$(value --family-prefix)"
    echo
    ;;
  "ecs describe-task-definition")
    arn="$(value --task-definition)"
    image="$(awk -v arn="$arn" '$1 == arn { print $2 }' "$FIXTURES/images")"
    echo "${image:-reg.example/erplora/hub:tag-${arn##*:}}"
    ;;
  "ecs update-service")
    service="$(value --service)"
    : > "$STATE/moved-$service"
    # The circuit breaker of FAKE_CIRCUIT_BREAKER's service puts its old revision back.
    if [ "${FAKE_CIRCUIT_BREAKER:-}" != "$service" ]; then
      value --task-definition > "$STATE/primary-$service"
    fi
    ;;
  *) ;;
esac
FAKE
  chmod +x "$work/bin/aws" "$work/bin/sleep"
}

# run_rollback [VAR=value...]: rolls back with the fake and CONFIRM=ROLLBACK; the arguments override.
run_rollback() {
  env -u CLUSTER -u POLL_SECONDS -u ROLLOUT_TIMEOUT_SECONDS \
    PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK "$@" \
    bash "$here/ecs-rollback.sh" > "$work/out.log" 2>&1
}

# run_rollback_without <VAR>: the same with <VAR> unset.
run_rollback_without() {
  env PATH="$work/bin:$PATH" AWS_REGION=eu-south-2 CONFIRM=ROLLBACK \
    env -u "$1" bash "$here/ecs-rollback.sh" > "$work/out.log" 2>&1
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
# reads_of <service>: how many times its PRIMARY deployment was read after the wait.
reads_of() {
  local from
  from="$(line_of "wait services-stable")"
  if [ -z "$from" ]; then
    echo 0
    return
  fi
  tail -n "+$from" "$CALLS_LOG" | grep -c -- "describe-services .*--services $1 " || true
}

# --- confirmation ---------------------------------------------------------------
setup
run_rollback_without CONFIRM && status=0 || status=$?
check "without CONFIRM it fails before any aws call" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'
check "the error asks for ROLLBACK" 'grep -q "::error::.*ROLLBACK" "$work/out.log"'
setup
run_rollback CONFIRM=rollback && status=0 || status=$?
check "CONFIRM must be exactly ROLLBACK" '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ]'

# --- a rollback that succeeds -------------------------------------------------------
setup
run_rollback && status=0 || status=$?
check "rollback succeeds" '[ "$status" -eq 0 ]'
check "warns that migrations are not undone" 'grep -qi "migrations are not undone" "$work/out.log"'
check "lists the ACTIVE revisions of each family, newest first" \
  'for s in hub worker; do grep -q "list-task-definitions --family-prefix erplora-prod-$s --status ACTIVE --sort DESC" "$CALLS_LOG" || exit 1; done'
check "hub goes back to the ACTIVE revision right before its PRIMARY one, of its own family" \
  'grep -q "update-service .*--service hub --task-definition $td/erplora-prod-hub:10 " "$CALLS_LOG"'
check "worker goes back to its previous revision" \
  'grep -q "update-service .*--service worker --task-definition $td/erplora-prod-worker:10 " "$CALLS_LOG"'
check "the rollback waits for both services to be stable" \
  '[ "$(line_of "wait services-stable .*--services hub worker")" -gt "$(last_line_of "update-service")" ]'
check "after the wait, each service's PRIMARY deployment is checked" \
  'for s in hub worker; do [ "$(last_line_of "describe-services .*--services $s ")" -gt "$(line_of "wait services-stable")" ] || exit 1; done'
check "the image tag is read from the restored revision" \
  'grep -q "describe-task-definition --task-definition $td/erplora-prod-hub:10 " "$CALLS_LOG"'
check "the restored tag is recorded in SSM" \
  'grep -q "^ssm put-parameter --name /erplora/prod/hub/image_tag --value tag-10 --type String --overwrite" "$CALLS_LOG"'
check "the tag is recorded only after the services are checked" \
  '[ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services")" ]'
check "every aws call names the region" '[ -s "$CALLS_LOG" ] && ! grep -qv -- "--region eu-south-2" "$CALLS_LOG"'

# --- nothing to roll back to ----------------------------------------------------------
setup
printf '%s\t' "$td/erplora-prod-hub-migrate:11" "$td/erplora-prod-hub:13" "$td/erplora-prod-hub:12" \
  > "$FIXTURES/list-erplora-prod-hub"
run_rollback && status=0 || status=$?
check "without a previous ACTIVE revision it fails" '[ "$status" -ne 0 ]'
check "and changes no service and records no tag" '! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "its error names the service" 'grep -q "::error::hub " "$work/out.log"'

setup
echo None > "$STATE/primary-worker"
run_rollback && status=0 || status=$?
check "a service without a PRIMARY deployment fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "::error::worker " "$work/out.log"'

# --- previous revisions that do not match ---------------------------------------------
setup
echo "$td/erplora-prod-worker:10 reg.example/erplora/hub:tag-9" > "$FIXTURES/images"
run_rollback && status=0 || status=$?
check "previous revisions on different tags fail without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG"'
check "that error names both tags" 'grep -q "::error::.*tag-10.*tag-9" "$work/out.log"'

setup
echo "$td/erplora-prod-hub:10 other.example/thing:1" > "$FIXTURES/images"
run_rollback && status=0 || status=$?
check "a previous revision without the hub image fails without changing anything" \
  '[ "$status" -ne 0 ] && ! grep -Eq "update-service|put-parameter" "$CALLS_LOG" && grep -q "other.example/thing:1" "$work/out.log"'

# --- the rollout after services-stable ----------------------------------------
# services-stable can return while the PRIMARY deployment is still IN_PROGRESS: ECS marks it
# COMPLETED once the old tasks have drained from the ALB, seconds to a minute later.
# rollback_error <service>: the error of a service the circuit breaker put back on revision 12.
rollback_error() {
  grep -qF "::error::$1 runs $td/erplora-prod-$1:12 (COMPLETED), not $td/erplora-prod-$1:10; rolled back by the circuit breaker? See the service events" "$work/out.log"
}

setup
run_rollback FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: IN_PROGRESS on the first read and COMPLETED on the second, the rollback succeeds" '[ "$status" -eq 0 ]'
check "rollout: each service's PRIMARY deployment is read again after one pause of POLL_SECONDS" \
  '[ "$(reads_of hub)" -eq 2 ] && [ "$(reads_of worker)" -eq 2 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15" ]'
check "rollout: the restored tag is recorded once every rollout is COMPLETED" \
  'grep -q "^ssm put-parameter --name /erplora/prod/hub/image_tag --value tag-10 " "$CALLS_LOG" &&
   [ "$(line_of "ssm put-parameter")" -gt "$(last_line_of "describe-services")" ]'
setup
run_rollback POLL_SECONDS=5 FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "rollout: POLL_SECONDS sets the pause" '[ "$status" -eq 0 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "5" ]'

setup
run_rollback FAKE_ROLLOUT_STATES=FAILED && status=0 || status=$?
check "a FAILED rollout fails the rollback at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "a FAILED rollout records no tag" '! grep -q "put-parameter" "$CALLS_LOG"'
check "the rollout error names the service and the state" 'grep -q "::error::hub .*FAILED" "$work/out.log"'
setup
run_rollback FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED" && status=0 || status=$?
check "a rollout that turns FAILED fails the rollback on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 2 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 1 ] && ! grep -q "put-parameter" "$CALLS_LOG"'

# The circuit breaker puts back the revision the service ran (12), and services-stable still succeeds.
setup
run_rollback FAKE_CIRCUIT_BREAKER=worker && status=0 || status=$?
check "a service the circuit breaker puts back fails the rollback at once, without a pause" \
  '[ "$status" -ne 0 ] && [ "$(reads_of worker)" -eq 1 ] && [ ! -s "$SLEEP_LOG" ]'
check "its error names the service and both revisions" 'rollback_error worker'
check "and no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_rollback FAKE_PRIMARY_REVISIONS="10 12" FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED" && status=0 || status=$?
check "a rollout IN_PROGRESS that the circuit breaker puts back fails the rollback on that read" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 2 ] && rollback_error hub && ! grep -q "put-parameter" "$CALLS_LOG"'

setup
run_rollback FAKE_ROLLOUT_STATES=IN_PROGRESS ROLLOUT_TIMEOUT_SECONDS=30 && status=0 || status=$?
check "rollout timeout 30 s: reads at 0, 15 and 30 seconds, then fails" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 3 ] && [ "$(paste -sd " " - < "$SLEEP_LOG")" = "15 15" ]'
check "rollout timeout: the error names each service and the limit" \
  'grep -q "::error::rollout of hub did not complete in 30 s" "$work/out.log" &&
   grep -q "::error::rollout of worker did not complete in 30 s" "$work/out.log"'
check "rollout timeout: no tag is recorded" '! grep -q "put-parameter" "$CALLS_LOG"'
setup
run_rollback FAKE_ROLLOUT_STATES=IN_PROGRESS && status=0 || status=$?
check "rollout timeout: 600 seconds by default (41 reads, 40 pauses)" \
  '[ "$status" -ne 0 ] && [ "$(reads_of hub)" -eq 41 ] && [ "$(wc -l < "$SLEEP_LOG")" -eq 40 ] &&
   grep -q "::error::rollout of hub did not complete in 600 s" "$work/out.log"'
for var in POLL_SECONDS ROLLOUT_TIMEOUT_SECONDS; do
  setup
  run_rollback "$var=soon" && status=0 || status=$?
  check "a $var that is not a number fails before any aws call" \
    '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q "::error::$var" "$work/out.log"'
done

# --- required environment -----------------------------------------------------------
setup
run_rollback_without AWS_REGION && status=0 || status=$?
check "without AWS_REGION it fails before any aws call" \
  '[ "$status" -ne 0 ] && [ ! -s "$CALLS_LOG" ] && grep -q AWS_REGION "$work/out.log"'

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
