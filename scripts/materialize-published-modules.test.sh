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

# ── 9. A Mac-built bundle carries AppleDouble `._<module>` entries ────────────
#    Regression test for ERPlora/hub#1153 (CI red of PR #1256, run 33128409723).
#    `MODULES_DEPLOY_KEYS` is a tar+base64 built on a Mac, so for every key it
#    also carries an AppleDouble sidecar `._<module>`. The inline version of this
#    loop listed the bundle with plain `ls`, which HIDES dotfiles, so it never saw
#    them; this script listed it with `ls -A`, which does not — and the catalogue
#    became 54 "modules". The 27 real ones cloned fine and the 27 sidecars each
#    died with `git@github.com: Permission denied (publickey)`, failing the job.
#
#    A module id is `^[a-z][a-z0-9_]*$` (schemas/module.schema.json), so anything
#    else in the bundle is not a module and must be ignored — out loud, never in
#    silence, because a genuinely mistyped id has to stay visible.
#
#    The case also pins WHICH key each clone uses: a fake `ssh` on PATH records
#    its `-i` argument and then serves the upload-pack locally, so it stays
#    offline. `._mod01` must never be handed to git as a key.
base=$(make_catalogue 26)
OUT="$base/out"
keys="$base/keys"
mkdir -p "$keys" "$base/bin"
export KEYLOG="$base/KEYS_USED"
: > "$KEYLOG"
for i in $(seq 1 26); do
    id=$(printf 'mod%02d' "$i")
    printf 'real-key-for-%s\n' "$id" > "$keys/$id"
    printf 'Mac Finder junk\n'      > "$keys/._$id"      # the AppleDouble sidecar
