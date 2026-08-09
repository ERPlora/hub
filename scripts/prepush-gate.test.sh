#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Tests for .githooks/pre-push — the LOCAL test gate that replaces the
# "Hub tests (Rust · Postgres)" workflow on pull requests.
#
# Run:  scripts/prepush-gate.test.sh
#
# The hook is driven through injection points so these tests never compile Rust,
# never touch Docker and never call GitHub:
#   HUB_GATE_TEST_CMD    the suite to run       (default: cargo test --workspace …)
#   HUB_GATE_STATUS_CMD  how to publish the commit status  (default: gh api …)
#   HUB_GATE_STATE_DIR   where the green marks and the lock live
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.githooks/pre-push"
ZERO=0000000000000000000000000000000000000000
pass=0
fail=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# A throwaway git repo with one commit, so the hook has a real tree to hash.
make_repo() {
    local dir
    dir=$(mktemp -d)
    git -C "$dir" init -q
    git -C "$dir" config user.email gate@test
    git -C "$dir" config user.name gate
    echo one > "$dir/file"
    git -C "$dir" add file
    git -C "$dir" commit -qm one
    echo "$dir"
}

# Run the hook inside $repo with the given stdin, capturing exit code + output.
run_hook() {
    local repo=$1 stdin=$2
    shift 2
    ( cd "$repo" && printf '%s\n' "$stdin" | env "$@" bash "$HOOK" ) >"$repo/.out" 2>&1
    echo $?
}

echo "pre-push local gate"

# ── 1. Disarmed is the default: it must never block anyone ────────────────────
repo=$(make_repo)
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "disarmed: lets the push through without running the suite" \
    || bad "disarmed: lets the push through without running the suite" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 2. Armed + branch deletion only: nothing to test ──────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
code=$(run_hook "$repo" "refs/heads/x $ZERO refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "armed: a branch deletion skips the suite" \
    || bad "armed: a branch deletion skips the suite" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 3. Armed + explicit bypass ────────────────────────────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" SKIP_HUB_TESTS=1 \
    HUB_GATE_TEST_CMD="touch $repo/RAN; true")
[ "$code" = 0 ] && [ ! -f "$repo/RAN" ] \
    && ok "armed: SKIP_HUB_TESTS=1 bypasses the gate" \
    || bad "armed: SKIP_HUB_TESTS=1 bypasses the gate" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no)"

# ── 4. Armed + red suite: the push must ABORT ─────────────────────────────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 >> $repo/STATUS" \
    HUB_GATE_TEST_CMD="touch $repo/RAN; false")
# `code != 0` alone would also pass when the hook is missing entirely (127),
# so require proof that the suite actually ran and was judged red.
[ "$code" = 1 ] && [ -f "$repo/RAN" ] && [ ! -f "$repo/STATUS" ] \
    && ok "red suite: aborts the push and publishes no green status" \
    || bad "red suite: aborts the push and publishes no green status" "exit=$code ran=$([ -f "$repo/RAN" ] && echo yes || echo no) status=$(cat "$repo/STATUS" 2>/dev/null)"

# ── 5. Armed + green suite: push proceeds and the status names the pushed sha ──
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="echo \$1 > $repo/STATUS" \
    HUB_GATE_TEST_CMD="true")
sleep 1   # the status is published in the background, after the push lands
[ "$code" = 0 ] && [ "$(cat "$repo/STATUS" 2>/dev/null)" = "$sha" ] \
    && ok "green suite: push proceeds and the status carries the pushed sha" \
    || bad "green suite: push proceeds and the status carries the pushed sha" "exit=$code status=$(cat "$repo/STATUS" 2>/dev/null) want=$sha"

# ── 6. Same tree twice: the second push must NOT recompile ────────────────────
#    This is what keeps the fleet's 42 pushes/day from becoming 42 full suites.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
for _ in 1 2; do
    code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
        HUB_GATE_STATE_DIR="$repo/.state" \
        HUB_GATE_STATUS_CMD="true" \
        HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
done
runs=$(wc -l < "$repo/RUNS" 2>/dev/null | tr -d ' ')
[ "$code" = 0 ] && [ "$runs" = 1 ] \
    && ok "unchanged tree: the suite runs once, the second push reuses the green" \
    || bad "unchanged tree: the suite runs once, the second push reuses the green" "exit=$code runs=$runs want=1"

# ── 7. A changed tree must NOT reuse the previous green ───────────────────────
echo two > "$repo/file"
git -C "$repo" commit -qam two
sha2=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha2 refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" \
    HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo run >> $repo/RUNS; true")
runs=$(wc -l < "$repo/RUNS" 2>/dev/null | tr -d ' ')
[ "$code" = 0 ] && [ "$runs" = 2 ] \
    && ok "changed tree: the green does not carry over" \
    || bad "changed tree: the green does not carry over" "exit=$code runs=$runs want=2"

# ── 8. The lock serialises concurrent pushes (19 worktrees share this hook) ────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
# Each run appends on entry and on exit; interleaved marks mean they overlapped.
slow="echo enter >> $repo/TRACE; sleep 2; echo leave >> $repo/TRACE; true"
run_hook "$repo" "refs/heads/a $sha refs/heads/a $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="$slow" >/dev/null &
first=$!
sleep 0.3
# A different tree, so the second push cannot short-circuit on the cache.
echo other > "$repo/file2"; git -C "$repo" add file2; git -C "$repo" commit -qm two
sha2=$(git -C "$repo" rev-parse HEAD)
run_hook "$repo" "refs/heads/b $sha2 refs/heads/b $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="$slow" >/dev/null &
second=$!
wait $first $second
[ "$(tr '\n' ' ' < "$repo/TRACE")" = "enter leave enter leave " ] \
    && ok "lock: two concurrent pushes run their suites one at a time" \
    || bad "lock: two concurrent pushes run their suites one at a time" "trace=$(tr '\n' ' ' < "$repo/TRACE")"

