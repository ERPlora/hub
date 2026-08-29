#!/usr/bin/env bash
# Contract tests for `scripts/canonical-mirrors-verdict.sh` — the hub-side verdict on the
# toolkit's vendored copies. Regression tests for ERPlora/hub#1296.
#
# What it protects, and why each case is here:
#
#   · The toolkit vendors files whose authority lives in this repository and compares them byte
#     for byte. Run from a hub PR that ADDS contract (a route, a type), that comparison is red BY
#     CONSTRUCTION: the copy cannot be ahead of the canonical. Five approved PRs sat blocked on
#     it in one afternoon (hub#1296). The market pattern (Kubernetes publishing-bot, rust-lang
#     subtrees, Envoy api): the canonical never blocks on the copy — the copy FOLLOWS after the
#     merge and fails only when it DIVERGES.
#
#   · So the verdict has three answers, not two, and each one is a case below with the exact
#     shape it must take: a copy that is BEHIND an additive change is a warning; a copy that
#     carries content the hub never had (edited by hand) is a failure; a copy the hub is
#     RETIRING from (a file or a line removed) is a failure too, because that is the one case
#     where the copy must move at the same time — the pair rule of ERPlora/pm#181 stays for it.
#
#   · The schema is the exception on purpose: the module gate READS it, so a copy behind even an
#     addition (a new `required` entry) publishes modules the hub then refuses to install. It
#     keeps the strict rule.
#
#   · The toolkit's own run still executes, and its failure is re-read here instead of thrown
#     away: a failure with nothing behind is a failure for ANOTHER reason (a hand-ported list, a
#     broken reader) and stays red. So does a failure on a change that touched the sources of
#     those lists — this verdict cannot classify them, so it does not pretend to.
#
# Everything is hermetic: a scratch hub repository with real history and a scratch toolkit
# carrying the one export the verdict reads (`VENDORED_FROM_THE_HUB`).
#
# Run:  bash scripts/tests/canonical-mirrors-verdict.test.sh

set -uo pipefail

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../canonical-mirrors-verdict.sh"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-mirrors-verdict-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0
case_n=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    if [ -f "$tmp_dir/out" ]; then
        printf -- '--- output ---\n' >&2
        cat "$tmp_dir/out" >&2
    fi
    exit 1
}

[ -f "$script" ] || fail "no such script: $script"

ROUTES='contracts/kernel/routes.snapshot'
ENGINE='contracts/kernel/engine.snapshot'
SCHEMA='schemas/module.schema.json'

routes_v1=$'# routes\nGET     /api/a    auth:none\nGET     /api/b    auth:session\n'
routes_v2=$'# routes\nGET     /api/a    auth:none\nGET     /api/b    auth:session\nGET     /api/c    auth:session\n'
routes_retired=$'# routes\nGET     /api/a    auth:none\n'
engine_v1=$'# engine\n[system_params]\nhub_id\n'
schema_v1=$'{\n  "title": "manifest",\n  "properties": {}\n}\n'
schema_v2=$'{\n  "title": "manifest",\n  "required": ["id"],\n  "properties": {}\n}\n'

git_q() { git -c user.name=test -c user.email=test@example.invalid -c commit.gpgsign=false "$@"; }

# A scratch hub with one commit carrying v1 of every vendored file (and a parsed-list source).
new_hub() {
    case_n=$((case_n + 1))
    hub="$tmp_dir/hub-$case_n"
    mkdir -p "$hub"
    git_q -C "$hub" init -q -b develop
    write_hub "$ROUTES" "$routes_v1"
    write_hub "$ENGINE" "$engine_v1"
    write_hub "$SCHEMA" "$schema_v1"
    write_hub 'crates/runtime/src/hub_users.rs' $'const CORE_QUERIES: &[&str] = &["users.me"];\n'
    hub_commit 'c1: v1 of everything'
}

write_hub() { # $1=path $2=content
    mkdir -p "$hub/$(dirname -- "$1")"
    printf '%s' "$2" > "$hub/$1"
}

hub_commit() {
    git_q -C "$hub" add -A
    git_q -C "$hub" commit -q -m "$1"
}

