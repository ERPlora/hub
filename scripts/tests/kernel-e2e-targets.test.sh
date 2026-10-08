#!/usr/bin/env bash
# Contract tests for scripts/ci/kernel-e2e-targets.sh — the guard that decides WHICH e2e targets
# `test-hub-modules.yml` runs against the published catalogue.
#
# Regression test for ERPlora/hub#1359 (the red that surfaced it: hub#1354). What it protects,
# and why each case is here:
#
#   · The set of targets is DERIVED from the tree (`require_modules_workspace`), which is right:
#     a new e2e joins on its own and no hand-written list rots in silence. But a derived set can
#     also SHRINK in silence, so hub#1229 bolted a floor on it — a magic `>= 30`. That number is
#     not a contract, it is a snapshot: hub#1264 moves module-owned e2e out of the hub into the
#     modules' own batteries, and the seventh slice took the count to 29 and turned `develop` RED
#     for the whole fleet ("solo 29 targets — el grep no está encontrando los e2e"). Every future
#     slice would break it again, and the only available repair — lower the number — teaches
#     exactly the wrong reflex: the guard becomes a speed bump you edit to make it stop.
#
#   · So the floor stops being a number and becomes a LIST: `scripts/ci/kernel-e2e-targets.txt`,
#     checked in and reviewed. Removing a target now requires editing that list IN THE SAME PR,
#     and that edit is the reviewable act — a reviewer sees `- verifactu_desglose_e2e` in the
#     diff and asks where its coverage went, which a `30` → `29` never made them ask.
#
#   · The guard is BIDIRECTIONAL on purpose. A target deleted without editing the list is the
#     hub#1354 case. A target present in the tree but absent from the list is the OTHER silent
#     failure the number never caught: an e2e whose coverage nobody signed off, and — because a
#     count only ever grows there — one that could be deleted later without moving the count
#     below its floor at all.
#
# Everything here is hermetic: a scratch tests/ dir and a scratch manifest, no repo, no network.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/kernel-e2e-targets.sh"
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-kernel-e2e-targets-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

# The workflow that RUNS this file on a pull request. `--caller` lets the last section be pointed
# at a MUTATED copy to prove it catches the positive — the knob `visual-baselines-workflow.test.sh`
# and `canonical-mirrors-workflow.test.sh` already expose for their own callers.
caller="$repo_root/.github/workflows/actionlint.yml"

while [ $# -gt 0 ]; do
    case "$1" in
        --caller) caller="$2"; shift 2 ;;
        *) printf 'usage: %s [--caller <path>]\n' "$0" >&2; exit 2 ;;
    esac
done

passed=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

ok() {
    passed=$((passed + 1))
}

if [ ! -f "$script" ]; then
    fail "no such script: $script"
fi

# ── Fixtures ────────────────────────────────────────────────────────────────────────────
# A scratch `tests/` directory shaped like `crates/runtime/tests/`: top-level integration
# targets, a nested fixture tree (which cargo does NOT compile as a target), and a mix of
# targets that do and do not need the published catalogue.
make_tree() { # $1=dir, rest=names of targets that call require_modules_workspace()
    local dir="$1"
    shift
    rm -rf "$dir"
    mkdir -p "$dir/fixture_1076/migrations/postgres"

    # A plain e2e that does NOT need the modules: it must never enter the set.
    cat > "$dir/plain_unit_e2e.rs" <<'EOF'
#[test]
fn runs_without_the_published_catalogue() {}
EOF

    # A nested file that DOES mention the guard. `basename` on it would yield a target name that
    # `cargo test --test` cannot resolve, so the resolver must ignore anything below the top level.
    cat > "$dir/fixture_1076/helper.rs" <<'EOF'
// require_modules_workspace() is mentioned here, but this is not a cargo test target.
EOF

    local name
    for name in "$@"; do
        cat > "$dir/$name.rs" <<'EOF'
use erplora_runtime::e2e_support::require_modules_workspace;

#[test]
fn needs_the_published_catalogue() {
    if !require_modules_workspace() {
        return;
    }
}
EOF
    done
}

make_manifest() { # $1=file, rest=declared target names
    local file="$1"
    shift
    {
        echo "# Scratch manifest for the tests. Comments and blank lines are ignored."
        echo
        printf '%s\n' "$@"
    } > "$file"
}

run_guard() { # $1=tests dir, $2=manifest  → stdout in $out, stderr in $err, status in $status
    out=$("$script" --tests-dir "$1" --manifest "$2" 2>"$tmp_dir/err")
    status=$?
    err=$(cat "$tmp_dir/err")
}

