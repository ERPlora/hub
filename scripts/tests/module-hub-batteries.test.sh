#!/usr/bin/env bash
# Contract tests for scripts/ci/module-hub-batteries.sh — the guard that decides WHICH module
# `*.hub.test.py|sh` batteries `test-hub-modules.yml` runs against the published kernel image.
#
# Regression test for ERPlora/hub#1381. What it protects, and why each case is here:
#
#   · hub#1264 moves the e2e that assert MODULE behaviour out of the hub and into each module's
#     own `erplora test` battery. The premise is that coverage CHANGES PLACE. On 2026-08-30 it
#     did not: hub#1372 deleted `services_package_redeem_e2e.rs` (391 lines, run by the pre-push
#     gate and by this very workflow) and the battery that replaced it —
#     `services/tests/package_redeem.hub.test.py` — was run by NOBODY. `git grep against-hub`
#     over `origin/develop` returned nothing. Both CIs were green, which is what made it
#     expensive: no red anywhere said the coverage had stopped being exercised.
#
#   · So the batteries get a runner, and the runner gets this guard. The list
#     (`scripts/ci/module-hub-batteries.txt`) is the OTHER half of
#     `scripts/ci/kernel-e2e-targets.txt`: a hub#1264 slice deletes a line THERE and adds the
#     battery it moved to HERE, in the same PR. That pair of edits is the reviewable act, and
#     it is what authorises deleting a hub e2e — while the battery runs nowhere, the deletion
#     has nothing to hand its coverage to.
#
#   · The guard is BIDIRECTIONAL, like its sibling. A DECLARED battery missing from the
#     published module is the hub#1381 case itself: the e2e is gone and its replacement never
#     landed (or was renamed), so the behaviour is asserted nowhere at all. A battery IN THE
#     TREE that nobody declared is the quieter one: it runs, but no reviewer ever tied it to
#     the coverage it was supposed to inherit, so the hub e2e it should have retired stays —
#     or worse, gets deleted later with everyone assuming the pairing was checked.
#
#   · And a module that never made it into the catalogue is an ENVIRONMENT error (exit 2), not
#     a verdict (exit 1). A failed clone must never read as "the battery is missing" — the same
#     separation `kernel-e2e-targets.sh` draws, and for the same reason: hub#1294 spent a red
#     job and nine blocked PRs on a transport flake that looked like a content failure.
#
# Everything here is hermetic: a scratch catalogue and a scratch manifest, no repo, no network.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/module-hub-batteries.sh"
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-module-hub-batteries-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    if [ -n "${err:-}" ]; then
        printf '  stderr was:\n%s\n' "$(printf '%s\n' "$err" | sed 's/^/    /')" >&2
    fi
    exit 1
}

ok() {
    passed=$((passed + 1))
}

if [ ! -f "$script" ]; then
    fail "no such script: $script"
fi

# ── Fixtures ────────────────────────────────────────────────────────────────────────────
# A scratch catalogue shaped like what `materialize-published-modules.sh` leaves on disk: one
# directory per module id, each with its `module.json`, and batteries under `tests/`.
make_module() { # $1=catalogue dir, $2=module id, rest=battery paths relative to the module
    local catalogue="$1" id="$2" rel
    shift 2
    mkdir -p "$catalogue/$id"
    printf '{"id": "%s", "version": "1.0.0"}\n' "$id" > "$catalogue/$id/module.json"
    for rel in "$@"; do
        mkdir -p "$catalogue/$id/$(dirname "$rel")"
        printf '# scratch battery\n' > "$catalogue/$id/$rel"
    done
}

make_manifest() { # $1=file, rest=declared `<module-id>/<battery path>` entries
    local file="$1"
    shift
    {
        echo "# Scratch manifest for the tests. Comments and blank lines are ignored."
        echo
        printf '%s\n' "$@"
    } > "$file"
}

out=""
err=""
rc=0
# Every run is pinned to one "today" so the `until` of a pending-publication marker (hub#1994) is
# measured against a fixed clock, never the machine's.
today=2026-09-23
run_guard() { # $1=catalogue, $2=manifest
    out=$("$script" --catalogue "$1" --manifest "$2" --today "$today" 2>"$tmp_dir/stderr")
    rc=$?
    err=$(cat "$tmp_dir/stderr")
    return 0
}

