#!/usr/bin/env bash
# Tests for deploy-order.sh against throwaway git repositories and a fake aws CLI that answers the
# tag the environment runs (RUNNING_TAG) and records its calls.
#   bash .github/scripts/deploy-order.test.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Commits never read the developer's git configuration (identity, signing).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
commit() { git -C "$1" -c user.name=ci -c user.email=ci@example.com commit --quiet --allow-empty -m "$2"; git -C "$1" rev-parse HEAD; }

# origin: c1 - c2 - c3 on main, and c4 on a line that left main after c1. The checkout is a clone of
# origin taken before c3, as a deploy job checks out its commit: c3 is only in origin.
git init --quiet -b main "$work/origin"
c1="$(commit "$work/origin" c1)"
c2="$(commit "$work/origin" c2)"
git clone --quiet "$work/origin" "$work/checkout"
c3="$(commit "$work/origin" c3)"
git -C "$work/origin" switch --quiet -c side "$c1"
c4="$(commit "$work/origin" c4)"
git -C "$work/origin" switch --quiet main
git -C "$work/checkout" fetch --quiet origin side

mkdir -p "$work/bin"
cat > "$work/bin/aws" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$CALLS_LOG"
if [ -n "${AWS_FAILS:-}" ]; then
  echo "An error occurred (AccessDeniedException) when calling the GetParameter operation" >&2
  exit 254
fi
echo "$RUNNING_TAG"
FAKE
chmod +x "$work/bin/aws"
export CALLS_LOG="$work/calls.log"

# order [VAR=value...]: runs deploy-order.sh in the checkout; prints its GITHUB_OUTPUT or FAILS.
order() {
  local output="$work/output"
  : > "$output"
  : > "$CALLS_LOG"
  if (cd "$work/checkout" && env PATH="$work/bin:$PATH" AWS_REGION=eu-west-1 ENVIRONMENT=prod \
    GITHUB_OUTPUT="$output" RELEASE="" "$@" bash "$here/deploy-order.sh") > /dev/null 2>&1; then
    cat "$output"
  else
    echo FAILS
    if [ -s "$output" ]; then echo "(wrote output)"; fi
  fi
}

# expect <name> <expected> <actual>
expect() {
  if [ "$3" = "$2" ]; then
    echo "ok   - $1"
  else
    echo "FAIL - $1: expected '$2', got '$3'"
    failures=$((failures + 1))
  fi
}

# --- which deploys go on ------------------------------------------------------------------------
expect "a commit newer than the running one deploys" "deploy=true" "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c1")"
expect "the running commit itself (a re-run) deploys" "deploy=true" "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c2")"
expect "a commit older than the running one deploys nothing" "deploy=false" \
  "$(order IMAGE_TAG="$c1" RUNNING_TAG="$c2")"
expect "a running commit only origin has is fetched: an older one deploys nothing" "deploy=false" \
  "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c3")"
expect "a commit off the running one's line deploys" "deploy=true" "$(order IMAGE_TAG="$c4" RUNNING_TAG="$c2")"
expect "a running tag that is no commit (bootstrap) deploys" "deploy=true" \
  "$(order IMAGE_TAG="$c2" RUNNING_TAG=bootstrap)"
expect "a running tag that names a branch, not a commit, deploys" "deploy=true" \
  "$(order IMAGE_TAG="$c1" RUNNING_TAG=main)"
expect "a release redeploy goes back on purpose" "deploy=true" \
  "$(order IMAGE_TAG="$c1" RUNNING_TAG="$c2" RELEASE=hub-v2026.10.13.1)"
expect "a release redeploy reads no parameter" "" "$(cat "$CALLS_LOG")"

# --- the parameter of its environment -------------------------------------------------------------
order IMAGE_TAG="$c2" RUNNING_TAG="$c1" > /dev/null
expect "prod reads /erplora/prod/hub/image_tag" \
  "ssm get-parameter --name /erplora/prod/hub/image_tag --query Parameter.Value --output text --region eu-west-1" \
  "$(cat "$CALLS_LOG")"
order IMAGE_TAG="$c2" RUNNING_TAG="$c1" ENVIRONMENT=pre > /dev/null
expect "pre reads /erplora/pre/hub/image_tag" \
  "ssm get-parameter --name /erplora/pre/hub/image_tag --query Parameter.Value --output text --region eu-west-1" \
  "$(cat "$CALLS_LOG")"
order IMAGE_TAG="$c2" RUNNING_TAG="$c1" PROJECT=saas > /dev/null
expect "saas reads its own parameter" \
  "ssm get-parameter --name /erplora/prod/saas/image_tag --query Parameter.Value --output text --region eu-west-1" \
  "$(cat "$CALLS_LOG")"

# --- refusals, writing nothing --------------------------------------------------------------------
expect "an unreadable parameter fails" FAILS "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c1" AWS_FAILS=1)"
expect "an empty parameter fails" FAILS "$(order IMAGE_TAG="$c2" RUNNING_TAG="")"
expect "an image tag that is no commit here fails" FAILS "$(order IMAGE_TAG=0123abc RUNNING_TAG="$c1")"
expect "a missing IMAGE_TAG fails" FAILS "$(order IMAGE_TAG="" RUNNING_TAG="$c1")"
expect "an unknown environment fails" FAILS "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c1" ENVIRONMENT=dev)"
expect "a missing AWS_REGION fails" FAILS "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c1" AWS_REGION="")"
expect "a missing GITHUB_OUTPUT fails" FAILS "$(order IMAGE_TAG="$c2" RUNNING_TAG="$c1" GITHUB_OUTPUT="")"

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