tree="$tmp_dir/tests"
manifest="$tmp_dir/kernel-e2e-targets.txt"

# ── 1 · Tree and list agree → green, and the resolved targets go to stdout ───────────────
# stdout is the CONTRACT with the workflow: it builds `--test <name>` args out of it, so the
# diagnostics have to stay on stderr or they would end up as cargo arguments.
make_tree "$tree" reads_e2e pagination_e2e module_seed_e2e
make_manifest "$manifest" module_seed_e2e pagination_e2e reads_e2e

run_guard "$tree" "$manifest"
[ "$status" -eq 0 ] || fail "hub#1359: a matching tree and list must pass, got status $status: $err"
ok
[ "$out" = "module_seed_e2e
pagination_e2e
reads_e2e" ] || fail "hub#1359: stdout must carry the sorted targets, got: $out"
ok
grep -q "plain_unit_e2e" <<<"$out" \
    && fail "hub#1359: a target that does not call require_modules_workspace() must stay out"
ok
grep -q "helper" <<<"$out" \
    && fail "hub#1359: a nested fixture file is not a cargo target and must stay out"
ok

# ── 2 · A target DELETED without editing the list fails, NAMING it ───────────────────────
# The hub#1354 case, in miniature: a hub#1264 slice removes `pagination_e2e.rs` and says nothing.
rm -f "$tree/pagination_e2e.rs"
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a target deleted without editing the list must FAIL"
ok
grep -q "pagination_e2e" <<<"$err" \
    || fail "hub#1359: the failure must NAME the missing target, got: $err"
ok
# A guard that fails without saying what to do gets "fixed" by deleting the guard.
grep -q "kernel-e2e-targets.txt" <<<"$err" \
    || fail "hub#1359: the failure must name the manifest to edit, got: $err"
ok

# ── 3 · A target ADDED without declaring it fails, NAMING it ─────────────────────────────
# The direction the number never covered: coverage nobody signed off, and a target that could
# later be deleted without ever moving the count below its floor.
make_tree "$tree" reads_e2e pagination_e2e module_seed_e2e brand_new_e2e
make_manifest "$manifest" module_seed_e2e pagination_e2e reads_e2e
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a target present in the tree but not in the list must FAIL"
ok
grep -q "brand_new_e2e" <<<"$err" \
    || fail "hub#1359: the failure must NAME the undeclared target, got: $err"
ok

# ── 4 · Both directions at once are reported TOGETHER ────────────────────────────────────
# `cargo test --no-fail-fast` is in this workflow for the same reason: stopping at the first
# problem hides the rest and costs another 45-minute round trip to find it.
make_tree "$tree" reads_e2e brand_new_e2e
make_manifest "$manifest" module_seed_e2e pagination_e2e reads_e2e
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a tree and list that disagree both ways must FAIL"
ok
for expected in module_seed_e2e pagination_e2e brand_new_e2e; do
    grep -q "$expected" <<<"$err" \
        || fail "hub#1359: both directions must be reported in one pass, missing $expected: $err"
done
ok

# ── 5 · An EMPTY list is refused ─────────────────────────────────────────────────────────
# "Delete the entries until it passes" is the degenerate form of "lower the number", and it has
# to be as impossible as the number was easy.
make_tree "$tree" reads_e2e
: > "$manifest"
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: an empty manifest must FAIL, not resolve to zero targets"
ok

# A manifest of nothing but comments is empty too — the trap `code_of()` dodges elsewhere in
# this repo, where a rule written in a comment reads as a rule that is still in force.
make_manifest "$manifest"
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a comments-only manifest must FAIL"
ok

# ── 6 · A duplicated entry is refused ────────────────────────────────────────────────────
# Two lines for one target would make `cargo test --test x --test x` run it twice and, worse,
# would let a later deletion pass with the entry still standing.
make_tree "$tree" reads_e2e pagination_e2e
make_manifest "$manifest" reads_e2e pagination_e2e reads_e2e
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a duplicated manifest entry must FAIL"
ok
grep -q "reads_e2e" <<<"$err" \
    || fail "hub#1359: the duplicate failure must name the entry, got: $err"
ok

# ── 7 · A missing manifest or tests dir is an ENVIRONMENT error, not a verdict ────────────
# Exit 2, so a broken checkout never reads as "the targets are wrong" — the same separation the
# alert step makes between an environmental failure and "the modules are broken".
make_tree "$tree" reads_e2e
run_guard "$tree" "$tmp_dir/does-not-exist.txt"
[ "$status" -eq 2 ] || fail "hub#1359: a missing manifest must exit 2, got $status"
ok
make_manifest "$manifest" reads_e2e
run_guard "$tmp_dir/no-such-tests-dir" "$manifest"
[ "$status" -eq 2 ] || fail "hub#1359: a missing tests dir must exit 2, got $status"
ok

# ── 8 · The REAL manifest matches the REAL tree ──────────────────────────────────────────
# The cases above prove the mechanism; this one is the guard actually standing. It is what turns
# `develop` green again, and what a future hub#1264 slice will trip if it forgets the list.
#
# It is NOT wrapped in `if [ -d … ]` any more (hub#1369): a case that skips itself when its
# subject is missing is an open guard — the suite would still print PASS, two cases lighter, and
# nobody reads the count. The directory is part of this repo, so its absence is a failure.
[ -d "$repo_root/crates/runtime/tests" ] \
    || fail "hub#1359: $repo_root/crates/runtime/tests is missing — the case that compares the real
manifest with the real tree cannot be skipped: skipping it is how a guard passes without guarding"
ok
real_out=$("$script" 2>"$tmp_dir/real-err")
real_status=$?
[ "$real_status" -eq 0 ] || fail "hub#1359: the checked-in manifest does not match crates/runtime/tests:
$(cat "$tmp_dir/real-err")"
ok
real_count=$(printf '%s\n' "$real_out" | grep -c .)
[ "$real_count" -ge 1 ] || fail "hub#1359: the real run resolved no targets at all"
ok
printf 'note: the checked-in manifest declares %s kernel e2e target(s)\n' "$real_count"

# ── 10 · --catalogue: every module a target installs must BE in the published catalogue ──
# pm#655 changed where the catalogue comes from (the org's public, non-archived module repos) and
# silently dropped `invoice_series` — archived and private — which six kernel e2e still installed
# from it. The workflow tests passed 115/115 and 14 mutants, and the first sign was `cargo test`
# dying twenty minutes in with `instalar invoice_series: Io(NotFound)` on every kernel PR. With
# `--catalogue <dir>` the guard answers that in seconds, BEFORE cargo, naming target and module.
# The three ways the real tree names a module are covered: a literal `modules_root().join("x")`,
# a one-line helper wrapping it (`mdir("x")`), and a `for m in [..]` whose body joins `m`.
add_installing_target() { # $1=dir, $2=name, $3=body of the test fn
    cat > "$1/$2.rs" <<EOF
use erplora_runtime::e2e_support::{modules_root, require_modules_workspace};
use std::path::PathBuf;

fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}

#[tokio::test]
async fn installs_modules() {
    if !require_modules_workspace() {
        return;
    }
$3
}
EOF
}
make_catalogue() { # $1=dir, rest=module ids published in it
    local dir="$1" id
    shift
    rm -rf "$dir"
    mkdir -p "$dir"
    for id in "$@"; do
        mkdir -p "$dir/$id"
        printf '{"id": "%s"}\n' "$id" > "$dir/$id/module.json"
    done
}
run_guard_catalogue() { # $1=tests dir, $2=manifest, $3=catalogue
    out=$("$script" --tests-dir "$1" --manifest "$2" --catalogue "$3" 2>"$tmp_dir/err")
    status=$?
    err=$(cat "$tmp_dir/err")
}
catalogue="$tmp_dir/catalogue"