# ── 1 · Tree and list agree → exit 0, and stdout is the RUNNER's worklist ────────────────
# stdout is the contract with `test-hub-modules.yml`: the module ids to hand to
# `erplora test <dir> --against-hub`, one per line, sorted, DISTINCT. Every diagnostic goes to
# stderr so it can never be consumed as a module id.
catalogue="$tmp_dir/c1"
manifest="$tmp_dir/m1.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_module "$catalogue" verifactu "tests/desglose.hub.test.py"
make_module "$catalogue" inventory   # no battery at all: not declared, so not a finding
make_manifest "$manifest" \
    "services/tests/package_redeem.hub.test.py" \
    "verifactu/tests/desglose.hub.test.py"

run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "agreeing tree and list must exit 0, got $rc"
ok
[ "$out" = "services
verifactu" ] || fail "stdout must be the sorted distinct module ids, got: $(printf '%s' "$out" | tr '\n' ' ')"
ok

# A module with TWO batteries is still ONE unit of work: `erplora test <dir>` runs the whole
# directory, so emitting the id twice would boot the kernel image twice for nothing.
catalogue="$tmp_dir/c1b"
manifest="$tmp_dir/m1b.txt"
rm -rf "$catalogue"
make_module "$catalogue" verifactu "tests/desglose.hub.test.py" "tests/chain_import.hub.test.py"
make_manifest "$manifest" \
    "verifactu/tests/chain_import.hub.test.py" \
    "verifactu/tests/desglose.hub.test.py"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "two batteries in one module must still agree, got $rc"
ok
[ "$out" = "verifactu" ] || fail "a module with two batteries must be emitted ONCE, got: $(printf '%s' "$out" | tr '\n' ' ')"
ok

# ── 2 · DECLARED but absent from the module → exit 1, naming it (the hub#1381 case) ──────
# The hub e2e was deleted against a battery that is not there: the behaviour is now asserted
# nowhere. This is the direction that must never be silent.
catalogue="$tmp_dir/c2"
manifest="$tmp_dir/m2.txt"
rm -rf "$catalogue"
make_module "$catalogue" services            # the battery never landed (or was renamed)
make_manifest "$manifest" "services/tests/package_redeem.hub.test.py"

run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a declared battery missing from the module must exit 1, got $rc"
ok
case "$err" in
    *"services/tests/package_redeem.hub.test.py"*) ok ;;
    *) fail "the verdict must NAME the missing battery" ;;
esac
[ -z "$out" ] || fail "a failing guard must print no worklist, got: $out"
ok

# ── 3 · IN THE TREE but undeclared → exit 1, naming it ───────────────────────────────────
# It runs, but nobody tied it to the coverage it inherits. That pairing is the whole point of
# the list: without it a hub e2e gets deleted later with everyone assuming it was checked.
catalogue="$tmp_dir/c3"
manifest="$tmp_dir/m3.txt"
rm -rf "$catalogue"
make_module "$catalogue" sales "tests/void_reversal.hub.test.py"
make_manifest "$manifest" "# nothing declared yet"

run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "an undeclared battery in the tree must exit 1, got $rc"
ok
case "$err" in
    *"sales/tests/void_reversal.hub.test.py"*) ok ;;
    *) fail "the verdict must NAME the undeclared battery" ;;
esac

# ── 4 · `.hub.test.sh` counts too, and a plain test does NOT ─────────────────────────────
# The toolkit discovers `*.hub.test.py` and `*.hub.test.sh`. A guard that only knew about the
# Python half would let a shell battery land undeclared and unrun — the same hole one level down.
catalogue="$tmp_dir/c4"
manifest="$tmp_dir/m4.txt"
rm -rf "$catalogue"
make_module "$catalogue" staff "tests/commissions.hub.test.sh"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "an undeclared .hub.test.sh battery must exit 1, got $rc"
ok
case "$err" in
    *"staff/tests/commissions.hub.test.sh"*) ok ;;
    *) fail "the verdict must NAME the undeclared shell battery" ;;
esac

