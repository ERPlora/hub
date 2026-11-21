#!/usr/bin/env bash
# Clones a GitHub repository at depth 1 as the job's token, retrying a failed attempt:
#   GH_TOKEN=<token> bash .github/scripts/clone-repo.sh <owner/name> <dir> [<path>...]
# With paths, only those are checked out, and only their files are downloaded.
# GitHub limits anonymous clones from its shared runners and refuses them with a 403. git only offers
# credentials after a 401, which a public repository never asks for, so the token goes up front in an
# Authorization header, on every call that reaches GitHub: the clone and, in a sparse one, the checkout
# that fetches the paths' files. It goes through git's environment, so it is in neither the arguments
# nor the clone's config. An attempt that fails (a 403, a 5xx, a cut or hung connection) starts over
# from an empty folder: ATTEMPTS in all, RETRY_DELAY_SECONDS apart, each cut at ATTEMPT_TIMEOUT_SECONDS.
#
# Env: GH_TOKEN (required), optional ATTEMPTS (5), RETRY_DELAY_SECONDS (10), ATTEMPT_TIMEOUT_SECONDS (120).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

if [ "$#" -lt 2 ]; then
  fail "usage: clone-repo.sh <owner/name> <dir> [<path>...]"
fi
repo="$1" dir="$2"
shift 2
if [ -z "${GH_TOKEN:-}" ]; then
  fail "GH_TOKEN is empty: GitHub refuses anonymous clones from its runners, so $repo is cloned as the job's token"
fi
attempts="${ATTEMPTS:-5}" delay="${RETRY_DELAY_SECONDS:-10}" timeout="${ATTEMPT_TIMEOUT_SECONDS:-120}"
if ! [[ "$attempts" =~ ^[1-9][0-9]*$ ]]; then
  fail "ATTEMPTS must be a whole number of 1 or more, not '$attempts'"
fi
if ! [[ "$delay" =~ ^[0-9]+$ ]]; then
  fail "RETRY_DELAY_SECONDS must be a whole number of 0 or more, not '$delay'"
fi
if ! [[ "$timeout" =~ ^[1-9][0-9]*$ ]]; then
  fail "ATTEMPT_TIMEOUT_SECONDS must be a whole number of 1 or more, not '$timeout'"
fi

server="${GITHUB_SERVER_URL:-https://github.com}"
credentials="$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')"
echo "::add-mask::$credentials"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.$server/.extraheader"
export GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $credentials"

clone() {
  if [ "$#" -eq 0 ]; then
    timeout "$timeout" git clone --quiet --depth 1 "$server/$repo.git" "$dir"
  else
    timeout "$timeout" git clone --quiet --depth 1 --filter=blob:none --sparse "$server/$repo.git" "$dir" &&
      timeout "$timeout" git -C "$dir" sparse-checkout set "$@"
  fi
}

for attempt in $(seq "$attempts"); do
  rm -rf "$dir"
  if clone "$@"; then
    exit 0
  fi
  if [ "$attempt" -lt "$attempts" ]; then
    echo "attempt $attempt of $attempts to clone $repo failed; trying again in $delay s" >&2
    sleep "$delay"
  fi
done
rm -rf "$dir"
fail "could not clone $repo after $attempts attempt(s) (git's error above); if GitHub is down, re-run the job once it answers"
