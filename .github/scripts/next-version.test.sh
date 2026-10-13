#!/usr/bin/env bash
# Tests for next-version.sh, the next CalVer release tag of a project.
#   bash .github/scripts/next-version.test.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0

# next <project> <day> [tag...]: runs next-version.sh with the tags on stdin.
next() {
  local project="$1" day="$2"
  shift 2
  printf '%s\n' "$@" | bash "$here/next-version.sh" "$project" "$day"
}

# expect <name> <expected output | FAILS> <project> <day> [tag...]
expect() {
  local name="$1" expected="$2" actual
  shift 2
  actual="$(next "$@" 2> /dev/null)" || actual="FAILS"
  if [ "$actual" = "$expected" ]; then
    echo "ok   - $name"
  else
    echo "FAIL - $name: expected '$expected', got '$actual'"
    failures=$((failures + 1))
  fi
}

# --- next number ------------------------------------------------------------
expect "first release ever is .1" \
  hub-v2026.10.11.1 hub 2026.10.11
expect "first release of the day is .1" \
  hub-v2026.10.11.1 hub 2026.10.11 hub-v2026.10.09.1 hub-v2026.10.10.5
expect "same day counts up" \
  hub-v2026.10.11.3 hub 2026.10.11 hub-v2026.10.11.1 hub-v2026.10.11.2
expect "the order of the tags does not matter" \
  hub-v2026.10.11.3 hub 2026.10.11 hub-v2026.10.11.2 hub-v2026.10.11.1
expect "numbers compare as numbers, not as text" \
  hub-v2026.10.11.11 hub 2026.10.11 hub-v2026.10.11.9 hub-v2026.10.11.10
expect "a gap continues after the highest number" \
  hub-v2026.10.11.4 hub 2026.10.11 hub-v2026.10.11.1 hub-v2026.10.11.3
expect "the other project's tags do not count" \
  hub-v2026.10.11.1 hub 2026.10.11 saas-v2026.10.11.4
expect "saas gets its own sequence" \
  saas-v2026.10.11.2 saas 2026.10.11 saas-v2026.10.11.1 hub-v2026.10.11.7
expect "look-alike tags are ignored" \
  hub-v2026.10.11.1 hub 2026.10.11 \
  hubx-v2026.10.11.7 xhub-v2026.10.11.6 hub-v2026.10.11.2-rc hub-v2026.10.11 \
  hub-v2026.10.11. hub-v2026x10x11.5 hub-v2026.10.111.1

# --- invalid input ----------------------------------------------------------
expect "an unknown project fails" FAILS nope 2026.10.11
expect "a missing project fails" FAILS "" 2026.10.11
expect "a missing day fails" FAILS hub ""
expect "a day that is not YYYY.MM.DD fails" FAILS hub 2026-10-11

echo
if [ "$failures" -ne 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