# A scratch toolkit: the export the verdict reads, plus whichever copies a case hands it.
new_toolkit() {
    toolkit="$tmp_dir/toolkit-$case_n"
    mkdir -p "$toolkit/scripts"
    cat > "$toolkit/scripts/sync-hub-mirrors.mjs" <<'EOF'
// The one export `canonical-mirrors-verdict.sh` reads from the real toolkit.
export const VENDORED_FROM_THE_HUB = [
  'schemas/module.schema.json',
  'contracts/kernel/engine.snapshot',
  'contracts/kernel/routes.snapshot',
];
EOF
}

write_toolkit() { # $1=path $2=content
    mkdir -p "$toolkit/$(dirname -- "$1")"
    printf '%s' "$2" > "$toolkit/$1"
}

# The copy in sync with the hub's HEAD for every vendored path.
toolkit_in_sync() {
    new_toolkit
    for p in "$ROUTES" "$ENGINE" "$SCHEMA"; do
        if [ -f "$hub/$p" ]; then
            mkdir -p "$toolkit/$(dirname -- "$p")"
            cp "$hub/$p" "$toolkit/$p"
        fi
    done
}

run() { # the verdict, with whatever extra arguments the case needs; output in $tmp_dir/out
    : > "$tmp_dir/gh-output"
    : > "$tmp_dir/gh-summary"
    GITHUB_OUTPUT="$tmp_dir/gh-output" GITHUB_STEP_SUMMARY="$tmp_dir/gh-summary" \
        bash "$script" --hub "$hub" --toolkit "$toolkit" "$@" > "$tmp_dir/out" 2>&1
    status=$?
}

expect_status() { [ "$status" -eq "$1" ] || fail "$2 (exit $status, wanted $1)"; }
expect_out() { grep -q -- "$1" "$tmp_dir/out" || fail "$2 (no \`$1\` in the output)"; }
expect_not_out() { grep -q -- "$1" "$tmp_dir/out" && fail "$2 (found \`$1\` in the output)"; }
expect_output_var() { grep -q -- "^$1=$2\$" "$tmp_dir/gh-output" || fail "$3 (GITHUB_OUTPUT has $(cat "$tmp_dir/gh-output" | tr '\n' ' '))"; }
ok() { passed=$((passed + 1)); }

# ── 1 · In sync ─────────────────────────────────────────────────────────────────────
new_hub; toolkit_in_sync
run
expect_status 0 'a copy in sync with the hub must pass'
expect_not_out '::warning' 'a copy in sync must not warn'
expect_not_out '::error' 'a copy in sync must not error'
expect_output_var verdict synced 'a copy in sync reports verdict=synced'
ok

# ── 2 · BEHIND an additive change → warning, exit 0 (the hub#1296 case) ─────────────
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"; hub_commit 'c2: +GET /api/c'
run
expect_status 0 'a copy behind an ADDITIVE change must not block the canonical (hub#1296)'
expect_out "::warning file=$ROUTES" 'a copy behind must warn, naming the file'
expect_out 'behind' 'the warning says the copy is behind'
expect_out 'sync-mirrors' 'the warning says how the copy catches up'
expect_not_out '::error' 'a copy behind an additive change is not an error'
expect_output_var verdict behind 'a copy behind reports verdict=behind'
ok

# ── 3 · The hub RETIRES a line the copy still carries → failure (pair rule, pm#181) ──
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_retired"; hub_commit 'c2: -GET /api/b'
run
expect_status 1 'a retirement must keep the pair rule: the copy has to move at the same time'
expect_out "::error file=$ROUTES" 'a retirement fails naming the file'
expect_out 'retire' 'the error says it is a retirement'
expect_out 'Depends-On' 'the error points at the pair rule'
expect_output_var verdict blocked 'a retirement reports verdict=blocked'
ok

# ── 4 · The copy carries content the hub NEVER had (edited by hand) → failure ────────
new_hub; toolkit_in_sync
write_toolkit "$ROUTES" $'# routes\nGET     /api/a    auth:none\nGET     /api/b    auth:session\nGET     /api/handmade    auth:none\n'
run
expect_status 1 'a copy with content the hub never had is divergent and must fail'
expect_out "::error file=$ROUTES" 'a divergent copy fails naming the file'
expect_out 'diverge' 'the error says the copy diverged'
ok

# ── 5 · The hub DELETED a file the copy still carries → failure (retirement) ─────────
new_hub; toolkit_in_sync
git_q -C "$hub" rm -q "$ENGINE"; hub_commit 'c2: drop engine.snapshot'
run
expect_status 1 'a file the hub dropped and the copy still carries is a retirement'
expect_out "::error file=$ENGINE" 'the dropped file is named'
expect_out 'retire' 'the error says it is a retirement'
ok