# A module's ordinary unit tests are NOT hub batteries: they already run in the module's own
# gate. Flagging them would make the guard cry wolf on every module in the catalogue.
catalogue="$tmp_dir/c4b"
manifest="$tmp_dir/m4b.txt"
rm -rf "$catalogue"
make_module "$catalogue" sales "tests/test_pricing.py" "tests/unit.test.js" "tests/notes.md"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "ordinary module tests must not be treated as hub batteries, got $rc: $err"
ok
[ -z "$out" ] || fail "a catalogue with no batteries yields an empty worklist, got: $out"
ok

# The toolkit classifies a battery as family `hub` by NAME (`*.hub.test.py|sh`) **or** by CONTENT
# (it reads `ERPLORA_HUB_BASE_URL` / `<ID>_HUB_BASE_URL`). A guard that only knew the naming half
# would let a hub battery hide behind an ordinary name — renamed by accident or on purpose — and
# go undeclared, which is the very silence being closed here.
catalogue="$tmp_dir/c4c"
manifest="$tmp_dir/m4c.txt"
rm -rf "$catalogue"
make_module "$catalogue" pricing "tests/rounding.test.py"
printf 'import os\nBASE = os.environ["ERPLORA_HUB_BASE_URL"]\n' > "$catalogue/pricing/tests/rounding.test.py"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a hub battery detected by CONTENT must exit 1, got $rc"
ok
case "$err" in
    *"pricing/tests/rounding.test.py"*) ok ;;
    *) fail "the verdict must NAME the content-detected battery" ;;
esac

# ...but the shared plumbing is not a battery. Every module with batteries ships a
# `tests/hub_harness.py` that mentions the same variable and is imported BY the batteries. It does
# not match `*.test.py|sh`, so it must never be flagged — otherwise the guard is red on all 11
# modules the day it lands, which is how a guard gets switched off.
catalogue="$tmp_dir/c4d"
manifest="$tmp_dir/m4d.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/hub_harness.py"
printf 'BASE = os.environ["ERPLORA_HUB_BASE_URL"]\n' > "$catalogue/services/tests/hub_harness.py"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "tests/hub_harness.py is plumbing, not a battery; got $rc: $err"
ok

# ── 5 · Discovery does not stop at `tests/` ──────────────────────────────────────────────
# A battery parked outside `tests/` must surface as UNDECLARED, never be skipped. A discoverer
# that quietly stops discovering is the same class of lie as the one this whole issue is about
# (hub#1327, hub#1359), one level up.
catalogue="$tmp_dir/c5"
manifest="$tmp_dir/m5.txt"
rm -rf "$catalogue"
make_module "$catalogue" appointments "e2e/availability.hub.test.py"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a battery outside tests/ must still be discovered, got $rc"
ok
case "$err" in
    *"appointments/e2e/availability.hub.test.py"*) ok ;;
    *) fail "the verdict must NAME a battery found outside tests/" ;;
esac

# ...but the module's own dependencies and build output are not its source. A vendored copy
# under `node_modules/` or a build artefact under `dist/` is not a battery anybody wrote.
catalogue="$tmp_dir/c5b"
manifest="$tmp_dir/m5b.txt"
rm -rf "$catalogue"
make_module "$catalogue" sales \
    "node_modules/@erplora/kit/tests/sample.hub.test.py" \
    "dist/tests/copied.hub.test.py"
make_manifest "$manifest" "# nothing declared"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "node_modules/ and dist/ must be excluded from discovery, got $rc: $err"
ok

# ── 6 · A module absent from the catalogue is an ENVIRONMENT error (exit 2) ──────────────
# A clone that failed must not read as "the battery is missing". hub#1294: one SSH flake turned
# the whole job red and blocked nine approved PRs; blaming the wrong layer is what made it cost
# half-hour diagnoses.
catalogue="$tmp_dir/c6"
manifest="$tmp_dir/m6.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_manifest "$manifest" \
    "services/tests/package_redeem.hub.test.py" \
    "appointments/tests/availability.hub.test.py"

run_guard "$catalogue" "$manifest"
[ "$rc" -eq 2 ] || fail "a declared module missing from the CATALOGUE must exit 2, got $rc"
ok
case "$err" in
    *appointments*) ok ;;
    *) fail "the environment error must NAME the module that never materialised" ;;
