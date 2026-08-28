#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Tests for scripts/materialize-published-modules.sh — the materialiser of the
# PUBLISHED module catalogue.
#
# Regression test for ERPlora/hub#1153: the local gate used to point the module
# e2e at the shared `modules-workspace/modules` checkout, whose content is
# whatever branch the last agent left each module on (9 of 27 were off `main`
# on 2026-08-28). A gate whose verdict depends on that is a raffle, and it goes
# both ways: a module BEHIND reds a push that did not cause it (`sales_e2e`),
# a module AHEAD greens a contract that already moved in production (hub#540).
#
# Every case runs against LOCAL bare repos over `file://` — no network, no
# GitHub, no deploy keys — so this suite is deterministic and runnable in CI.
#
# Run:  bash scripts/materialize-published-modules.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/materialize-published-modules.sh"
pass=0
fail=0

ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

# ── Fixture ──────────────────────────────────────────────────────────────────
# For each module id: a BARE repo (its "GitHub"), whose `main` carries the
# PUBLISHED version, plus a working checkout parked on a feature branch with a
# DIFFERENT version — the exact shape of `modules-workspace` on the fleet
# machine. The checkout is only ever allowed to contribute the module ID and
# the remote URL; its content must never reach the suite.
make_catalogue() {           # $1 = how many modules
    local count=$1 base i id origin work
    base=$(cd "$(mktemp -d)" && pwd -P)
    mkdir -p "$base/origins" "$base/workspace"
    for i in $(seq 1 "$count"); do
        id=$(printf 'mod%02d' "$i")
        origin="$base/origins/$id.git"
        work="$base/build/$id"
        mkdir -p "$work"
        git -C "$work" init -q -b main
        git -C "$work" config user.email cat@test
        git -C "$work" config user.name catalogue
        printf '{"id":"%s","version":"2.0.0"}\n' "$id" > "$work/module.json"
        echo published > "$work/marker"
        git -C "$work" add module.json marker
        git -C "$work" commit -qm published
        git init -q --bare "$origin"
        git -C "$work" remote add origin "$origin"
        git -C "$work" push -q origin main
        # …and the PARKED local checkout, on a branch that is NOT main.
        git clone -q "$origin" "$base/workspace/$id"
        git -C "$base/workspace/$id" checkout -qb feat/parked
        printf '{"id":"%s","version":"1.0.0-parked"}\n' "$id" > "$base/workspace/$id/module.json"
        echo parked > "$base/workspace/$id/marker"
        git -C "$base/workspace/$id" -c user.email=p@test -c user.name=p commit -qam parked
    done
    echo "$base"
}

# Move a module's published `main` forward, so the cache has something to catch up with.
publish_new_version() {      # $1 = base  $2 = id  $3 = version
    local work="$1/build/$2"
    printf '{"id":"%s","version":"%s"}\n' "$2" "$3" > "$work/module.json"
    git -C "$work" commit -qam "release $3"
    git -C "$work" push -q origin main
}

run_script() {               # prints exit code; stdout+stderr land in $OUT
    "$@" >"$OUT" 2>&1
    echo $?
}

echo "materialize-published-modules"

# ── 1. The materialised tree is `main`, never the parked checkout ─────────────
#    The heart of hub#1153. `--ids-from` hands over the workspace, and the ONLY
#    things taken from it are the module ids and each remote URL.
base=$(make_catalogue 26)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
n=$(find "$base/dest" -mindepth 2 -maxdepth 2 -name module.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n" = 26 ] || errs="$errs manifests=$n(want 26)"
grep -q '"version":"2.0.0"' "$base/dest/mod01/module.json" 2>/dev/null || errs="$errs mod01-is-not-the-published-version"
grep -q parked "$base/dest/mod01/marker" 2>/dev/null && errs="$errs parked-content-reached-the-suite"
[ -z "$errs" ] \
    && ok "materialises every module at its published main, never the parked checkout" \
    || bad "materialises every module at its published main, never the parked checkout" "$errs out=$(tail -c 400 "$OUT")"

# ── 2. The resolved directory is the ONLY thing on stdout ─────────────────────
#    Callers (the hook, the workflow) consume it; progress goes to stderr.
base=$(make_catalogue 25)
outdir=$(bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25 2>/dev/null)
errs=""
[ -n "$outdir" ] || errs="$errs stdout-was-empty"
[ -f "$outdir/mod01/module.json" ] 2>/dev/null || errs="$errs stdout-does-not-point-at-a-materialised-catalogue"
[ "$outdir" = "$(cd "$base/dest" 2>/dev/null && pwd -P)" ] || errs="$errs stdout='$outdir'-is-not-the-dest"
[ -z "$errs" ] \
    && ok "stdout carries exactly the resolved catalogue directory" \
    || bad "stdout carries exactly the resolved catalogue directory" "$errs"

# ── 3. The floor REFUSES a short catalogue, and says the count ────────────────
#    Without it a partial clone silently shrinks coverage: the first version of
#    the CI job cloned 13 of 27 and would have passed at 21 (hub#1216).
base=$(make_catalogue 24)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-on-a-short-catalogue"
grep -q '24' "$OUT" || errs="$errs error-does-not-say-how-many-were-found"
grep -qi '25' "$OUT" || errs="$errs error-does-not-say-the-floor"
[ -z "$errs" ] \
    && ok "floor: fewer than 25 manifests is a LOUD failure, naming the count" \
    || bad "floor: fewer than 25 manifests is a LOUD failure, naming the count" "$errs out=$(tail -c 400 "$OUT")"

# ── 4. Cached, and refreshed when `origin/main` moves ─────────────────────────
#    A re-clone of 27 repos on every push would make the opt-in unusable; a
#    cache that never refreshes would recreate the very staleness of hub#1153.
base=$(make_catalogue 25)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
first_sha=$(git -C "$base/dest/mod01" rev-parse HEAD 2>/dev/null)
publish_new_version "$base" mod01 3.1.4
code2=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] || errs="$errs first-exit=$code"
[ "$code2" = 0 ] || errs="$errs second-exit=$code2"
grep -q '"version":"3.1.4"' "$base/dest/mod01/module.json" 2>/dev/null \
    || errs="$errs cache-did-not-catch-up-with-origin-main"