# ── 6 · The hub has a file the copy does not carry yet → behind, warning ─────────────
new_hub; toolkit_in_sync
rm "$toolkit/$ENGINE"
run
expect_status 0 'a new surface the copy has not vendored yet is merely behind'
expect_out "::warning file=$ENGINE" 'the missing copy is named in a warning'
expect_output_var verdict behind 'a missing copy reports verdict=behind'
ok

# ── 7 · The SCHEMA is a gate input: behind even an addition → failure ────────────────
new_hub; toolkit_in_sync
write_hub "$SCHEMA" "$schema_v2"; hub_commit 'c2: schema requires id'
run
expect_status 1 'the schema is read by the module gate: a copy behind it must pair (hub#1278)'
expect_out "::error file=$SCHEMA" 'the schema is named'
expect_out 'gate' 'the error says why the schema is strict'
expect_out 'Depends-On' 'the error points at the pair rule'
ok

# ── 8 · The toolkit's own run failed with NOTHING behind → another reason, stays red ─
new_hub; toolkit_in_sync
run --toolkit-outcome failure
expect_status 1 'a toolkit failure with every copy in sync is a failure for another reason'
expect_out '::error' 'it is reported as an error'
expect_out 'another reason' 'the error says the failure is not a lagging copy'
ok

# ── 9 · Toolkit failed, copy behind, but a hand-ported list source changed → red ─────
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"
write_hub 'crates/runtime/src/hub_users.rs' $'const CORE_QUERIES: &[&str] = &["users.me", "setup.status"];\n'
hub_commit 'c2: +route +core query'
run --toolkit-outcome failure
expect_status 1 'a change touching a hand-ported list source cannot be classified here: stays red'
expect_out 'crates/runtime/src/hub_users.rs' 'the touched source is named'
expect_out 'Depends-On' 'the error points at the pair rule'
ok

# ── 10 · Toolkit failed, copy behind, no list source touched → warning, exit 0 ───────
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"; hub_commit 'c2: +GET /api/c'
run --toolkit-outcome failure
expect_status 0 'the toolkit failure was the lagging copy: downgraded to a warning'
expect_out "::warning file=$ROUTES" 'the lagging copy is named'
expect_not_out '::error' 'no error when the only failure is the lagging copy'
ok

# ── 11 · The toolkit's run did not happen → no verdict without it ────────────────────
new_hub; toolkit_in_sync
run --toolkit-outcome skipped
expect_status 1 'a toolkit run that did not happen leaves the hand-ported lists unchecked: red'
expect_out 'skipped' 'the outcome is named'
ok

# ── 12 · A toolkit without the export → red, naming the contract ─────────────────────
new_hub; toolkit_in_sync
rm "$toolkit/scripts/sync-hub-mirrors.mjs"
run
expect_status 1 'a toolkit that does not say what it vendors cannot be checked: red, never green'
expect_out 'VENDORED_FROM_THE_HUB' 'the missing export is named'
ok

# ── 13 · The list sources this verdict refuses to classify are printable ─────────────
new_hub; toolkit_in_sync
run --print-parsed-sources
expect_status 0 '--print-parsed-sources exits 0'
for src in crates/db/src/lib.rs crates/runtime/src/manifest.rs crates/runtime/src/hub_users.rs \
           crates/runtime/src/migration_guard.rs apps/web/src/main.ts; do
    grep -qx -- "$src" "$tmp_dir/out" || fail "--print-parsed-sources lists $src"
done
ok

# ── 14 · Base that cannot be resolved with a toolkit failure → red, never a guess ────
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"; hub_commit 'c2: +GET /api/c'
run --toolkit-outcome failure --base does-not-exist
expect_status 1 'an unresolvable base means the touched sources are unknown: red'
expect_out 'does-not-exist' 'the base is named'
ok

# ── 15 · The step summary carries the table ──────────────────────────────────────────
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"; hub_commit 'c2: +GET /api/c'
run
grep -q -- "$ROUTES" "$tmp_dir/gh-summary" || fail 'the step summary names the lagging file'
grep -q -- "$ENGINE" "$tmp_dir/gh-summary" || fail 'the step summary names the synced file too'
ok