esac

# ── 7 · The degenerate repairs are refused ───────────────────────────────────────────────
# Emptying the list is how you make a coverage guard pass by removing what it guards — the
# lesson `kernel-e2e-targets.sh` learned from the numeric floor everyone just lowered.
catalogue="$tmp_dir/c7"
manifest="$tmp_dir/m7.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_manifest "$manifest" "# everything commented out"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "an empty manifest with batteries on disk must exit 1, got $rc"
ok

# A duplicated entry would run the module twice and, worse, let a later deletion pass with the
# other copy still standing.
catalogue="$tmp_dir/c7b"
manifest="$tmp_dir/m7b.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_manifest "$manifest" \
    "services/tests/package_redeem.hub.test.py" \
    "services/tests/package_redeem.hub.test.py"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a duplicated manifest entry must exit 1, got $rc"
ok

# An entry with no module prefix cannot be checked against anything: refuse it loudly instead
# of silently treating the whole string as a module id with no battery.
catalogue="$tmp_dir/c7c"
manifest="$tmp_dir/m7c.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_manifest "$manifest" "package_redeem.hub.test.py"
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a manifest entry without a <module>/<path> shape must exit 1, got $rc"
ok

# ── 8 · Broken invocation is an environment error, never a verdict ───────────────────────
run_guard "$tmp_dir/does-not-exist" "$manifest"
[ "$rc" -eq 2 ] || fail "a missing catalogue directory must exit 2, got $rc"
ok

run_guard "$catalogue" "$tmp_dir/no-such-manifest.txt"
[ "$rc" -eq 2 ] || fail "a missing manifest must exit 2, got $rc"
ok

# ── 9 · The shipped manifest agrees with the shipped guard ───────────────────────────────
# The list in the repo has to be parseable by the guard that reads it. A manifest that only the
# tests ever exercise is how a workflow discovers at 3am that its input was malformed.
shipped_manifest="$repo_root/scripts/ci/module-hub-batteries.txt"
[ -f "$shipped_manifest" ] || fail "no shipped manifest at $shipped_manifest"
ok

declared_shipped=$(sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    "$shipped_manifest" | grep -v '^$')