# A monorepo layout: hub/ with modules-workspace/ as its sibling.
# `cd && pwd -P` so the expected path is symlink-resolved too: on macOS mktemp hands
# back /var/folders/… while the hook reports the real /private/var/folders/….
make_monorepo() {
    local base
    base=$(cd "$(mktemp -d)" && pwd -P)
    mkdir -p "$base/modules-workspace/modules" "$base/blueprints" "$base/hub"
    git -C "$base/hub" init -q
    git -C "$base/hub" config user.email gate@test
    git -C "$base/hub" config user.name gate
    git -C "$base/hub" config --bool hooks.hubPrepushGate true
    echo one > "$base/hub/file"
    git -C "$base/hub" add file
    git -C "$base/hub" commit -qm one
    echo "$base"
}

# ── 9. Default is CI PARITY: the module e2e are skipped, exactly as in CI ─────
#    CI never runs them (the guard sees CI=true and skips). On a clean develop they
#    are 120 failures / 25 targets, so running them by default would block every
#    push. Parity is also what makes "we turned the CI gate off" an honest claim.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_MODULES_DIR:-} skip=\${ERPLORA_E2E_ALLOW_SKIP:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
[ "$code" = 0 ] && [ "$got" = "dir= skip=1" ] \
    && ok "default: module e2e skipped, same as the CI gate it replaces" \
    || bad "default: module e2e skipped, same as the CI gate it replaces" "exit=$code got='$got'"

# ── 10. Opt-in runs them, and finds them from ANY worktree ────────────────────
#    The fleet works out of /private/tmp worktrees, outside the monorepo, where the
#    relative path crates/runtime/../../../modules-workspace/modules does not resolve
#    and the guard panics instead of skipping (hub#253). The hook resolves it.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_MODULES_DIR:-} skip=\${ERPLORA_E2E_ALLOW_SKIP:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
[ "$code" = 0 ] && [ "$got" = "dir=$base/modules-workspace/modules skip=" ] \
    && ok "opt-in: the suite is pointed at modules-workspace, wherever it is" \
    || bad "opt-in: the suite is pointed at modules-workspace, wherever it is" "exit=$code got='$got'"

# ── 11. Opt-in without modules on disk: skip, never the hub#253 panic ─────────
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_WITH_MODULES=1 HOME="$repo/nowhere" \
    HUB_GATE_TEST_CMD="echo \"skip=\${ERPLORA_E2E_ALLOW_SKIP:-}\" > $repo/ENV; true")
got=$(cat "$repo/ENV" 2>/dev/null)
[ "$code" = 0 ] && [ "$got" = "skip=1" ] \
    && ok "opt-in with no modules on disk: skips instead of panicking" \
    || bad "opt-in with no modules on disk: skips instead of panicking" "exit=$code got='$got'"

# ── 12. `blueprints/` is resolved too, or the gate red-lines from every worktree ─
#    `sector_packs_pg_e2e` reads the sector seeds out of the SIBLING repo
#    (`blueprints/starter_catalogs/es/<sector>/seed.sql`). Unlike the module e2e
#    there is no opt-in: those two tests run always, so from a worktree outside
#    the monorepo the relative path misses and the gate fails with
#    "no se pudo leer …/seed.sql" — a red that has nothing to do with the push.
#
#    Measured 2026-08-09: the whole fleet works out of /private/tmp worktrees, so
#    that was every gated push. `ERPLORA_BLUEPRINTS_DIR` is the escape the test
#    already documents; the hook just never set it, the way it does for modules.
base=$(make_monorepo)
sha=$(git -C "$base/hub" rev-parse HEAD)
code=$(run_hook "$base/hub" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$base/.state" HUB_GATE_STATUS_CMD="true" \
    HUB_GATE_TEST_CMD="echo \"dir=\${ERPLORA_BLUEPRINTS_DIR:-}\" > $base/ENV; true")
got=$(cat "$base/ENV" 2>/dev/null)
[ "$code" = 0 ] && [ "$got" = "dir=$base/blueprints" ] \
    && ok "the suite is pointed at blueprints/, wherever the worktree is" \
    || bad "the suite is pointed at blueprints/, wherever the worktree is" "exit=$code got='$got'"

# ── 13. No blueprints on disk: the gate still runs, it just cannot point at them ─
#    Refusing the push would be worse than the red it prevents: a checkout without
#    the sibling repo is a legitimate state, and the two tests say so themselves.
repo=$(make_repo)
git -C "$repo" config --bool hooks.hubPrepushGate true
sha=$(git -C "$repo" rev-parse HEAD)
code=$(run_hook "$repo" "refs/heads/x $sha refs/heads/x $ZERO" \
    HUB_GATE_STATE_DIR="$repo/.state" HUB_GATE_STATUS_CMD="true" HOME="$repo/nowhere" \
    HUB_GATE_TEST_CMD="true")
[ "$code" = 0 ] \
    && ok "no blueprints on disk: the gate still runs" \
    || bad "no blueprints on disk: the gate still runs" "exit=$code"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
