#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Tests for scripts/install-hooks.sh — the one sanctioned way to sync the
# INSTALLED gate hook with the versioned `.githooks/pre-push` (hub#746).
#
# Run:  bash scripts/install-hooks.test.sh
#
# Everything is driven through injection points so the tests NEVER touch the
# real installed hooks (~/.erplora/hooks/hub) or the real repo config:
#   HUB_HOOKS_INSTALL_DIR   where to install the hook   (default: ~/.erplora/hooks/hub)
#   HUB_HOOKS_GIT_DIR       the repo whose config to arm (default: this repo)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="$SCRIPTS_DIR/install-hooks.sh"
VERSIONED="$SCRIPTS_DIR/../.githooks/pre-push"
pass=0
fail=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n     %s\n' "$1" "$2"; fail=$((fail + 1)); }

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

echo "install-hooks.sh"

# ── 1. Fresh install: hook copied, executable, and the repo armed to use it ───
repo=$(make_repo)
dest="$repo/hooks-dest"
# The injection env is ALWAYS passed: without it the installer would touch the
# real ~/.erplora/hooks/hub, which live sessions are using right now.
out=$(HUB_HOOKS_INSTALL_DIR="$dest" HUB_HOOKS_GIT_DIR="$repo" bash "$INSTALLER" 2>&1); code=$?
errs=""
[ "$code" = 0 ]                                   || errs="$errs exit=$code(want 0)"
[ -x "$dest/pre-push" ]                           || errs="$errs not-installed-or-not-executable"
cmp -s "$VERSIONED" "$dest/pre-push"              || errs="$errs installed-copy-differs"
[ "$(git -C "$repo" config core.hooksPath)" = "$dest" ] || errs="$errs hooksPath=$(git -C "$repo" config core.hooksPath)"
[ -z "$errs" ] \
    && ok "fresh install: copies the hook, marks it executable, sets core.hooksPath" \
    || bad "fresh install: copies the hook, marks it executable, sets core.hooksPath" "$errs $out"

# ── 2. Re-install over a DRIFTED copy: backs it up, then resyncs ──────────────
echo "# local drift" >> "$dest/pre-push"
out=$(HUB_HOOKS_INSTALL_DIR="$dest" HUB_HOOKS_GIT_DIR="$repo" bash "$INSTALLER" 2>&1); code=$?
errs=""
[ "$code" = 0 ]                          || errs="$errs exit=$code(want 0)"
cmp -s "$VERSIONED" "$dest/pre-push"     || errs="$errs still-drifted"
ls "$dest"/pre-push.bak-* >/dev/null 2>&1 || errs="$errs no-backup"
[ -z "$errs" ] \
    && ok "drifted install: keeps a .bak and resyncs to the versioned hook" \
    || bad "drifted install: keeps a .bak and resyncs to the versioned hook" "$errs $out"

# ── 3. Idempotent: an in-sync re-run changes nothing and adds no backup ───────
baks_before=$(ls "$dest"/pre-push.bak-* 2>/dev/null | wc -l | tr -d ' ')
out=$(HUB_HOOKS_INSTALL_DIR="$dest" HUB_HOOKS_GIT_DIR="$repo" bash "$INSTALLER" 2>&1); code=$?
baks_after=$(ls "$dest"/pre-push.bak-* 2>/dev/null | wc -l | tr -d ' ')
errs=""
[ "$code" = 0 ]                       || errs="$errs exit=$code(want 0)"
[ "$baks_before" = "$baks_after" ]    || errs="$errs backup-added($baks_before->$baks_after)"
cmp -s "$VERSIONED" "$dest/pre-push"  || errs="$errs copy-differs"
[ -z "$errs" ] \
    && ok "idempotent: an in-sync re-run is a no-op" \
    || bad "idempotent: an in-sync re-run is a no-op" "$errs $out"

# ── 4. The keepalive travels with the gate (hub#788): arming installs it ──────
#    `git push` opens the SSH transport BEFORE the hook runs; a lock wait on an
#    idle connection gets killed by GitHub. Whoever arms the gate must arm the
#    keepalive too — separating them is what produced hub#788.
sshcmd=$(git -C "$repo" config core.sshCommand 2>/dev/null)
errs=""
grep -q 'ServerAliveInterval' <<<"$sshcmd" || errs="$errs no-keepalive sshCommand='$sshcmd'"
[ -z "$errs" ] \
    && ok "install arms the SSH keepalive in the target repo's config" \
    || bad "install arms the SSH keepalive in the target repo's config" "$errs"

# ── 5. A repo with its OWN core.sshCommand is left alone ──────────────────────
repo2=$(make_repo)
dest2="$repo2/hooks-dest"
git -C "$repo2" config core.sshCommand "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=100"
out=$(HUB_HOOKS_INSTALL_DIR="$dest2" HUB_HOOKS_GIT_DIR="$repo2" bash "$INSTALLER" 2>&1); code=$?
got=$(git -C "$repo2" config core.sshCommand)
errs=""
[ "$code" = 0 ]                                          || errs="$errs exit=$code(want 0)"
[ "$got" = "ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=100" ] || errs="$errs overwrote='$got'"
[ -z "$errs" ] \
    && ok "an existing keepalive config is not overwritten" \
    || bad "an existing keepalive config is not overwritten" "$errs $out"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
