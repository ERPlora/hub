#!/usr/bin/env bash
# Downloads a tool the CI pins and checks it against its SHA-256:
#   bash .github/scripts/download-tool.sh <url> <sha256> <output>
# A passing error of the server (a 5xx, a cut connection, an answer that hangs) is retried, so one
# bad answer of GitHub does not turn a PR red (hub#830): ATTEMPTS attempts in all, RETRY_DELAY_SECONDS
# apart, each cut at ATTEMPT_TIMEOUT_SECONDS (GitHub's 504 came after 2 minutes of waiting); with the
# defaults the worst case is 5 x 60 s + 4 x 10 s = 340 s, or 410 s when the server asks to wait with
# Retry-After (the 350 s budget below plus one attempt), inside test.yml's 15-minute job. When every
# attempt fails, or the file is not the pinned one, it fails with an ::error:: that names the URL;
# <output> only appears when the file matches its pin.
#
# Env: optional ATTEMPTS (5), RETRY_DELAY_SECONDS (10), ATTEMPT_TIMEOUT_SECONDS (60).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

if [ "$#" -ne 3 ]; then
  fail "usage: download-tool.sh <url> <sha256> <output>"
fi
url="$1" sha256="$2" output="$3"
if ! [[ "$sha256" =~ ^[0-9a-f]{64}$ ]]; then
  fail "the pin of $url must be a SHA-256 (64 lowercase hex digits), not '$sha256'"
fi

attempts="${ATTEMPTS:-5}" delay="${RETRY_DELAY_SECONDS:-10}" timeout="${ATTEMPT_TIMEOUT_SECONDS:-60}"
if ! [[ "$attempts" =~ ^[1-9][0-9]*$ ]]; then
  fail "ATTEMPTS must be a whole number of 1 or more, not '$attempts'"
fi
if ! [[ "$delay" =~ ^[0-9]+$ ]]; then
  fail "RETRY_DELAY_SECONDS must be a whole number of 0 or more, not '$delay'"
fi
if ! [[ "$timeout" =~ ^[1-9][0-9]*$ ]]; then
  fail "ATTEMPT_TIMEOUT_SECONDS must be a whole number of 1 or more, not '$timeout'"
fi

# The download goes to a partial file next to <output>, which only takes its name once it matches.
partial="$output.partial"
rm -f "$partial"
trap 'rm -f "$partial"' EXIT

# --retry-all-errors: curl's --retry alone gives up on a cut connection. RETRY_DELAY_SECONDS=0 leaves
# the wait to curl's own backoff (1 s, doubling each time). --retry-max-time: a Retry-After of the
# server longer than --retry-delay replaces it, so a 429/503 asking for minutes would outlast the job;
# past this budget curl gives up at once instead of waiting it out, and a curl that gives up that way
# can still exit 0 with nothing downloaded (curl 8.22 does), so a missing file is a failure too.
budget=$((attempts * (timeout + delay)))
if ! curl --fail --silent --show-error --location \
  --retry "$((attempts - 1))" --retry-delay "$delay" --retry-all-errors --max-time "$timeout" \
  --retry-max-time "$budget" --output "$partial" "$url" || [ ! -f "$partial" ]; then
  fail "could not download $url (curl's error above): it gave up after $attempts attempt(s) or ${budget} s of retries; if GitHub is down, re-run the job once it answers"
fi

actual="$(sha256sum "$partial" | cut -d ' ' -f 1)"
if [ "$actual" != "$sha256" ]; then
  fail "$url is not the pinned file: its SHA-256 is $actual, the pin $sha256"
fi
mv "$partial" "$output"