# ── 16 · A merge ref TREESAME to the PR side still sees the base branch's history ────
# On a pull request HEAD is the merge of the base branch into the PR. When the PR already carried
# the base's hunk (a cherry-pick, the same route added twice), the merge takes the PR's blob whole
# and `git rev-list <ref> -- <path>` — default history simplification — follows ONLY that parent:
# the base branch's version of the file, which is exactly what the toolkit copied, would come out
# as "content the hub never had" and the canonical would go red with a lie. `--full-history` is
# what keeps every reachable version in view.
new_hub; toolkit_in_sync
git_q -C "$hub" checkout -q -b pr
write_hub "$ROUTES" $'# routes\nGET     /api/c    auth:session\nGET     /api/a    auth:none\nGET     /api/b    auth:session\nGET     /api/d    auth:none\n'
hub_commit 'pr: +GET /api/c at the top, +GET /api/d at the bottom'
git_q -C "$hub" checkout -q develop
write_hub "$ROUTES" $'# routes\nGET     /api/c    auth:session\nGET     /api/a    auth:none\nGET     /api/b    auth:session\n'
hub_commit 'develop: +GET /api/c at the top'
cp "$hub/$ROUTES" "$toolkit/$ROUTES"   # the copy was synced from develop
git_q -C "$hub" merge -q --no-edit pr || fail 'the merge in case 16 must be clean (identical top hunk)'
[ "$(git -C "$hub" rev-parse HEAD:$ROUTES)" = "$(git -C "$hub" rev-parse pr:$ROUTES)" ] ||
    fail 'case 16 needs the merge ref TREESAME to the PR side'
run --toolkit-outcome failure
expect_status 0 'a copy synced from the base branch is BEHIND on a merge ref TREESAME to the PR side, not divergent (hub#1296)'
expect_out "::warning file=$ROUTES" 'the lagging copy is named in a warning'
expect_not_out 'diverge' 'a version the base branch had is not "content the hub never had"'
expect_output_var verdict behind 'the merge-ref case reports verdict=behind'
ok

# ── 17 · Toolkit failed, copy behind, and the change ADDS a file to contracts/kernel/ → red ──
# The SET of files under `contracts/kernel/` is a hand-ported list in the toolkit
# (`KERNEL_CONTRACT_FILES` + `KERNEL_CONTRACT_NOT_MIRRORED`, module-toolkit#115/#121), and its
# `sync-mirrors` copies only what that list names. A sixth surface is therefore a change this
# verdict cannot classify — the same rule as the Rust sources — and a lagging copy elsewhere
# must not downgrade it to a warning: "nothing is downgraded blind".
new_hub; toolkit_in_sync
write_hub "$ROUTES" "$routes_v2"
write_hub 'contracts/kernel/events.snapshot' $'# events\n'
hub_commit 'c2: +GET /api/c +a sixth frozen surface'
run --toolkit-outcome failure
expect_status 1 'a new file under contracts/kernel/ changes the set the toolkit enumerates by hand: red, even with another copy behind'
expect_out 'contracts/kernel/events.snapshot' 'the new file is named'
expect_out 'Depends-On' 'the error points at the pair rule'
ok

# ── 18 · The sixth surface alone (nothing behind) is named, not just "another reason" ────
new_hub; toolkit_in_sync
write_hub 'contracts/kernel/events.snapshot' $'# events\n'
hub_commit 'c2: a sixth frozen surface'
run --toolkit-outcome failure
expect_status 1 'a sixth surface with every copy in sync is still red'
expect_out 'contracts/kernel/events.snapshot' 'the new file is named so nobody hunts through the toolkit log'
ok

# ── 19 · Editing prose the toolkit does not mirror is NOT a set change → still a warning ──
new_hub; toolkit_in_sync
write_hub 'contracts/kernel/README.md' $'# kernel\nv1\n'; hub_commit 'c2: the README the toolkit does not mirror'
write_hub 'contracts/kernel/README.md' $'# kernel\nv2\n'; write_hub "$ROUTES" "$routes_v2"
hub_commit 'c3: +GET /api/c, README edited'
run --toolkit-outcome failure
expect_status 0 'a modified README.md (not mirrored, module-toolkit#121) is not a change of the set: the lagging copy stays a warning'
expect_not_out 'README.md' 'the README is not named as a set change'
ok

printf 'PASS: %d canonical-mirrors verdict cases\n' "$passed"
