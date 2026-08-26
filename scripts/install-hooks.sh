#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install-hooks.sh — sync the INSTALLED gate hook with the versioned one
# (hub#746), and arm the machine config that must travel with it (hub#788).
#
# The gate that decides a push is whatever `core.hooksPath` points at — on the
# fleet machine that is ~/.erplora/hooks/hub, OUTSIDE the repo — and nothing
# used to sync it with `.githooks/pre-push`. Drift is silent in both
# directions: a stale copy re-reds already-fixed tests (false red) or skips
# checks the repo added while still publishing the attestation (false green).
# This script is the one sanctioned resync path for a FIRST install. Since
# hub#1207 the hook also resyncs ITSELF when it finds it is stale — warning was
# demonstrably not enough: the fleet ran a copy from 2026-08-13 for two weeks,
# so every change to `.githooks/pre-push` was a change to a file nothing
# executed. That self-heal lives in the INSTALLED copy, though, so a machine
# whose installed hook predates hub#1207 still needs this script exactly once.
#
#   bash scripts/install-hooks.sh
#
# Injection points (used by scripts/install-hooks.test.sh — and the reason the
# tests never touch the real installed hooks):
#   HUB_HOOKS_INSTALL_DIR   target dir            (default: ~/.erplora/hooks/hub)
#   HUB_HOOKS_GIT_DIR       repo whose config to arm (default: this checkout)
#
# What it does:
#   1. copies .githooks/pre-push → $HUB_HOOKS_INSTALL_DIR/pre-push (0755),
#      keeping a timestamped .bak of a differing installed copy;
#   2. points the repo's `core.hooksPath` at the install dir;
#   3. arms the SSH keepalive (`core.sshCommand`) unless one is already set —
#      `git push` opens the SSH transport BEFORE the pre-push hook runs, so a
#      long lock wait on an idle connection gets closed by GitHub (hub#788).
#      The keepalive margin (Interval × CountMax = 7200s) must stay ABOVE the
#      gate's maximum lock wait (HUB_GATE_LOCK_WAIT, default 3600s).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SRC="$REPO_ROOT/.githooks/pre-push"
DEST_DIR="${HUB_HOOKS_INSTALL_DIR:-$HOME/.erplora/hooks/hub}"
TARGET_REPO="${HUB_HOOKS_GIT_DIR:-$REPO_ROOT}"
KEEPALIVE_SSH="ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=240 -o TCPKeepAlive=yes"

[ -f "$SRC" ] || { echo "❌ install-hooks: $SRC not found — run from a hub checkout." >&2; exit 1; }

mkdir -p "$DEST_DIR"

if [ -f "$DEST_DIR/pre-push" ] && ! cmp -s "$SRC" "$DEST_DIR/pre-push"; then
    bak="$DEST_DIR/pre-push.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$DEST_DIR/pre-push" "$bak"
    echo "ℹ️  install-hooks: the installed copy differed — kept it as $bak"
fi

if ! cmp -s "$SRC" "$DEST_DIR/pre-push" 2>/dev/null; then
    install -m 0755 "$SRC" "$DEST_DIR/pre-push"
    echo "✅ install-hooks: installed $SRC → $DEST_DIR/pre-push"
else
    chmod 0755 "$DEST_DIR/pre-push"
    echo "✅ install-hooks: $DEST_DIR/pre-push already in sync."
fi

if git -C "$TARGET_REPO" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$TARGET_REPO" config core.hooksPath "$DEST_DIR"
    echo "✅ install-hooks: core.hooksPath → $DEST_DIR"

    # The keepalive travels WITH the gate: separating them is what produced
    # hub#788. An existing core.sshCommand is respected — it is someone's
    # deliberate config, and the hook itself warns if it lacks a keepalive.
    if [ -z "$(git -C "$TARGET_REPO" config core.sshCommand 2>/dev/null || true)" ]; then
        git -C "$TARGET_REPO" config core.sshCommand "$KEEPALIVE_SSH"
        echo "✅ install-hooks: core.sshCommand → SSH keepalive armed (hub#788)"
    fi
else
    echo "⚠️  install-hooks: $TARGET_REPO is not a git repo — hook installed, config NOT armed." >&2
fi
