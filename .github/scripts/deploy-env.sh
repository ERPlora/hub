#!/usr/bin/env bash
# Picks the environment a run of deploy.yml or rollback.yml works on, from its branch: main → prod,
# pre → pre (the team's pre-production, pre.erplora.com; aws-next README, "Contrato"). Writes to
# $GITHUB_OUTPUT:
#   environment     prod | pre
#   ecr_repository  erplora/<project> | erplora/<project>-pre (pre has repositories of its own, so its
#                   pushes never expire prod's images)
#   readyz_host     the public host whose /readyz closes a deploy
#   role_arn        the deploy role of that environment: AWS_DEPLOY_ROLE_ARN (trusts main) or
#                   AWS_DEPLOY_ROLE_ARN_PRE (trusts pre); never the other one
# Refuses, writing nothing: a branch that is neither main nor pre; a manual run that asks for an
# environment other than its branch's; a release outside prod (releases are prod's); an event other
# than a push or a manual run; an empty role variable for that environment.
#
# Env: PROJECT (hub | saas), GITHUB_REF, GITHUB_EVENT_NAME (push | workflow_dispatch), GITHUB_OUTPUT;
#      INPUT_ENVIRONMENT (manual runs: prod | pre), INPUT_RELEASE (optional), AWS_DEPLOY_ROLE_ARN,
#      AWS_DEPLOY_ROLE_ARN_PRE.
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

if [ -z "${GITHUB_OUTPUT:-}" ]; then
  fail "GITHUB_OUTPUT is required"
fi

PROJECT="${PROJECT:-}"
case "$PROJECT" in
  hub) prod_host=hubs.erplora.com pre_host=hubs.pre.erplora.com ;;
  saas) prod_host=erplora.com pre_host=pre.erplora.com ;;
  *) fail "PROJECT must be hub or saas, not '$PROJECT'" ;;
esac

ref="${GITHUB_REF:-}"
case "$ref" in
  refs/heads/main) environment=prod ;;
  refs/heads/pre) environment=pre ;;
  "") fail "GITHUB_REF is required" ;;
  *) fail "only main (prod) and pre deploy, not $ref" ;;
esac

event="${GITHUB_EVENT_NAME:-}"
case "$event" in
  push) ;;
  workflow_dispatch)
    asked="${INPUT_ENVIRONMENT:-}"
    case "$asked" in
      prod | pre) ;;
      "") fail "a manual run must name its environment (prod or pre)" ;;
      *) fail "unknown environment '$asked' (prod or pre)" ;;
    esac
    if [ "$asked" != "$environment" ]; then
      fail "a manual run for $asked must start from its branch, not from ${ref#refs/heads/} ($environment)"
    fi
    ;;
  *) fail "the event '$event' deploys nowhere: only a push or a manual run" ;;
esac

if [ -n "${INPUT_RELEASE:-}" ] && [ "$environment" != prod ]; then
  fail "a release is prod's: $environment redeploys by running deploy.yml on its branch, without a release"
fi

if [ "$environment" = prod ]; then
  role_variable=AWS_DEPLOY_ROLE_ARN ecr_repository="erplora/$PROJECT" readyz_host="$prod_host"
else
  role_variable=AWS_DEPLOY_ROLE_ARN_PRE ecr_repository="erplora/$PROJECT-pre" readyz_host="$pre_host"
fi
role_arn="${!role_variable:-}"
if [ -z "$role_arn" ]; then
  fail "empty repository variable $role_variable, the deploy role of $environment (aws-next README)"
fi

{
  echo "environment=$environment"
  echo "ecr_repository=$ecr_repository"
  echo "readyz_host=$readyz_host"
  echo "role_arn=$role_arn"
} >> "$GITHUB_OUTPUT"
echo "environment: $environment ($ecr_repository, $readyz_host)"
