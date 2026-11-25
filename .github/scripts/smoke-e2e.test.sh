#!/usr/bin/env bash
# Tests for smoke-e2e.sh: run from a throwaway git checkout whose scripts/nightly_e2e.py is a fake that logs the
# arguments and the settings it gets, so what is checked is the smoke's own contract with the night's stack.
#   bash .github/scripts/smoke-e2e.test.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# The smoke's cap, measured on the Mac's loaded stack: raising it is a decision, not a fix for a slow run.
CAP_MINUTES=20

g() { git -c user.name=smoke -c user.email=smoke@example.com -c init.defaultBranch=main "$@"; }

checkout="$root/hub"
scripts="$checkout/.github/scripts"
mkdir -p "$scripts" "$checkout/scripts" "$root/home"
if [ -f "$here/smoke-e2e.sh" ]; then
  cp "$here/smoke-e2e.sh" "$scripts/smoke-e2e.sh"
else
  echo '#!/usr/bin/env bash' > "$scripts/smoke-e2e.sh"
fi
cat > "$checkout/scripts/nightly_e2e.py" <<'EOF'
import os
import sys

settings = " ".join(f"{label}={os.environ.get(name, 'unset')}" for label, name in (
    ("GREP", "NIGHTLY_GREP"), ("REF", "NIGHTLY_HUB_REF"), ("MAX", "NIGHTLY_MAX_MINUTES"), ("DIR", "NIGHTLY_DIR"),
    ("PORT", "NIGHTLY_HUB_PORT")))
with open(os.environ["FAKE_CALLS"], "a", encoding="utf-8") as calls:
    calls.write(f"night args={' '.join(sys.argv[1:])} {settings}\n")
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
EOF
chmod +x "$scripts"/*.sh
g init -q "$checkout"
g -C "$checkout" add -A
g -C "$checkout" commit -q -m first
# A commit of a branch not pushed: the smoke checks what is checked out, never main.
g -C "$checkout" switch -q -c feature
g -C "$checkout" commit -q --allow-empty -m feature
head="$(git -C "$checkout" rev-parse HEAD)"

export FAKE_CALLS="$root/calls.log"

# smoke [VAR=value...] [-- <arguments>]: one smoke from the checkout, with a clean environment for the night's
# settings. Sets status; its output is $root/out, what the fake night got $FAKE_CALLS.
smoke() {
  local settings=()
  while [ $# -gt 0 ] && [ "$1" != -- ]; do
    settings+=("$1")
    shift
  done
  [ $# -eq 0 ] || shift
  : > "$FAKE_CALLS"
  status=0
  (cd "$root" && env -u NIGHTLY_GREP -u NIGHTLY_HUB_REF -u NIGHTLY_MAX_MINUTES -u NIGHTLY_DIR -u NIGHTLY_HUB_PORT \
    HOME="$root/home" ${settings[@]+"${settings[@]}"} bash "$scripts/smoke-e2e.sh" "$@") > "$root/out" 2>&1 || status=$?
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
calls() { grep -cF -- "$1" "$FAKE_CALLS" || true; }

smoke
expect "a green smoke ends green (0)" 0 "$status"
expect "it runs the night's stack once" 1 "$(calls 'night args=')"
expect "only the tests tagged @smoke" 1 "$(calls 'GREP=@smoke ')"
expect "on the commit checked out, even one not pushed" 1 "$(calls "REF=$head ")"
expect "cut at its measured cap" 1 "$(calls "MAX=$CAP_MINUTES ")"
expect "with no argument but its --spec" 1 "$(calls 'night args= GREP=')"
expect "in a folder of its own, so a night and a smoke never share a lock" 1 \
  "$(calls "DIR=$root/home/.erplora/hub-smoke-e2e ")"
expect "on ports of its own, beside the night's 9770" 1 "$(calls 'PORT=9780')"

smoke FAKE_EXIT=1
expect "a red smoke ends red (1)" 1 "$status"
smoke FAKE_EXIT=3
expect "a smoke while another runs in its folder says so (3)" 3 "$status"

smoke NIGHTLY_GREP=. NIGHTLY_MAX_MINUTES=360 NIGHTLY_HUB_REF=main
expect "the caller cannot widen the filter" 1 "$(calls 'GREP=@smoke ')"
expect "nor raise the cap" 1 "$(calls "MAX=$CAP_MINUTES ")"
expect "nor choose another commit" 1 "$(calls "REF=$head ")"

smoke NIGHTLY_DIR="$root/stack" NIGHTLY_HUB_PORT=20790
expect "a worker moves it to its own folder and ports" 1 "$(calls "DIR=$root/stack PORT=20790")"

smoke -- --spec tests/e2e/login-and-shell.spec.ts --spec tests/e2e/two-orgs-isolated.spec.ts
expect "--spec narrows it to those specs' @smoke tests" 1 \
  "$(calls 'night args=--spec tests/e2e/login-and-shell.spec.ts --spec tests/e2e/two-orgs-isolated.spec.ts GREP=@smoke ')"
expect "and a narrowed smoke still ends green (0)" 0 "$status"

for arguments in "--spec" "--spec --publish" "--spec tests/e2e/sale-pos.spec.ts --publish" "--grep ." "--publish"; do
  # shellcheck disable=SC2086 # the words of $arguments are the script's arguments
  smoke -- $arguments
  expect "the arguments '$arguments' are refused (2)" 2 "$status"
  expect "and nothing runs" 0 "$(calls 'night args=')"
done

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