make_tree "$tree"
add_installing_target "$tree" literal_e2e '    rt.install_from_dir(&modules_root().join("taxes")).await.unwrap();'
add_installing_target "$tree" helper_e2e '    rt.install_from_dir(&mdir("sales")).await.unwrap();'
add_installing_target "$tree" loop_e2e '    for m in ["inventory", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m)).await.unwrap();
    }
    // A loop over TABLE names that never reaches modules_root() names no module.
    for t in ["sales_sale", "fiscal"] {
        assert!(!t.is_empty());
    }
    // A comment is not an install: modules_root().join("ghost_in_a_comment")'
make_manifest "$manifest" helper_e2e literal_e2e loop_e2e

make_catalogue "$catalogue" taxes sales inventory verifactu
run_guard_catalogue "$tree" "$manifest" "$catalogue"
[ "$status" -eq 0 ] || fail "pm#655: a catalogue with every installed module must pass, got $status: $err"
ok
[ "$out" = "helper_e2e
literal_e2e
loop_e2e" ] || fail "pm#655: --catalogue must not change the stdout contract, got: $out"
ok

for gone in taxes sales verifactu; do
    make_catalogue "$catalogue" taxes sales inventory verifactu
    rm -rf "${catalogue:?}/$gone"
    run_guard_catalogue "$tree" "$manifest" "$catalogue"
    [ "$status" -eq 1 ] \
        || fail "pm#655: a target installing \`$gone\`, absent from the catalogue, must FAIL (1), got $status"
    ok
    grep -q "$gone" <<<"$err" || fail "pm#655: the failure must NAME the module \`$gone\`, got: $err"
    ok
    [ -z "$out" ] || fail "pm#655: a failed run must print no targets for cargo, got: $out"
    ok
done
grep -q "loop_e2e" <<<"$err" || fail "pm#655: the failure must NAME the target that installs it, got: $err"
ok
grep -q "tests/fixtures" <<<"$err" \
    || fail "pm#655: the failure must say how to fix it (a fixture under crates/runtime/tests/fixtures), got: $err"
ok

# The negatives: neither a table-name loop nor a comment is an install.
make_catalogue "$catalogue" taxes sales inventory verifactu
run_guard_catalogue "$tree" "$manifest" "$catalogue"
for ghost in sales_sale fiscal ghost_in_a_comment; do
    grep -q "$ghost" <<<"$err" && fail "pm#655: \`$ghost\` is not an installed module, got: $err"
done
ok

# A catalogue directory that does not exist is the ENVIRONMENT, not a verdict (exit 2).
run_guard_catalogue "$tree" "$manifest" "$tmp_dir/no-such-catalogue"
[ "$status" -eq 2 ] || fail "pm#655: a missing catalogue dir must exit 2, got $status"
ok

# ── 9 · The guard actually RUNS on the pull requests that can break it ───────────────────
# A guard nobody executes is a comment. Three properties, asserted one after another so the
# failure names the one that broke:
#
#   a) a STEP of actionlint.yml invokes this file. Asserting any mention would be a false green:
#      the caller names this script twice — in `paths:` and in the `run:` — so deleting the step
#      still matches the `paths:` entry. That exact false green shipped once (hub#1250/#1325) and
#      is open again in a sibling contract (hub#1365).
#   b) this test file is in the caller's `paths:`, or a PR that only touched the test would not
#      run it.
#   c) `crates/runtime/tests/**` is in the caller's `paths:` — the property this section was
#      written for (hub#1369, from the post-merge review of hub#1360). The list can only be
#      broken by a PR that adds or deletes a kernel e2e, and such a PR need not touch a single
#      path the caller currently watches.
#      `test-hub-modules.yml` lost its `pull_request` trigger with hub#1362 and got it back with
#      pm#655, but that run takes tens of minutes and skips drafts; this guard costs seconds and
#      answers on every PR. Without this entry, a hub#1264 slice that deletes the `.rs` and
#      forgets the `.txt` line would only learn it from the long run — or, on a draft, not before
#      merge at all, and `develop` goes red for the whole fleet on the push — the very failure
#      hub#1359 abolished.
SELF='scripts/tests/kernel-e2e-targets.test.sh'
TESTS_GLOB='crates/runtime/tests/**'
if [ ! -f "$caller" ]; then
    fail "hub#1369: the caller was not found at $caller"
elif ! grep -qE "^[[:space:]]*(run:[[:space:]]*)?bash (\./)?${SELF//./\\.}[[:space:]]*$" "$caller"; then
    fail "hub#1369: no step of $caller invokes \`bash ./${SELF}\` — naming the file in a comment
or in \`paths:\` does NOT run it, and without the step this whole contract is decoration"
elif ! grep -qE "^[[:space:]]*- [\"']?${SELF//./\\.}[\"']?[[:space:]]*\$" "$caller"; then
    fail "hub#1369: ${SELF} is missing from the \`paths:\` filter of $caller — a PR touching only
this test would not execute it"
elif ! grep -qE "^[[:space:]]*- [\"']?crates/runtime/(tests/)?\*\*[\"']?[[:space:]]*\$" "$caller"; then
    fail "hub#1369: ${TESTS_GLOB} is missing from the \`paths:\` filter of $caller — a hub#1264
slice that deletes a kernel e2e without editing scripts/ci/kernel-e2e-targets.txt would meet no
fast guard at pull-request time (test-hub-modules.yml skips drafts and takes tens of minutes, and
the pre-push gate never consults the list). It could merge green and turn develop red on the push
— the failure hub#1359 abolished"
fi
ok

printf 'PASS: %s kernel-e2e-targets cases\n' "$passed"