done
printf 'junk\n' > "$keys/.DS_Store"
cat > "$base/bin/ssh" <<'FAKE'
#!/usr/bin/env bash
# fake ssh: records the -i key it was handed, then runs the git command locally
key=""; prev=""
for a in "$@"; do [ "$prev" = "-i" ] && key="$a"; prev="$a"; done
[ -n "$key" ] && [ -n "${KEYLOG:-}" ] && printf '%s\n' "$(basename "$key")" >> "$KEYLOG"
cmd="${!#}"
exec sh -c "${cmd/#git-upload-pack/git upload-pack}"
FAKE
chmod +x "$base/bin/ssh"
code=$(PATH="$base/bin:$PATH" run_script bash "$SCRIPT" --dest "$base/dest" \
        --keys "$keys" --floor 25 \
        --remote-template "ssh://localhost$base/origins/%s.git")
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
n=$(find "$base/dest" -mindepth 2 -maxdepth 2 -name module.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n" = 26 ] || errs="$errs manifests=$n(want 26)"
# Nothing named `._*` may be treated as a module…
grep -q '^\._' <<<"$(ls -A "$base/dest" 2>/dev/null)" && errs="$errs applelDouble-was-materialised-as-a-module"
# `── ._mod…` is the per-module failure header: it can only appear if a sidecar
# reached the clone loop. The names themselves DO appear in the "ignored" notice,
# on purpose, so a bare grep for `._mod` would be wrong here.
grep -q '── \._' "$OUT" && errs="$errs applelDouble-reached-the-clone-loop"
# …and the announcement must count 26, never 52+1.
grep -q '26 module(s)' "$OUT" || errs="$errs id-count-is-not-26"
# The keys actually handed to git are the REAL ones, never a sidecar.
grep -q '^\._' "$KEYLOG" && errs="$errs an-AppleDouble-file-was-used-AS-A-KEY"
[ "$(sort -u "$KEYLOG" | wc -l | tr -d ' ')" = 26 ] || errs="$errs distinct-keys=$(sort -u "$KEYLOG" | wc -l | tr -d ' ')(want 26)"
grep -qx 'mod07' "$KEYLOG" || errs="$errs mod07-was-not-cloned-with-its-own-key"
# Ignoring is LOUD: a mistyped id must not vanish in silence.
grep -qi 'ignor' "$OUT" || errs="$errs entries-were-dropped-silently"
unset KEYLOG
[ -z "$errs" ] \
    && ok "a Mac-built bundle's AppleDouble entries are ignored, and each clone uses its real key" \
    || bad "a Mac-built bundle's AppleDouble entries are ignored, and each clone uses its real key" "$errs out=$(tail -c 500 "$OUT")"

# ── 10-12. Retry on transient clone failures ───────────────────────────────
# Regression tests for ERPlora/hub#1294: on 2026-08-28 at 11:55-11:56Z a ONE
# clone in the "e2e con módulos reales" job hit `git@github.com: Permission
# denied (publickey)` while the SAME deploy key had cloned the same module
# fine three hours earlier (a transient rejection, not a config problem) —
# and with zero retry, that one flake turned the whole job red and blocked
# nine approved PRs. A fake `git` on PATH stands in for a flaky remote: it
# fails the first N `clone` invocations, then delegates to the real git, so
# these cases stay offline and deterministic. Delays are driven down to 0s via
# `HUB_MATERIALIZE_RETRY_DELAYS` so the suite does not sit through real
# backoff.
REAL_GIT="$(command -v git)"

# Writes a `git` stub to $1 (a bin dir) that fails every `clone` invocation
# while its shared counter is <= $STUB_FAIL_COUNT, writing $STUB_FAIL_MESSAGE
# to stderr; every other invocation (including later `clone` calls once the
# threshold is passed) runs the real git. Config comes through env vars —
# set STUB_COUNTER/STUB_FAIL_COUNT/STUB_FAIL_MESSAGE/STUB_REAL_GIT — so the
# heredoc itself never needs per-case quoting.
make_flaky_git_stub() {      # $1 = bin dir
    mkdir -p "$1"
    cat > "$1/git" <<'STUB'
#!/usr/bin/env bash
if [ "$1" = "clone" ]; then
    n=$(( $(cat "$STUB_COUNTER" 2>/dev/null || echo 0) + 1 ))
    printf '%s\n' "$n" > "$STUB_COUNTER"
    if [ "$n" -le "$STUB_FAIL_COUNT" ]; then
        printf '%s\n' "$STUB_FAIL_MESSAGE" >&2
        exit 128
    fi
fi
exec "$STUB_REAL_GIT" "$@"
STUB
    chmod +x "$1/git"
}

# ── 10. A clone that fails twice with a transient error, then succeeds ───────
base=$(make_catalogue 25)
OUT="$base/out"
make_flaky_git_stub "$base/bin"
export STUB_COUNTER="$base/clone-attempts" STUB_FAIL_COUNT=2 \
       STUB_FAIL_MESSAGE='git@github.com: Permission denied (publickey).' \
       STUB_REAL_GIT="$REAL_GIT"
: > "$STUB_COUNTER"
code=$(PATH="$base/bin:$PATH" HUB_MATERIALIZE_RETRY_DELAYS="0 0 0" \
        run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
[ -f "$base/dest/mod01/module.json" ] || errs="$errs mod01-was-not-materialised"
retries=$(grep -ci 'retry\|retrying' "$OUT" || true)
[ "${retries:-0}" -ge 2 ] || errs="$errs retries-not-logged(saw=$retries)"
unset STUB_COUNTER STUB_FAIL_COUNT STUB_FAIL_MESSAGE STUB_REAL_GIT
[ -z "$errs" ] \
    && ok "hub#1294: a transient Permission-denied clone failure is retried, and each retry is logged" \
    || bad "hub#1294: a transient Permission-denied clone failure is retried, and each retry is logged" "$errs out=$(tail -c 500 "$OUT")"

# ── 11. A clone that keeps failing transiently exhausts the retry budget ─────
#    "The door does not open": once retries run out, the module is still
#    reported as NOT materialised — never silently dropped.
base=$(make_catalogue 25)
OUT="$base/out"
make_flaky_git_stub "$base/bin"
export STUB_COUNTER="$base/clone-attempts" STUB_FAIL_COUNT=99 \
       STUB_FAIL_MESSAGE='git@github.com: Permission denied (publickey).' \
       STUB_REAL_GIT="$REAL_GIT"
: > "$STUB_COUNTER"
code=$(PATH="$base/bin:$PATH" HUB_MATERIALIZE_RETRY_DELAYS="0 0 0" \
        run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-with-a-persistently-failing-clone"
grep -q 'could NOT materialise:.*mod01' "$OUT" || errs="$errs failure-does-not-name-mod01"
[ -f "$base/dest/mod01/module.json" ] && errs="$errs mod01-was-materialised-despite-exhausted-retries"
unset STUB_COUNTER STUB_FAIL_COUNT STUB_FAIL_MESSAGE STUB_REAL_GIT
[ -z "$errs" ] \
    && ok "hub#1294: a persistently failing transient clone exhausts retries and is still reported, never silently" \
    || bad "hub#1294: a persistently failing transient clone exhausts retries and is still reported, never silently" "$errs out=$(tail -c 500 "$OUT")"

# ── 12. "repository not found" is a PERMANENT failure: no retry at all ───────
#    Retrying a config error just delays the same answer. This also proves
#    the retry loop discriminates by message, not just "any git failure".
base=$(make_catalogue 25)
OUT="$base/out"
make_flaky_git_stub "$base/bin"
export STUB_COUNTER="$base/clone-attempts" STUB_FAIL_COUNT=99 \
       STUB_FAIL_MESSAGE="ERROR: Repository not found." \
       STUB_REAL_GIT="$REAL_GIT"
: > "$STUB_COUNTER"
code=$(PATH="$base/bin:$PATH" HUB_MATERIALIZE_RETRY_DELAYS="0 0 0" \
        run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-with-an-unreachable-repository"
grep -q 'could NOT materialise:.*mod01' "$OUT" || errs="$errs failure-does-not-name-mod01"
grep -qi 'retry\|retrying' "$OUT" && errs="$errs retried-a-permanent-repository-not-found-failure"
# Only mod01 was attempted once before giving up; the rest of the 25 modules
# clone normally (their attempts push the shared counter well past 1), so a
# counter of exactly 25 proves mod01 was never retried.
[ "$(cat "$STUB_COUNTER" 2>/dev/null)" = 25 ] || errs="$errs unexpected-clone-attempt-count=$(cat "$STUB_COUNTER" 2>/dev/null)"
unset STUB_COUNTER STUB_FAIL_COUNT STUB_FAIL_MESSAGE STUB_REAL_GIT
[ -z "$errs" ] \
    && ok "hub#1294: 'repository not found' fails immediately, with no retry" \
    || bad "hub#1294: 'repository not found' fails immediately, with no retry" "$errs out=$(tail -c 500 "$OUT")"

# ── 13-15. La caché es COMPARTIDA: tiene que sanearse sola (hub#1380) ────────
# El 2026-08-30 el gate murió para TODA la flota con los 27 módulos fallando a
# la vez. Dos síntomas distintos, una sola causa: `fetch_existing_tree` hacía
# `checkout` SIN `-f`, así que cualquier suciedad dentro de la caché abortaba el
# checkout —y el `clean` que la habría quitado va DESPUÉS, o sea que no llegaba
# a correr nunca—. La caché la comparten los ~19 worktrees del hub
# (`STATE_DIR=$(git rev-parse --git-common-dir)/hub-gate`), así que que un
# directorio quede sucio no es un accidente raro: es el estado normal.

# ── 13. Un fichero tocado dentro de la caché se sanea solo ───────────────────
#    Hoy: «error: Your local changes to the following files would be overwritten
#    by checkout» y el gate queda muerto PARA SIEMPRE, porque nada lo limpia.
base=$(make_catalogue 25)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
publish_new_version "$base" mod01 3.1.4
echo '{"id":"mod01","version":"DIRTY-local-edit"}' > "$base/dest/mod01/module.json"
code2=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ]  || errs="$errs first-exit=$code"
[ "$code2" = 0 ] || errs="$errs second-exit=$code2(la-cache-sucia-atasco-el-gate)"
grep -q '"version":"3.1.4"' "$base/dest/mod01/module.json" 2>/dev/null \
    || errs="$errs cache-no-se-saneo(module.json=$(cat "$base/dest/mod01/module.json" 2>/dev/null))"
[ -z "$(git -C "$base/dest/mod01" status --porcelain 2>/dev/null)" ] \
    || errs="$errs la-cache-quedo-sucia-tras-el-saneo"
[ -z "$errs" ] \
    && ok "hub#1380: una caché con un fichero tocado se sanea sola en vez de atascar el gate" \
    || bad "hub#1380: una caché con un fichero tocado se sanea sola en vez de atascar el gate" "$errs out=$(tail -c 500 "$OUT")"

# ── 14. Un directorio que es OTRO repo se re-clona ───────────────────────────
#    Los 27 directorios tenían dentro un clon DEL HUB (639 MB) con su árbol, y
#    el checkout del módulo chocaba contra ficheros del hub que allí eran
#    untracked. Un fetch encima de otro repo no se arregla nunca solo.
base=$(make_catalogue 25)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
rm -rf "$base/dest/mod01"
mkdir -p "$base/dest/mod01"
git -C "$base/dest/mod01" init -q -b main
git -C "$base/dest/mod01" config user.email foreign@test
git -C "$base/dest/mod01" config user.name foreign
echo 'fn main() {}' > "$base/dest/mod01/hub-thing.rs"
git -C "$base/dest/mod01" add hub-thing.rs
git -C "$base/dest/mod01" commit -qm "soy otro repo"
git -C "$base/dest/mod01" remote add origin "$base/origins/mod02.git"
# untracked AQUÍ, pero versionados en el módulo: es lo que aborta el checkout.
printf '{"id":"otro","version":"0.0.0"}\n' > "$base/dest/mod01/module.json"
echo foreign > "$base/dest/mod01/marker"
code2=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code2" = 0 ] || errs="$errs exit=$code2(un-repo-ajeno-en-la-cache-atasco-el-gate)"
got_origin=$(git -C "$base/dest/mod01" remote get-url origin 2>/dev/null)
[ "$got_origin" = "$base/origins/mod01.git" ] \
    || errs="$errs no-se-re-clono(origin='$got_origin')"
grep -q '"id":"mod01"' "$base/dest/mod01/module.json" 2>/dev/null \
    || errs="$errs la-cache-no-tiene-el-modulo-esperado"
grep -q '"version":"2.0.0"' "$base/dest/mod01/module.json" 2>/dev/null \
    || errs="$errs no-quedo-en-la-version-publicada"
[ -e "$base/dest/mod01/hub-thing.rs" ] && errs="$errs quedaron-restos-del-repo-ajeno"
[ -z "$errs" ] \
    && ok "hub#1380: un directorio de caché que es OTRO repo se re-clona solo" \
    || bad "hub#1380: un directorio de caché que es OTRO repo se re-clona solo" "$errs out=$(tail -c 500 "$OUT")"

# ── 15. El fallo dice DÓNDE está el problema ─────────────────────────────────
#    Los dos fallos —«no llego al repo» y «la caché no sirve»— decían lo mismo:
#    *fix the access (deploy key, ssh agent, network)*. Ahí es donde se pierde
#    el tiempo: apunta al sitio equivocado en la mitad de los casos.
base=$(make_catalogue 26)
OUT="$base/out"
rm -rf "$base/origins/mod07.git"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-con-un-modulo-inalcanzable"
grep -qi 'deploy key\|ssh\|network\|acces' "$OUT" \
    || errs="$errs un-fallo-de-ACCESO-no-menciona-el-acceso"
[ -z "$errs" ] \
    && ok "hub#1380: un fallo de ACCESO manda a mirar la llave/red" \
    || bad "hub#1380: un fallo de ACCESO manda a mirar la llave/red" "$errs out=$(tail -c 400 "$OUT")"

# …y el gemelo: un fallo LOCAL no puede mandar a mirar la red. Se fuerza con el
# stub de git fallando el `fetch` con un error permanente que no es de acceso.
base=$(make_catalogue 25)
OUT="$base/out"
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
mkdir -p "$base/bin"
cat > "$base/bin/git" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do
    if [ "$a" = "fetch" ]; then
        printf 'error: cannot lock ref '"'"'refs/heads/main'"'"': Unable to create file: File exists\n' >&2
        exit 128
    fi
done
exec "$STUB_REAL_GIT" "$@"
STUB
chmod +x "$base/bin/git"
export STUB_REAL_GIT="$REAL_GIT"
code2=$(PATH="$base/bin:$PATH" HUB_MATERIALIZE_RETRY_DELAYS="0 0 0" \
        run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
unset STUB_REAL_GIT
errs=""
[ "$code2" = 0 ] && errs="$errs exited-0-con-el-fetch-roto"
grep -qi 'cach\|derived\|deriv\|borrar\|delete\|rm -rf' "$OUT" \
    || errs="$errs un-fallo-LOCAL-no-dice-que-la-cache-se-puede-borrar"
[ -z "$errs" ] \
    && ok "hub#1380: un fallo LOCAL manda a la caché (borrable), no a la red" \
    || bad "hub#1380: un fallo LOCAL manda a la caché (borrable), no a la red" "$errs out=$(tail -c 400 "$OUT")"

# ── 16. hub#1388: the INHERITED git environment never decides what is cloned ──
#    Root cause of hub#1388, and it is not a race (the first diagnosis) nor the
#    id source. `git push` FROM A WORKTREE exports `GIT_DIR=<repo>/.git/worktrees/<name>`
#    into the pre-push hook — a push from the main checkout does NOT, which is
#    exactly why it never reproduced by hand and always reproduced on the fleet,
#    which works only out of worktrees. `GIT_DIR` OVERRIDES `git -C <dir>`, so
#    `remote_for()` asked the module checkout for its origin and got the HUB's
#    (`git@github:ERPlora/hub.git`, SSH alias and all) for all 27 ids. Both
#    branches of `remote_for` read correctly in isolation, which is what made
#    this so hard to see: the poison is in the ENVIRONMENT, not the arguments.
#    The hub was then cloned into all 27 directories, none carried a module.json,
#    and every push with HUB_GATE_WITH_MODULES=1 died for the whole fleet.
#    The same inherited GIT_DIR is why the cache never self-healed: hub#1385's
#    `tree_is_the_module` compared the hub's origin against the hub's origin and
#    said "yes, this is the module", taking the FETCH path — whose
#    `checkout -qf --detach FETCH_HEAD` then ran against the pushing worktree
#    (hub#1387: the gate leaves the worktree in detached HEAD on main).
base=$(make_catalogue 26)
OUT="$base/out"
# A stand-in for the hub: a real bare repo whose content is NOT a module, so the
# wrong clone SUCCEEDS and reproduces the observed symptom instead of an access
# error. Its remote name is the one seen in the poisoned cache.
hub_work="$base/build/hub"
mkdir -p "$hub_work"
git -C "$hub_work" init -q -b main
git -C "$hub_work" config user.email hub@test
git -C "$hub_work" config user.name hub
echo '[workspace]' > "$hub_work/Cargo.toml"
echo 'ARQUITECTURA' > "$hub_work/ARQUITECTURA.md"
git -C "$hub_work" add -A
git -C "$hub_work" commit -qm hub
git init -q --bare "$base/origins/hub.git"
git -C "$hub_work" remote add origin "$base/origins/hub.git"
git -C "$hub_work" push -q origin main
# …and the checkout the push comes from, whose git dir the hook inherits.
git clone -q "$base/origins/hub.git" "$base/hubcheckout"
code=$(
    # Exactly what `git push` from a worktree exports, measured on git 2.50.1:
    # GIT_DIR and nothing else. Setting GIT_WORK_TREE too would make `clone`
    # fail outright ("working tree already exists") — a DIFFERENT symptom that
    # would hide the one hub#1388 actually reported.
    export GIT_DIR="$base/hubcheckout/.git"
    bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25 >"$OUT" 2>&1
    echo $?
)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
wrong=0
for i in $(seq 1 26); do
    id=$(printf 'mod%02d' "$i")
    [ "$(git -C "$base/dest/$id" remote get-url origin 2>/dev/null)" = "$base/origins/$id.git" ] \
        || wrong=$((wrong + 1))
done
[ "$wrong" = 0 ] || errs="$errs $wrong-of-26-directories-do-not-carry-their-own-module-origin"
[ -f "$base/dest/mod01/module.json" ] || errs="$errs mod01-has-no-module.json"
[ -e "$base/dest/mod01/ARQUITECTURA.md" ] && errs="$errs the-hub-was-cloned-into-a-module-directory"
[ -z "$errs" ] \
    && ok "hub#1388: an inherited GIT_DIR does not redirect the clones at the hub" \
    || bad "hub#1388: an inherited GIT_DIR does not redirect the clones at the hub" "$errs out=$(tail -c 600 "$OUT")"

# ── 17. hub#1388: a tree that cloned fine but is NOT the module says so ───────
#    The clone SUCCEEDS, so there is no access failure anywhere — yet the run
#    ended with «Fix the access above» and sent two separate diagnoses into the
#    deploy keys, which were never broken. A tree without a module.json is a
#    LOCAL problem and has to name the URL it actually cloned from.
base=$(make_catalogue 26)
OUT="$base/out"
# mod07's published main really carries no module.json: same shape, no network.
git -C "$base/build/mod07" rm -q module.json
git -C "$base/build/mod07" commit -qm "drop the manifest"
git -C "$base/build/mod07" push -q origin main
code=$(run_script bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 25)
errs=""
[ "$code" = 0 ] && errs="$errs exited-0-without-a-manifest"
grep -q 'mod07' "$OUT" || errs="$errs failure-does-not-name-the-module"
grep -qi 'cach\|deriv\|rm -rf' "$OUT" || errs="$errs does-not-point-at-the-local-cache"
grep -q "$base/origins/mod07.git" "$OUT" || errs="$errs does-not-say-which-url-it-cloned-from"
[ -z "$errs" ] \
    && ok "hub#1388: a manifest-less tree reports LOCAL and names the URL cloned" \
    || bad "hub#1388: a manifest-less tree reports LOCAL and names the URL cloned" "$errs out=$(tail -c 600 "$OUT")"

# ── 18. hub#1388: the inherited CONFIG environment cannot redirect a clone either ──
#    Case 16 closes GIT_DIR. This one closes the rest of the same class, because
#    a hand-written list of variables is exactly the kind of guard that rots: git
#    itself considers FIFTEEN variables repository-local (`git rev-parse
#    --local-env-vars`) and the first fix named eight of them.
#    This is not hypothetical. `git -c <key>=<value> push` exports
#    `GIT_CONFIG_PARAMETERS` into the pre-push hook — measured on git 2.50.1 —
#    and `fleet-supervisor.sh` pushes EVERY fleet branch with
#    `git -c credential.helper='!gh auth git-credential' push`. So the config
#    environment reaches this script on every single push the fleet makes. An
#    inherited `url.<x>.insteadOf` then rewrites where the clone connects, the
#    tree that lands is not the module, and hub#1388 comes back through a
#    different door with the identical symptom: a clone that WORKED and carries
#    no module.json.
base=$(make_catalogue 2)
# A stand-in for the hub, reachable at the address an inherited rewrite sends us to.
for i in 1 2; do
    id=$(printf 'mod%02d' "$i")
    evil="$base/build/evil-$id"
    mkdir -p "$evil"
    git -C "$evil" init -q -b main
    git -C "$evil" config user.email hub@test
    git -C "$evil" config user.name hub
    echo 'ARQUITECTURA' > "$evil/ARQUITECTURA.md"
    git -C "$evil" add -A
    git -C "$evil" commit -qm hub
    git init -q --bare "$base/evil/$id.git"
    git -C "$evil" remote add origin "$base/evil/$id.git"
    git -C "$evil" push -q origin main
done
# Both spellings git accepts for injected config: the one `git -c` exports, and
# the numbered one. Either alone is enough to hijack all 27 clones.
for spelling in parameters numbered; do
    errs=""
    rm -rf "$base/dest"
    OUT="$base/out.$spelling"
    code=$(
        if [ "$spelling" = parameters ]; then
            export GIT_CONFIG_PARAMETERS="'url.$base/evil/.insteadOf'='$base/origins/'"
        else
            export GIT_CONFIG_COUNT=1
            export GIT_CONFIG_KEY_0="url.$base/evil/.insteadOf"
            export GIT_CONFIG_VALUE_0="$base/origins/"
        fi
        bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 2 >"$OUT" 2>&1
        echo $?
    )
    [ "$code" = 0 ] || errs="$errs exit=$code"
    for i in 1 2; do
        id=$(printf 'mod%02d' "$i")
        [ -f "$base/dest/$id/module.json" ] || errs="$errs $id-has-no-module.json"
        [ -e "$base/dest/$id/ARQUITECTURA.md" ] && errs="$errs the-hub-was-cloned-into-$id"
    done
    [ -z "$errs" ] \
        && ok "hub#1388: an inherited git config ($spelling) does not redirect the clones" \
        || bad "hub#1388: an inherited git config ($spelling) does not redirect the clones" \
               "$errs out=$(tail -c 400 "$OUT")"
done

# ── 19. hub#1387: the run never reaches into the WORKTREE THAT IS PUSHING ─────
#    The second symptom of the same cause, and the one that cost a worker its
#    branch. With GIT_DIR inherited, `tree_is_the_module` compared the hub's
#    origin against the hub's origin, agreed the cached tree WAS the module, and
#    took the fetch path — where `git -C "$tree" checkout -qf --detach
#    FETCH_HEAD` and `git -C "$tree" clean -qfdx` both ignore `-C` and land on
#    GIT_DIR instead: the pushing worktree. It ends up detached on the hub's
#    main with its untracked work deleted, which is exactly what hub#1387
#    reported. Case 16 proves the clones are right; this proves the gate does
#    not eat the branch it was invoked from.
base=$(make_catalogue 2)
OUT="$base/out"
# The hub, and a checkout of it with a WORKTREE — the shape a fleet push has.
hub_work="$base/build/hub"
mkdir -p "$hub_work"
git -C "$hub_work" init -q -b main
git -C "$hub_work" config user.email hub@test
git -C "$hub_work" config user.name hub
echo 'ARQUITECTURA' > "$hub_work/ARQUITECTURA.md"
git -C "$hub_work" add -A
git -C "$hub_work" commit -qm hub
git init -q --bare "$base/origins/hub.git"
git -C "$hub_work" remote add origin "$base/origins/hub.git"
git -C "$hub_work" push -q origin main
git clone -q "$base/origins/hub.git" "$base/hubcheckout"
git -C "$base/hubcheckout" worktree add -q "$base/pushing" -b feat/pushing
echo 'work in progress' > "$base/pushing/WIP.txt"
# A cache directory that already holds the hub — the poisoned state a previous
# run left behind, and the only state in which the FETCH path is even reached.
git clone -q "$base/origins/hub.git" "$base/dest/mod01"
code=$(
    export GIT_DIR="$base/hubcheckout/.git/worktrees/pushing"
    bash "$SCRIPT" --dest "$base/dest" --ids-from "$base/workspace" --floor 2 >"$OUT" 2>&1
    echo $?
)
errs=""
[ "$code" = 0 ] || errs="$errs exit=$code"
[ "$(git -C "$base/pushing" rev-parse --abbrev-ref HEAD)" = "feat/pushing" ] \
    || errs="$errs the-pushing-worktree-was-left-detached"
[ -f "$base/pushing/WIP.txt" ] || errs="$errs the-pushing-worktree-lost-its-untracked-work"
[ -f "$base/dest/mod01/module.json" ] || errs="$errs mod01-has-no-module.json"
[ -z "$errs" ] \
    && ok "hub#1387: the pushing worktree keeps its branch and its untracked work" \
    || bad "hub#1387: the pushing worktree keeps its branch and its untracked work" \
           "$errs out=$(tail -c 400 "$OUT")"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
