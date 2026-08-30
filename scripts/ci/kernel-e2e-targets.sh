#!/usr/bin/env bash
# Resolve the `crates/runtime` e2e targets that need the PUBLISHED module catalogue, and check
# them against the reviewed list in `scripts/ci/kernel-e2e-targets.txt`.
#
# Prints the resolved target names to STDOUT, one per line, sorted — that is the contract with
# `test-hub-modules.yml`, which turns them into `cargo test --test <name>` arguments. Every
# diagnostic goes to STDERR so it can never end up as a cargo argument.
#
# Exit codes: 0 = tree and list agree · 1 = they disagree (the verdict) · 2 = environment error
# (no manifest, no tests dir). The separation matters: a broken checkout must not read as "the
# targets are wrong", the same way the workflow's alert step refuses to call an environmental
# failure "the modules are broken".
#
# Regression test for ERPlora/hub#1359 (the red it fixed: hub#1354); cases in
# `scripts/tests/kernel-e2e-targets.test.sh`.
#
# WHY A LIST AND NOT A NUMBER. The set is derived from the tree (a `require_modules_workspace()`
# call), which is right: a new e2e joins on its own and no hand-written list rots in silence. But
# a derived set can also SHRINK in silence, so hub#1229 bolted a floor on it — `[ "$count" -ge 30 ]`.
# That number was a snapshot, not a contract: hub#1264 is moving module-owned e2e out of the hub
# into each module's own `erplora test` battery, the seventh slice took the count to 29, and
# `develop` went red for the whole fleet with a message about a grep that was working perfectly
# ("solo 29 targets — el grep no está encontrando los e2e"). The only repair the number offered
# was to lower it, which is the wrong reflex to teach about a coverage guard.
#
# The list keeps what the number was for and drops what it was not. Removing a target now takes
# an edit to `kernel-e2e-targets.txt` IN THE SAME PR, and that edit is the reviewable act: a
# reviewer reads `- verifactu_desglose_e2e` in the diff and asks where its coverage went, which
# `30` → `29` never made anyone ask. And it is bidirectional — a target in the tree that nobody
# declared also fails, the direction a floor can never catch because counts only grow there.
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

tests_dir="$repo_root/crates/runtime/tests"
manifest="$script_dir/kernel-e2e-targets.txt"
# The guard that puts a target in the set. Kept in one place so the workflow, the manifest header
# and this resolver cannot drift apart on it.
marker="require_modules_workspace"

while [ $# -gt 0 ]; do
    case "$1" in
        --tests-dir) tests_dir="$2"; shift 2 ;;
        --manifest) manifest="$2"; shift 2 ;;
        -h | --help)
            printf 'usage: %s [--tests-dir <dir>] [--manifest <file>]\n' "$0"
            exit 0
            ;;
        *)
            printf 'usage: %s [--tests-dir <dir>] [--manifest <file>]\n' "$0" >&2
            exit 2
            ;;
    esac
done

if [ ! -d "$tests_dir" ]; then
    printf 'kernel-e2e-targets: no such tests directory: %s\n' "$tests_dir" >&2
    exit 2
fi
if [ ! -f "$manifest" ]; then
    printf 'kernel-e2e-targets: no such manifest: %s\n' "$manifest" >&2
    exit 2
fi

# ── What the TREE says ──────────────────────────────────────────────────────────────────
# Only the top level of `tests/`: cargo compiles `tests/*.rs` as integration targets and
# everything below (the `fixture_*` trees) as plain data. A `basename` over a nested match would
# invent a `--test <name>` that cargo cannot resolve — a red with no bug behind it.
actual=$(
    find "$tests_dir" -maxdepth 1 -type f -name '*.rs' -print0 |
        xargs -0 grep -l -- "$marker" 2>/dev/null |
        while IFS= read -r path; do
            name=${path##*/}
            printf '%s\n' "${name%.rs}"
        done | LC_ALL=C sort
)

# ── What the LIST says ──────────────────────────────────────────────────────────────────
# `#` comments and blank lines are ignored; surrounding whitespace is trimmed so a stray space
# never turns into a phantom target name.
declared_raw=$(sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    "$manifest" | grep -v '^$' | LC_ALL=C sort)

failures=""

if [ -z "$declared_raw" ]; then
    failures="$failures
  - the manifest declares NO targets. Emptying the list is the degenerate form of lowering the
    old numeric floor: it makes the guard pass by removing what it guards."
fi

duplicates=$(printf '%s\n' "$declared_raw" | grep -v '^$' | uniq -d)
if [ -n "$duplicates" ]; then
    failures="$failures
  - duplicated entries in the manifest (they would run the target twice, and would let a later
    deletion pass with the entry still standing):
$(printf '%s\n' "$duplicates" | sed 's/^/      /')"
fi

declared=$(printf '%s\n' "$declared_raw" | grep -v '^$' | uniq)

missing=$(LC_ALL=C comm -23 <(printf '%s\n' "$declared" | grep -v '^$') \
    <(printf '%s\n' "$actual" | grep -v '^$'))
undeclared=$(LC_ALL=C comm -13 <(printf '%s\n' "$declared" | grep -v '^$') \
    <(printf '%s\n' "$actual" | grep -v '^$'))

if [ -n "$missing" ]; then
    failures="$failures
  - DECLARED but not in the tree — the target was deleted (or stopped calling
    ${marker}()) without editing the list:
$(printf '%s\n' "$missing" | sed 's/^/      /')"
fi

if [ -n "$undeclared" ]; then
    failures="$failures
  - IN THE TREE but not declared — an e2e whose coverage nobody signed off:
$(printf '%s\n' "$undeclared" | sed 's/^/      /')"
fi

if [ -n "$failures" ]; then
    {
        printf 'kernel-e2e-targets: the reviewed list and %s disagree.\n' "$tests_dir"
        printf '%s\n\n' "$failures"
        printf 'The list is %s.\n\n' "$manifest"
        printf 'If the change is intended — a hub#1264 slice moving a module-owned e2e into that\n'
        printf "module's own \`erplora test\` battery — the SAME PR edits the list: drop the line,\n"
        printf 'and say in the PR body where the coverage went. That edit is the reviewable act.\n'
        printf 'If it is a new kernel e2e, add its line.\n'
    } >&2
    exit 1
fi

printf '%s\n' "$actual"