[ "$(git -C "$base/dest/mod01" rev-parse HEAD)" != "$first_sha" ] || errs="$errs head-did-not-move"
grep -q '"version":"2.0.0"' "$base/dest/mod02/module.json" 2>/dev/null \
    || errs="$errs untouched-module-was-lost-on-refresh"
[ -z "$errs" ] \
    && ok "cache: reused across runs and refreshed when origin/main moves" \
    || bad "cache: reused across runs and refreshed when origin/main moves" "$errs out=$(tail -c 400 "$OUT")"

# ── 5. A module that cannot be fetched is NAMED, and the run fails ────────────
#    Silence here is how a catalogue quietly loses a module.
base=$(make_catalogue 26)
OUT="$base/out"
rm -rf "$base/origins/mod07.git"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-with-an-unreachable-module"
grep -q 'mod07' "$OUT" || errs="$errs failure-does-not-name-the-module"
[ -z "$errs" ] \
    && ok "an unreachable module fails the run and is named" \
    || bad "an unreachable module fails the run and is named" "$errs out=$(tail -c 400 "$OUT")"

# ── 6. The id list comes from the KEYS BUNDLE when there is one ───────────────
#    That is what CI has, and it is the only source that cannot quietly fall
#    short: a module without its deploy key cannot be cloned there anyway.
base=$(make_catalogue 26)
OUT="$base/out"
keys="$base/keys"
mkdir -p "$keys"
for i in $(seq 1 26); do : > "$keys/$(printf 'mod%02d' "$i")"; done
rm -rf "$base/workspace/mod13"          # absent locally: the bundle must still list it
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --keys "$keys" \
        --ids-from "$base/workspace" --floor 25 \
        --remote-template "$base/origins/%s.git")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
[ -f "$base/dest/mod13/module.json" ] || errs="$errs module-only-in-the-bundle-was-not-materialised"
[ -z "$errs" ] \
    && ok "the keys bundle is the id source when present" \
    || bad "the keys bundle is the id source when present" "$errs out=$(tail -c 400 "$OUT")"

# ── 7. No id source at all: refuse, never produce an empty catalogue ──────────
base=$(make_catalogue 1)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/nowhere" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-with-no-ids"
grep -qi 'no module ids' "$OUT" || errs="$errs failure-does-not-say-there-are-no-module-ids"
[ -z "$errs" ] \
    && ok "no resolvable module ids: refuses instead of handing back an empty tree" \
    || bad "no resolvable module ids: refuses instead of handing back an empty tree" "$errs out=$(tail -c 400 "$OUT")"

# ── 8. No deploy key: the developer's OWN ssh is used, never an EMPTY one ─────
#    Regression test for ERPlora/hub#1153 (review). The fallback path — no keys
#    bundle, remotes taken from the local checkouts — used to export
#    `GIT_SSH_COMMAND=""`, and git does not read an empty value as "unset": it
#    tries to run an empty program ("error: cannot run : No such file or
#    directory / fatal: unable to fork"), so EVERY ssh remote failed. The 27
#    checkouts on the fleet machine are https, which is why a smoke test there
#    never saw it; a developer with `git@github.com:` remotes would have.
#    A fake `ssh` on PATH stands in for the developer's own: it drops the host
#    and runs the upload-pack locally, so the case stays offline.
base=$(make_catalogue 25)
OUT="$base/out"
mkdir -p "$base/bin"
cat > "$base/bin/ssh" <<'FAKE'
#!/usr/bin/env bash
# fake ssh: `ssh [options] host '<git command>'` → run the command locally
cmd="${!#}"
exec sh -c "${cmd/#git-upload-pack/git upload-pack}"
FAKE
chmod +x "$base/bin/ssh"
for i in $(seq 1 25); do
    id=$(printf 'mod%02d' "$i")
    git -C "$base/workspace/$id" remote set-url origin "ssh://localhost$base/origins/$id.git"
done
code=$(PATH="$base/bin:$PATH" run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
grep -q 'unable to fork\|cannot run :' "$OUT" && errs="$errs git-was-handed-an-EMPTY-ssh-command"
n=$(find "$base/dest" -mindepth 2 -maxdepth 2 -name module.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n" = 25 ] || errs="$errs manifests=$n(want 25)"
[ -z "$errs" ] \
    && ok "no deploy key: ssh remotes go through the developer's own ssh, not an empty GIT_SSH_COMMAND" \
    || bad "no deploy key: ssh remotes go through the developer's own ssh, not an empty GIT_SSH_COMMAND" "$errs out=$(tail -c 400 "$OUT")"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
