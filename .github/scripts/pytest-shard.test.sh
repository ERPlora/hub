#!/usr/bin/env bash
# Tests for pytest-shard.sh against a fake uv and date on the PATH: shard <index> of <total> (GitHub's
# strategy.job-index, from 0, and strategy.job-total) runs pytest-split's group <index + 1> of <total> with
# the locked environment and the rest of the arguments, ends with pytest's own exit code, warns when it
# took longer than it was told, and refuses an index or total that would leave part of the suite unrun.
#   bash .github/scripts/pytest-shard.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later.
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

# The fake commands log each call to $FAKE_CALLS, one line per call.
#   uv run --locked pytest <args...>: logs "pytest <args...>" and exits with $FAKE_PYTEST_EXIT (0); any other
#   call of uv (another subcommand, without --locked, without pytest) fails like an unknown command (exit 2).
#   date +%s: logs "date" and prints the next second of $FAKE_CLOCK, one per line (each read is consumed),
#   so the case decides how long pytest took; any other call of date fails.
mkdir -p "$root/bin"
cat > "$root/bin/uv" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" != run ] || [ "${2:-}" != --locked ] || [ "${3:-}" != pytest ]; then
  echo "uv $*" >> "$FAKE_CALLS"
  echo "error: unexpected uv call: $*" >&2
  exit 2
fi
shift 3
echo "pytest $*" >> "$FAKE_CALLS"
echo "pytest ran"
exit "${FAKE_PYTEST_EXIT:-0}"
EOF
cat > "$root/bin/date" <<'EOF'
#!/usr/bin/env bash
echo "date $*" >> "$FAKE_CALLS"
if [ "$*" != "+%s" ]; then
  echo "date: unexpected call: $*" >&2
  exit 1
fi
head -n 1 "$FAKE_CLOCK"
tail -n +2 "$FAKE_CLOCK" > "$FAKE_CLOCK.next" && mv "$FAKE_CLOCK.next" "$FAKE_CLOCK"
EOF
chmod +x "$root/bin/uv" "$root/bin/date"

# shard <seconds pytest takes> [VAR=value...] -- <arguments of pytest-shard.sh...>: runs pytest-shard.sh with
# the fake commands, the clock starting at 1000 and moving <seconds> while pytest runs. Sets status (its exit
# code) and work: $work/out.log (its output) and $work/calls (the fake commands' calls).
shard() {
  local took="$1"
  shift
  local settings=()
  while [ "$1" != -- ]; do
    settings+=("$1")
    shift
  done
  shift
  work="$(mktemp -d "$root/case.XXXXXX")"
  printf '%s\n' 1000 "$((1000 + took))" > "$work/clock"
  : > "$work/calls"
  status=0
  # ${settings[@]+...}: an empty array under set -u is an unbound variable for macOS's bash 3.2, which then ends the
  # whole file with exit 0 through the EXIT trap, a green without a single case run.
  env PATH="$root/bin:$PATH" FAKE_CALLS="$work/calls" FAKE_CLOCK="$work/clock" ${settings[@]+"${settings[@]}"} \
    bash "$here/pytest-shard.sh" "$@" > "$work/out.log" 2>&1 || status=$?
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    sed 's/^/       /' "$work/out.log"
    sed 's/^/       call: /' "$work/calls"
    failures=$((failures + 1))
  fi
}

# ran <args>: pytest ran once, with exactly <args>.
ran() { [ "$(grep -c '^pytest' "$work/calls" | tr -d ' ')" = 1 ] && [ "$(grep '^pytest' "$work/calls")" = "pytest $1" ]; }
# never_ran: pytest did not run at all.
never_ran() { ! grep -q '^pytest' "$work/calls"; }
# warned: a GitHub warning annotation was written.
warned() { grep -q '^::warning' "$work/out.log"; }
# refused <regex>: red, pytest never ran and an ::error:: matches <regex>.
refused() { [ "$status" -ne 0 ] && never_ran && grep -qE "::error::.*$1" "$work/out.log"; }

# --- which part of the suite ----------------------------------------------------------------------
shard 60 -- 0 3 20 -q -n 4
check "the first job of the matrix (index 0) runs group 1 of 3, the rest of the arguments after" \
  '[ "$status" = 0 ] && ran "--splits 3 --group 1 --splitting-algorithm least_duration -q -n 4"'

shard 60 -- 2 3 20 -q
check "the last job (index 2 of 3) runs group 3" 'ran "--splits 3 --group 3 --splitting-algorithm least_duration -q"'

shard 60 -- 0 1 20
check "a matrix of one job runs the whole suite as group 1 of 1" \
  'ran "--splits 1 --group 1 --splitting-algorithm least_duration"'

# Every group of a split, and only those: the union of the jobs of a matrix is the whole suite.
groups=""
for index in 0 1 2 3; do
  shard 60 -- "$index" 4 20
  groups="$groups $(sed -n 's/^pytest --splits 4 --group \([0-9]*\) .*/\1/p' "$work/calls")"
done
check "the four jobs of a matrix of four run the groups 1, 2, 3 and 4, once each" '[ "$groups" = " 1 2 3 4" ]'

# --- what it ends with ----------------------------------------------------------------------------
shard 60 FAKE_PYTEST_EXIT=1 -- 1 3 20 -q
check "a failing test ends the shard in red with pytest's own exit code" '[ "$status" = 1 ] && ran "--splits 3 --group 2 --splitting-algorithm least_duration -q"'

shard 60 FAKE_PYTEST_EXIT=5 -- 1 3 20
check "a group where pytest collects nothing is red too (pytest's exit 5)" '[ "$status" = 5 ]'

shard 60 -- 1 3 20
check "it says how long its pytest took" 'grep -q "shard 2 of 3: pytest took 1 min 0 s" "$work/out.log"'

# --- the warning before the job's timeout ---------------------------------------------------------
shard 1200 -- 1 3 20
check "a shard that took exactly the minutes it was given does not warn" '[ "$status" = 0 ] && ! warned'

shard 1201 -- 1 3 20
check "a shard that took longer warns, saying which shard and that the matrix needs another one" \
  '[ "$status" = 0 ] && grep -qE "^::warning.*shard 2 of 3.*20 min.*add a shard" "$work/out.log"'

shard 1500 FAKE_PYTEST_EXIT=1 -- 0 3 20
check "a slow shard that fails warns and stays red" '[ "$status" = 1 ] && warned'

# --- what it is given -----------------------------------------------------------------------------
for arguments in "3 3 20" "4 3 20" "0 0 20" "x 3 20" "0 x 20" "0 3 x" "0 3 0" "-1 3 20" "0 3"; do
  # shellcheck disable=SC2086 # the words of $arguments are the script's arguments
  shard 60 -- $arguments
  check "the arguments '$arguments' are refused before pytest runs" 'refused "usage|index|total|minutes"'
done

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
