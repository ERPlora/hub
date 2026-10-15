#!/usr/bin/env bash
# Tests for deploy-env.sh: the environment of a deploy or rollback run, picked from its branch.
#   bash .github/scripts/deploy-env.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
PROD_ROLE="arn:aws:iam::123456789012:role/gha-deploy-hub"
PRE_ROLE="arn:aws:iam::123456789012:role/gha-deploy-hub-pre"

# pick [VAR=value...]: runs deploy-env.sh for a push of the hub to main with both roles set; the
# arguments override that environment. Its GITHUB_OUTPUT is $work/output, its log $work/out.log.
pick() {
  work="$(mktemp -d)"
  : > "$work/output"
  env -u INPUT_ENVIRONMENT -u INPUT_RELEASE \
    PROJECT=hub GITHUB_REF=refs/heads/main GITHUB_EVENT_NAME=push GITHUB_OUTPUT="$work/output" \
    AWS_DEPLOY_ROLE_ARN="$PROD_ROLE" AWS_DEPLOY_ROLE_ARN_PRE="$PRE_ROLE" "$@" \
    bash "$here/deploy-env.sh" > "$work/out.log" 2>&1
}

# output_is <lines...>: GITHUB_OUTPUT holds exactly these lines, in this order.
output_is() { [ "$(cat "$work/output")" = "$(printf '%s\n' "$@")" ]; }

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    failures=$((failures + 1))
  fi
}

# refused <words>: the run failed, wrote no output and its ::error:: names <words>.
refused() { [ "$status" -ne 0 ] && [ ! -s "$work/output" ] && grep -q "::error::.*$1" "$work/out.log"; }

# --- a push picks the environment of its branch -----------------------------------
pick && status=0 || status=$?
check "push to main: prod, the hub's ECR repository, hubs.erplora.com and the prod role" \
  '[ "$status" -eq 0 ] && output_is environment=prod ecr_repository=erplora/hub readyz_host=hubs.erplora.com "role_arn=$PROD_ROLE"'
pick GITHUB_REF=refs/heads/pre && status=0 || status=$?
check "push to pre: pre, its own ECR repository, hubs.pre.erplora.com and the pre role" \
  '[ "$status" -eq 0 ] && output_is environment=pre ecr_repository=erplora/hub-pre readyz_host=hubs.pre.erplora.com "role_arn=$PRE_ROLE"'
pick PROJECT=saas && status=0 || status=$?
check "the saas on main: erplora/saas and erplora.com" \
  '[ "$status" -eq 0 ] && output_is environment=prod ecr_repository=erplora/saas readyz_host=erplora.com "role_arn=$PROD_ROLE"'
pick PROJECT=saas GITHUB_REF=refs/heads/pre && status=0 || status=$?
check "the saas on pre: erplora/saas-pre and pre.erplora.com" \
  '[ "$status" -eq 0 ] && output_is environment=pre ecr_repository=erplora/saas-pre readyz_host=pre.erplora.com "role_arn=$PRE_ROLE"'

# --- any other branch or ref ------------------------------------------------------
for ref in refs/heads/feature refs/heads/pre-x refs/heads/main2 refs/tags/hub-v2026.10.14.1 refs/pull/3/merge; do
  pick GITHUB_REF="$ref" && status=0 || status=$?
  check "$ref deploys nowhere" 'refused "$ref"'
done
pick GITHUB_REF= && status=0 || status=$?
check "without GITHUB_REF it deploys nowhere" 'refused GITHUB_REF'

# --- a manual run must ask for its branch's environment ---------------------------
pick GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=prod && status=0 || status=$?
check "manual run of main asking for prod: prod" '[ "$status" -eq 0 ] && grep -qx environment=prod "$work/output"'
pick GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=pre && status=0 || status=$?
check "manual run of pre asking for pre: pre" '[ "$status" -eq 0 ] && grep -qx environment=pre "$work/output"'
pick GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=pre && status=0 || status=$?
check "manual run of main asking for pre is refused" 'refused "pre.*main"'
pick GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=prod && status=0 || status=$?
check "manual run of pre asking for prod is refused" 'refused "prod.*pre"'
pick GITHUB_EVENT_NAME=workflow_dispatch && status=0 || status=$?
check "manual run without an environment is refused" 'refused environment'
pick GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=staging && status=0 || status=$?
check "manual run asking for an unknown environment is refused" 'refused staging'

# --- releases are prod's ----------------------------------------------------------
pick GITHUB_EVENT_NAME=workflow_dispatch INPUT_ENVIRONMENT=prod INPUT_RELEASE=hub-v2026.10.14.1 && status=0 || status=$?
check "a release in prod is allowed" '[ "$status" -eq 0 ] && grep -qx environment=prod "$work/output"'
pick GITHUB_EVENT_NAME=workflow_dispatch GITHUB_REF=refs/heads/pre INPUT_ENVIRONMENT=pre INPUT_RELEASE=hub-v2026.10.14.1 &&
  status=0 || status=$?
check "a release in pre is refused" 'refused "release"'

# --- only pushes and manual runs --------------------------------------------------
for event in pull_request schedule workflow_call ""; do
  pick GITHUB_EVENT_NAME="$event" && status=0 || status=$?
  check "the event '$event' deploys nowhere" 'refused "event"'
done

# --- the deploy role of that environment, never the other one ---------------------
pick AWS_DEPLOY_ROLE_ARN= && status=0 || status=$?
check "prod without AWS_DEPLOY_ROLE_ARN is refused" 'refused AWS_DEPLOY_ROLE_ARN'
pick GITHUB_REF=refs/heads/pre AWS_DEPLOY_ROLE_ARN_PRE= && status=0 || status=$?
check "pre without AWS_DEPLOY_ROLE_ARN_PRE is refused, never falling back to prod's role" \
  'refused AWS_DEPLOY_ROLE_ARN_PRE'
pick GITHUB_REF=refs/heads/pre AWS_DEPLOY_ROLE_ARN= && status=0 || status=$?
check "pre does not need prod's role" '[ "$status" -eq 0 ] && grep -qx "role_arn=$PRE_ROLE" "$work/output"'

# --- required environment ---------------------------------------------------------
for project in "" web hubs; do
  pick PROJECT="$project" && status=0 || status=$?
  check "PROJECT '$project' is refused" 'refused PROJECT'
done
work="$(mktemp -d)"
env -u GITHUB_OUTPUT PROJECT=hub GITHUB_REF=refs/heads/main GITHUB_EVENT_NAME=push AWS_DEPLOY_ROLE_ARN="$PROD_ROLE" \
  bash "$here/deploy-env.sh" > "$work/out.log" 2>&1 && status=0 || status=$?
check "without GITHUB_OUTPUT it fails" '[ "$status" -ne 0 ] && grep -q "::error::GITHUB_OUTPUT" "$work/out.log"'

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