while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    case "$entry" in
        */*) ;;
        *) fail "shipped manifest entry is not <module>/<path>: $entry" ;;
    esac
    case "$entry" in
        *.hub.test.py | *.hub.test.sh) ;;
        *) fail "shipped manifest entry is not a hub battery: $entry" ;;
    esac
done <<EOF_ENTRIES
$declared_shipped
EOF_ENTRIES
ok

# ── 10 · The incident of hub#1396 stays pinned ───────────────────────────────────────────
# On 2026-09-01 `inventory` published `tests/combo_stock.hub.test.py` (inventory#77, v1.2.44) and
# the half of the pair that lives HERE was never written. The guard did its job — but only where
# the catalogue is, which is `test-hub-modules.yml`. So the red landed POST-MERGE, in somebody
# else's push, and stayed for 14 runs and a full day; and because the guard runs BEFORE
# `cargo test`, the crater — the 27 published modules against the runtime — did not run once in
# all that time.
#
# This pin is the cheap half of the answer: it moves the detection of THAT line going missing from
# "a day later, in CI" to "now, in the gate that runs this file". The expensive half — making the
# module's own gate demand the pairing before it merges, so the author sees it in their PR — is
# hub#1439.
#
# WHEN TO CHANGE THIS: when `combo_stock.hub.test.py` is legitimately retired from `inventory`,
# this case goes with it in the SAME commit. It is a pin on one incident, not a rule about the
# module — do not "fix" it by weakening it.
combo_entry='inventory/tests/combo_stock.hub.test.py'
grep -Fxq "$combo_entry" <<<"$declared_shipped" || fail \
    "the shipped manifest no longer declares $combo_entry (hub#1396)"
ok

# ── 11 · `--batteries`: the same discovery, one line per BATTERY (hub#1381) ──────────────
# The runner (`scripts/ci/run-module-hub-batteries.sh`) needs the FILES, not just the module ids:
# it runs the `*.hub.test.py|sh` batteries and nothing else, never the `.postgres`/`.pg` families
# next door. It gets them from here on purpose — a second copy of "what is a hub battery" (the
# name rule AND the `_HUB_BASE_URL` content rule) is exactly how the two halves drift apart, and
# a discoverer that quietly stops discovering is the lie one level up (hub#1327, hub#1359).
#
# The verdict is unchanged: `--batteries` only swaps WHAT is printed on the agreeing path.
catalogue="$tmp_dir/c11"
manifest="$tmp_dir/m11.txt"
rm -rf "$catalogue"
make_module "$catalogue" services "tests/package_redeem.hub.test.py"
make_module "$catalogue" verifactu "tests/desglose.hub.test.py" "tests/chain.hub.test.sh"
cat > "$manifest" <<'EOF'
services/tests/package_redeem.hub.test.py
verifactu/tests/chain.hub.test.sh
verifactu/tests/desglose.hub.test.py
EOF

out=$("$script" --catalogue "$catalogue" --manifest "$manifest" --batteries 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 0 ] || fail "--batteries on an agreeing pair must exit 0, got $rc"
ok
[ "$out" = "services/tests/package_redeem.hub.test.py
verifactu/tests/chain.hub.test.sh
verifactu/tests/desglose.hub.test.py" ] || fail \
    "--batteries must print <module>/<path> per battery, got: $(printf '%s' "$out" | tr '\n' ' ')"
ok

# A disagreement is still a disagreement: `--batteries` must never turn a verdict into a worklist,
# or the runner would happily run a list that already lost a battery.
cat > "$manifest" <<'EOF'
services/tests/package_redeem.hub.test.py
EOF
out=$("$script" --catalogue "$catalogue" --manifest "$manifest" --batteries 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 1 ] || fail "--batteries must still fail an undeclared battery, got $rc"
ok
[ -z "$out" ] || fail "--batteries must print no worklist on the failing path, got: $out"
ok

# ── 12 · `# pending-publication: <repo>#<n>` breaks the DEADLOCK of a NEW battery (kitchen#84) ──
# A battery that retires nothing — a brand-new one — could not land at all. The two halves of the
# pair guard each other: the module's gate (module-toolkit#163) refuses the battery until THIS list
# on `develop` declares it, and this guard refuses the declaration until the module's `main`
# publishes it. Both PRs red, forever; `MERGE_PR_FORCE` is not an exit. kitchen#79 had to drop its
# hub battery for exactly that reason, and kitchen#84 is the battery that was left out.
#
# The marker goes on its OWN comment line, right above the entry, because the module's gate
# compares whole lines: a trailing `# …` would stop it from recognising the declaration.
#
# What the marker excuses is ONE direction and nothing else: "declared but not published yet". It
# names the issue that will publish it, so a pending line is never anonymous; and it never puts
# the unpublished battery on the runner's worklist, which comes from the catalogue.
catalogue="$tmp_dir/c12"
manifest="$tmp_dir/m12.txt"
rm -rf "$catalogue"
make_module "$catalogue" kitchen "tests/tickets.hub.test.py"   # the new battery is NOT published yet
cat > "$manifest" <<'EOF'
kitchen/tests/tickets.hub.test.py
# pending-publication: kitchen#84 until 2026-10-01
kitchen/tests/closed_check.hub.test.py
EOF

out=$("$script" --catalogue "$catalogue" --manifest "$manifest" --batteries --today "$today" 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 0 ] || fail "a declared battery marked pending-publication must not fail the pair, got $rc"
ok
[ "$out" = "kitchen/tests/tickets.hub.test.py" ] || fail \
    "an unpublished pending battery must never reach the runner's worklist, got: $(printf '%s' "$out" | tr '\n' ' ')"
ok
grep -Fq 'kitchen/tests/closed_check.hub.test.py' <<<"$err" || fail \
    "the pending battery must be named on stderr so it never goes quiet"
ok
grep -Fq 'pending-publication: kitchen/tests/closed_check.hub.test.py (kitchen#84, until 2026-10-01)' <<<"$err" || fail \
    "the pending notice must name the battery and the issue that publishes it"
ok
if grep -Fq 'stale-pending-publication' <<<"$err"; then
    fail "an unpublished pending battery is not stale"
fi
ok

# Positive control: the SAME fixture without the marker is still the hub#1381 red. If this passed,
# the case above would prove nothing about the marker.
cat > "$manifest" <<'EOF'
kitchen/tests/tickets.hub.test.py
kitchen/tests/closed_check.hub.test.py
EOF
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "without the marker an unpublished declared battery must still exit 1, got $rc"
ok

# The marker excuses only the entry RIGHT BELOW it — not the next one down the file.
cat > "$manifest" <<'EOF'
# pending-publication: kitchen#84 until 2026-10-01
kitchen/tests/tickets.hub.test.py
kitchen/tests/closed_check.hub.test.py
EOF
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a marker must excuse only the entry directly below it, got $rc"
ok

# The marker's OWN refusals are measured against a PUBLISHED entry, so the marker is the only thing
# that can put them red — against an unpublished one they would go red through the hub#1381
# direction and a guard that ignored the marker entirely would pass them.
catalogue="$tmp_dir/c12b"
rm -rf "$catalogue"
make_module "$catalogue" kitchen "tests/tickets.hub.test.py" "tests/closed_check.hub.test.py"

# A marker without an issue is refused: a pending line nobody owns is how it stays pending forever.
for bad in '' 'soon' 'kitchen 84'; do
    printf 'kitchen/tests/tickets.hub.test.py\n# pending-publication: %s\nkitchen/tests/closed_check.hub.test.py\n' \
        "$bad" > "$manifest"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 1 ] || fail "a pending-publication marker without <repo>#<n> ('$bad') must exit 1, got $rc"
    ok
done

# A marker with no entry right below it (a blank line, a comment or the end of the file) is
# refused too: it would read as a pending battery that excuses nothing, or — worse — the wrong
# one after an edit.
for gap in '' '# a comment'; do
    printf 'kitchen/tests/tickets.hub.test.py\n# pending-publication: kitchen#84 until 2026-10-01\n%s\nkitchen/tests/closed_check.hub.test.py\n' \
        "$gap" > "$manifest"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 1 ] || fail "a marker separated from its entry by '$gap' must exit 1, got $rc"
    ok
done
cat > "$manifest" <<'EOF2'
kitchen/tests/tickets.hub.test.py
kitchen/tests/closed_check.hub.test.py
# pending-publication: kitchen#84 until 2026-10-01
EOF2
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "a dangling pending-publication marker at the end of the list must exit 1, got $rc"
ok

# Once the module publishes it, the battery is a normal declared one: green, on the worklist, and a
# notice asks for the now-stale marker to go. Never red — that would put the hub's CI red in the
# push of whoever comes next, the inventory#77 crater this whole pairing exists to avoid.
make_module "$catalogue" kitchen "tests/closed_check.hub.test.py"
cat > "$manifest" <<'EOF'
kitchen/tests/tickets.hub.test.py
# pending-publication: kitchen#84 until 2026-10-01
kitchen/tests/closed_check.hub.test.py
EOF
out=$("$script" --catalogue "$catalogue" --manifest "$manifest" --batteries --today "$today" 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 0 ] || fail "a pending battery that got published must pass, got $rc"
ok
[ "$out" = "kitchen/tests/closed_check.hub.test.py
kitchen/tests/tickets.hub.test.py" ] || fail \
    "a published pending battery must reach the worklist, got: $(printf '%s' "$out" | tr '\n' ' ')"
ok
grep -Fq 'stale-pending-publication: kitchen/tests/closed_check.hub.test.py (kitchen#84, until 2026-10-01)' <<<"$err" || fail \
    "a published battery still marked pending must get a stale-pending-publication notice"
ok

# ── 13 · A pending-publication marker EXPIRES (hub#1994) ─────────────────────────────────────
# Case 12 lets a NEW battery land before its module publishes it. The price is a direction of the
# pair that goes quiet: while it is pending, nothing runs it and the pass stays green. Without an
# end date a marker whose module never publishes stays pending for months with no red and no
# annotation anywhere — the same silence as hub#1381 (coverage nobody runs, both CIs green).
#
# So the marker carries its own deadline, `until <YYYY-MM-DD>`, at most 30 days ahead of the day
# it is checked. Past it, an entry that is STILL unpublished is red (exit 1): the nightly opens its
# alert issue, and the fix is a reviewable edit — publish the battery, or drop the entry. A
# published one past its date is only the stale notice of case 12: it runs, nothing is hidden.
catalogue="$tmp_dir/c13"
manifest="$tmp_dir/m13.txt"
rm -rf "$catalogue"
make_module "$catalogue" kitchen "tests/tickets.hub.test.py"   # closed_check is NOT published
write_pending() { # $1=the text after `pending-publication:`
    printf 'kitchen/tests/tickets.hub.test.py\n# pending-publication: %s\nkitchen/tests/closed_check.hub.test.py\n' \
        "$1" > "$manifest"
}

# The deadline itself is still inside the window: `until` names the LAST day the marker excuses.
write_pending 'kitchen#84 until 2026-09-23'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "a marker on its own until day must still excuse the entry, got $rc"
ok

# One day past it, an unpublished entry is red — and the verdict names it and the issue.
write_pending 'kitchen#84 until 2026-09-22'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "an EXPIRED marker on an unpublished battery must exit 1, got $rc"
ok
grep -Fq 'expired-pending-publication: kitchen/tests/closed_check.hub.test.py (kitchen#84, until 2026-09-22)' <<<"$err" || fail \
    "the expiry verdict must name the battery, the issue and the date it expired"
ok
[ -z "$out" ] || fail "an expired marker must print no worklist, got: $out"
ok

# Expiry compares DATES, not strings of any shape: a month boundary and a year boundary.
today=2026-10-01
write_pending 'kitchen#84 until 2026-09-30'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "until 2026-09-30 checked on 2026-10-01 is expired, got $rc"
ok
today=2027-01-01
write_pending 'kitchen#84 until 2026-12-31'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "until 2026-12-31 checked on 2027-01-01 is expired, got $rc"
ok
write_pending 'kitchen#84 until 2027-01-31'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "until 2027-01-31 checked on 2027-01-01 (30 days ahead) is valid, got $rc"
ok
today=2026-09-23

# A deadline further than 30 days out is refused: `until 2099-01-01` would be "never" in disguise.
# The 30 days count from the WRITER's today, and the writer's calendar may already be on the day
# after UTC's (hub#2416): at 01:00 in Madrid on 2026-09-30 it is still 2026-09-29 in UTC, and the
# fleet wrote `until 2026-10-30` — its today plus 30 — which the CI, checking in UTC, read as 31
# days and turned `develop` red for an hour. No clock on Earth runs more than one calendar day
# ahead of UTC (UTC+14), so the last day allowed is UTC's today + 31.
write_pending 'kitchen#84 until 2026-10-23'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "a marker exactly 30 days ahead must be allowed, got $rc"
ok
write_pending 'kitchen#84 until 2026-10-24'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "a marker 30 days ahead of a writer already on UTC's tomorrow must be allowed, got $rc"
ok
for far in 2026-10-25 2099-01-01; do
    write_pending "kitchen#84 until $far"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 1 ] || fail "a marker more than 30 days ahead of any writer (until $far) must exit 1, got $rc"
    ok
done

# The exact red of run 36642817538: `inventory#128 until 2026-10-30`, written at 01:00 CEST on
# 2026-09-30 and checked at 23:22Z on 2026-09-29.
today=2026-09-29
write_pending 'inventory#128 until 2026-10-30'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "'until 2026-10-30' written in Madrid on 2026-09-30 and checked on UTC's 2026-09-29 must pass, got $rc: $err"
ok
write_pending 'inventory#128 until 2026-10-31'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "'until 2026-10-31' is 31 days past the Madrid writer's 2026-09-30 and must exit 1, got $rc"
ok
today=2026-09-23

# A marker with no deadline, or one that is not a real calendar date, is refused: an undated
# marker is exactly the pending-forever this case exists to end.
for bad in 'kitchen#84' 'kitchen#84 until' 'kitchen#84 until soon' 'kitchen#84 until 2026-9-30' \
    'kitchen#84 by 2026-09-30' 'kitchen#84 until 2026-09-30 or later'; do
    write_pending "$bad"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 1 ] || fail "a marker without a valid 'until <YYYY-MM-DD>' ('$bad') must exit 1, got $rc"
    ok
done
# Impossible calendar dates, each checked on a day where — read as the day it would roll over to —
# it would be in the window and unexpired. Otherwise the expiry or the horizon would put them red
# and the date validation itself would go untested.
for pair in '2026-02-20 2026-02-30' '2026-02-20 2026-02-29' '2026-12-20 2026-13-01' \
    '2026-04-20 2026-04-31' '2026-09-20 2026-09-00'; do
    today=${pair%% *}
    write_pending "kitchen#84 until ${pair##* }"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 1 ] || fail "'until ${pair##* }' is not a calendar date (checked on $today), must exit 1, got $rc"
    ok
done
# Positive control for the leap-year rule: February 29th exists in 2028 and in 2000.
for pair in '2028-02-20 2028-02-29' '2000-02-20 2000-02-29'; do
    today=${pair%% *}
    write_pending "kitchen#84 until ${pair##* }"
    run_guard "$catalogue" "$manifest"
    [ "$rc" -eq 0 ] || fail "'until ${pair##* }' is a real leap day (checked on $today), must pass, got $rc"
    ok
done
# The window across February of a century year that is NOT a leap year: 2100-02-20 to 2100-03-23
# is exactly 31 days (February 2100 has 28) — 30 from a writer already on UTC's tomorrow — so it is
# the last day allowed and the next one is refused. A day count that treated 2100 as a leap year
# would get both wrong.
today=2100-02-20
write_pending 'kitchen#84 until 2100-03-23'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "2100-02-20 → 2100-03-23 is 31 days (30 from UTC's tomorrow) and must pass, got $rc"
ok
write_pending 'kitchen#84 until 2100-03-24'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 1 ] || fail "2100-02-20 → 2100-03-24 is 32 days and must exit 1, got $rc"
ok
today=2026-09-23

# Past its date but PUBLISHED: nothing is hidden, the battery runs — the stale notice of case 12,
# never a red (that red would land in the push of whoever merges next, the inventory#77 crater).
make_module "$catalogue" kitchen "tests/closed_check.hub.test.py"
write_pending 'kitchen#84 until 2026-09-01'
run_guard "$catalogue" "$manifest"
[ "$rc" -eq 0 ] || fail "an expired marker on a PUBLISHED battery must not go red, got $rc"
ok
grep -Fq 'stale-pending-publication: kitchen/tests/closed_check.hub.test.py (kitchen#84, until 2026-09-01)' <<<"$err" || fail \
    "an expired marker on a published battery must still get the stale notice"
ok

# Without `--today`, the guard reads the real clock (UTC). A marker dated today must pass, which
# proves the default is wired, not that it happens to be some fixed day.
rm -rf "$catalogue"
make_module "$catalogue" kitchen "tests/tickets.hub.test.py"
write_pending "kitchen#84 until $(date -u +%Y-%m-%d)"
out=$("$script" --catalogue "$catalogue" --manifest "$manifest" 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 0 ] || fail "a marker dated today (real clock) must pass without --today, got $rc"
ok

# A malformed `--today` is the CALLER's error (exit 2), never a verdict on the list.
out=$("$script" --catalogue "$catalogue" --manifest "$manifest" --today yesterday 2>"$tmp_dir/stderr")
rc=$?
err=$(cat "$tmp_dir/stderr")
[ "$rc" -eq 2 ] || fail "a malformed --today must exit 2, got $rc"
ok

# The shipped list obeys the same grammar: every marker in it carries a valid, in-window `until`.
# Measured against its own catalogue-free shape — the markers are checked before any catalogue
# comparison, so an empty catalogue with the list's modules is enough to surface a bad marker.
shipped="$repo_root/scripts/ci/module-hub-batteries.txt"
while IFS= read -r marker; do
    grep -Eq '^# pending-publication: [A-Za-z0-9_./-]+#[0-9]+ until [0-9]{4}-[0-9]{2}-[0-9]{2}$' <<<"$marker" || \
        fail "the shipped list carries a marker without 'until <YYYY-MM-DD>': $marker"
done < <(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$shipped" | grep '^# pending-publication:' || true)
ok

printf 'PASS: %d module-hub-batteries guard cases\n' "$passed"
