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
# `--catalogue <dir>` (pm#655) adds a second check: every module a resolved target installs from
# `modules_root()` has to be IN that catalogue. pm#655 moved the catalogue to the org's public,
# non-archived module repos and `invoice_series` (archived, private) fell out of it while six
# kernel e2e still installed it — `cargo test` only said so twenty minutes later, as
# `Io(NotFound)`. A retired module the kernel still has to be tested against becomes a fixture
# under `crates/runtime/tests/fixtures/`, never a dependency on the catalogue.
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
catalogue=""
# The guard that puts a target in the set. Kept in one place so the workflow, the manifest header
# and this resolver cannot drift apart on it.
marker="require_modules_workspace"

while [ $# -gt 0 ]; do
    case "$1" in
        --tests-dir) tests_dir="$2"; shift 2 ;;
        --manifest) manifest="$2"; shift 2 ;;
        --catalogue) catalogue="$2"; shift 2 ;;
        -h | --help)
            printf 'usage: %s [--tests-dir <dir>] [--manifest <file>] [--catalogue <dir>]\n' "$0"
            exit 0
            ;;
        *)
            printf 'usage: %s [--tests-dir <dir>] [--manifest <file>] [--catalogue <dir>]\n' "$0" >&2
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
if [ -n "$catalogue" ] && [ ! -d "$catalogue" ]; then
    printf 'kernel-e2e-targets: no such catalogue directory: %s\n' "$catalogue" >&2
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

# ── What the CATALOGUE has (only with --catalogue) ──────────────────────────────────────
# The module ids a target installs, read from its source in the three shapes the tree uses: a
# literal `modules_root().join("x")`, a one-line helper that wraps it (`fn mdir(n: &str) ->
# PathBuf { …modules_root().join(n) }` called as `mdir("x")`), and a `for m in [..]` whose body
# joins `m`. Line comments are dropped first, and a `for` over table names that never reaches
# `modules_root()` names nothing. Targets that walk the WHOLE catalogue name no id and pass.
if [ -n "$catalogue" ] && [ -z "$failures" ] && [ -n "$actual" ]; then
    installs=$(printf '%s\n' "$actual" | python3 -c '
import re, sys
tests_dir = sys.argv[1]
ID = r"[a-z][a-z0-9_]*"
for name in sys.stdin.read().split():
    src = re.sub(r"//[^\n]*", "", open(f"{tests_dir}/{name}.rs", encoding="utf-8").read())
    ids = set(re.findall(r"modules_root\(\)\.join\(\"(" + ID + r")\"\)", src))
    helpers = [h for h, _ in re.findall(
        r"fn (\w+)\(\s*(\w+)\s*:\s*&str\s*\)\s*->\s*PathBuf\s*\{\s*[\w:]*modules_root\(\)\.join\(\2\)\s*\}",
        src)]
    for helper in helpers:
        ids |= set(re.findall(r"\b" + helper + r"\(\s*\"(" + ID + r")\"", src))
    for loop in re.finditer(r"for (\w+) in &?\[([^\]]*)\]\s*\{", src):
        var, depth, i = loop.group(1), 1, loop.end()
        while i < len(src) and depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        body = src[loop.end():i]
        joins = re.search(r"modules_root\(\)\.join\(&?" + var + r"\)", body) or any(
            re.search(r"\b" + h + r"\(\s*&?" + var + r"\s*\)", body) for h in helpers)
        if joins:
            ids |= set(re.findall(r"\"(" + ID + r")\"", loop.group(2)))
    for module in sorted(ids):
        print(name, module)
' "$tests_dir") || {
        printf 'kernel-e2e-targets: could not read the modules the targets install (python3 failed above)\n' >&2
        exit 2
    }
    absent=$(printf '%s\n' "$installs" | while read -r target module; do
        [ -n "$module" ] || continue
        [ -f "$catalogue/$module/module.json" ] || printf '      %s installs `%s`\n' "$target" "$module"
    done)
    if [ -n "$absent" ]; then
        {
            printf 'kernel-e2e-targets: kernel e2e install modules that the catalogue %s does not have:\n' "$catalogue"
            printf '%s\n\n' "$absent"
            printf 'The catalogue is the PUBLISHED one: the org'"'"'s public, non-archived module repos.\n'
            printf 'A module missing from it was retired, archived or made private, and `cargo test`\n'
            printf 'would only say `Io(NotFound)` after building everything. If the kernel still has to\n'
            printf 'be tested against it (hubs that keep it installed), freeze what the test needs as\n'
            printf 'a fixture under crates/runtime/tests/fixtures/<id>/ and install it from there, as\n'
            printf 'export_test/import_test do with invoice_series (pm#655).\n'
        } >&2
        exit 1
    fi
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
