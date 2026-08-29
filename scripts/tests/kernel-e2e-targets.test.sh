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
printf '%s' "$out" | grep -q "plain_unit_e2e" \
    && fail "hub#1359: a target that does not call require_modules_workspace() must stay out"
ok
printf '%s' "$out" | grep -q "helper" \
    && fail "hub#1359: a nested fixture file is not a cargo target and must stay out"
ok

# ── 2 · A target DELETED without editing the list fails, NAMING it ───────────────────────
# The hub#1354 case, in miniature: a hub#1264 slice removes `pagination_e2e.rs` and says nothing.
rm -f "$tree/pagination_e2e.rs"
run_guard "$tree" "$manifest"
[ "$status" -ne 0 ] || fail "hub#1359: a target deleted without editing the list must FAIL"
ok
printf '%s' "$err" | grep -q "pagination_e2e" \
    || fail "hub#1359: the failure must NAME the missing target, got: $err"
ok
# A guard that fails without saying what to do gets "fixed" by deleting the guard.
printf '%s' "$err" | grep -q "kernel-e2e-targets.txt" \
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
printf '%s' "$err" | grep -q "brand_new_e2e" \
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
    printf '%s' "$err" | grep -q "$expected" \
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
printf '%s' "$err" | grep -q "reads_e2e" \
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
if [ -d "$repo_root/crates/runtime/tests" ]; then
    real_out=$("$script" 2>"$tmp_dir/real-err")
    real_status=$?
    [ "$real_status" -eq 0 ] || fail "hub#1359: the checked-in manifest does not match crates/runtime/tests:
$(cat "$tmp_dir/real-err")"
    ok
    real_count=$(printf '%s\n' "$real_out" | grep -c .)
    [ "$real_count" -ge 1 ] || fail "hub#1359: the real run resolved no targets at all"
    ok
    printf 'note: the checked-in manifest declares %s kernel e2e target(s)\n' "$real_count"
fi

printf 'PASS: %s kernel-e2e-targets cases\n' "$passed"
