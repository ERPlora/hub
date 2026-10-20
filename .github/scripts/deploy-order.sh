#!/usr/bin/env bash
# Decides whether a run of deploy.yml still deploys: an environment never goes back to an older
# commit. Tests and image build run outside the deploy lock (only the deploy job holds it), so the
# deploy job of an older push may get the lock after a newer push has deployed; it then deploys
# nothing (the newer commit already contains it). A release redeploy goes back on purpose.
# Reads the tag the environment runs (/erplora/<environment>/<project>/image_tag, which ecs-deploy.sh
# and ecs-rollback.sh record) and writes to $GITHUB_OUTPUT:
#   deploy=false  IMAGE_TAG is an ancestor of the running commit, and not that commit itself;
#   deploy=true   a newer commit, the same one (a re-run), one off the running commit's line, a running
#                 tag that is no full commit SHA (bootstrap), or a release redeploy (RELEASE given).
# The running commit is fetched from origin when the checkout lacks it.
# Refuses, writing nothing: missing env, an unknown environment, an unreadable or empty parameter, an
# IMAGE_TAG that is no commit of the checkout.
#
# Env: AWS_REGION, ENVIRONMENT (prod | pre), IMAGE_TAG (the commit to deploy), GITHUB_OUTPUT;
#      optional PROJECT (hub), RELEASE (the release a manual run redeploys).
# Runs in the checkout of the repository.
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

for var in AWS_REGION IMAGE_TAG GITHUB_OUTPUT; do
  if [ -z "${!var:-}" ]; then
    fail "$var is required"
  fi
done
case "${ENVIRONMENT:-}" in
  prod | pre) ;;
  *) fail "ENVIRONMENT must be prod or pre, not '${ENVIRONMENT:-}'" ;;
esac
PROJECT="${PROJECT:-hub}"

if [ -n "${RELEASE:-}" ]; then
  echo "deploy=true" >> "$GITHUB_OUTPUT"
  echo "redeploying the release $RELEASE"
  exit 0
fi

if ! git cat-file -e "${IMAGE_TAG}^{commit}" 2> /dev/null; then
  fail "$IMAGE_TAG is not a commit of this checkout"
fi

parameter="/erplora/$ENVIRONMENT/$PROJECT/image_tag"
if ! running="$(aws ssm get-parameter --name "$parameter" --query Parameter.Value --output text \
  --region "$AWS_REGION")"; then
  fail "cannot read $parameter"
fi
if [ -z "$running" ]; then
  fail "$parameter is empty"
fi

# Only a full commit SHA is a commit here: never a ref name that happens to resolve.
deploy=true
if [ "$running" != "$IMAGE_TAG" ] && [[ "$running" =~ ^[0-9a-f]{40}$ ]]; then
  if ! git cat-file -e "${running}^{commit}" 2> /dev/null; then
    git fetch --quiet --no-tags origin "$running" 2> /dev/null || true
  fi
  if git cat-file -e "${running}^{commit}" 2> /dev/null && git merge-base --is-ancestor "$IMAGE_TAG" "$running"; then
    deploy=false
  fi
fi

echo "deploy=$deploy" >> "$GITHUB_OUTPUT"
if [ "$deploy" = true ]; then
  echo "$ENVIRONMENT runs $running: deploying $IMAGE_TAG"
else
  echo "$ENVIRONMENT already runs $running, newer than $IMAGE_TAG: nothing to deploy"
fi
